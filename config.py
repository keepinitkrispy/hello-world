import os

# ── Solana RPC ────────────────────────────────────────────────────────────────
RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# ── Wallet ────────────────────────────────────────────────────────────────────
KEYPAIR_PATH = "./keypair.json"

# ── Trade sizing ──────────────────────────────────────────────────────────────
TRADE_PCT       = float(os.environ.get("TRADE_PCT", "0.30"))
GAS_RESERVE_SOL = float(os.environ.get("GAS_RESERVE_SOL", "0.05"))
MIN_TRADE_SOL   = 0.01

# ── pump.fun monitoring ───────────────────────────────────────────────────────
MOMENTUM_WINDOW_SEC  = 20
MIN_BC_RISE_PCT      = 5
MAX_BC_RISE_PCT      = 40
MAX_BC_PCT           = 90

# ── Exit conditions ────────────────────────────────────────────────────────────────
PROFIT_TARGET_PCT    = 20
STOP_LOSS_PCT        = 7
MAX_HOLD_SECONDS     = 60

# ── Trailing stop ────────────────────────────────────────────────────────────
TRAIL_ACTIVATE_PCT   = 5
TRAIL_DRAWDOWN_PCT   = 5

# ── Timing ────────────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC = 0.5

# ── Jupiter ───────────────────────────────────────────────────────────────────
SLIPPAGE_BPS = 300
PRIORITY_FEE = "auto"
GAS_COST_ROUNDTRIP_SOL = float(os.environ.get("GAS_COST_ROUNDTRIP_SOL", "0.038"))

# ── Token addresses ───────────────────────────────────────────────────────────
SOL_MINT  = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# ── Profit parking ────────────────────────────────────────────────────────────
PARK_PROFITS  = True
PARK_AS_USDC  = False

# ── Coin filters ──────────────────────────────────────────────────────────────
MAX_TOP_HOLDER_PCT    = 35
MAX_TOP5_COMBINED_PCT = 50
MAX_CREATOR_COINS     = 4
MIN_REPLY_COUNT       = 0
MIN_AGE_SECONDS       = 20
COPY_SIMILARITY_PCT   = 80
