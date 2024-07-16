import requests
import msgspec
import json

from urllib3.exceptions import HeaderParsingError
from .tournament import Player
from icecream import ic

DB_URL: str = "http://localhost:8000"
HEADERS: dict = {"Accept": "application/json", "NS": "test", "DB": "test"}


def snake_case(name: str) -> str:
    return name.lower().replace(" ", "_").replace("î", "i").replace("-", "_")


def status_ok(response: requests.Response) -> bool:
    return response.json()["result"]["status"] == "OK"


def sql(data: str) -> None:
    response = requests.post(url=f"{DB_URL}/sql", headers=HEADERS, data=data)
    assert response.status_code == 200 and status_ok(response), (
        "SQL ERROR",
        response.content,
    )


def create(table: str, id: str | int, data: dict) -> None:
    response = requests.post(
        url=f"{DB_URL}/key/{table}/{id}",
        headers=HEADERS,
        json=data,
    )
    assert response.status_code == 200 and status_ok(response), (
        f"create {table}:{id} failed",
        response.content,
    )


def put(table: str, id: str | int, data: dict) -> None:
    response = requests.patch(
        url=f"{DB_URL}/key/{table}/{id}",
        headers=HEADERS,
        json=data,
    )
    assert response.status_code == 200 and status_ok(response), (
        f"put {table}:{id} failed",
        response.content,
    )


def patch(table: str, id: str | int, data: dict) -> None:
    response = requests.patch(
        url=f"{DB_URL}/key/{table}/{id}",
        headers=HEADERS,
        json=data,
    )
    assert response.status_code == 200 and status_ok(response), (
        f"patch {table}:{id} failed",
        response.content,
    )


def delete(table: str, id: int) -> None:
    response = requests.delete(
        url=f"{DB_URL}/key/{table}/{id}",
        headers=HEADERS,
    )
    assert response.status_code == 200, (
        f"delete {table}:{id} failed",
        response.content,
    )


def create_tables() -> None:
    pass
    data = """
    """
    sql(data)


def add_players() -> None:
    players = json.load(open("data/players.json", "r"))

    for player in players:
        response = requests.post(
            url=f"{DB_URL}/key/player/{snake_case(player["name"])}",
            headers=HEADERS,
            data=player,
        )
        assert response.status_code == 200, ("player creating failed", response.content)


def add_rounds() -> None:
    rounds = json.load(open("data/tournament.json", "r"))

    for k, v in rounds.items():
        ic(k, v)
