# Bot State — Read This First

This is a Solana pump.fun momentum trading bot. It monitors the PumpPortal WebSocket for coins with real buying pressure near graduation and trades them for quick exits.

## Deployment

- Hosted on **Railway.app**, auto-deploys from **master branch**
- Always push to master (directly or via merge) to deploy
- Use branch `claude/debug-solana-trader-bot-iZVpf` for development, then merge to master
- Do NOT create PRs expecting auto-merge — merge manually every time

## Architecture

| File | Role |
|---|---|
| `bot.py` | Main loop. Reads from signal queue, runs `_handle()` per coin in async tasks |
| `monitor.py` | PumpPortal WebSocket listener. Fires signals into queue |
| `trader.py` | Buy/sell execution. PumpPortal primary, Jupiter fallback |
| `filters.py` | Pre-trade filters: age, clone check, reply count, holder concentration |
| `positions.py` | Persist open positions to `open_positions.json` for restart recovery |
| `profits.py` | Track parked profits so they aren't re-spent |
| `config.py` | All tunable parameters |
| `wallet.py` | Keypair load/create |

## Signal Logic (monitor.py)

- Single persistent WebSocket to `wss://pumpportal.fun/api/data`
- Subscribes to `subscribeNewToken` (catches every launch)
- Zone poller every 15s subscribes to coins already in BC zone
- **Signal fires when:** 3+ consecutive buys within 10s AND BC rises 3–15pts
- `_permanent_blocks` set: mints blocked after stop-loss exit (session-scoped, prevents re-entry)
- `_signal_times` dict: 10-minute cooldown per mint before re-signaling

## Config Values — Current + Rationale

```python
MONITOR_BC_MIN = 50       # raised from 30 — real momentum + exit liquidity starts here
MONITOR_BC_MAX = 88       # stop before graduation (liquidity risk)
MIN_BC_RISE_PCT = 3.0     # NEVER lower below 2.0 — 1.0 caused buying on noise (FOREVER rug)
MAX_BC_RISE_PCT = 15.0    # reject coordinated pump-and-dumps (ODYSSEY was +42pts spike)
PROFIT_TARGET_PCT = 8     # take profit at +8%
STOP_LOSS_PCT = 4         # stop loss at -4% (tightens to -3% after 15s)
TRAIL_ACTIVATE_PCT = 5    # start trailing at +5% peak
TRAIL_DRAWDOWN_PCT = 2    # exit if drops 2pts off peak (tightened from 3)
MAX_HOLD_SECONDS = 60     # force sell after 60s regardless (reduced from 90)
MOMENTUM_STALL_PEAK_AGE_SEC = 10  # exit if no new peak for 10s (reduced from 20)
POSITION_POLL_SEC = 0.5   # check position value every 500ms
PRIORITY_FEE_LAMPORTS = 1_000_000  # 0.001 SOL — "auto" is NOT valid for Jupiter
SELL_SLIPPAGE_BPS = 300   # 3% — NEVER set above 500; 5000 caused catastrophic MEV losses
```

## Bugs Fixed (Do Not Reintroduce)

### 1. Duplicate re-buys at a loss
**Problem:** Bot would sell a coin at a loss, then buy it again on a new signal.
**Fix:** `_permanent_blocks` in monitor.py. After stop-loss exit, `monitor.block_mint(mint)` is called from bot.py's finally block. Mint cannot signal again this session.

### 2. Orphaned positions on sell failure
**Problem:** `positions.remove()` was called unconditionally. If sell failed, position was removed from JSON but bot had no record — lost on restart.
**Fix:** `positions.remove()` only called when `sol_back > 0` (confirmed sell).

### 3. Buying at top of spike (2s too late)
**Problem:** REST polling every 2s meant bot always arrived after the pump peak.
**Fix:** Replaced REST polling with PumpPortal WebSocket. Events arrive the instant they land on-chain.

### 4. Zero signals after WebSocket switch
**Problem:** `MONITOR_BC_MIN=65` + API sorted by bondingCurve DESC only returned coins at 0-27%. Nothing was in zone.
**Fix:** Lowered `MONITOR_BC_MIN=30`, changed sort param to `bondingCurve`.

