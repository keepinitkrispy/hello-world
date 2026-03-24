"""
Momentum monitor — catches coins with rapidly rising bonding curve %.

Strategy:
  1. Poll pump.fun for coins sorted by recent activity.
  2. Track bonding_curve_percentage over time per coin.
  3. Fire when a coin's bonding % rises >= MIN_BC_RISE_PCT in the window
     AND is not already too close to graduation (>= MAX_BC_PCT).
  4. Each mint is only queued once per session.
"""

import asyncio
import time
from collections import defaultdict, deque

import aiohttp

import config

PUMPFUN_API = "https://frontend-api.pump.fun/coins"

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
        "sort":        "last_trade_unix_timestamp",
        "order":       "DESC",
        "limit":       50,
        "includeNsfw": "true",
    }
    try:
        async with session.get(
            PUMPFUN_API,
            params=params,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                print(f"[monitor] API returned {resp.status}")
                return []
            data = await resp.json()
    except Exception as e:
        print(f"[monitor] Fetch error: {e}")
        return []

    results = []
    for coin in data:
        if not isinstance(coin, dict):
            continue
        if coin.get("complete"):
            continue
        bc = _bc_pct(coin)
        if bc >= config.MAX_BC_PCT:
            continue  # too close to graduation chaos
        results.append(coin)
    return results


def _record_and_check(coin: dict) -> tuple[bool, float]:
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
        if rise > config.MAX_BC_RISE_PCT:
            return False, rise  # too fast — bots
        return True, rise

    return False, rise


async def run(queue: asyncio.Queue, seen_mints: set) -> None:
    _tick = 0
    async with aiohttp.ClientSession() as session:
        while True:
            coins = await _fetch_active(session)
            _tick += 1

            if _tick % 20 == 1:
                print(f"[monitor] tick {_tick} | {len(coins)} candidates")
                if coins:
                    s = coins[0]
                    print(f"[monitor] sample: {s.get('symbol')} bc={_bc_pct(s):.1f}%")

            for coin in coins:
                mint = coin.get("mint")
                if not mint or mint in seen_mints:
                    continue

                should_buy, rise = _record_and_check(coin)

                if should_buy:
                    seen_mints.add(mint)
                    symbol = coin.get("symbol", "???")
                    print(
                        f"[monitor] MOMENTUM {symbol} ({mint[:8]}…) "
                        f"BC +{rise:.1f}pts in {config.MOMENTUM_WINDOW_SEC}s"
                    )
                    await queue.put(coin)

            await asyncio.sleep(config.POLL_INTERVAL_SEC)
