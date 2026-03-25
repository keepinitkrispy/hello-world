"""Persist open positions to disk so they survive bot restarts."""

import json
import os
import time

_PATH = os.environ.get("POSITIONS_FILE", "./open_positions.json")


def _load() -> dict:
    try:
        with open(_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    with open(_PATH, "w") as f:
        json.dump(data, f)


def record(trade) -> None:
    """Save a trade after buying."""
    data = _load()
    data[trade.mint] = {
        "mint":         trade.mint,
        "symbol":       trade.symbol,
        "token_amount": trade.token_amount,
        "sol_spent":    trade.sol_spent,
        "entry_time":   trade._entry_time,
    }
    _save(data)
    print(f"[positions] saved {trade.symbol}", flush=True)


def remove(mint: str) -> None:
    """Remove a position after selling."""
    data = _load()
    if mint in data:
        del data[mint]
        _save(data)


def load_open() -> list[dict]:
    """Return all saved positions on startup."""
    return list(_load().values())
