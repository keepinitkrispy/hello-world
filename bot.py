import argparse
import asyncio
import os
import sys
import time

import aiohttp
from solana.rpc.async_api import AsyncClient

import config
import filters
import monitor
import positions
import profits
import trader
import wallet


def _validate_deploy_config(dry_run: bool) -> None:
    """Fail fast on missing production credentials/config."""
    if dry_run:
        return

    has_env_key = bool(os.environ.get("SOLANA_PRIVATE_KEY"))
    has_file_key = os.path.exists(config.KEYPAIR_PATH)
    if not has_env_key and not has_file_key:
        print(
            "[bot] Missing wallet credentials. Set SOLANA_PRIVATE_KEY in Railway "
            "or provide keypair.json before deploying.",
            flush=True,
        )
        sys.exit(1)


def _task_error_handler(task: asyncio.Task) -> None:
    try:
        exc = task.exception()
        if exc:
            import traceback
            print(f"[bot] TASK CRASHED: {task.get_name()}: {exc}", flush=True)
            traceback.print_exception(type(exc), exc, exc.__traceback__)
    except asyncio.CancelledError:
        pass


async def _monitor_existing(session, rpc, keypair, trade, active):
    """Sell a position recovered from a previous run as quickly as possible."""
    symbol = trade.symbol
    _sold = False
    try:
        print(f"[bot] Recovered position: {symbol} — selling immediately", flush=True)
        for attempt in range(1, 4):
            sol_back = await trader.sell(session, rpc, keypair, trade, "RESTART RECOVERY")
            if sol_back > 0:
                _sold = True
                break
            await asyncio.sleep(3)
        if not _sold:
            print(f"[bot] Recovery sell failed for {symbol} — keeping in positions.json", flush=True)
    finally:
        if _sold:
            positions.remove(trade.mint)
        active.discard(trade.mint)


async def _handle(session, rpc, keypair, coin, dry_run, active):
    mint   = coin.get("mint")
    symbol = coin.get("symbol", "???")
    trade          = None
    _position_sold = False
    _stop_loss_exit = False

    try:
        ok, reason = await filters.passes_all(session, rpc, coin)
        if not ok:
            return

        if dry_run:
            print(f"[bot] [DRY RUN] PASS {symbol}", flush=True)
            return

        bal_resp    = await rpc.get_balance(keypair.pubkey())
        balance_sol = bal_resp.value / 1_000_000_000
        parked      = profits.load()
        spendable   = max(0.0, balance_sol - config.GAS_RESERVE_SOL - parked)
        buy_amount  = round(min(spendable * config.TRADE_PCT, config.MAX_TRADE_SOL), 6)

        if buy_amount < config.MIN_TRADE_SOL:
            print(f"[bot] Skipping {symbol} — only {spendable:.4f} SOL spendable", flush=True)
            return

        print(
            f"[bot] Buying {symbol} | bal={balance_sol:.4f} spendable={spendable:.4f} bet={buy_amount:.4f} SOL",
            flush=True,
        )

        trade = await trader.buy(session, rpc, keypair, mint, symbol, buy_amount)
        if trade is None:
            return

        positions.record(trade)

        peak_pnl      = 0.0
        peak_pnl_time = time.time()
        none_since    = None

        while True:
            await asyncio.sleep(config.POSITION_POLL_SEC)
            elapsed = trade.elapsed()

            if elapsed >= config.MAX_HOLD_SECONDS:
                sol_back = await trader.sell(session, rpc, keypair, trade, "TIME LIMIT")
                _position_sold = sol_back > 0
                break

            value = await trader.current_value_sol(session, trade)
            if value is None:
                if none_since is None:
                    none_since = time.time()
                elif time.time() - none_since >= 10:
                    sol_back = await trader.sell(session, rpc, keypair, trade, "NO PRICE 10s")
                    _position_sold = sol_back > 0
                    break
                continue

            none_since = None
            pnl = trade.pnl_pct(value)

            if pnl > peak_pnl:
                peak_pnl      = pnl
                peak_pnl_time = time.time()

            print(
                f"[bot] {symbol} P&L={pnl:+.1f}% peak={peak_pnl:+.1f}% held={elapsed:.0f}s",
                flush=True,
            )

            # House money: sell 50% at +10%, let the rest ride free
            if pnl >= 10.0 and not trade._half_sold:
                sol_back = await trader.sell_partial(
                    session, rpc, keypair, trade, 0.5, "HOUSE MONEY +10%"
                )
                if sol_back > 0:
                    trade._half_sold = True
                    if config.PARK_PROFITS and sol_back > trade.sol_spent * 0.5:
                        gain  = sol_back - trade.sol_spent * 0.5
                        total = profits.add(gain)
                        print(f"[bot] Parked +{gain:.4f} SOL (running total: {total:.4f} SOL)", flush=True)
                    # Recost basis to the remaining 50% so PnL/stops are correct
                    trade.sol_spent *= 0.5
                    peak_pnl = pnl
                # Continue managing the remaining 50%
                continue

            # Dynamic stop: full stop for first 15s, tightens to 3% after
            dyn_stop = config.STOP_LOSS_PCT if elapsed < 15 else 3.0

            if pnl >= config.PROFIT_TARGET_PCT:
                sol_back = await trader.sell(session, rpc, keypair, trade, "TAKE PROFIT")
                _position_sold = sol_back > 0
                if config.PARK_PROFITS and sol_back > trade.sol_spent:
                    gain  = sol_back - trade.sol_spent
                    total = profits.add(gain)
                    print(f"[bot] Parked +{gain:.4f} SOL (running total: {total:.4f} SOL)", flush=True)
                break

            elif peak_pnl >= config.TRAIL_ACTIVATE_PCT and pnl <= peak_pnl - config.TRAIL_DRAWDOWN_PCT:
                sol_back = await trader.sell(
                    session, rpc, keypair, trade, f"TRAILING STOP (peak {peak_pnl:+.1f}%)"
                )
                _position_sold = sol_back > 0
                if config.PARK_PROFITS and sol_back > trade.sol_spent:
                    gain  = sol_back - trade.sol_spent
                    total = profits.add(gain)
                    print(f"[bot] Parked +{gain:.4f} SOL (running total: {total:.4f} SOL)", flush=True)
                break

            elif (
                elapsed >= 15
                and time.time() - peak_pnl_time > config.MOMENTUM_STALL_PEAK_AGE_SEC
                and peak_pnl < config.PROFIT_TARGET_PCT
            ):
                # No new high in MOMENTUM_STALL_PEAK_AGE_SEC seconds — get out
                sol_back = await trader.sell(
                    session, rpc, keypair, trade,
                    f"MOMENTUM STALL (peak {peak_pnl:+.1f}% {config.MOMENTUM_STALL_PEAK_AGE_SEC}s ago)",
                )
                _position_sold = sol_back > 0
                break

            elif pnl <= -dyn_stop:
                _stop_loss_exit = True
                sol_back = await trader.sell(
                    session, rpc, keypair, trade, f"STOP LOSS ({dyn_stop:.0f}%)"
                )
                _position_sold = sol_back > 0
                break

    finally:
        if _position_sold:
            positions.remove(mint)
        elif trade is not None:
            print(
                f"[bot] Sell failed for {symbol} — position kept in positions.json for recovery",
                flush=True,
            )
        active.discard(mint)
        if _stop_loss_exit:
            monitor.block_mint(mint)


