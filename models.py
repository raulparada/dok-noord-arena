#!/usr/bin/env python

import csv
import datetime
from enum import StrEnum
from pathlib import Path
from textwrap import dedent

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


class Player(BaseModel):
    id: str
    alias: str

class Outcome(StrEnum):
    UNKNOWN = "0"
    TEAM_1_WINNER = "1"
    TEAM_2_WINNER = "2"
    DRAW = "3"
    CANCELLED = "4"

Team = Annotated[list[str], BeforeValidator(split_string)]


class Match(BaseModel):
    date: datetime.datetime
    team_1: Team = Field(default_factory=list)
    team_2: Team = Field(default_factory=list)
    outcome: Outcome = Field(default=Outcome.UNKNOWN)

    @property
    def is_ready(self):
        return len(self.team_1) == len(self.team_2) == 5

    @property
    def is_done(self):
        return self.outcome is not Outcome.UNKNOWN

    @property
    def team_1_(self):
        return " | ".join(PLAYERS[player_id].alias for player_id in self.team_1)

    @property
    def team_2_(self):
        return " | ".join(PLAYERS[player_id].alias for player_id in self.team_2)

    def __str__(self):
        return dedent(
            f"""\
            {self.date.strftime(DATE_FORMAT)}\n
            {self.team_1_}\n
            vs
            {self.team_2_}"""
        )


def from_csv[T](cls: type[T], file: str) -> list[T]:
    if not issubclass(cls, BaseModel):
        raise RuntimeError("CSV parsing must be from pydantic model.")
    with open(f"{file}.csv") as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        return [cls.model_validate(row) for row in reader]


if __name__ == "__main__":
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
