#!/usr/bin/env python
import csv
import datetime
import logging
import os
import re
import sys
from enum import StrEnum
from pathlib import Path
from textwrap import dedent
from typing import NoReturn, Self

import jinja2
from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer
from rich.logging import RichHandler
from typing_extensions import Annotated

FORMAT = "%(message)s"
logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "NOTSET"),
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler()],
)
logger = logging.getLogger(__name__)

CSV_DELIMITER = ","
CSV_LIST_SEPARATOR = "_"
DATE_FORMAT = "%Y-%m-%dT%H:%M"

REPO_URL = "https://github.com/raulparada/dok-noord-arena"
DISPATCH_URL = os.getenv(
    "DISPATCH_URL", "https://api.github.com/repos/raulparada/dok-noord-arena/dispatches"
)

MATCHES: list["Match"] = []  # list
PLAYERS: dict[str, "Player"] = {}  # by id


class NotEnoughPlayersError(BaseException):
    pass


def team_split(players: list["Player"]):
    logger.warning("Using dummy placeholder matchmaking logic.")
    team_1 = players[:5]
    team_2 = players[5:10]
    return team_1, team_2


def from_csv[T](cls: type[T], file: str) -> list[T]:
    if not issubclass(cls, BaseModel):
        raise RuntimeError("CSV parsing must be from pydantic model.")
    with open(f"{file}.csv") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        return [cls.model_validate(row) for row in reader]


def to_csv(instance: BaseModel, file: str) -> NoReturn:
    if not isinstance(instance, BaseModel):
        raise RuntimeError("CSV writing must be from pydantic model.")
    with open(f"{file}.csv", "a") as f:
        writer = csv.DictWriter(
            f,
            delimiter=CSV_DELIMITER,
            fieldnames=instance.model_fields,
        )
        writer.writerow(instance.model_dump())


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


class Player(BaseModel):
    id: str
    alias: str

    @property
    def stats(self) -> PlayerStats:
        played = sum(self in match for match in MATCHES)
        wins = sum(match.is_winner(self) for match in MATCHES)
        losses = sum(match.is_loser(self) for match in MATCHES)
        tournament_wins = sum(
            match.is_winner(self) for match in MATCHES if match.is_tournament_mode
        )
        return PlayerStats(
            played=played,
            wins=wins,
            losses=losses,
            tournament_wins=tournament_wins,
        )


class Outcome(StrEnum):
    PENDING = "0"
    TEAM_1_WINNER = "1"
    TEAM_2_WINNER = "2"
    DRAW = "3"
    CANCELLED = "4"
    UNKNOWN = "9"


class Team(BaseModel):
    raw_str: str
    player_ids: list[str]
    color: str | None

    @property
    def players(self):
        return [PLAYERS[player_id] for player_id in self.player_ids]

    @classmethod
    def from_string(cls: Self, raw_str: str):
        pattern = r"\[(.*?)\]"
        match = re.search(pattern, raw_str)
        if match:
            color = match.group(1)
            player_ids = raw_str.replace(match.group(), "").split(CSV_LIST_SEPARATOR)
        else:
            color = None
            player_ids = raw_str.split(CSV_LIST_SEPARATOR)
        return cls(raw_str=raw_str, player_ids=player_ids, color=color)

    def to_string(self):
        return f"[{self.color}]{self.raw_str}"

    def __contains__(self, item: Player):
        return item in self.players

    # def __str__(self):
    #     return " • ".join(sorted(player.alias for player in self.players))


