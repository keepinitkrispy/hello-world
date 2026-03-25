import time
from typing import Optional

from solana.rpc.async_api import AsyncClient

import aiohttp
import config

_CLONE_TARGETS = {
    "bonk", "wif", "dogwifhat", "popcat", "book of meme", "bome",
    "myro", "slerf", "wen", "moo deng", "pnut", "peanut", "goat", "fartcoin",
    "trump", "melania", "maga", "biden", "elon", "musk",
    "doge", "shib", "pepe", "floki", "inu",
}
_SCAM_AFFIXES = {
    "baby", "mini", "micro", "mega", "ultra", "super", "og",
    "classic", "v2", "v3", "2.0", "ai", "gpt", "x", "sol", "solana",
}


def _coin_age_seconds(coin: dict) -> float:
    created = coin.get("created_timestamp") or coin.get("created_at") or 0
    if isinstance(created, str):
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.timestamp()
        except Exception:
            return 9999
    if created > 1e12:
        created /= 1000
    return time.time() - created


def _similarity(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b: return 100
    if not a or not b: return 0
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[:], i
        for j in range(1, n + 1):
            dp[j] = min(dp[j] + 1, dp[j-1] + 1, prev[j-1] + (0 if a[i-1] == b[j-1] else 1))
    return int(100 * (1 - dp[n] / max(m, n)))


def _is_clone(name: str, symbol: str) -> tuple[bool, str]:
    nl, sl = name.lower().strip(), symbol.lower().strip()
    for t in _CLONE_TARGETS:
        if _similarity(nl, t) >= config.COPY_SIMILARITY_PCT:
            return True, f"name~'{t}'"
        if _similarity(sl, t) >= config.COPY_SIMILARITY_PCT:
            return True, f"symbol~'{t}'"
    parts = set(nl.replace("-", " ").replace("_", " ").split())
    if parts & _SCAM_AFFIXES and parts & _CLONE_TARGETS:
        return True, f"clone pattern"
    return False, ""


async def passes_all(session: aiohttp.ClientSession, rpc: Optional[AsyncClient], coin: dict) -> tuple[bool, str]:
    symbol = coin.get("symbol", "?")
    name   = coin.get("name", "?")

    age = _coin_age_seconds(coin)
    if age < config.MIN_AGE_SECONDS:
        print(f"[filters] SKIP {symbol}: too new ({age:.0f}s)", flush=True)
        return False, "too new"

    # Skip stale coins — if last trade was >60s ago the momentum is already dead
    last_trade = coin.get("last_trade_timestamp") or 0
    if last_trade > 1e12:
        last_trade /= 1000
    if last_trade and (time.time() - last_trade) > 60:
        stale_s = time.time() - last_trade
        print(f"[filters] SKIP {symbol}: last trade {stale_s:.0f}s ago", flush=True)
        return False, "stale"

    is_clone, reason = _is_clone(name, symbol)
    if is_clone:
        print(f"[filters] SKIP {symbol}: copy coin {reason}", flush=True)
        return False, reason

    replies = int(coin.get("reply_count") or coin.get("comment_count") or 0)
    if replies < config.MIN_REPLY_COUNT:
        print(f"[filters] SKIP {symbol}: low engagement", flush=True)
        return False, "low engagement"

    return True, ""
