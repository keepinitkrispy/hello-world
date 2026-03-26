import os

RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
KEYPAIR_PATH = "./keypair.json"

TRADE_PCT = float(os.environ.get("TRADE_PCT", "0.15"))
GAS_RESERVE_SOL = float(os.environ.get("GAS_RESERVE_SOL", "0.01"))
MAX_TRADE_SOL = float(os.environ.get("MAX_TRADE_SOL", "0.2"))
MIN_TRADE_SOL = 0.015

# Near-graduation zone only. Coins here have real liquidity and real momentum.
# 1% was watching the entire curve — mostly noise with no graduation pressure.
MONITOR_BC_MIN = 50        # raised from 30 — real momentum + exit liquidity starts here
MONITOR_BC_MAX = 88

MOMENTUM_WINDOW_SEC = 15
MIN_BC_RISE_PCT = 3.0
MAX_BC_RISE_PCT = 15.0  # reject coordinated pump signals

PROFIT_TARGET_PCT = 8
STOP_LOSS_PCT = 4          # tightened from 5 — cut losses faster
MAX_HOLD_SECONDS = 60      # reduced from 90 — dead coins don't recover

TRAIL_ACTIVATE_PCT = 5
TRAIL_DRAWDOWN_PCT = 2     # tightened from 3 — don't give back gains

POLL_INTERVAL_SEC = 2.0
POSITION_POLL_SEC = 0.5

SLIPPAGE_BPS = 2000      # buys: don't overpay on entry
SELL_SLIPPAGE_BPS = 300  # sells: 3% — tight enough to avoid MEV, wide enough to fill

# Priority fee in lamports (integer). "auto" is not a valid Jupiter parameter.
# 0.001 SOL = 1_000_000 lamports. Use this everywhere.
PRIORITY_FEE_LAMPORTS = int(os.environ.get("PRIORITY_FEE_LAMPORTS", "1000000"))

GAS_COST_ROUNDTRIP_SOL = float(os.environ.get("GAS_COST_ROUNDTRIP_SOL", "0.002"))

SOL_MINT  = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

PARK_PROFITS = False  # let profits compound into larger trade sizes

MAX_CONCURRENT_POSITIONS = 1  # only one open trade at a time — prevents stack blowup

MAX_CREATOR_COINS   = 4
MIN_REPLY_COUNT     = 3    # raised from 1 — require actual engagement
MIN_AGE_SECONDS     = 30   # raised from 5 — dev dump window is first 30s
COPY_SIMILARITY_PCT = 70   # lowered from 80 — catch more clone variants

# Momentum stall: exit if peak P&L hasn't been refreshed in this many seconds
MOMENTUM_STALL_PEAK_AGE_SEC = 10  # reduced from 20 — exit dead coins faster