class Match(BaseModel):
    date: Annotated[
        datetime.datetime, PlainSerializer(lambda date: date.strftime(DATE_FORMAT))
    ]
    team_1: Annotated[
        Team | None,
        BeforeValidator(Team.from_string),
        PlainSerializer(lambda team: team.to_string()),
    ]
    team_2: Annotated[
        Team | None,
        BeforeValidator(Team.from_string),
        PlainSerializer(lambda team: team.to_string()),
    ]
    outcome: Outcome = Field(default=Outcome.PENDING)
    highlights_id: str | None

    @property
    def is_playable(self):
        return len(self.team_1) == len(self.team_2) == 5 and not self.is_played

    @property
    def is_won(self):
        return self.outcome in (Outcome.TEAM_1_WINNER, Outcome.TEAM_2_WINNER)

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

    def is_loser(self, player: Player):
        return player in self and self.is_won and not self.is_winner(player)

    @property
    def is_tournament_mode(self):
        # TODO add support
        return False

    def __contains__(self, item: Player):
        return item in self.team_1 or item in self.team_2

    def __str__(self):
        return dedent(
            f"""\n
            {self.date.strftime(DATE_FORMAT)} Dok-Noord Arena
            {self.team_1}
            vs
            {self.team_2}"""
        )

    @classmethod
    def from_matchmaking_file(cls, file: str):
        """Instantiate from standard matchmaking string (i.e. Whatsapp group format)"""
        text_raw = Path(file).read_text()
        text = ""
        for filter in ("\u2060",):
            text = text_raw.replace(filter, "")
        lines = text.strip().split("\n")
        # Parse the date line (first line)
        date_line = lines[0]
        date_match = re.match(r"(\w+) (\d{2}/\d{2}) @(\d{2}:\d{2})", date_line)
        if not date_match:
            raise ValueError(f"Invalid date format: {date_line}.")

        day_of_week, date_str, time = date_match.groups()
        date_str = f"{date_str} {time}"  # Format: "DD/MM HH:MM"

        # Parse player lines
        players = []
        for line in lines[1:]:
            # Match player number and name, handling invisible characters
            player_match = re.match(r"(\d+)\.?[^\w]* ([^⁠]+)", line)
            if player_match:
                position, player_name = player_match.groups()

                # Find existing player by alias or create a placeholder
                player = None
                for p_id, p in PLAYERS.items():
                    if p.alias.strip().lower() == player_name.strip().lower():
                        player = p
                        break

                if player:
                    players.append(player)
                else:
                    # If you need to handle non-existing players
                    logger.warning(
                        f"Player '{player_name.strip()}' not found in database."
                    )

        # Validate we have enough players
        if len(players) < 10:
            raise NotEnoughPlayersError(f"Not enough players. Found {len(players)}/10.")

        # Ugh, vibin'
        team_1, team_2 = team_split(players)
        team_1_ids = [p.id for p in team_1]
        team_2_ids = [p.id for p in team_2]
        match = cls(
            date=datetime.datetime.strptime(date_str, "%d/%m %H:%M").replace(
                year=datetime.datetime.now().year
            ),
            team_1=CSV_LIST_SEPARATOR.join(team_1_ids),
            team_2=CSV_LIST_SEPARATOR.join(team_2_ids),
            outcome=Outcome.PENDING,
            highlights_id=None,
        )
        match.team_1.color = "black"
        match.team_2.color = "white"
        return match


def matchmaking(file: dict):
    logger.info(f"Matchmaking with file='{file}'.")
    try:
        match = Match.from_matchmaking_file(file)
        # Add logic to save the match to CSV or process it
        logger.info(f"Created match: {match}")
        to_csv(match, "data/matches")

    except ValueError as e:
        logger.error(f"Error parsing matchmaking text: {e}.")


if __name__ == "__main__":
    MATCHES = from_csv(Match, "data/matches")
    PLAYERS = {player.id: player for player in from_csv(Player, "data/players")}
    logger.debug(f"Players {PLAYERS}.")
    logger.debug(f"Matches {MATCHES}.")

    if sys.argv[1] == "build":
        # Render html output from jinja template.
        # https://jinja.palletsprojects.com/en/stable
        with open("docs/index.html", "w") as index:
            index.write(
                jinja2.Template(Path("index.html.jinja").read_text()).render(**locals())
            )
    else:
        globals()[sys.argv[1]](*sys.argv[2:])
