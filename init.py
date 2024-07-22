import os
import json
import asyncio
from dotenv import load_dotenv
import requests
from datetime import datetime
from icecream import ic
from surrealdb import Surreal
from src.formulars import win_percentages


DB = Surreal("ws://localhost:8000/rpc")


async def connect():
    await DB.connect()
    await DB.signin({"user": USER, "pass": PASSWORD})
    await DB.use("main", "main")


async def create_tables():
    await DB.query(
        """
        DEFINE TABLE IF NOT EXISTS player;
        DEFINE FIELD name ON TABLE player TYPE string;
        DEFINE FIELD elo ON TABLE player TYPE int;
        DEFINE FIELD rank ON TABLE player TYPE string;
        DEFINE FIELD starting_number ON TABLE player TYPE number;

        DEFINE TABLE IF NOT EXISTS match;
        DEFINE FIELD winner ON TABLE match TYPE option<record<player>>;
        DEFINE FIELD looser ON TABLE match TYPE option<record<player>>;
        DEFINE FIELD next_match_for_winner ON TABLE match TYPE option<record<match>>;
        DEFINE FIELD next_match_for_looser ON TABLE match TYPE option<record<match>>;
        DEFINE FIELD round ON TABLE match TYPE record<round>;
        DEFINE FIELD odds ON TABLE match TYPE option<array<number>>;

        DEFINE TABLE IF NOT EXISTS gambler;
        DEFINE FIELD name ON TABLE gambler TYPE string;
        DEFINE FIELD username ON TABLE gambler TYPE string;
        DEFINE FIELD chat_id ON TABLE gambler TYPE int;
        DEFINE FIELD balance ON TABLE  gambler TYPE number DEFAULT 1000;

        DEFINE TABLE IF NOT EXISTS round;
        DEFINE FIELD name ON TABLE round TYPE string;
        DEFINE FIELD deadline ON TABLE round TYPE datetime;
        DEFINE FIELD active ON TABLE round TYPE bool DEFAULT FALSE;

        DEFINE TABLE IF NOT EXISTS message;

        DEFINE TABLE IF NOT EXISTS plays;
        DEFINE FIELD in ON TABLE plays TYPE record<player>;
        DEFINE FIELD out ON TABLE plays TYPE record<match>;

        DEFINE TABLE IF NOT EXISTS bets;
        DEFINE FIELD in ON TABLE bets TYPE record<gambler>;
        DEFINE FIELD out ON TABLE bets TYPE record<match>;
        DEFINE FIELD winner ON TABLE bets TYPE record<player>;
        DEFINE FIELD amount ON TABLE bets TYPE number;
        """
    )


async def add_tables_from_json() -> None:
    players = json.load(open("data/players.json"))
    matches = json.load(open("data/matches.json"))
    rounds = json.load(open("data/rounds.json"))

    for player in players:
        await DB.create("player", data=player)
    for match in matches:
        await DB.create("match", data=match)
    for round in rounds:
        await DB.create("round", data=round)


async def add_plays_first_round() -> None:
    players = await DB.query("SELECT * FROM player ORDER BY starting_number")
    # first round 1 the matches
    first_16 = await DB.query("SELECT * from player ORDER BY starting_number limit 16")
    first_16 = first_16[0]["result"]

    last_16 = await DB.query(
        "SELECT * FROM player ORDER BY starting_number DESC limit 16"
    )
    last_16 = last_16[0]["result"]
    # First round drafting is random that is why the order weird
    # Take a look at the pairing table round 1: https://www.eurogofed.org/egc/2024.html
    order = [1, 9, 13, 5, 7, 15, 11, 3, 4, 12, 16, 8, 6, 14, 10, 2]

    for board_id, strong, weak in zip(order, first_16, last_16):
        await DB.query(f"RELATE {strong["id"]}->plays->match:{board_id}")
        await DB.query(f"RELATE {weak["id"]}->plays->match:{board_id}")


async def add_all_odds() -> None:
    matches = await DB.query(
        "select id,<-plays<-player.elo as elo, <-plays<-player.name as name from match"
    )
    matches = list(filter(lambda x: len(x["elo"]) > 0, matches[0]["result"]))

    for match in matches:
        r1, r2 = match["elo"]
        p1, p2 = win_percentages(r1, r2)
        await DB.query(f"UPDATE {match["id"]} set odds={[p1,p2]}")


async def main():

    await connect()
    await create_tables()
    await add_tables_from_json()
    await add_plays_first_round()
    await add_all_odds()
    await DB.close()


if __name__ == "__main__":
    load_dotenv()
    USER = os.getenv("SURREAL_USER")
    PASSWORD = os.getenv("SURREAL_PASSWORD")
    asyncio.run(main())
