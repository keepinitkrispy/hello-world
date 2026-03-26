import asyncio
import time
from typing import Optional

import aiohttp
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts, TokenAccountOpts

import config

PUMPPORTAL    = "https://pumpportal.fun/api/trade-local"
JUPITER_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
JUPITER_SWAP  = "https://lite-api.jup.ag/swap/v1/swap"
LAMPORTS      = 1_000_000_000


# ── PumpPortal (primary) ───────────────────────────────────────────────────────

async def _pumpportal_tx(
    session:   aiohttp.ClientSession,
    rpc:       AsyncClient,
    keypair:   Keypair,
    action:    str,
    mint:      str,
    amount,
    denom_sol: bool,
    slippage:  int = 15,
) -> Optional[str]:
    data = {
        "publicKey":        str(keypair.pubkey()),
        "action":           action,
        "mint":             mint,
        "denominatedInSol": "true" if denom_sol else "false",
        "amount":           amount,
        "slippage":         slippage,
        "priorityFee":      config.PRIORITY_FEE_LAMPORTS / LAMPORTS,  # PumpPortal takes SOL float
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

async def _jupiter_quote(session, input_mint, output_mint, amount, slippage_bps: int = None):
    params = {
        "inputMint":   input_mint,
        "outputMint":  output_mint,
        "amount":      str(amount),
        "slippageBps": str(slippage_bps if slippage_bps is not None else config.SLIPPAGE_BPS),
    }
    try:
        async with session.get(
            JUPITER_QUOTE, params=params, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            return await resp.json() if resp.status == 200 else None
    except Exception:
        return None


async def _jupiter_swap(session, rpc, keypair, quote) -> Optional[float]:
    """Execute Jupiter swap. Returns SOL received (balance delta) on success, None on failure."""
    import base64
    body = {
        "quoteResponse":             quote,
        "userPublicKey":             str(keypair.pubkey()),
        "wrapAndUnwrapSol":          True,
        "prioritizationFeeLamports": config.PRIORITY_FEE_LAMPORTS,
    }
    try:
        async with session.post(
            JUPITER_SWAP, json=body, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                err = await resp.text()
                print(f"[trader] Jupiter swap {resp.status}: {err[:200]}", flush=True)
                return None
            data = await resp.json()
        tx_bytes  = base64.b64decode(data["swapTransaction"])
        tx        = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [keypair])
        bal_before = await _get_sol_balance(rpc, keypair)
        result    = await rpc.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
        print(f"[trader] Jupiter tx submitted: {result.value}", flush=True)
        await asyncio.sleep(3)
        bal_after = await _get_sol_balance(rpc, keypair)
        sol_received = bal_after - bal_before + config.GAS_COST_ROUNDTRIP_SOL / 2
        if sol_received > 0.001:
            return sol_received
        print(f"[trader] Jupiter tx landed but balance unchanged — tx likely failed", flush=True)
        return None
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
        self._half_sold   = False  # tracks whether the 50% house-money sell has fired

    def elapsed(self) -> float:
        return time.time() - self._entry_time

    def pnl_pct(self, current_sol_value: float) -> float:
        net_out = current_sol_value - config.GAS_COST_ROUNDTRIP_SOL
        cost_in = self.sol_spent + config.GAS_COST_ROUNDTRIP_SOL
        return (net_out - cost_in) / cost_in * 100


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


# ── Balance helper ────────────────────────────────────────────────────────────

async def _get_sol_balance(rpc: AsyncClient, keypair: Keypair) -> float:
    try:
        resp = await rpc.get_balance(keypair.pubkey())
        return resp.value / LAMPORTS
    except Exception:
        return 0.0


# ── Buy ────────────────────────────────────────────────────────────────────────

async def buy(
    session:    aiohttp.ClientSession,
    rpc:        AsyncClient,
    keypair:    Keypair,
    mint:       str,
    symbol:     str,
    amount_sol: float,
) -> Optional[Trade]:
    print(f"[trader] Buying {symbol} via PumpPortal: {amount_sol:.4f} SOL", flush=True)

    # Estimate token output from bonding curve before the buy (not applicable for graduated tokens)
    token_out = 0
    if not config.BONDED_ONLY:
        try:
            async with session.get(
                f"https://frontend-api-v3.pump.fun/coins/{mint}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    coin = await resp.json(content_type=None)
                    vsol = coin.get("virtual_sol_reserves") or 1
                    vtok = coin.get("virtual_token_reserves") or 1
                    amount_lamports = int(amount_sol * LAMPORTS)
                    token_out = int(vtok * amount_lamports / (vsol + amount_lamports))
        except Exception:
            pass

    sig = None
    if not config.BONDED_ONLY:
        sig = await _pumpportal_tx(session, rpc, keypair, "buy", mint, amount_sol, denom_sol=True)

    if not sig:
        if not config.BONDED_ONLY:
            print(f"[trader] PumpPortal buy failed, trying Jupiter…", flush=True)
        lamports = int(amount_sol * LAMPORTS)
        quote    = await _jupiter_quote(session, config.SOL_MINT, mint, lamports)
        if quote:
            sol_out = await _jupiter_swap(session, rpc, keypair, quote)
            if sol_out is not None:
                token_out = int(quote.get("outAmount", 0))
                sig = "jupiter"

    if not sig or (sig == "jupiter" and token_out == 0):
        print(f"[trader] Buy failed for {symbol}", flush=True)
        return None

    # Read actual token balance from chain so sells are complete (no dust)
    if sig != "jupiter":
        try:
            await asyncio.sleep(2)
            from solders.pubkey import Pubkey
            accts = await rpc.get_token_accounts_by_owner_json_parsed(
                keypair.pubkey(),
                TokenAccountOpts(mint=Pubkey.from_string(mint)),
            )
            if accts.value:
                actual = int(accts.value[0].account.data.parsed["info"]["tokenAmount"]["amount"])
                if actual > 0:
                    print(f"[trader] Bought {symbol}: {sig} | actual_tokens={actual} est={token_out}", flush=True)
                    return Trade(mint, symbol, actual, amount_sol)
        except Exception as e:
            print(f"[trader] Could not read actual token balance: {e}", flush=True)

    print(f"[trader] Bought {symbol}: {sig} | est_tokens={token_out}", flush=True)
    return Trade(mint, symbol, token_out, amount_sol)


# ── Token balance helper ───────────────────────────────────────────────────────

async def _token_balance(rpc: AsyncClient, keypair: Keypair, mint: str) -> int:
    """
    Read on-chain token balance in raw units.
    Returns 0 if account not found, -1 on RPC error.
    """
    from solders.pubkey import Pubkey
    try:
        accts = await rpc.get_token_accounts_by_owner_json_parsed(
            keypair.pubkey(),
            TokenAccountOpts(mint=Pubkey.from_string(mint)),
        )
        if not accts.value:
            return 0
        return int(accts.value[0].account.data.parsed["info"]["tokenAmount"]["amount"])
    except Exception as e:
        print(f"[trader] _token_balance error: {e}", flush=True)
        return -1


async def _poll_until_sold(
    rpc: AsyncClient, keypair: Keypair, mint: str, original: int, timeout: float = 12.0
) -> bool:
    """Poll token balance every 1.5s until <2% of original remains. Returns True if confirmed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        bal = await _token_balance(rpc, keypair, mint)
        if bal >= 0 and bal < original * 0.02:
            return True
        await asyncio.sleep(1.5)
    return False


# ── Jupiter sell-only submit (no SOL delta logic) ──────────────────────────────

async def _jupiter_submit(
    session: aiohttp.ClientSession,
    rpc:     AsyncClient,
    keypair: Keypair,
    quote,
) -> Optional[str]:
    """
    Build, sign, and submit a Jupiter swap transaction.
    Returns the transaction signature on success, None on failure.
    Does NOT wait for confirmation — caller confirms via _poll_until_sold.
    """
    import base64
    body = {
        "quoteResponse":             quote,
        "userPublicKey":             str(keypair.pubkey()),
        "wrapAndUnwrapSol":          True,
        "prioritizationFeeLamports": config.PRIORITY_FEE_LAMPORTS,
    }
    try:
        async with session.post(
            JUPITER_SWAP, json=body, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                err = await resp.text()
                print(f"[trader] Jupiter swap {resp.status}: {err[:200]}", flush=True)
                return None
            data = await resp.json()
        tx_bytes  = base64.b64decode(data["swapTransaction"])
        tx        = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [keypair])
        result    = await rpc.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=True, preflight_commitment="confirmed"),
        )
        print(f"[trader] Jupiter tx submitted: {result.value}", flush=True)
        return str(result.value)
    except Exception as e:
        print(f"[trader] Jupiter submit error: {e}", flush=True)
        return None


# ── Sell ───────────────────────────────────────────────────────────────────────

async def sell(
    session: aiohttp.ClientSession,
    rpc:     AsyncClient,
    keypair: Keypair,
    trade:   Trade,
    reason:  str,
) -> float:
    """
    Sell 100% of position. Returns SOL received on success, 0.0 on failure.

    PumpPortal primary — "100%" amount, no unit ambiguity, works on bonding curve.
    Jupiter fallback — for graduated tokens.
    Both confirmed by polling on-chain token balance, not SOL delta guesswork.
    Up to 3 attempts with exponential backoff (2s, 4s, 8s).
    """
    value = await current_value_sol(session, trade)
    pnl   = trade.pnl_pct(value) if value else 0.0
    print(
        f"[trader] SELL {trade.symbol} [{reason}] | est={value:.4f} SOL P&L={pnl:+.1f}%",
        flush=True,
    )

    slippage_pct = config.SELL_SLIPPAGE_BPS // 100

    for attempt in range(1, 4):
        bal_before = await _get_sol_balance(rpc, keypair)

        # ── 1. PumpPortal — skip in BONDED_ONLY mode ──
        if not config.BONDED_ONLY:
            sig = await _pumpportal_tx(
                session, rpc, keypair, "sell", trade.mint,
                "100%", denom_sol=False, slippage=slippage_pct,
            )
            if sig:
                print(f"[trader] PumpPortal sig={sig} — confirming…", flush=True)
                if await _poll_until_sold(rpc, keypair, trade.mint, trade.token_amount):
                    bal_after    = await _get_sol_balance(rpc, keypair)
                    sol_received = max(0.0, bal_after - bal_before + config.GAS_COST_ROUNDTRIP_SOL / 2)
                    print(
                        f"[trader] Sold {trade.symbol} via PumpPortal (attempt {attempt}): {sol_received:.4f} SOL",
                        flush=True,
                    )
                    return sol_received
                print(f"[trader] PumpPortal sig={sig} but tokens unchanged (attempt {attempt})", flush=True)

        # ── 2. Jupiter — primary in BONDED_ONLY mode, fallback otherwise ──
        quote = await _jupiter_quote(
            session, trade.mint, config.SOL_MINT,
            trade.token_amount, slippage_bps=config.SELL_SLIPPAGE_BPS,
        )
        if quote:
            sig = await _jupiter_submit(session, rpc, keypair, quote)
            if sig:
                print(f"[trader] Jupiter sig={sig} — confirming…", flush=True)
                if await _poll_until_sold(rpc, keypair, trade.mint, trade.token_amount):
                    bal_after    = await _get_sol_balance(rpc, keypair)
                    sol_received = max(0.0, bal_after - bal_before + config.GAS_COST_ROUNDTRIP_SOL / 2)
                    print(
                        f"[trader] Sold {trade.symbol} via Jupiter (attempt {attempt}): {sol_received:.4f} SOL",
                        flush=True,
                    )
                    return sol_received
                print(f"[trader] Jupiter sig={sig} but tokens unchanged (attempt {attempt})", flush=True)

        wait = 2 ** attempt
        print(f"[trader] Sell attempt {attempt}/3 failed — retrying in {wait}s", flush=True)
        await asyncio.sleep(wait)

    print(f"[trader] GAVE UP selling {trade.symbol} after 3 attempts", flush=True)
    return 0.0


# ── Partial sell (house money) ─────────────────────────────────────────────────

async def sell_partial(
    session:  aiohttp.ClientSession,
    rpc:      AsyncClient,
    keypair:  Keypair,
    trade:    Trade,
    pct:      float,
    reason:   str,
) -> float:
    """
    Sell `pct` fraction (0.0–1.0) of position. Updates trade.token_amount in place.
    Returns SOL received.
    """
    tokens_to_sell = int(trade.token_amount * pct)
    if tokens_to_sell == 0:
        return 0.0

    value = await current_value_sol(session, trade)
    print(
        f"[trader] PARTIAL SELL {trade.symbol} {pct*100:.0f}% [{reason}] | est={value:.4f} SOL",
        flush=True,
    )

    slippage_pct  = config.SELL_SLIPPAGE_BPS // 100
    bal_before    = await _get_sol_balance(rpc, keypair)
    tokens_before = await _token_balance(rpc, keypair, trade.mint)

    # ── PumpPortal primary — skip in BONDED_ONLY mode ──
    if not config.BONDED_ONLY:
        sig = await _pumpportal_tx(
            session, rpc, keypair, "sell", trade.mint,
            tokens_to_sell, denom_sol=False, slippage=slippage_pct,
        )
        if sig:
            print(f"[trader] PumpPortal partial sig={sig} — confirming…", flush=True)
            await asyncio.sleep(4)
            tokens_after = await _token_balance(rpc, keypair, trade.mint)
            if tokens_before >= 0 and tokens_after >= 0 and (tokens_before - tokens_after) >= tokens_to_sell * 0.8:
                bal_after    = await _get_sol_balance(rpc, keypair)
                sol_received = max(0.0, bal_after - bal_before + config.GAS_COST_ROUNDTRIP_SOL / 4)
                trade.token_amount = tokens_after
                print(
                    f"[trader] Partial sold {trade.symbol} via PumpPortal: {sol_received:.4f} SOL "
                    f"| remaining tokens: {trade.token_amount}",
                    flush=True,
                )
                return sol_received
            actually_sold = max(0, (tokens_before - tokens_after)) if tokens_before >= 0 and tokens_after >= 0 else -1
            print(
                f"[trader] PumpPortal partial sig={sig} but only confirmed {actually_sold}/{tokens_to_sell} tokens sold",
                flush=True,
            )

    # ── Jupiter primary (BONDED_ONLY) or fallback ──
    quote = await _jupiter_quote(
        session, trade.mint, config.SOL_MINT,
        tokens_to_sell, slippage_bps=config.SELL_SLIPPAGE_BPS,
    )
    if quote:
        sig = await _jupiter_submit(session, rpc, keypair, quote)
        if sig:
            print(f"[trader] Jupiter partial sig={sig} — confirming…", flush=True)
            await asyncio.sleep(4)
            tokens_after = await _token_balance(rpc, keypair, trade.mint)
            if tokens_before >= 0 and tokens_after >= 0 and (tokens_before - tokens_after) >= tokens_to_sell * 0.8:
                bal_after    = await _get_sol_balance(rpc, keypair)
                sol_received = max(0.0, bal_after - bal_before + config.GAS_COST_ROUNDTRIP_SOL / 4)
                trade.token_amount = tokens_after
                print(
                    f"[trader] Partial sold {trade.symbol} via Jupiter: {sol_received:.4f} SOL "
                    f"| remaining tokens: {trade.token_amount}",
                    flush=True,
                )
                return sol_received

    print(f"[trader] Partial sell failed for {trade.symbol}", flush=True)
    return 0.0
