import json
import os

_PATH = os.environ.get("PARKED_PROFITS_PATH", "./parked_profits.json")


def load() -> float:
    try:
        return float(json.loads(open(_PATH).read()).get("parked_sol", 0.0))
    except Exception:
        return 0.0


def add(sol: float) -> float:
    total = load() + sol
    with open(_PATH, "w") as f:
        json.dump({"parked_sol": round(total, 9)}, f)
    return total
