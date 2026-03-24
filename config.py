import os

# ── Solana RPC ────────────────────────────────────────────────────────────────
# Override with a faster dedicated RPC (Helius, QuickNode, etc.) via env var
RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# ── Wallet ────────────────────────────────────────────────────────────────────
KEYPAIR_PATH = "./keypair.json"

# ── Trade sizing ──────────────────────────────────────────────────────────────
# Bot bets a % of spendable balance each trade so it compounds wins and
# scales back after losses — you should never need to top it up.
TRADE_PCT       = float(os.environ.get("TRADE_PCT", "0.30"))   # 30% of spendable per trade
GAS_RESERVE_SOL = float(os.environ.get("GAS_RESERVE_SOL", "0.05"))  # always kept back for fees
MIN_TRADE_SOL   = 0.01      # don't bother trading below this (fees would eat it)

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

# Priority fee sent to Jupiter so txs land fast during congestion
# "auto" lets Jupiter pick; or set a fixed lamport value e.g. 500_000
PRIORITY_FEE = "auto"

# Estimated round-trip gas cost (buy tx + sell tx) in SOL.
# At ~$130/SOL, $5 ≈ 0.038 SOL — used to calculate true net profit.
GAS_COST_ROUNDTRIP_SOL = float(os.environ.get("GAS_COST_ROUNDTRIP_SOL", "0.038"))

# ── Token addresses ───────────────────────────────────────────────────────────
SOL_MINT  = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# ── Profit parking ────────────────────────────────────────────────────────────
# After a winning trade, keep profit aside so it's never re-risked.
# PARK_PROFITS=True  → hold profit as SOL (no extra swap, no extra gas)
# PARK_AS_USDC=True  → additionally convert profit to USDC (costs one more tx)
PARK_PROFITS  = True
PARK_AS_USDC  = False  # set True only if you want hard USDC conversion

# ── Coin filters ──────────────────────────────────────────────────────────────
# Holder concentration: skip if top real holders (excl. bonding curve) own > this %
MAX_TOP_HOLDER_PCT   = 35   # no single wallet should hold more than 35%
MAX_TOP5_COMBINED_PCT = 50  # top 5 real wallets combined shouldn't exceed 50%

# Dev spam: skip if creator has launched this many coins before
MAX_CREATOR_COINS    = 4

# Organic trading: minimum social engagement (pump.fun reply count)
MIN_REPLY_COUNT      = 1

# Bonding curve velocity: skip if coin went from 0 → threshold in under N seconds
# (too fast = coordinated bot buy-up)
MIN_AGE_SECONDS      = 60   # coin must be at least 1 minute old

# Copy-coin: skip if name/symbol too similar to a known popular coin
# (checked via fuzzy match against a built-in list)
COPY_SIMILARITY_PCT  = 80   # Levenshtein similarity threshold (0-100)
