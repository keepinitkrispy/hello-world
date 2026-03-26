import os

RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
KEYPAIR_PATH = "./keypair.json"

TRADE_PCT = float(os.environ.get("TRADE_PCT", "0.15"))
GAS_RESERVE_SOL = float(os.environ.get("GAS_RESERVE_SOL", "0.01"))
MAX_TRADE_SOL = float(os.environ.get("MAX_TRADE_SOL", "0.05"))
MIN_TRADE_SOL = 0.015

# Near-graduation zone only. Coins here have real liquidity and real momentum.
# 1% was watching the entire curve — mostly noise with no graduation pressure.
MONITOR_BC_MIN = 30
MONITOR_BC_MAX = 88

MOMENTUM_WINDOW_SEC = 15
MIN_BC_RISE_PCT = 3.0
MAX_BC_RISE_PCT = 15.0  # reject coordinated pump signals

PROFIT_TARGET_PCT = 8
STOP_LOSS_PCT = 5
MAX_HOLD_SECONDS = 90

TRAIL_ACTIVATE_PCT = 5
TRAIL_DRAWDOWN_PCT = 3  # tightened from 5 — don't give back that much off peak

POLL_INTERVAL_SEC = 2.0
POSITION_POLL_SEC = 0.5

SLIPPAGE_BPS = 2000

# Priority fee in lamports (integer). "auto" is not a valid Jupiter parameter.
# 0.001 SOL = 1_000_000 lamports. Use this everywhere.
PRIORITY_FEE_LAMPORTS = int(os.environ.get("PRIORITY_FEE_LAMPORTS", "1000000"))

GAS_COST_ROUNDTRIP_SOL = float(os.environ.get("GAS_COST_ROUNDTRIP_SOL", "0.002"))

SOL_MINT  = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

PARK_PROFITS = True

MAX_CREATOR_COINS   = 4
MIN_REPLY_COUNT     = 1
MIN_AGE_SECONDS     = 5
COPY_SIMILARITY_PCT = 80

# Momentum stall: exit if peak P&L hasn't been refreshed in this many seconds
# regardless of whether we're in profit. Sitting on a dead position bleeds gas
# and blocks capital. Reduced from the implicit ~30s to 20s.
MOMENTUM_STALL_PEAK_AGE_SEC = 20
