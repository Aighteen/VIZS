"""Reproducible loopback backend. Pairing writes only to ignored .env, never logs keys."""
import argparse
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def ensure_pairing(env_file):
    path = Path(env_file)
    values = dotenv_values(path, interpolate=False, encoding="utf-8-sig")
    if values.get("VIZS_EXTENSION_TOKEN"):
        return False
    with path.open("a", encoding="utf-8") as output:
        output.write("\nVIZS_EXTENSION_TOKEN=" + secrets.token_urlsafe(32) + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Run VIZS local backend; offline by default")
    parser.add_argument("--pair", action="store_true", help="Create pairing token in ignored root .env if absent")
    parser.add_argument("--live", action="store_true", help="Enable provider requests that may use credits")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be in 1024..65535")
    if args.pair:
        ensure_pairing(ROOT / ".env")
        print("Pairing configured in root .env; copy VIZS_EXTENSION_TOKEN locally into extension settings. Value omitted.")
    os.environ["VIZS_PROVIDER_MODE"] = "live" if args.live else "offline"
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
