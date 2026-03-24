import base64
import time
from typing import Optional

import aiohttp
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

import config

JUPITER_QUOTE = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP  = "https://quote-api.jup.ag/v6/swap"
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
        "quoteResponse":    quote,
        "userPublicKey":    str(keypair.pubkey()),
        "wrapAndUnwrapSol": True,
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
        return (current_sol_value - self.sol_spent) / self.sol_spent * 100


# ── Public buy / sell / price ─────────────────────────────────────────────────

async def buy(
    session: aiohttp.ClientSession,
    rpc: AsyncClient,
    keypair: Keypair,
    mint: str,
    symbol: str,
) -> Optional[Trade]:
    lamports = int(config.BUY_AMOUNT_SOL * LAMPORTS)
    quote    = await _quote(session, config.SOL_MINT, mint, lamports)
    if not quote:
        print(f"[trader] No buy quote for {symbol}")
        return None

    token_out = int(quote.get("outAmount", 0))
    print(f"[trader] Buying {symbol}: {config.BUY_AMOUNT_SOL} SOL → {token_out:,} tokens")

    sig = await _swap(session, rpc, keypair, quote)
    if not sig:
        print(f"[trader] Buy failed for {symbol}")
        return None

    print(f"[trader] Bought {symbol}: {sig}")
    return Trade(mint, symbol, token_out, config.BUY_AMOUNT_SOL)


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
) -> None:
    quote = await _quote(session, trade.mint, config.SOL_MINT, trade.token_amount)
    if not quote:
        print(f"[trader] No sell quote for {trade.symbol} — retrying next cycle")
        return

    sol_out = int(quote.get("outAmount", 0)) / LAMPORTS
    pnl     = trade.pnl_pct(sol_out)
    net     = sol_out - trade.sol_spent
    print(f"[trader] Selling {trade.symbol} [{reason}] | {sol_out:.4f} SOL | P&L {pnl:+.1f}% ({net:+.4f} SOL)")

    sig = await _swap(session, rpc, keypair, quote)
    if sig:
        print(f"[trader] Sold {trade.symbol}: {sig}")
    else:
        print(f"[trader] Sell tx failed for {trade.symbol}")
