"""
Coin selection filters.

Checks (in order, cheapest first):
  1. Age             -- coin must be old enough
  2. Copy detection  -- name/symbol too close to a known popular coin
  3. Dev spam        -- creator wallet has launched too many coins
  4. Social proof    -- at least N pump.fun replies

Holder concentration check removed from hot path: coins at 65%+ BC have
already survived real trading pressure and the RPC call is too slow/unreliable
on public mainnet to use on every candidate.
"""

import time
from typing import Optional

import aiohttp
from solana.rpc.async_api import AsyncClient

import config

# ── Known coins that scammers endlessly clone ──────────────────────────────────
_CLONE_TARGETS = {
    "bonk", "wif", "dogwifhat", "popcat", "book of meme", "bome",
    "myro", "slerf", "wen", "jeo boden", "jeo", "moo deng",
    "pnut", "peanut", "goat", "fartcoin",
    "trump", "melania", "maga", "biden", "elon", "musk",
    "doge", "shib", "pepe", "floki", "inu",
}

_SCAM_AFFIXES = {
    "baby", "mini", "micro", "mega", "ultra", "super", "og",
    "classic", "v2", "v3", "2.0", "ai", "gpt", "x",
    "sol", "solana",
}


# ── 1. Age check ─────────────────────────────────────────────────────────────────

def _coin_age_seconds(coin: dict) -> float:
    created = coin.get("created_timestamp") or coin.get("created_at") or 0
    if isinstance(created, str):
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            created = dt.timestamp()
        except Exception:
            return 9999
    now = time.time()
    if created > 1e12:
        created /= 1000
    return now - created


def _passes_age(coin: dict) -> tuple[bool, str]:
    age = _coin_age_seconds(coin)
    if age < config.MIN_AGE_SECONDS:
        return False, f"too new ({age:.0f}s)"
    return True, ""


# ── 2. Copy-coin detection ─────────────────────────────────────────────────────────

def _similarity(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b:
        return 100
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev[j - 1] + cost)
    return int(100 * (1 - dp[n] / max(m, n)))


def _is_clone(name: str, symbol: str) -> tuple[bool, str]:
    name_lc   = name.lower().strip()
    symbol_lc = symbol.lower().strip()
    for target in _CLONE_TARGETS:
        if _similarity(name_lc, target) >= config.COPY_SIMILARITY_PCT:
            return True, f"name similar to '{target}'"
        if _similarity(symbol_lc, target) >= config.COPY_SIMILARITY_PCT:
            return True, f"symbol similar to '{target}'"
    parts = set(name_lc.replace("-", " ").replace("_", " ").split())
    if parts & _SCAM_AFFIXES and parts & _CLONE_TARGETS:
        match = (parts & _CLONE_TARGETS).pop()
        return True, f"clone pattern ('{match}' + affix)"
    return False, ""


def _passes_copy_check(coin: dict) -> tuple[bool, str]:
    is_clone, reason = _is_clone(coin.get("name", ""), coin.get("symbol", ""))
    if is_clone:
        return False, f"copy coin \u2014 {reason}"
    return True, ""


# ── 3. Dev spam check ───────────────────────────────────────────────────────────────

async def _creator_coin_count(session: aiohttp.ClientSession, creator: str) -> int:
    if not creator:
        return 0
    url    = "https://frontend-api.pump.fun/coins"
    params = {"creator": creator, "limit": config.MAX_CREATOR_COINS + 1}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                return 0
            data = await resp.json()
            return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


async def _passes_dev_check(session: aiohttp.ClientSession, coin: dict) -> tuple[bool, str]:
    count = await _creator_coin_count(session, coin.get("creator", ""))
    if count > config.MAX_CREATOR_COINS:
        return False, f"dev spam ({count} coins from same wallet)"
    return True, ""


# ── 4. Social proof ───────────────────────────────────────────────────────────────

def _passes_social(coin: dict) -> tuple[bool, str]:
    replies = int(coin.get("reply_count") or coin.get("comment_count") or 0)
    if replies < config.MIN_REPLY_COUNT:
        return False, f"low engagement ({replies} replies)"
    return True, ""


# ── Public entry point ─────────────────────────────────────────────────────────────

async def passes_all(
    session: aiohttp.ClientSession,
    rpc: Optional[AsyncClient],
    coin: dict,
) -> tuple[bool, str]:
    name   = coin.get("name", "?")
    symbol = coin.get("symbol", "?")

    for check_fn in (_passes_age, _passes_copy_check, _passes_social):
        ok, reason = check_fn(coin)
        if not ok:
            print(f"[filters] SKIP {symbol}/{name}: {reason}")
            return False, reason

    ok, reason = await _passes_dev_check(session, coin)
    if not ok:
        print(f"[filters] SKIP {symbol}/{name}: {reason}")
        return False, reason

    # Holder concentration check intentionally skipped:
    # coins at 65%+ BC have survived real trading; RPC calls here are too
    # slow on public mainnet and add latency before a time-sensitive entry.

    return True, ""
