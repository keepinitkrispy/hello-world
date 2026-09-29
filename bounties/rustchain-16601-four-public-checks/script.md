# Script — Four Public RustChain Checks From an Android Phone

**Target length:** about 4 minutes.

## 00:00–00:25 — Hook
You do not need a desktop dashboard to inspect basic RustChain state. This walkthrough uses an Android phone, an ordinary shell, and four read-only HTTPS requests. Every command shown is documented in the RustChain repository, and the outputs are captured from the live public node rather than reconstructed.

## 00:25–01:05 — Check 1: node health
Run:

```bash
curl -fsS https://rustchain.org/health
```

On the reference capture the node returned JSON with `"ok": true`, `"db_rw": true`, version `"2.2.1-rip200"`, and an uptime value. Those values can change between captures. The reusable point is that one request returns the node's current health object.

## 01:05–01:45 — Check 2: current epoch
Run:

```bash
curl -fsS https://rustchain.org/epoch
```

At reference-capture time the response reported epoch 300, slot 43234, 144 blocks per epoch, 33 enrolled miners, an epoch pot of 1.5 RTC, and a total-supply field.

Those are observations, not constants. RustChain's SDK exposes the same `/epoch` endpoint programmatically.

## 01:45–02:35 — Check 3: active miners
Run:

```bash
curl -fsS https://rustchain.org/api/miners
```

The project documentation says this endpoint lists active miners and supports `limit` and `offset`. In the reference phone capture, the response contained 14 miner records.

Records include fields such as miner identifier, architecture, hardware type, last attestation time, and an antiquity multiplier. The Python SDK also accepts the server's object-wrapped miner list.

This is a network-wide view. It is not the endpoint for checking one miner ID's balance.

## 02:35–03:25 — Check 4: one RustChain miner-ID balance
Run:

```bash
curl -fsS "https://rustchain.org/wallet/balance?miner_id=capcart-mobile"
```

The live node returned:

```json
{"amount_i64":0,"amount_rtc":0.0,"miner_id":"capcart-mobile"}
```

That zero is intentional evidence. This package makes no earnings claim.

RustChain's `START_HERE.md` also distinguishes a RustChain `miner_id` from an Ethereum or Solana address.

## 03:25–04:00 — Recap
Together these calls provide a small inspection surface:

- `/health` — current node-health object
- `/epoch` — current epoch state
- `/api/miners` — active-miner view
- `/wallet/balance` — one miner-ID balance

They work from an Android shell because they are ordinary HTTPS reads. The package includes the verbatim reference outputs and an immutable source revision so later captures can be checked instead of guessed.
