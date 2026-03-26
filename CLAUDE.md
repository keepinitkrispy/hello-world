# Bot State — Read This First

This is a Solana pump.fun momentum trading bot. It monitors the PumpPortal WebSocket for coins with real buying pressure near graduation and trades them for quick exits.

## Deployment

- Hosted on **Railway.app**, auto-deploys from **master branch**
- Always push to master (directly or via merge) to deploy
- Use branch `claude/fix-duplicate-coin-trades-N7vHu` for development, then merge to master
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
MONITOR_BC_MIN = 30       # was 65, lowered because API only returns 0-27% coins at top
MONITOR_BC_MAX = 88       # stop before graduation (liquidity risk)
MIN_BC_RISE_PCT = 3.0     # NEVER lower below 2.0 — 1.0 caused buying on noise (FOREVER rug)
MAX_BC_RISE_PCT = 15.0    # reject coordinated pump-and-dumps (ODYSSEY was +42pts spike)
PROFIT_TARGET_PCT = 8     # take profit at +8%
STOP_LOSS_PCT = 5         # stop loss at -5% (tightens to -3% after 30s)
TRAIL_ACTIVATE_PCT = 5    # start trailing at +5% peak
TRAIL_DRAWDOWN_PCT = 3    # exit if drops 3pts off peak
MAX_HOLD_SECONDS = 90     # force sell after 90s regardless
MOMENTUM_STALL_PEAK_AGE_SEC = 20  # exit if no new peak for 20s
POSITION_POLL_SEC = 0.5   # check position value every 500ms
PRIORITY_FEE_LAMPORTS = 1_000_000  # 0.001 SOL — "auto" is NOT valid for Jupiter
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

## Trade Lifecycle (bot.py `_handle`)

1. Signal arrives from queue
2. `filters.passes_all()` — age, clone, replies, holder check
3. Buy via `trader.buy()` — PumpPortal first, Jupiter fallback
4. `positions.record()` — saved to JSON immediately
5. Poll loop every 0.5s:
   - `+10% P&L` → sell 50%, set `_half_sold=True`, remainder is house money
   - `+8% P&L` → full take profit
   - Peak >= 5% then drops 3pts → trailing stop
   - No new peak for 20s → momentum stall exit
   - `-5% P&L (first 30s)` or `-3% (after 30s)` → stop loss + block mint
   - `90s elapsed` → force sell
6. `positions.remove()` only on confirmed sell (`sol_back > 0`)
7. Stop-loss → `monitor.block_mint(mint)`

## Known Limitations

- Holder check compares token account addresses, not wallet owners — can't detect coordinated wallets that each hold <40%
- Position recovery on restart sells immediately (no re-entry logic)
- `open_positions.json` path configurable via `POSITIONS_FILE` env var
