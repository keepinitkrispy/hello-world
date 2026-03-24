"""
Solana pump.fun sniper / scalper bot.

Usage:
  python bot.py            # live trading
  python bot.py --dry-run  # monitor only, no trades executed
"""

import argparse
import asyncio
import sys
import time

import aiohttp
from solana.rpc.async_api import AsyncClient

import config
import filters
import monitor
import trader
import wallet


def _task_error_handler(task: asyncio.Task) -> None:
    """Log any exception from a fire-and-forget task so it isn't silently lost."""
    try:
        exc = task.exception()
        if exc:
            import traceback
            print(f"[bot] TASK CRASHED: {task.get_name()}: {exc}", flush=True)
            traceback.print_exception(type(exc), exc, exc.__traceback__)
    except asyncio.CancelledError:
        pass


async def _handle(
    session: aiohttp.ClientSession,
    rpc: AsyncClient,
    keypair,
    coin: dict,
    dry_run: bool,
    active: set,
) -> None:
    mint   = coin.get("mint")
    symbol = coin.get("symbol", "???")
    pct    = coin.get("_bonding_pct", 0)

    try:
        ok, reason = await filters.passes_all(session, rpc, coin)
        if not ok:
            return

        if dry_run:
            print(f"[bot] [DRY RUN] PASS {symbol} @ {pct:.1f}% bonding")
            return

        bal_resp    = await rpc.get_balance(keypair.pubkey())
        balance_sol = bal_resp.value / 1_000_000_000
        spendable   = max(0.0, balance_sol - config.GAS_RESERVE_SOL)
        buy_amount  = round(spendable * config.TRADE_PCT, 6)

        if buy_amount < config.MIN_TRADE_SOL:
            print(f"[bot] Skipping {symbol} — spendable {spendable:.4f} SOL too low to trade")
            return

        print(f"[bot] Balance {balance_sol:.4f} SOL | spendable {spendable:.4f} | betting {buy_amount:.4f} SOL ({config.TRADE_PCT*100:.0f}%)")
        trade = await trader.buy(session, rpc, keypair, mint, symbol, buy_amount)
        if trade is None:
            return

        peak_pnl = 0.0
        while True:
            await asyncio.sleep(config.POLL_INTERVAL_SEC)

            value = await trader.current_value_sol(session, trade)
            if value is None:
                continue

            pnl      = trade.pnl_pct(value)
            elapsed  = trade.elapsed()
            peak_pnl = max(peak_pnl, pnl)
            print(f"[bot] {symbol} | P&L {pnl:+.1f}% | peak {peak_pnl:+.1f}% | held {elapsed:.0f}s")

            if pnl >= config.PROFIT_TARGET_PCT:
                sol_back = await trader.sell(session, rpc, keypair, trade, "TAKE PROFIT")
                if config.PARK_PROFITS and sol_back > trade.sol_spent:
                    profit = sol_back - trade.sol_spent
                    if config.PARK_AS_USDC:
                        await trader.park_profit_in_usdc(session, rpc, keypair, profit)
                    else:
                        print(f"[bot] Profit {profit:+.4f} SOL parked as SOL")
                break
            elif peak_pnl >= config.TRAIL_ACTIVATE_PCT and pnl <= peak_pnl - config.TRAIL_DRAWDOWN_PCT:
                sol_back = await trader.sell(session, rpc, keypair, trade, f"TRAILING STOP (peak {peak_pnl:+.1f}%)")
                if config.PARK_PROFITS and sol_back > trade.sol_spent:
                    profit = sol_back - trade.sol_spent
                    if config.PARK_AS_USDC:
                        await trader.park_profit_in_usdc(session, rpc, keypair, profit)
                    else:
                        print(f"[bot] Profit {profit:+.4f} SOL parked as SOL")
                break
            elif pnl <= -config.STOP_LOSS_PCT:
                await trader.sell(session, rpc, keypair, trade, "STOP LOSS")
                break
            elif elapsed >= config.MAX_HOLD_SECONDS:
                sol_back = await trader.sell(session, rpc, keypair, trade, "TIME LIMIT")
                if config.PARK_PROFITS and sol_back > trade.sol_spent:
                    profit = sol_back - trade.sol_spent
                    if config.PARK_AS_USDC:
                        await trader.park_profit_in_usdc(session, rpc, keypair, profit)
                    else:
                        print(f"[bot] Profit {profit:+.4f} SOL parked as SOL")
                break
    finally:
        active.discard(mint)


async def main(dry_run: bool) -> None:
    kp = wallet.load_or_create(config.KEYPAIR_PATH)

    if not dry_run:
        rpc          = AsyncClient(config.RPC_URL)
        balance_resp = await rpc.get_balance(kp.pubkey())
        balance_sol  = balance_resp.value / 1_000_000_000
        spendable    = max(0.0, balance_sol - config.GAS_RESERVE_SOL)
        print(f"[bot] Balance: {balance_sol:.4f} SOL | gas reserve: {config.GAS_RESERVE_SOL} SOL | spendable: {spendable:.4f} SOL", flush=True)
        if spendable < config.MIN_TRADE_SOL:
            print(f"[bot] !! Spendable balance too low — fund {kp.pubkey()} then restart", flush=True)
            sys.exit(1)
    else:
        rpc = None
        print("[bot] DRY RUN — monitoring only, no trades will execute", flush=True)

    print("[bot] STARTING — window={}s stop={}% trail=+{}%/{}% max_hold={}s".format(
        config.MOMENTUM_WINDOW_SEC, config.STOP_LOSS_PCT,
        config.TRAIL_ACTIVATE_PCT, config.TRAIL_DRAWDOWN_PCT,
        config.MAX_HOLD_SECONDS,
    ), flush=True)

    queue         = asyncio.Queue()
    seen_mints:   set = set()
    active_mints: set = set()

    monitor_task = asyncio.create_task(monitor.run(queue, seen_mints), name="monitor")
    monitor_task.add_done_callback(_task_error_handler)

    last_heartbeat = time.time()

    async with aiohttp.ClientSession() as session:
        try:
            while True:
                # Heartbeat every 30s so we know the bot is alive even when idle
                try:
                    coin = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    print(f"[bot] heartbeat — waiting for momentum signals...", flush=True)
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
            print("\n[bot] Shutting down …", flush=True)
        finally:
            monitor_task.cancel()
            if rpc:
                await rpc.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pump.fun sniper/scalper")
    parser.add_argument("--dry-run", action="store_true", help="Monitor only — no trades")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.dry_run))
    except KeyboardInterrupt:
        pass
