import base58
import json
import os

from solders.keypair import Keypair


def _parse_key(raw: str) -> Keypair:
    """
    Accept either:
      - A JSON byte array: [12, 34, 56, ...]   (what we generate / Solana CLI)
      - A base58 string                         (what Phantom exports)
    """
    raw = raw.strip()
    if raw.startswith("["):
        return Keypair.from_bytes(bytes(json.loads(raw)))
    else:
        return Keypair.from_bytes(base58.b58decode(raw))


def load_or_create(keypair_path: str) -> Keypair:
    """
    Priority:
      1. SOLANA_PRIVATE_KEY env var (Railway / cloud) — accepts base58 or JSON array
      2. keypair.json local file
      3. Generate a brand-new wallet and print instructions
    """
    env_key = os.environ.get("SOLANA_PRIVATE_KEY")
    if env_key:
        try:
            keypair = _parse_key(env_key)
            print(f"[wallet] Loaded wallet from env: {keypair.pubkey()}")
            return keypair
        except Exception as e:
            raise RuntimeError(f"SOLANA_PRIVATE_KEY is set but could not be parsed: {e}")

    if os.path.exists(keypair_path):
        with open(keypair_path, "r") as f:
            keypair = _parse_key(f.read())
        print(f"[wallet] Loaded wallet from file: {keypair.pubkey()}")
        return keypair

    keypair    = Keypair()
    secret_lst = list(bytes(keypair))
    with open(keypair_path, "w") as f:
        json.dump(secret_lst, f)

    print(f"[wallet] Generated new wallet: {keypair.pubkey()}")
    print(f"[wallet] !! Fund this address with SOL before trading !!")
    print(f"[wallet] To use your existing Phantom wallet instead, set:")
    print(f"[wallet]   SOLANA_PRIVATE_KEY=<your base58 private key from Phantom>")
    print(f"[wallet] Keypair also saved to: {keypair_path}")
    return keypair
