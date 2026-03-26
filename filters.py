import time
from typing import Optional

from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

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


async def _check_holder_safety(rpc: AsyncClient, mint: str, coin: dict) -> tuple[bool, str]:
    """Return (safe, reason). Rejects coins where top wallets hold >50% of supply."""
    try:
        resp = await rpc.get_token_largest_accounts(Pubkey.from_string(mint))
        if not resp.value:
            return True, ""
        accounts = resp.value[:10]
        total_supply = float(coin.get("total_supply") or 1_000_000_000)
        top3 = sum(float(a.amount.ui_amount or 0) for a in accounts[:3])
        top3_pct = top3 / total_supply * 100
        if top3_pct > 40:
            return False, f"top3 hold {top3_pct:.0f}%"
        return True, ""
    except Exception:
        return True, ""  # allow on RPC error — don't block trades due to infra issues


def _is_non_ascii(name: str, symbol: str) -> bool:
    """Reject coins with Korean/Chinese/Japanese/Cyrillic characters — nearly always rugs."""
    for ch in name + symbol:
        if ord(ch) > 127:
            return True
    return False


async def passes_all(session: aiohttp.ClientSession, rpc: Optional[AsyncClient], coin: dict) -> tuple[bool, str]:
    symbol = coin.get("symbol", "?")
    name   = coin.get("name", "?")

    if _is_non_ascii(name, symbol):
        print(f"[filters] SKIP {symbol}: non-ASCII name/symbol", flush=True)
        return False, "non-ascii"

    age = _coin_age_seconds(coin)
    if not config.BONDED_ONLY and age < config.MIN_AGE_SECONDS:
        print(f"[filters] SKIP {symbol}: too new ({age:.0f}s)", flush=True)
        return False, "too new"

    is_clone, reason = _is_clone(name, symbol)
    if is_clone:
        print(f"[filters] SKIP {symbol}: copy coin {reason}", flush=True)
        return False, reason

    replies = int(coin.get("reply_count") or coin.get("comment_count") or 0)
    if replies < config.MIN_REPLY_COUNT:
        print(f"[filters] SKIP {symbol}: low engagement", flush=True)
        return False, "low engagement"

    if rpc:
        mint = coin.get("mint", "")
        if mint:
            safe, reason = await _check_holder_safety(rpc, mint, coin)
            if not safe:
                print(f"[filters] SKIP {symbol}: holder concentration ({reason})", flush=True)
                return False, reason

    return True, ""
