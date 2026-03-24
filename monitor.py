"""
Near-graduation monitor.

Finds pump.fun coins already in the 65-88% bonding curve zone that are
actively rising toward graduation. These coins have real liquidity and
Jupiter can route them. Coins at 5-40% BC can't be reliably traded.

Root-cause fix: pump.fun frontend API blocks headless requests.
We send browser-like headers so every fetch succeeds.
"""

import asyncio
import time
from collections import defaultdict, deque

import aiohttp

import config

PUMPFUN_API = "https://frontend-api-v3.pump.fun/coins"

# Must send browser headers — pump.fun blocks plain server requests
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer":         "https://pump.fun/",
    "Origin":          "https://pump.fun",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# mint -> deque of (timestamp, bonding_pct) snapshots
_bc_history: dict[str, deque] = defaultdict(lambda: deque())


def _bc_pct(coin: dict) -> float:
    return float(
        coin.get("bonding_curve_percentage")
        or coin.get("bonding_curve_progress")
        or coin.get("progress")
        or 0
    )


async def _fetch_active(session: aiohttp.ClientSession) -> list[dict]:
    params = {
        "sort":        "bonding_curve_percentage",
        "order":       "DESC",
        "limit":       50,
        "includeNsfw": "true",
    }
    try:
        async with session.get(
            PUMPFUN_API,
            params=params,
            headers=_HEADERS,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"[monitor] API {resp.status}: {body[:300]}", flush=True)
                return []
            data = await resp.json(content_type=None)

            if isinstance(data, dict):
                coins_raw = (
                    data.get("coins")
                    or data.get("data")
                    or data.get("results")
                    or []
                )
                print(f"[monitor] API ok (dict keys={list(data.keys())}) \u2014 {len(coins_raw)} coins", flush=True)
            elif isinstance(data, list):
                coins_raw = data
                print(f"[monitor] API ok \u2014 {len(coins_raw)} coins", flush=True)
            else:
                print(f"[monitor] Unexpected response: {type(data)} {str(data)[:200]}", flush=True)
                return []
    except Exception as e:
        print(f"[monitor] Fetch error: {repr(e)}", flush=True)
        return []

    results = []
    for coin in coins_raw:
        if not isinstance(coin, dict):
            continue
        if coin.get("complete"):
            continue
        bc = _bc_pct(coin)
        if bc < config.MONITOR_BC_MIN or bc > config.MONITOR_BC_MAX:
            continue
        results.append(coin)
    return results


def _record_and_check(coin: dict) -> tuple[bool, float]:
    """Signal when a near-graduation coin shows upward momentum."""
    mint = coin["mint"]
    bc   = _bc_pct(coin)
    now  = time.time()

    history = _bc_history[mint]
    history.append((now, bc))

    cutoff = now - config.MOMENTUM_WINDOW_SEC
    while history and history[0][0] < cutoff:
        history.popleft()

    if len(history) < 2:
        return False, 0.0

    rise = bc - history[0][1]
    if rise >= config.MIN_BC_RISE_PCT:
        return True, rise
    return False, rise


async def _run_inner(queue: asyncio.Queue, seen_mints: set) -> None:
    _tick      = 0
    _err_count = 0

    async with aiohttp.ClientSession() as session:
        while True:
            coins = await _fetch_active(session)
            _tick += 1

            if not coins:
                _err_count += 1
                backoff = min(2 * _err_count, 30)
                print(f"[monitor] no data (attempt {_err_count}), retry in {backoff}s", flush=True)
                await asyncio.sleep(backoff)
                continue
            else:
                _err_count = 0

            # First successful tick: dump a raw coin so we can verify field names
            if _tick == 1:
                print(f"[monitor] first-tick sample: {str(coins[0])[:500]}", flush=True)

            if _tick % 20 == 1:
                print(
                    f"[monitor] tick {_tick} | {len(coins)} in zone "
                    f"({config.MONITOR_BC_MIN}\u2013{config.MONITOR_BC_MAX}%)",
                    flush=True,
                )
                if coins:
                    s = coins[0]
                    print(f"[monitor] top: {s.get('symbol')} bc={_bc_pct(s):.1f}%", flush=True)

            for coin in coins:
                mint = coin.get("mint")
                if not mint or mint in seen_mints:
                    continue

                should_buy, rise = _record_and_check(coin)
                if should_buy:
                    seen_mints.add(mint)
                    symbol = coin.get("symbol", "???")
                    bc     = _bc_pct(coin)
                    print(
                        f"[monitor] SIGNAL {symbol} ({mint[:8]}\u2026) "
                        f"BC={bc:.1f}% +{rise:.1f}pts",
                        flush=True,
                    )
                    await queue.put(coin)

            await asyncio.sleep(config.POLL_INTERVAL_SEC)


async def run(queue: asyncio.Queue, seen_mints: set) -> None:
    try:
        await _run_inner(queue, seen_mints)
    except Exception as exc:
        import traceback
        print(f"[monitor] FATAL: {repr(exc)}", flush=True)
        traceback.print_exc()
        raise
