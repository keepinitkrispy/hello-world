"""
Momentum monitor — catches coins in the early stage of a pump.

Strategy:
  1. Poll pump.fun for recently active coins every POLL_INTERVAL_SEC.
  2. Keep a rolling price history for each coin.
  3. When a coin's price rises >= MIN_PRICE_RISE_PCT over MOMENTUM_WINDOW_SEC
     AND is not a suspicious spike (> MAX_PRICE_RISE_PCT), queue it for buying.
  4. Each coin is only queued once per session (seen_mints guard).
"""

import asyncio
import time
from collections import defaultdict, deque

import aiohttp

import config

PUMPFUN_API = "https://frontend-api.pump.fun/coins"

# mint -> deque of (timestamp, price) snapshots within the window
_price_history: dict[str, deque] = defaultdict(lambda: deque())


def _current_price(coin: dict) -> float:
    """Derive USD price per token. Falls back to mcap/supply."""
    for field in ("price", "usd_price", "last_price", "token_price"):
        v = coin.get(field)
        if v:
            return float(v)
    # Reliable fallback: market_cap_usd / total_supply
    mcap   = float(coin.get("usd_market_cap") or coin.get("market_cap_usd") or 0)
    supply = float(coin.get("total_supply") or 1_000_000_000)
    if mcap > 0 and supply > 0:
        return mcap / supply
    return 0.0


def _mcap(coin: dict) -> float:
    return float(coin.get("usd_market_cap") or coin.get("market_cap_usd") or 0)


async def _fetch_active(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch the most recently traded coins."""
    params = {
        "sort":         "last_trade_unix_timestamp",
        "order":        "DESC",
        "limit":        50,
        "includeNsfw":  "true",
    }
    try:
        async with session.get(
            PUMPFUN_API,
            params=params,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
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
            continue  # already graduated, skip
        mcap  = _mcap(coin)
        price = _current_price(coin)
        if price <= 0:
            continue
        if not (config.MIN_MCAP_USD <= mcap <= config.MAX_MCAP_USD):
            continue
        results.append(coin)

    if data and not results:
        # Help diagnose why everything is filtered — show first coin's mcap
        sample = next((c for c in data if isinstance(c, dict)), {})
        print(f"[monitor] All {len(data)} coins filtered — sample mcap: ${_mcap(sample):,.0f} (range ${config.MIN_MCAP_USD:,}–${config.MAX_MCAP_USD:,})")

    return results


def _record_and_check(coin: dict) -> tuple[bool, float]:
    """
    Add latest price snapshot. Return (should_buy, rise_pct) if momentum
    threshold crossed, else (False, 0).
    """
    mint  = coin["mint"]
    price = _current_price(coin)
    now   = time.time()

    history = _price_history[mint]
    history.append((now, price))

    # Drop snapshots outside the momentum window
    cutoff = now - config.MOMENTUM_WINDOW_SEC
    while history and history[0][0] < cutoff:
        history.popleft()

    if len(history) < 2:
        return False, 0.0

    oldest_price = history[0][1]
    if oldest_price <= 0:
        return False, 0.0

    rise_pct = (price - oldest_price) / oldest_price * 100

    if rise_pct >= config.MIN_PRICE_RISE_PCT:
        if rise_pct > config.MAX_PRICE_RISE_PCT:
            return False, rise_pct  # suspicious spike — skip
        return True, rise_pct

    return False, rise_pct


async def run(queue: asyncio.Queue, seen_mints: set) -> None:
    """Continuously poll pump.fun and enqueue momentum candidates."""
    async with aiohttp.ClientSession() as session:
        while True:
            coins = await _fetch_active(session)
            for coin in coins:
                mint = coin.get("mint")
                if not mint or mint in seen_mints:
                    continue

                should_buy, rise_pct = _record_and_check(coin)
                if should_buy:
                    seen_mints.add(mint)
                    symbol = coin.get("symbol", "???")
                    mcap   = _mcap(coin)
                    print(
                        f"[monitor] MOMENTUM {symbol} ({mint[:8]}…) "
                        f"+{rise_pct:.1f}% in {config.MOMENTUM_WINDOW_SEC}s "
                        f"| mcap ${mcap:,.0f}"
                    )
                    await queue.put(coin)

            await asyncio.sleep(config.POLL_INTERVAL_SEC)