### 5. Weak signal entries (FOREVER rug)
**Problem:** `MIN_BC_RISE_PCT=1.0` — bot bought FOREVER at +1.04pts rise, immediately -10.8%.
**Fix:** Raised to `MIN_BC_RISE_PCT=3.0`. Requires real buying pressure.

### 6. Coordinated pump entries (ODYSSEY rug)
**Problem:** BC spiked +42pts in 10s — coordinated pump-and-dump. Bot bought at top.
**Fix:** `MAX_BC_RISE_PCT=15.0` — rejects signals where BC rose too fast (likely coordinated).

### 7. Holder concentration rugs
**Problem:** Coins where top 3 wallets hold >40% of supply tend to rug immediately.
**Fix:** `filters.py` calls `rpc.get_token_largest_accounts()` and rejects top3 > 40%.

### 8. PRIORITY_FEE="auto" crash
**Problem:** Another AI's config used `"auto"` for priority fee. Jupiter doesn't accept strings.
**Fix:** `PRIORITY_FEE_LAMPORTS = 1_000_000` (integer, 0.001 SOL). Used everywhere.

### 9. House money partial sell never fired
**Problem:** Code existed but was never deployed (PR was merged at wrong commit).
**Fix:** Always merge directly to master. The `_half_sold` flag on Trade + `sell_partial()` at +10% P&L is live.

### 10. 50% sell slippage — catastrophic MEV losses
**Problem:** `SELL_SLIPPAGE_BPS = 5000` allowed Jupiter to fill exits up to 50% worse than quoted. Bot showed +8% P&L but sold into -40% fills.
**Fix:** `SELL_SLIPPAGE_BPS = 300` (3%). If a fill can't execute within 3% of quote, retry via PumpPortal fallback.

### 11. `_fetch_coin` blocked the WebSocket event loop
**Problem:** The HTTP call to fetch full coin data was awaited inline in the WS message handler. All incoming trade events were buffered unprocessed for up to 5s while the HTTP call ran. By the time the buy executed, the pump had peaked.
**Fix:** Signal detection (buy history, BC rise check) stays synchronous. Once conditions are met, `asyncio.create_task(_enqueue_signal(...))` fetches coin data and queues the signal without ever blocking the WS loop.

### 12. P&L used spot price instead of actual AMM output
**Problem:** `current_value_sol` used `(vsol/vtok) * token_amount / LAMPORTS` — the marginal price assuming zero sell size. This ignored price impact and always overstated position value.
**Fix:** Uses constant-product AMM formula: `sol_out = vsol - (vsol * vtok) / (vtok + token_amount)`. This is what a sell would actually return.

### 13. positions.json not updated after partial sell
**Problem:** After house-money 50% sell, `trade.token_amount` was halved in memory but `positions.json` still had the original amount. Recovery after crash would try to sell tokens no longer held.
**Fix:** `positions.record(trade)` called again after each successful partial sell.

## Trade Lifecycle (bot.py `_handle`)

1. Signal arrives from queue
2. `filters.passes_all()` — age, clone, replies, holder check
3. Buy via `trader.buy()` — PumpPortal first, Jupiter fallback
4. `positions.record()` — saved to JSON immediately
5. Poll loop every 0.5s:
   - `+10% P&L` → sell 50%, set `_half_sold=True`, update positions.json with new token_amount, remainder is house money
   - `+8% P&L` → full take profit
   - Peak >= 5% then drops 2pts → trailing stop
   - No new peak for 10s → momentum stall exit
   - `-4% P&L (first 15s)` or `-3% (after 15s)` → stop loss + block mint
   - `60s elapsed` → force sell
6. `positions.remove()` only on confirmed sell (`sol_back > 0`)
7. Stop-loss → `monitor.block_mint(mint)`

## Known Limitations

- Holder check compares token account addresses, not wallet owners — can't detect coordinated wallets that each hold <40%
- Position recovery on restart sells immediately (no re-entry logic)
- `open_positions.json` path configurable via `POSITIONS_FILE` env var
