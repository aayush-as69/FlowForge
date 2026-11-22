#!/usr/bin/env python3
"""Build a clean source zip of FlowForge and refuse to ship anything that must not leave the machine.

Usage: python scripts/make_release.py [output.zip]
"""
import fnmatch
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["package.json", "package-lock.json", "Dockerfile", "backend/requirements.txt"]
FORBIDDEN = [".env", ".env.*", "*.db", "*.db-wal", "*.db-shm", "*.sqlite", "*.sqlite3", ".secret_key", "*.pem", "*.key",
             "node_modules/*", ".next/*", "*/__pycache__/*", "*.pyc", "backend/.pylibs/*", ".git/*", ".pytest_cache/*"]
ALLOWED = {".env.example"}


def candidate_files() -> list[str]:
    """Tracked plus untracked-but-not-ignored files, so a release matches what git would commit."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         check=True, capture_output=True, text=True).stdout
    return sorted(set(filter(None, out.splitlines())))


def forbidden(path: str) -> bool:
    if path in ALLOWED:
        return False
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(name, pat) for pat in FORBIDDEN)


def main() -> int:
    files = [f for f in candidate_files() if (ROOT / f).is_file()]
    missing = [r for r in REQUIRED if r not in files]
    if missing:
        print("Refusing to build: missing " + ", ".join(missing) +
              ("\n  (run `npm install` and commit package-lock.json so installs are reproducible)" if "package-lock.json" in missing else ""))
        return 1
    bad = [f for f in files if forbidden(f)]
    if bad:
        print("Refusing to build: forbidden files would be included:\n  " + "\n  ".join(bad))
        return 1
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "flowforge-release.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(ROOT / f, f"flowforge/{f}")
    print(f"Wrote {target} ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
