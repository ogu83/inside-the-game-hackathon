"""Sync required app packages into hosted/src/commentary/app/ for self-contained deployment."""

import shutil
from pathlib import Path

HOSTED_DIR = Path(__file__).resolve().parent
REPO_ROOT = HOSTED_DIR.parent
SOURCE_APP = REPO_ROOT / "app"
TARGET_APP = HOSTED_DIR / "src" / "commentary" / "app"

SUBPACKAGES = ["agents", "ledger", "simulator"]
FILES = ["__init__.py", "observability.py"]


def sync(target_app: Path | None = None) -> Path:
    """Copy required app modules into hosted build context, skipping cache files."""
    dest = target_app if target_app is not None else TARGET_APP
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    for filename in FILES:
        src = SOURCE_APP / filename
        if src.exists():
            shutil.copy2(src, dest / filename)

    for pkg in SUBPACKAGES:
        src_pkg = SOURCE_APP / pkg
        dest_pkg = dest / pkg
        shutil.copytree(
            src_pkg,
            dest_pkg,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
        )
    print(f"Synced app packages to {dest}")
    return dest


if __name__ == "__main__":
    sync()