async def main(dry_run: bool) -> None:
    _validate_deploy_config(dry_run)
    kp = wallet.load_or_create(config.KEYPAIR_PATH)

    if not dry_run:
        rpc          = AsyncClient(config.RPC_URL)
        balance_resp = await rpc.get_balance(kp.pubkey())
        balance_sol  = balance_resp.value / 1_000_000_000
        parked_total = profits.load()
        spendable    = max(0.0, balance_sol - config.GAS_RESERVE_SOL - parked_total)
        print(
            f"[bot] Balance={balance_sol:.4f} SOL parked={parked_total:.4f} SOL spendable={spendable:.4f} SOL",
            flush=True,
        )
        if spendable < config.MIN_TRADE_SOL:
            print(f"[bot] !! Too low — fund {kp.pubkey()} then restart", flush=True)
            sys.exit(1)
    else:
        rpc = None
        print("[bot] DRY RUN", flush=True)

    print(
        f"[bot] READY | zone={config.MONITOR_BC_MIN}-{config.MONITOR_BC_MAX}% "
        f"signal={config.MONITOR_CONSECUTIVE_BUYS} buys/{config.MOMENTUM_WINDOW_SEC}s "
        f"rise={config.MIN_BC_RISE_PCT}-{config.MAX_BC_RISE_PCT}% "
        f"filters(age>={config.MIN_AGE_SECONDS}s replies>={config.MIN_REPLY_COUNT}) "
        f"stop={config.STOP_LOSS_PCT}%",
        flush=True,
    )

    queue         = asyncio.Queue()
    seen_mints:   set = set()
    active_mints: set = set()

    mt = asyncio.create_task(monitor.run(queue, seen_mints), name="monitor")
    mt.add_done_callback(_task_error_handler)

    async with aiohttp.ClientSession() as session:
        orphans = positions.load_open()
        if orphans:
            print(f"[bot] Recovering {len(orphans)} position(s) from previous run", flush=True)
        for p in orphans:
            t = trader.Trade(p["mint"], p["symbol"], p["token_amount"], p["sol_spent"])
            t._entry_time = p["entry_time"]
            active_mints.add(p["mint"])
            seen_mints.add(p["mint"])
            task = asyncio.create_task(
                _monitor_existing(session, rpc, kp, t, active_mints),
                name=f"recover-{p['mint'][:8]}",
            )
            task.add_done_callback(_task_error_handler)

        try:
            while True:
                try:
                    coin = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    print("[bot] heartbeat — watching...", flush=True)
                    continue

                mint = coin.get("mint")
                if mint and mint not in active_mints:
                    active_mints.add(mint)
                    t = asyncio.create_task(
                        _handle(session, rpc, kp, coin, dry_run, active_mints),
                        name=f"handle-{mint[:8]}",
                    )
                    t.add_done_callback(_task_error_handler)

        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            mt.cancel()
            if rpc:
                await rpc.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.dry_run))
    except KeyboardInterrupt:
        pass
