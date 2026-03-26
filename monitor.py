"""
Real-time momentum monitor — WebSocket-based (PumpPortal live feed).

Single persistent WS connection to wss://pumpportal.fun/api/data.
- subscribeNewToken  : catches every new launch and subscribes to its trades
- Zone poller (15s)  : REST poll to discover coins already in BC zone, subscribes to trades
- Signal condition   : 3+ consecutive buys within 10s with BC rising in zone

Why this beats polling: trade events arrive the instant they land on-chain.
The old 2s REST poll was always arriving after the pump.
"""

import asyncio
import json
import time
from collections import defaultdict

import aiohttp

import config

PUMPPORTAL_WS    = "wss://pumpportal.fun/api/data"
PUMPFUN_API      = "https://frontend-api-v3.pump.fun/coins"
PUMPFUN_COIN_URL = "https://frontend-api-v3.pump.fun/coins/{mint}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer":    "https://pump.fun/",
    "Origin":     "https://pump.fun",
    "Accept":     "application/json, text/plain, */*",
}

# Per-mint buy history: list of (timestamp, bc_pct)
_buy_history: dict[str, list] = defaultdict(list)

# Mints we've already subscribed to trade events
_subscribed: set = set()

# Signal cooldown tracking
_signal_times: dict[str, float] = {}
SIGNAL_COOLDOWN_SEC = 600

# Permanent session blocks (set after stop-loss exits)
_permanent_blocks: set = set()

# Strong references to background tasks so GC doesn't cancel them mid-flight
_bg_tasks: set = set()

CONSECUTIVE_BUYS = 3   # consecutive buys needed to fire a signal
TRADE_WINDOW_SEC = 10  # look-back window for consecutive buys


def block_mint(mint: str) -> None:
    """Permanently block a mint from re-signaling this session (called after stop-loss exit)."""
    _permanent_blocks.add(mint)
    print(f"[monitor] Blocked {mint[:8]}… from re-entry this session", flush=True)


def _bc_from_vsol(v_sol: float) -> float:
    """
    Calculate BC% from vSolInBondingCurve (WebSocket field, value in SOL not lamports).
    pump.fun initialises at 30 SOL virtual, graduates at 115 SOL (delta = 85 SOL).
    """
    pct = (v_sol - 30.0) / 85.0 * 100.0
    return max(0.0, min(99.9, pct))


def _bc_from_coin(coin: dict) -> float:
    """Calculate BC% from REST API coin dict (reserves in lamports)."""
    real_sol = coin.get("real_sol_reserves") or 0
    if real_sol:
        return min(99.9, float(real_sol) / 85e9 * 100)
    vsol = coin.get("virtual_sol_reserves") or 0
    if vsol:
        pct = (float(vsol) - 30e9) / 85e9 * 100
        return max(0.0, min(99.9, pct))
    return 0.0


async def _subscribe(ws, mints: list[str]) -> None:
    if not mints:
        return
    await ws.send_json({"method": "subscribeTokenTrade", "keys": mints})
    _subscribed.update(mints)


