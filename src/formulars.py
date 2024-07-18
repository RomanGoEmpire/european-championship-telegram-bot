import math


def win_percentages(your_rank: int, opponent_rank: int) -> tuple[float, float]:
    def beta(rank: int) -> float:
        return -7 * math.log(3300 - rank)

    se: float = 1 / (1 + math.exp(beta(opponent_rank) - beta(your_rank)))
    assert 0.0 <= se <= 1.0, "formular is wrong"
    return round(se, 4), round(1 - se, 4)
