import base64
import time
from typing import Optional

import aiohttp
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

import config

JUPITER_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
JUPITER_SWAP  = "https://lite-api.jup.ag/swap/v1/swap"
LAMPORTS      = 1_000_000_000


# ── Quote / Swap helpers ──────────────────────────────────────────────────────

async def _quote(
    session: aiohttp.ClientSession,
    input_mint: str,
    output_mint: str,
    amount: int,
) -> Optional[dict]:
    params = {
        "inputMint":   input_mint,
        "outputMint":  output_mint,
        "amount":      str(amount),
        "slippageBps": str(config.SLIPPAGE_BPS),
    }
    try:
        async with session.get(
            JUPITER_QUOTE,
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except Exception as e:
        print(f"[trader] Quote error: {e}")
        return None


async def _swap(
    session: aiohttp.ClientSession,
    rpc: AsyncClient,
    keypair: Keypair,
    quote: dict,
) -> Optional[str]:
    body = {
        "quoteResponse":              quote,
        "userPublicKey":              str(keypair.pubkey()),
        "wrapAndUnwrapSol":           True,
        "prioritizationFeeLamports":  config.PRIORITY_FEE,
    }
    try:
        async with session.post(
            JUPITER_SWAP,
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"[trader] Swap API {resp.status}: {text[:200]}")
                return None
            data = await resp.json()
    except Exception as e:
        print(f"[trader] Swap request error: {e}")
        return None

    tx_bytes   = base64.b64decode(data["swapTransaction"])
    tx         = VersionedTransaction.from_bytes(tx_bytes)
    signed_tx  = VersionedTransaction(tx.message, [keypair])

    try:
        result = await rpc.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed"),
        )
        return str(result.value)
    except Exception as e:
        print(f"[trader] Send tx error: {e}")
        return None


# ── Trade state ───────────────────────────────────────────────────────────────

class Trade:
    def __init__(self, mint: str, symbol: str, token_amount: int, sol_spent: float):
        self.mint         = mint
        self.symbol       = symbol
        self.token_amount = token_amount
        self.sol_spent    = sol_spent
        self._entry_time  = time.time()

    def elapsed(self) -> float:
        return time.time() - self._entry_time

    def pnl_pct(self, current_sol_value: float) -> float:
        """P&L after gas. gas is split: half charged on buy, half on sell."""
        net_out = current_sol_value - config.GAS_COST_ROUNDTRIP_SOL
        cost_in = self.sol_spent + config.GAS_COST_ROUNDTRIP_SOL
        return (net_out - cost_in) / cost_in * 100


# ── Public buy / sell / price ─────────────────────────────────────────────────

async def buy(
    session: aiohttp.ClientSession,
    rpc: AsyncClient,
    keypair: Keypair,
    mint: str,
    symbol: str,
    amount_sol: float,
) -> Optional[Trade]:
    lamports = int(amount_sol * LAMPORTS)
    quote    = await _quote(session, config.SOL_MINT, mint, lamports)
    if not quote:
        print(f"[trader] No buy quote for {symbol}")
        return None

    token_out = int(quote.get("outAmount", 0))
    print(f"[trader] Buying {symbol}: {amount_sol:.4f} SOL → {token_out:,} tokens")

    sig = await _swap(session, rpc, keypair, quote)
    if not sig:
        print(f"[trader] Buy failed for {symbol}")
        return None

    print(f"[trader] Bought {symbol}: {sig}")
    return Trade(mint, symbol, token_out, amount_sol)


async def current_value_sol(
    session: aiohttp.ClientSession,
    trade: Trade,
) -> Optional[float]:
    """Get a sell quote to find current SOL value of our position."""
    quote = await _quote(session, trade.mint, config.SOL_MINT, trade.token_amount)
    if not quote:
        return None
    return int(quote.get("outAmount", 0)) / LAMPORTS


async def sell(
    session: aiohttp.ClientSession,
    rpc: AsyncClient,
    keypair: Keypair,
    trade: Trade,
    reason: str,
) -> float:
    """Execute sell. Returns SOL received (0.0 on failure)."""
    quote = await _quote(session, trade.mint, config.SOL_MINT, trade.token_amount)
    if not quote:
        print(f"[trader] No sell quote for {trade.symbol} — retrying next cycle")
        return 0.0

    sol_out  = int(quote.get("outAmount", 0)) / LAMPORTS
    pnl      = trade.pnl_pct(sol_out)
    net      = sol_out - trade.sol_spent - config.GAS_COST_ROUNDTRIP_SOL
    print(f"[trader] Selling {trade.symbol} [{reason}] | {sol_out:.4f} SOL | P&L {pnl:+.1f}% (net after gas: {net:+.4f} SOL)")

    sig = await _swap(session, rpc, keypair, quote)
    if sig:
        print(f"[trader] Sold {trade.symbol}: {sig}")
        return sol_out
    else:
        print(f"[trader] Sell tx failed for {trade.symbol}")
        return 0.0


async def park_profit_in_usdc(
    session: aiohttp.ClientSession,
    rpc: AsyncClient,
    keypair: Keypair,
    profit_sol: float,
) -> None:
    """Swap profit SOL → USDC so it's safe and never risked again."""
    if profit_sol <= 0:
        return
    lamports = int(profit_sol * LAMPORTS)
    quote    = await _quote(session, config.SOL_MINT, config.USDC_MINT, lamports)
    if not quote:
        print(f"[trader] Could not get SOL→USDC quote for profit parking")
        return
    usdc_out = int(quote.get("outAmount", 0)) / 1_000_000  # USDC has 6 decimals
    print(f"[trader] Parking profit: {profit_sol:.4f} SOL → {usdc_out:.2f} USDC")
    sig = await _swap(session, rpc, keypair, quote)
    if sig:
        print(f"[trader] Profit parked in USDC: {sig}")
    else:
        print(f"[trader] USDC parking failed — profit stays as SOL")
