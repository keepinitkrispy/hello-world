import asyncio
import aiohttp

import config

PUMPFUN_API = "https://frontend-api.pump.fun/coins"


def _bonding_pct(coin: dict) -> float:
    """Return bonding curve progress 0-100 from whichever field exists."""
    return float(
        coin.get("bonding_curve_percentage")
        or coin.get("bonding_curve_progress")
        or coin.get("progress")
        or 0
    )


async def _fetch_candidates(session: aiohttp.ClientSession) -> list[dict]:
    params = {
        "sort": "bonding_curve_percentage",
        "order": "DESC",
        "limit": 50,
        "includeNsfw": "true",
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
            continue
        pct = _bonding_pct(coin)
        if config.BOND_THRESHOLD_MIN <= pct <= config.BOND_THRESHOLD_MAX:
            coin["_bonding_pct"] = pct
            results.append(coin)
    return results


async def run(queue: asyncio.Queue, seen_mints: set) -> None:
    """Continuously poll pump.fun and enqueue newly discovered candidates."""
    async with aiohttp.ClientSession() as session:
        while True:
            candidates = await _fetch_candidates(session)
            for coin in candidates:
                mint = coin.get("mint")
                if mint and mint not in seen_mints:
                    seen_mints.add(mint)
                    symbol = coin.get("symbol", "???")
                    pct = coin["_bonding_pct"]
                    print(f"[monitor] {symbol} ({mint[:8]}…) bonding {pct:.1f}%")
                    await queue.put(coin)
            await asyncio.sleep(config.POLL_INTERVAL_SEC)