async def _fetch_zone_mints(session: aiohttp.ClientSession) -> list[str]:
    """REST poll: return mints of coins currently in the BC zone."""
    params = {
        "sortBy":      "bondingCurve",
        "order":       "DESC",
        "limit":       100,
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
                return []
            raw = await resp.json(content_type=None)
            coins = raw if isinstance(raw, list) else raw.get("coins", raw.get("data", []))
            mints = []
            for coin in coins:
                if not isinstance(coin, dict) or coin.get("complete"):
                    continue
                bc = _bc_from_coin(coin)
                if config.MONITOR_BC_MIN <= bc <= config.MONITOR_BC_MAX:
                    mint = coin.get("mint")
                    if mint:
                        mints.append(mint)
            return mints
    except Exception as e:
        print(f"[monitor] Zone poll error: {e}", flush=True)
        return []


async def _fetch_coin(session: aiohttp.ClientSession, mint: str) -> dict:
    """Fetch full coin data for a mint (needed for filters: age, replies, name, etc.)."""
    try:
        async with session.get(
            PUMPFUN_COIN_URL.format(mint=mint),
            headers=_HEADERS,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                return await resp.json(content_type=None)
    except Exception:
        pass
    return {}


async def _zone_poller(ws, session: aiohttp.ClientSession) -> None:
    """Every 15s: discover coins already in BC zone and subscribe to their trades."""
    while True:
        mints = await _fetch_zone_mints(session)
        new   = [m for m in mints if m not in _subscribed]
        if new:
            await _subscribe(ws, new)
        print(
            f"[monitor] Zone poll: {len(mints)} in zone, +{len(new)} new ({len(_subscribed)} total)",
            flush=True,
        )
        await asyncio.sleep(5)


async def _enqueue_signal(
    mint:       str,
    bc_pct:     float,
    bc_rise:    float,
    symbol_hint: str,
    session:    aiohttp.ClientSession,
    queue:      asyncio.Queue,
    seen_mints: set,
) -> None:
    """Background task: fetch full coin data then enqueue signal. Never blocks the WS loop."""
    coin = await _fetch_coin(session, mint)
    if not coin:
        # Remove from seen_mints so the mint can signal again on next qualifying buy
        seen_mints.discard(mint)
        return

    symbol = coin.get("symbol") or symbol_hint or "???"
    print(
        f"[monitor] WS SIGNAL {symbol} ({mint[:8]}…) "
        f"BC={bc_pct:.1f}% +{bc_rise:.2f}pts | {CONSECUTIVE_BUYS} buys/{TRADE_WINDOW_SEC}s",
        flush=True,
    )
    await queue.put(coin)


def _handle_event(
    event:      dict,
    ws,
    session:    aiohttp.ClientSession,
    queue:      asyncio.Queue,
    seen_mints: set,
) -> None:
    """Synchronous fast-path: update buy history, fire signal as background task if conditions met."""
    mint    = event.get("mint")
    tx_type = event.get("txType")  # "buy" | "sell" | "create"

    if not mint or tx_type not in ("buy", "sell", "create"):
        return

    # On new token creation: subscribe to its trades if it's already in zone
    if tx_type == "create" and mint not in _subscribed:
        v_sol = float(event.get("vSolInBondingCurve") or 0)
        if config.MONITOR_BC_MIN <= _bc_from_vsol(v_sol) <= config.MONITOR_BC_MAX:
            t = asyncio.create_task(_subscribe(ws, [mint]))
            _bg_tasks.add(t)
            t.add_done_callback(_bg_tasks.discard)

    if tx_type != "buy":
        return

    # Skip if blocked or in cooldown
    if mint in seen_mints or mint in _permanent_blocks:
        return
    sig_t = _signal_times.get(mint)
    if sig_t and time.time() - sig_t < SIGNAL_COOLDOWN_SEC:
        return

    v_sol  = float(event.get("vSolInBondingCurve") or 0)
    bc_pct = _bc_from_vsol(v_sol)

    if not (config.MONITOR_BC_MIN <= bc_pct <= config.MONITOR_BC_MAX):
        return

    now     = time.time()
    history = _buy_history[mint]
    history.append((now, bc_pct))

    # Trim to window
    cutoff             = now - TRADE_WINDOW_SEC
    _buy_history[mint] = [(t, bc) for t, bc in history if t >= cutoff]
    history            = _buy_history[mint]

    if len(history) < CONSECUTIVE_BUYS:
        return

    # BC must be rising over the window — not too slow, not too fast (rug pump)
    bc_rise = history[-1][1] - history[0][1]
    if bc_rise < config.MIN_BC_RISE_PCT or bc_rise > config.MAX_BC_RISE_PCT:
        return

    # Mark as seen immediately (prevents duplicate tasks for this mint)
    seen_mints.add(mint)
    _signal_times[mint] = now

    # Fetch coin data and enqueue in a background task — never blocks the WS loop
    symbol_hint = event.get("symbol") or ""
    t = asyncio.create_task(
        _enqueue_signal(mint, bc_pct, bc_rise, symbol_hint, session, queue, seen_mints)
    )
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


async def _run_ws(queue: asyncio.Queue, seen_mints: set) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(PUMPPORTAL_WS, heartbeat=20) as ws:
            print("[monitor] WebSocket connected to PumpPortal", flush=True)

            # Catch every new token launch
            await ws.send_json({"method": "subscribeNewToken"})

            # Background task: discover existing in-zone coins every 15s
            poller = asyncio.create_task(_zone_poller(ws, session))

            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            event = json.loads(msg.data)
                        except json.JSONDecodeError:
                            continue

                        # Expire cooldowns
                        now     = time.time()
                        expired = [m for m, t in list(_signal_times.items()) if now - t > SIGNAL_COOLDOWN_SEC]
                        for m in expired:
                            seen_mints.discard(m)
                            del _signal_times[m]

                        _handle_event(event, ws, session, queue, seen_mints)

                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                        print(f"[monitor] WS disconnected: {msg.data}", flush=True)
                        break
            finally:
                poller.cancel()


async def run(queue: asyncio.Queue, seen_mints: set) -> None:
    """Entry point called by bot.py. Reconnects automatically on any failure."""
    while True:
        try:
            await _run_ws(queue, seen_mints)
        except Exception as exc:
            import traceback
            print(f"[monitor] WS error: {exc}", flush=True)
            traceback.print_exc()
        print("[monitor] Reconnecting in 5s…", flush=True)
        await asyncio.sleep(5)
