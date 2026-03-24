"""
Coin selection filters — all must pass before the bot will buy.

Checks (in order, cheapest first):
  1. Age             — coin must be old enough to show organic growth
  2. Copy detection  — name/symbol too close to a known popular coin
  3. Dev spam        — creator wallet has launched too many coins
  4. Social proof    — at least N pump.fun replies
  5. Holder spread   — top real holders don't own too much of the supply
"""

import time
from typing import Optional

import aiohttp
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient

import config

# ── Known coins that scammers endlessly clone ─────────────────────────────────
_CLONE_TARGETS = {
    # memecoins
    "bonk", "wif", "dogwifhat", "popcat", "book of meme", "bome",
    "myro", "slerf", "wen", "jeo boden", "jeo", "moo deng",
    "pnut", "peanut", "goat", "fartcoin",
    # political / celeb
    "trump", "melania", "maga", "biden", "elon", "musk",
    # classic
    "doge", "shib", "pepe", "floki", "inu",
}

# Common scam suffixes/prefixes that signal a copy coin
_SCAM_AFFIXES = {
    "baby", "mini", "micro", "mega", "ultra", "super", "og",
    "classic", "v2", "v3", "2.0", "ai", "gpt", "x",
    "sol", "solana",   # e.g. "trumpsol", "pepesol"
}


# ── 1. Age check ──────────────────────────────────────────────────────────────

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
    # pump.fun timestamps are usually in milliseconds
    if created > 1e12:
        created /= 1000
    return now - created


def _passes_age(coin: dict) -> tuple[bool, str]:
    age = _coin_age_seconds(coin)
    if age < config.MIN_AGE_SECONDS:
        return False, f"too new ({age:.0f}s < {config.MIN_AGE_SECONDS}s min)"
    return True, ""


# ── 2. Copy-coin detection ────────────────────────────────────────────────────

def _similarity(a: str, b: str) -> int:
    """Simple Levenshtein similarity 0-100."""
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
    dist = dp[n]
    return int(100 * (1 - dist / max(m, n)))


def _is_clone(name: str, symbol: str) -> tuple[bool, str]:
    name_lc   = name.lower().strip()
    symbol_lc = symbol.lower().strip()

    # Direct match or high similarity to a known target
    for target in _CLONE_TARGETS:
        if _similarity(name_lc, target) >= config.COPY_SIMILARITY_PCT:
            return True, f"name similar to '{target}'"
        if _similarity(symbol_lc, target) >= config.COPY_SIMILARITY_PCT:
            return True, f"symbol similar to '{target}'"

    # Name is just <scam_affix> + <clone_target>
    parts = set(name_lc.replace("-", " ").replace("_", " ").split())
    if parts & _SCAM_AFFIXES and parts & _CLONE_TARGETS:
        match = (parts & _CLONE_TARGETS).pop()
        return True, f"clone pattern ('{match}' + affix)"

    return False, ""


def _passes_copy_check(coin: dict) -> tuple[bool, str]:
    name   = coin.get("name", "")
    symbol = coin.get("symbol", "")
    is_clone, reason = _is_clone(name, symbol)
    if is_clone:
        return False, f"copy coin — {reason}"
    return True, ""


# ── 3. Dev spam check ─────────────────────────────────────────────────────────

async def _creator_coin_count(session: aiohttp.ClientSession, creator: str) -> int:
    """Ask pump.fun how many coins this wallet has already launched."""
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
    creator = coin.get("creator", "")
    count   = await _creator_coin_count(session, creator)
    if count > config.MAX_CREATOR_COINS:
        return False, f"dev spam ({count} coins from same wallet)"
    return True, ""


# ── 4. Social proof ───────────────────────────────────────────────────────────

def _passes_social(coin: dict) -> tuple[bool, str]:
    replies = int(coin.get("reply_count") or coin.get("comment_count") or 0)
    if replies < config.MIN_REPLY_COUNT:
        return False, f"low engagement ({replies} replies < {config.MIN_REPLY_COUNT} min)"
    return True, ""


# ── 5. Holder concentration ───────────────────────────────────────────────────

# Accounts that hold bonding curve supply or are known programs — not real holders
_INFRASTRUCTURE_PROGRAMS = {
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # pump.fun bonding curve program
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL Token program
    "11111111111111111111111111111111",                 # System program
}


async def _passes_holder_check(rpc: AsyncClient, mint: str) -> tuple[bool, str]:
    try:
        mint_pk      = Pubkey.from_string(mint)
        supply_resp  = await rpc.get_token_supply(mint_pk)
        largest_resp = await rpc.get_token_largest_accounts(mint_pk)

        total = float(supply_resp.value.ui_amount or 0)
        if total == 0:
            return True, ""  # can't check, let it through

        holders = largest_resp.value  # list of TokenAccountBalance
        # Filter out bonding curve / program accounts (those holding huge %)
        real_holders = []
        for h in holders:
            addr = str(h.address)
            pct  = float(h.ui_amount or 0) / total * 100
            if addr in _INFRASTRUCTURE_PROGRAMS:
                continue
            if pct > 50:
                # Almost certainly the bonding curve account for this token — skip
                continue
            real_holders.append((addr, pct))

        # Single wallet check
        for addr, pct in real_holders:
            if pct > config.MAX_TOP_HOLDER_PCT:
                return False, f"whale wallet holds {pct:.1f}%"

        # Top-5 combined check
        top5_combined = sum(pct for _, pct in real_holders[:5])
        if top5_combined > config.MAX_TOP5_COMBINED_PCT:
            return False, f"top 5 wallets hold {top5_combined:.1f}% combined"

    except Exception as e:
        # RPC errors are non-fatal — log and allow
        print(f"[filters] Holder check error for {mint[:8]}…: {e}")

    return True, ""


# ── Public entry point ────────────────────────────────────────────────────────

async def passes_all(
    session: aiohttp.ClientSession,
    rpc: Optional[AsyncClient],
    coin: dict,
) -> tuple[bool, str]:
    """
    Run all filters. Returns (True, "") if coin passes, or (False, reason) if not.
    rpc may be None in dry-run mode (holder check is skipped).
    """
    name   = coin.get("name", "?")
    symbol = coin.get("symbol", "?")

    # Cheap synchronous checks first
    for check_fn in (_passes_age, _passes_copy_check, _passes_social):
        ok, reason = check_fn(coin)
        if not ok:
            print(f"[filters] SKIP {symbol}/{name}: {reason}")
            return False, reason

    # Dev spam (one HTTP call)
    ok, reason = await _passes_dev_check(session, coin)
    if not ok:
        print(f"[filters] SKIP {symbol}/{name}: {reason}")
        return False, reason

    # Holder concentration (RPC call)
    if rpc is not None:
        mint = coin.get("mint", "")
        ok, reason = await _passes_holder_check(rpc, mint)
        if not ok:
            print(f"[filters] SKIP {symbol}/{name}: {reason}")
            return False, reason

    return True, ""
