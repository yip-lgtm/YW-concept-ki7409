"""Manually load .env file with ${VAR} expansion.

python-dotenv does NOT expand ${VAR} syntax. This loader does it manually.
Usage:
    from env_loader import load_env
    load_env()
"""
import os
from pathlib import Path
import re


def _expand(value: str) -> str:
    """Expand ${VAR} references from os.environ."""
    def replacer(match):
        var = match.group(1)
        return os.environ.get(var, match.group(0))
    return re.sub(r"\$\{([A-Z_][A-Z0-9_]*)\}", replacer, value)


def load_env(env_path: str | Path | None = None) -> None:
    """Read .env file and inject into os.environ.

    - Lines starting with # are comments
    - Empty lines are skipped
    - Format: KEY=VALUE
    - VALUE can use ${OTHER_VAR} for cross-references
    """
    if env_path is None:
        env_path = Path(__file__).resolve().parents[1] / ".env"
    env_path = Path(env_path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        value = _expand(value)
        if key not in os.environ:
            os.environ[key] = value


if __name__ == "__main__":
    load_env()
    for k in sorted(os.environ):
        if any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            print(f"{k}=***")
        else:
            print(f"{k}={os.environ[k]}")
