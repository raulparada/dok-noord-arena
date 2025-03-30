#!/usr/bin/env python

import csv
import datetime
from enum import StrEnum
from pathlib import Path
from textwrap import dedent
from typing import Self

import jinja2
from pydantic import BaseModel, BeforeValidator, Field
from typing_extensions import Annotated

DATE_FORMAT = "%Y-%m-%dT%H:%M"
CSV_LIST_SEPARATOR = "_"
CSV_DELIMITER = ","

MATCHES: list["Match"] = []  # list
PLAYERS: dict[str, "Player"] = {}  # by id
SERVER_URL = "http://localhost:7654"


def split_string(v):
    if not v:
        return []
    if isinstance(v, str):
        return [item.strip() for item in v.split(CSV_LIST_SEPARATOR)]
    return v


class PlayerStats(BaseModel):
    played: int = 0
    wins: int = 0
    losses: int = 0
    tournament_wins: int = 0


class StatsManager:
    @staticmethod
    def get_player_stats(player: "Player"):
        played = sum(player in match for match in MATCHES)
        wins = sum(match.is_winner(player) for match in MATCHES)
        losses = sum(not match.is_winner(player) for match in MATCHES)
        tournament_wins = sum(
            match.is_winner(player) for match in MATCHES if match.is_tournament_mode
        )
        return PlayerStats(
            played=played,
            wins=wins,
            losses=losses,
            tournament_wins=tournament_wins,
        )


class Player(BaseModel):
    id: str
    alias: str

    @property
    def stats(self) -> PlayerStats:
        return PLAYER_STATISTICS.get_player_stats(self)


class Outcome(StrEnum):
    PENDING = "0"
    TEAM_1_WINNER = "1"
    TEAM_2_WINNER = "2"
    DRAW = "3"
    CANCELLED = "4"
    UNKNOWN = "9"


class Team(BaseModel):
    player_ids: str
    color: str = Field(default="white")

    @property
    def player_ids_parsed(self):
        return split_string(self.player_ids)

    @property
    def players(self):
        return [PLAYERS[player_id] for player_id in self.player_ids_parsed]

    @classmethod
    def from_ids_string(cls: Self, ids_string):
        return cls(player_ids=ids_string)

    def __contains__(self, item: Player):
        return item in self.players

    def __str__(self):
        return " • ".join(sorted(player.alias for player in self.players))


class Match(BaseModel):
    date: datetime.datetime
    team_1: Annotated[Team | None, BeforeValidator(Team.from_ids_string)]
    team_2: Annotated[Team | None, BeforeValidator(Team.from_ids_string)]
    outcome: Outcome = Field(default=Outcome.PENDING)
    highlights_id: str | None

    @property
    def is_playable(self):
        return len(self.team_1) == len(self.team_2) == 5 and not self.is_played

    @property
    def is_played(self):
        return self.outcome in (
            Outcome.TEAM_1_WINNER,
            Outcome.TEAM_2_WINNER,
            Outcome.DRAW,
        )

    @property
    def is_done(self):
        return self.outcome is not Outcome.PENDING

    @property
    def is_cancelled(self):
        return self.outcome is Outcome.CANCELLED

    def is_winner(self, player: Player):
        if (
            player in self.team_1
            and self.outcome is Outcome.TEAM_1_WINNER
            or player in self.team_2
            and self.outcome is Outcome.TEAM_2_WINNER
        ):
            return True
        return False

    @property
    def is_tournament_mode(self):
        # TODO add support
        return False

    def __contains__(self, item: Player):
        return item in self.team_1 or item in self.team_2

    def __str__(self):
        return dedent(
            f"""\
            {self.date.strftime(DATE_FORMAT)}\n
            {self.team_1}\n
            vs
            {self.team_2}"""
        )


def from_csv[T](cls: type[T], file: str) -> list[T]:
    if not issubclass(cls, BaseModel):
        raise RuntimeError("CSV parsing must be from pydantic model.")
    with open(f"{file}.csv") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        return [cls.model_validate(row) for row in reader]


if __name__ == "__main__":
    PLAYER_STATISTICS = StatsManager()
    MATCHES = from_csv(Match, "data/matches")
    PLAYERS = {player.id: player for player in from_csv(Player, "data/players")}
    print("players", PLAYERS)
    print("matches", MATCHES)

    # Render html output from jinja template.
    # https://jinja.palletsprojects.com/en/stable
    with open("build/index.html", "w") as index:
        index.write(
            jinja2.Template(Path("index.html.jinja").read_text()).render(**locals())
        )
