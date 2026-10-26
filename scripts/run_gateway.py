"""Foreground local gateway; environment values override the optional .env file."""
import sys
from pathlib import Path

from local_env import load_env

ROOT = Path(__file__).resolve().parents[1]
load_env(ROOT / ".env")
sys.path.insert(0, str(ROOT / "gateway/src"))

from chainguard_gateway.__main__ import main

if __name__ == "__main__":
    main()
