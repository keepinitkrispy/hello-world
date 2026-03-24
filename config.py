import os

# ── Solana RPC ────────────────────────────────────────────────────────────────
# Override with a faster dedicated RPC (Helius, QuickNode, etc.) via env var
RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# ── Wallet ────────────────────────────────────────────────────────────────────
KEYPAIR_PATH = "./keypair.json"

# ── Trade sizing ──────────────────────────────────────────────────────────────
BUY_AMOUNT_SOL = 0.03       # SOL to spend per trade entry (adjust to your balance)

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
SOL_MINT  = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# ── Profit parking ────────────────────────────────────────────────────────────
# After a winning trade, sweep profit into USDC and only rebuy with principal
PARK_PROFITS = True

# ── Coin filters ──────────────────────────────────────────────────────────────
# Holder concentration: skip if top real holders (excl. bonding curve) own > this %
MAX_TOP_HOLDER_PCT   = 20   # no single wallet should hold more than 20%
MAX_TOP5_COMBINED_PCT = 20  # top 5 real wallets combined shouldn't exceed 20%

# Dev spam: skip if creator has launched this many coins before
MAX_CREATOR_COINS    = 4

# Organic trading: minimum social engagement (pump.fun reply count)
MIN_REPLY_COUNT      = 3

# Bonding curve velocity: skip if coin went from 0 → threshold in under N seconds
# (too fast = coordinated bot buy-up)
MIN_AGE_SECONDS      = 300  # coin must be at least 5 minutes old

# Copy-coin: skip if name/symbol too similar to a known popular coin
# (checked via fuzzy match against a built-in list)
COPY_SIMILARITY_PCT  = 80   # Levenshtein similarity threshold (0-100)
