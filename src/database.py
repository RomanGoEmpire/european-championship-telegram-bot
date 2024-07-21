from datetime import datetime
import json
import requests
from icecream import ic
from surrealdb import Surreal
from .formulars import win_percentages


async def add_tables_from_json() -> None:
    players = json.load(open("data/players.json"))
    matches = json.load(open("data/matches.json"))
    rounds = json.load(open("data/rounds.json"))

    for player in players:
        await db.create("player", data=player)
    for match in matches:
        await db.create("match", data=match)
    for round in rounds:
        await db.create("round", data=round)


async def add_plays_first_round() -> None:
    players = await db.query("SELECT * FROM player ORDER BY starting_number")
    # first round 1 the matches
    first_16 = await db.query("select * from player ORDER BY starting_number limit 16")

    last_16 = await db.query(
        "SELECT * FROM player ORDER BY starting_number DESC limit 16"
    )

    # First round drafting is random that is why the order weird
    # Take a look at the pairing table round 1: https://www.eurogofed.org/egc/2024.html
    order = [1, 9, 13, 5, 7, 15, 11, 3, 4, 12, 16, 8, 6, 14, 10, 2]

    for board_id, strong, weak in zip(order, first_16, last_16):
        await db.query(f"RELATE {strong["id"]}->plays->match:{board_id}")
        await db.query(f"RELATE {weak["id"]}->plays->match:{board_id}")


async def add_all_odds() -> None:
    matches = await db.query(
        "select id,<-plays<-player.elo as elo, <-plays<-player.name as name from match"
    )
    matches = list(filter(lambda x: len(x["elo"]) > 0, matches[0]["result"]))

    for match in matches:
        r1, r2 = match["elo"]
        p1, p2 = win_percentages(r1, r2)
        await db.query(f"UPDATE {match["id"]} set odds={[p1,p2]}")


async def add_odds_to_match(match_id: str) -> None:
    match = await db.query(f"select <-plays<-player.elo as elo from {match_id}")
    assert len(match["elo"]) == 2, ("Calculating odds failed. Not 2 players", match_id)

    r1, r2 = match["elo"]
    p1, p2 = win_percentages(r1, r2)
    await db.query(f"UPDATE {match_id} set odds={[p1,p2]}")


async def get_all_gamblers() -> list[dict]:
    await connect()
    gamblers = await db.query(f"SELECT * FROM gambler ORDER BY budget DESC")
    await db.close()
    return gamblers[0]["result"]
