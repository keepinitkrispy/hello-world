# Storyboard

Format: 16:9, 1920×1080. Use large monospaced terminal text. Never rewrite terminal output and call it a capture.

## 00:00–00:25
Title: **FOUR PUBLIC RUSTCHAIN CHECKS — FROM AN ANDROID PHONE**

Secondary: **Source-backed. Live output. No dashboard.**

## 00:25–01:05
Capture:
```bash
curl -fsS https://rustchain.org/health
```

Highlight `ok`, `db_rw`, and `version`. Keep the JSON itself unchanged.

## 01:05–01:45
Capture:
```bash
curl -fsS https://rustchain.org/epoch
```

Call out epoch, slot, blocks_per_epoch, enrolled_miners, and epoch_pot. Label values as capture-time data.

## 01:45–02:35
Capture:
```bash
curl -fsS https://rustchain.org/api/miners | python3 -c 'import json,sys; d=json.load(sys.stdin); xs=d if isinstance(d,list) else d.get("miners",[]); print("active records:",len(xs)); print(json.dumps(xs[:2],indent=2))'
```

Use the actual current result. The package's reference capture recorded 14 records.

## 02:35–03:25
Capture:
```bash
curl -fsS 'https://rustchain.org/wallet/balance?miner_id=capcart-mobile'
```

Show the response verbatim. Caption: **Reference ID currently reports 0.0 RTC. No earnings claimed.**

Then show the pinned documentation line distinguishing a RustChain `miner_id` from Ethereum/Solana addresses.

## 03:25–04:00
Recap graphic:

```
/health          node health
/epoch           epoch state
/api/miners      active miner records
/wallet/balance  one miner-ID balance
```

Final caption: **Re-run live endpoints; do not hard-code stale values.**
