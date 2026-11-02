"""Scan tracked/unignored source or built assets without printing secret values."""

import argparse
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--assets", type=Path)
args = parser.parse_args()
patterns = [
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"sb_secret_[A-Za-z0-9_-]{20,}"),
]
if args.assets:
    paths = list((root / args.assets).rglob("*"))
else:
    output = subprocess.check_output(["git", "ls-files", "--cached", "--others",
                                      "--exclude-standard", "-z"], cwd=root)
    paths = [root / path for path in output.decode().split("\0") if path]
failed = []
for path in paths:
    if not path.is_file() or path.name == Path(__file__).name:
        continue
    content = path.read_text(encoding="utf-8", errors="ignore")
    if any(pattern.search(content) for pattern in patterns):
        failed.append(str(path.relative_to(root)))
if failed:
    raise SystemExit("Potential secrets found in: " + ", ".join(failed))
print(f"Secret-pattern scan passed ({len(paths)} files).")
