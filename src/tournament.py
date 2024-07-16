import datetime
import os
import json
from icecream import ic
from msgspec import Struct


class Player(Struct):
    name: str
    elo: int
    rank: str


class Game(Struct):
    id: int
    player1_id: int
    winner_id: int
    looser_id: int
    next_game_id_winner: int
    next_game_id_looser: int | None
    deadline: datetime.datetime


class Gambler(Struct):
    id: int
    name: str
    budget: int = 1000
