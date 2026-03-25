"""
Momentum monitor — near-graduation strategy.

Polls pump.fun for coins in the 65-88% bonding curve zone.
Fires when a coin rises >= MIN_BC_RISE_PCT within MOMENTUM_WINDOW_SEC.
Coins this close to graduation already have real Jupiter liquidity.
"""

import asyncio
import time
from collections import defaultdict, deque

import aiohttp

import config

PUMPFUN_API = "https://frontend-api-v3.pump.fun/coins"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer":    "https://pump.fun/",
    "Origin":     "https://pump.fun",
    "Accept":     "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# mint -> deque of (timestamp, bonding_pct) snapshots
_bc_history: dict[str, deque] = defaultdict(lambda: deque())

_err_count = 0
_logged_sample = False


def _bc_pct(coin: dict) -> float:
    # Graduation = 85 SOL real reserves (confirmed from live completed coin data).
    # Use real_sol_reserves as primary — price-independent ground truth.
    real_sol = coin.get("real_sol_reserves") or 0
    if real_sol:
        return min(99.9, float(real_sol) / 85e9 * 100)

    # Fallback: virtual_sol_reserves — pump.fun inits at 30 SOL, graduates at 115 SOL
    vsol = coin.get("virtual_sol_reserves") or 0
    if vsol:
        pct = (float(vsol) - 30e9) / 85e9 * 100
        return max(0.0, min(99.9, pct))

    return 0.0


async def _fetch_zone(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch coins sorted by bonding curve progress descending (near graduation first)."""
    global _err_count
    params = {
        "sortBy":      "usd_market_cap",
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
                _err_count += 1
                wait = min(2 * _err_count, 30)
                print(f"[monitor] API {resp.status} (retry in {wait}s): {body[:200]}", flush=True)
                await asyncio.sleep(wait)
                return []

            raw = await resp.json(content_type=None)

            # Handle both plain list and {"coins": [...]} dict format
            if isinstance(raw, dict):
                data = raw.get("coins") or raw.get("data") or []
                if not isinstance(data, list):
                    print(f"[monitor] Unexpected dict keys: {list(raw.keys())}", flush=True)
                    return []
            elif isinstance(raw, list):
                data = raw
            else:
                print(f"[monitor] Unexpected response type: {type(raw)}", flush=True)
                return []

            _err_count = 0

            # Log BC distribution to verify field names and zone coverage
            if data:
                global _logged_sample
                bcs = sorted([_bc_pct(c) for c in data if isinstance(c, dict)], reverse=True)
                print(f"[monitor] API ok — {len(data)} coins | BC range: {bcs[-1]:.1f}%-{bcs[0]:.1f}%", flush=True)
                if not _logged_sample:
                    _logged_sample = True
                    print("[monitor] first coin keys+values:", flush=True)
                    for k, v in data[0].items():
                        print(f"  {k}: {v!r}", flush=True)
            else:
                print(f"[monitor] API ok — 0 coins returned", flush=True)

    except Exception as e:
        _err_count += 1
        wait = min(2 * _err_count, 30)
        print(f"[monitor] Fetch error ({type(e).__name__}): {e} — retry in {wait}s", flush=True)
        await asyncio.sleep(wait)
        return []

    # Only skip completed/graduated coins — let Jupiter handle liquidity filtering
    results = []
    for coin in data:
        if not isinstance(coin, dict):
            continue
        if coin.get("complete"):
            continue
        results.append(coin)

    return results


def _check_momentum(coin: dict) -> tuple[bool, float]:
    """Return (should_buy, rise_pts) for this coin."""
    mint = coin["mint"]
    bc   = _bc_pct(coin)
    now  = time.time()

    history = _bc_history[mint]
    history.append((now, bc))

    # Drop entries older than the window
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
    _tick = 0
    async with aiohttp.ClientSession() as session:
        while True:
            coins = await _fetch_zone(session)
            _tick += 1

            # Periodic status + sample every 20 ticks
            if _tick % 20 == 1:
                print(f"[monitor] tick={_tick} zone_coins={len(coins)}", flush=True)
                if coins:
                    s = coins[0]
                    print(
                        f"[monitor] top coin: {s.get('symbol','?')} bc={_bc_pct(s):.1f}%",
                        flush=True,
                    )

            for coin in coins:
                mint = coin.get("mint")
                if not mint or mint in seen_mints:
                    continue

                bc = _bc_pct(coin)
                if not (config.MONITOR_BC_MIN <= bc <= config.MONITOR_BC_MAX):
                    continue

                fired, rise = _check_momentum(coin)
                if fired:
                    seen_mints.add(mint)
                    symbol = coin.get("symbol", "???")
                    print(
                        f"[monitor] SIGNAL {symbol} ({mint[:8]}…) "
                        f"BC={_bc_pct(coin):.1f}% +{rise:.1f}pts/{config.MOMENTUM_WINDOW_SEC}s",
                        flush=True,
                    )
                    await queue.put(coin)

            await asyncio.sleep(config.POLL_INTERVAL_SEC)


async def run(queue: asyncio.Queue, seen_mints: set) -> None:
    try:
        await _run_inner(queue, seen_mints)
    except Exception as exc:
        import traceback
        print(f"[monitor] FATAL: {exc}", flush=True)
        traceback.print_exc()
        raise
