import os

RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
KEYPAIR_PATH = "./keypair.json"

TRADE_PCT = float(os.environ.get("TRADE_PCT", "0.15"))
GAS_RESERVE_SOL = float(os.environ.get("GAS_RESERVE_SOL", "0.01"))
MAX_TRADE_SOL = float(os.environ.get("MAX_TRADE_SOL", "0.03"))
MIN_TRADE_SOL = 0.015

# Near-graduation zone only. Coins here have real liquidity and real momentum.
# 1% was watching the entire curve — mostly noise with no graduation pressure.
MONITOR_BC_MIN = float(os.environ.get("MONITOR_BC_MIN", "35"))
MONITOR_BC_MAX = float(os.environ.get("MONITOR_BC_MAX", "88"))

MONITOR_CONSECUTIVE_BUYS = int(os.environ.get("MONITOR_CONSECUTIVE_BUYS", "2"))
MOMENTUM_WINDOW_SEC = int(os.environ.get("MOMENTUM_WINDOW_SEC", "10"))
MIN_BC_RISE_PCT = float(os.environ.get("MIN_BC_RISE_PCT", "2.0"))
MAX_BC_RISE_PCT = float(os.environ.get("MAX_BC_RISE_PCT", "15.0"))  # reject coordinated pump signals

PROFIT_TARGET_PCT = 25
STOP_LOSS_PCT = 8
MAX_HOLD_SECONDS = 120

TRAIL_ACTIVATE_PCT = 12
TRAIL_DRAWDOWN_PCT = 3

POLL_INTERVAL_SEC = 2.0
POSITION_POLL_SEC = 0.5

SLIPPAGE_BPS = 2000       # buys: don't overpay on entry
SELL_SLIPPAGE_BPS = 5000  # sells: guarantee execution over fill quality

# Priority fee in lamports (integer). "auto" is not a valid Jupiter parameter.
# 0.001 SOL = 1_000_000 lamports. Use this everywhere.
PRIORITY_FEE_LAMPORTS = int(os.environ.get("PRIORITY_FEE_LAMPORTS", "1000000"))

GAS_COST_ROUNDTRIP_SOL = float(os.environ.get("GAS_COST_ROUNDTRIP_SOL", "0.002"))

SOL_MINT  = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

MAX_CREATOR_COINS   = 4
MIN_REPLY_COUNT     = int(os.environ.get("MIN_REPLY_COUNT", "1"))
MIN_AGE_SECONDS     = int(os.environ.get("MIN_AGE_SECONDS", "15"))
COPY_SIMILARITY_PCT = int(os.environ.get("COPY_SIMILARITY_PCT", "75"))

# Momentum stall: exit if peak P&L hasn't been refreshed in this many seconds
MOMENTUM_STALL_PEAK_AGE_SEC = 10  # reduced from 20 — exit dead coins faster
