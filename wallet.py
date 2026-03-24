import json
import os

from solders.keypair import Keypair


def load_or_create(keypair_path: str) -> Keypair:
    """Load keypair from file, or generate a new one and save it."""
    if os.path.exists(keypair_path):
        with open(keypair_path, "r") as f:
            secret = json.load(f)
        keypair = Keypair.from_bytes(bytes(secret))
        print(f"[wallet] Loaded wallet: {keypair.pubkey()}")
        return keypair

    keypair = Keypair()
    with open(keypair_path, "w") as f:
        json.dump(list(bytes(keypair)), f)

    print(f"[wallet] Generated new wallet: {keypair.pubkey()}")
    print(f"[wallet] !! Fund this address with SOL before trading !!")
    print(f"[wallet] Keypair saved to: {keypair_path}  (keep this secret — it's gitignored)")
    return keypair
