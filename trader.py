import asyncio
import time
from typing import Optional

import aiohttp
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

import config

PUMPPORTAL  = "https://pumpportal.fun/api/trade-local"
JUPITER_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
JUPITER_SWAP  = "https://lite-api.jup.ag/swap/v1/swap"
LAMPORTS      = 1_000_000_000


# ── PumpPortal (primary) ───────────────────────────────────────────────────────

async def _pumpportal_tx(
    session:  aiohttp.ClientSession,
    rpc:      AsyncClient,
    keypair:  Keypair,
    action:   str,
    mint:     str,
    amount,
    denom_sol: bool,
) -> Optional[str]:
    data = {
        "publicKey":        str(keypair.pubkey()),
        "action":           action,
        "mint":             mint,
        "denominatedInSol": "true" if denom_sol else "false",
        "amount":           amount,
        "slippage":         15,
        "priorityFee":      0.001,
        "pool":             "pump",
    }
    try:
        async with session.post(
            PUMPPORTAL,
            data=data,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"[trader] PumpPortal {resp.status}: {text[:200]}", flush=True)
                return None
            tx_bytes = await resp.read()

        tx        = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [keypair])
        result    = await rpc.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
        return str(result.value)
    except Exception as e:
        print(f"[trader] PumpPortal error: {e}", flush=True)
        return None


# ── Jupiter (fallback for graduated tokens) ───────────────────────────────────

async def _jupiter_quote(session, input_mint, output_mint, amount):
    params = {
        "inputMint":   input_mint,
        "outputMint":  output_mint,
        "amount":      str(amount),
        "slippageBps": str(config.SLIPPAGE_BPS),
    }
    try:
        async with session.get(
            JUPITER_QUOTE, params=params, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            return await resp.json() if resp.status == 200 else None
    except Exception:
        return None


async def _jupiter_swap(session, rpc, keypair, quote):
    import base64
    body = {
        "quoteResponse":             quote,
        "userPublicKey":             str(keypair.pubkey()),
        "wrapAndUnwrapSol":          True,
        "prioritizationFeeLamports": config.PRIORITY_FEE,
    }
    try:
        async with session.post(
            JUPITER_SWAP, json=body, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        tx_bytes  = base64.b64decode(data["swapTransaction"])
        tx        = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [keypair])
        result    = await rpc.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
        return str(result.value)
    except Exception as e:
        print(f"[trader] Jupiter error: {e}", flush=True)
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
        """Price-based P&L. Gas is a fixed accepted cost, not included here."""
        return (current_sol_value - self.sol_spent) / self.sol_spent * 100


# ── Pricing ───────────────────────────────────────────────────────────────────

async def _pumpfun_value_sol(session: aiohttp.ClientSession, trade: Trade) -> Optional[float]:
    url = f"https://frontend-api-v3.pump.fun/coins/{trade.mint}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                return None
            coin = await resp.json(content_type=None)
        vsol = coin.get("virtual_sol_reserves") or 0
        vtok = coin.get("virtual_token_reserves") or 0
        if not vsol or not vtok:
            return None
        return (vsol / vtok) * trade.token_amount / LAMPORTS
    except Exception:
        return None


async def current_value_sol(session: aiohttp.ClientSession, trade: Trade) -> Optional[float]:
    """pump.fun curve first (always works pre-graduation), Jupiter for graduated tokens."""
    value = await _pumpfun_value_sol(session, trade)
    if value is not None:
        return value
    quote = await _jupiter_quote(session, trade.mint, config.SOL_MINT, trade.token_amount)
    if quote:
        return int(quote.get("outAmount", 0)) / LAMPORTS
    return None


# ── Buy / Sell ────────────────────────────────────────────────────────────────

async def buy(
    session:    aiohttp.ClientSession,
    rpc:        AsyncClient,
    keypair:    Keypair,
    mint:       str,
    symbol:     str,
    amount_sol: float,
) -> Optional[Trade]:
    print(f"[trader] Buying {symbol} via PumpPortal: {amount_sol:.4f} SOL", flush=True)
    sig = await _pumpportal_tx(session, rpc, keypair, "buy", mint, amount_sol, denom_sol=True)

    if not sig:
        print(f"[trader] PumpPortal buy failed, trying Jupiter…", flush=True)
        lamports = int(amount_sol * LAMPORTS)
        quote    = await _jupiter_quote(session, config.SOL_MINT, mint, lamports)
        if quote:
            sig = await _jupiter_swap(session, rpc, keypair, quote)
            token_out = int(quote.get("outAmount", 0))
        else:
            token_out = 0
    else:
        # Estimate token amount from reserves for tracking
        try:
            async with session.get(
                f"https://frontend-api-v3.pump.fun/coins/{mint}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                coin = await resp.json(content_type=None) if resp.status == 200 else {}
            vsol = coin.get("virtual_sol_reserves") or 1
            vtok = coin.get("virtual_token_reserves") or 1
            # Constant product: tokens_out = vtok * amount / (vsol + amount)
            lamports_in = int(amount_sol * LAMPORTS)
            token_out = int(vtok * lamports_in / (vsol + lamports_in))
        except Exception:
            token_out = 0

    if not sig:
        print(f"[trader] Buy failed for {symbol}", flush=True)
        return None

    print(f"[trader] Bought {symbol}: sig={sig} tokens≈{token_out:,}", flush=True)
    return Trade(mint, symbol, token_out, amount_sol)


async def sell(
    session: aiohttp.ClientSession,
    rpc:     AsyncClient,
    keypair: Keypair,
    trade:   Trade,
    reason:  str,
) -> float:
    """Sell with up to 3 attempts. Returns SOL received."""
    value = await current_value_sol(session, trade)
    pnl   = trade.pnl_pct(value) if value else 0
    print(f"[trader] Selling {trade.symbol} [{reason}] | est {value:.4f} SOL | P&L {pnl:+.1f}%", flush=True)

    for attempt in range(1, 4):
        sig = await _pumpportal_tx(
            session, rpc, keypair, "sell", trade.mint, "100%", denom_sol=False
        )
        if sig:
            print(f"[trader] Sold {trade.symbol}: {sig}", flush=True)
            return value or 0.0

        print(f"[trader] PumpPortal sell failed (attempt {attempt}), trying Jupiter…", flush=True)
        quote = await _jupiter_quote(session, trade.mint, config.SOL_MINT, trade.token_amount)
        if quote:
            sig = await _jupiter_swap(session, rpc, keypair, quote)
            if sig:
                sol_out = int(quote.get("outAmount", 0)) / LAMPORTS
                print(f"[trader] Sold {trade.symbol} via Jupiter: {sig}", flush=True)
                return sol_out

        await asyncio.sleep(2)

    print(f"[trader] GAVE UP selling {trade.symbol} after 3 attempts", flush=True)
    return 0.0
