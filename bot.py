"""
Solana pump.fun sniper / scalper bot.

Usage:
  python bot.py            # live trading
  python bot.py --dry-run  # monitor only, no trades executed
"""

import argparse
import asyncio
import sys

import aiohttp
from solana.rpc.async_api import AsyncClient

import config
import monitor
import trader
import wallet


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
        if dry_run:
            print(f"[bot] [DRY RUN] Would buy {config.BUY_AMOUNT_SOL} SOL of {symbol} @ {pct:.1f}% bonding")
            return

        trade = await trader.buy(session, rpc, keypair, mint, symbol)
        if trade is None:
            return

        # Scalp loop
        while True:
            await asyncio.sleep(config.POLL_INTERVAL_SEC)

            value = await trader.current_value_sol(session, trade)
            if value is None:
                continue

            pnl     = trade.pnl_pct(value)
            elapsed = trade.elapsed()
            print(f"[bot] {symbol} | P&L {pnl:+.1f}% | held {elapsed:.0f}s")

            if pnl >= config.PROFIT_TARGET_PCT:
                await trader.sell(session, rpc, keypair, trade, "TAKE PROFIT")
                break
            elif pnl <= -config.STOP_LOSS_PCT:
                await trader.sell(session, rpc, keypair, trade, "STOP LOSS")
                break
            elif elapsed >= config.MAX_HOLD_SECONDS:
                await trader.sell(session, rpc, keypair, trade, "TIME LIMIT")
                break
    finally:
        active.discard(mint)


async def main(dry_run: bool) -> None:
    kp = wallet.load_or_create(config.KEYPAIR_PATH)

    if not dry_run:
        rpc          = AsyncClient(config.RPC_URL)
        balance_resp = await rpc.get_balance(kp.pubkey())
        balance_sol  = balance_resp.value / 1_000_000_000
        print(f"[bot] Balance: {balance_sol:.4f} SOL")
        if balance_sol < config.BUY_AMOUNT_SOL:
            print(f"[bot] !! Need at least {config.BUY_AMOUNT_SOL} SOL — fund {kp.pubkey()} then restart")
            sys.exit(1)
    else:
        rpc = None
        print("[bot] DRY RUN — monitoring only, no trades will execute")

    print(
        f"[bot] Watching pump.fun for tokens at "
        f"{config.BOND_THRESHOLD_MIN}–{config.BOND_THRESHOLD_MAX}% bonding curve "
        f"(poll every {config.POLL_INTERVAL_SEC}s) …"
    )

    queue        = asyncio.Queue()
    seen_mints:  set = set()
    active_mints: set = set()

    monitor_task = asyncio.create_task(monitor.run(queue, seen_mints))

    async with aiohttp.ClientSession() as session:
        try:
            while True:
                coin = await queue.get()
                mint = coin.get("mint")
                if mint and mint not in active_mints:
                    active_mints.add(mint)
                    asyncio.create_task(
                        _handle(session, rpc, kp, coin, dry_run, active_mints)
                    )
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[bot] Shutting down …")
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
