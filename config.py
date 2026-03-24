# ── Solana RPC ────────────────────────────────────────────────────────────────
RPC_URL = "https://api.mainnet-beta.solana.com"

# ── Wallet ────────────────────────────────────────────────────────────────────
KEYPAIR_PATH = "./keypair.json"

# ── Trade sizing ──────────────────────────────────────────────────────────────
BUY_AMOUNT_SOL = 0.1        # SOL to spend per trade entry

# ── pump.fun monitoring ───────────────────────────────────────────────────────
BOND_THRESHOLD_MIN = 85     # Start watching at 85% bonding curve progress
BOND_THRESHOLD_MAX = 98     # Stop at 98% (already too close to graduation chaos)

# ── Exit conditions (whichever triggers first) ────────────────────────────────
PROFIT_TARGET_PCT = 20      # Sell when up 20%
STOP_LOSS_PCT     = 10      # Sell when down 10%
MAX_HOLD_SECONDS  = 120     # Force sell after 2 minutes

# ── Timing ────────────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC = 0.5     # How often to poll pump.fun and check positions

# ── Jupiter ───────────────────────────────────────────────────────────────────
SLIPPAGE_BPS = 300          # 3% slippage tolerance

# ── Token addresses ───────────────────────────────────────────────────────────
SOL_MINT = "So11111111111111111111111111111111111111112"
