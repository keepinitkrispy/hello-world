import os

# ── Solana RPC ────────────────────────────────────────────────────────────────
RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# ── Wallet ────────────────────────────────────────────────────────────────────
KEYPAIR_PATH = "./keypair.json"

# ── Trade sizing ──────────────────────────────────────────────────────────────
TRADE_PCT       = float(os.environ.get("TRADE_PCT", "0.30"))   # 30% of spendable per trade
GAS_RESERVE_SOL = float(os.environ.get("GAS_RESERVE_SOL", "0.05"))  # always kept back for fees
MIN_TRADE_SOL   = 0.01

# ── pump.fun monitoring ───────────────────────────────────────────────────────
# Near-graduation zone: coins at 65-88% BC have real liquidity and
# Jupiter can route them. Below 65% is too early; above 88% is graduation chaos.
MONITOR_BC_MIN       = 65    # only watch coins already at 65%+ bonding curve
MONITOR_BC_MAX       = 88    # stop below 88% (graduation chaos at 90%+)
MOMENTUM_WINDOW_SEC  = 30    # measure BC rise over this window
MIN_BC_RISE_PCT      = 2     # fire when BC rises 2+ points (coins at 65%+ move slower)

# ── Exit conditions (whichever triggers first) ────────────────────────────────
PROFIT_TARGET_PCT    = 20    # sell when up 20%
STOP_LOSS_PCT        = 7     # sell when down 7%
MAX_HOLD_SECONDS     = 60    # force sell after 1 minute

# ── Trailing stop ────────────────────────────────────────────────────────────
TRAIL_ACTIVATE_PCT   = 5     # start trailing once up 5%
TRAIL_DRAWDOWN_PCT   = 5     # sell if drops 5% from peak

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
MAX_CREATOR_COINS     = 4
MIN_REPLY_COUNT       = 0
MIN_AGE_SECONDS       = 20
COPY_SIMILARITY_PCT   = 80
