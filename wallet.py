import json
import os

from solders.keypair import Keypair


def load_or_create(keypair_path: str) -> Keypair:
    """
    Priority order:
      1. SOLANA_PRIVATE_KEY env var (JSON array of bytes) — used in cloud deployments
      2. keypair.json file — used locally
      3. Generate a new keypair and save to file (first-run only)
    """
    # 1. Env var (Railway / cloud)
    env_key = os.environ.get("SOLANA_PRIVATE_KEY")
    if env_key:
        try:
            secret  = json.loads(env_key)
            keypair = Keypair.from_bytes(bytes(secret))
            print(f"[wallet] Loaded wallet from env: {keypair.pubkey()}")
            return keypair
        except Exception as e:
            raise RuntimeError(f"SOLANA_PRIVATE_KEY is set but could not be parsed: {e}")

    # 2. Local file
    if os.path.exists(keypair_path):
        with open(keypair_path, "r") as f:
            secret = json.load(f)
        keypair = Keypair.from_bytes(bytes(secret))
        print(f"[wallet] Loaded wallet from file: {keypair.pubkey()}")
        return keypair

    # 3. Generate new
    keypair    = Keypair()
    secret_lst = list(bytes(keypair))
    with open(keypair_path, "w") as f:
        json.dump(secret_lst, f)

    print(f"[wallet] Generated new wallet: {keypair.pubkey()}")
    print(f"[wallet] !! Fund this address with SOL before trading !!")
    print(f"[wallet] Private key (set as SOLANA_PRIVATE_KEY env var in Railway):")
    print(f"[wallet]   {json.dumps(secret_lst)}")
    print(f"[wallet] Keypair also saved to: {keypair_path}")
    return keypair
