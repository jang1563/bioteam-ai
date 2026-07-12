#!/usr/bin/env python3
"""Fail closed when the tracked tree crosses the public release boundary."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "release" / "public_release_manifest.json"
MANIFEST_REL = MANIFEST_PATH.relative_to(ROOT).as_posix()

CREDENTIAL_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "Anthropic key": re.compile(rb"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "Hugging Face token": re.compile(rb"\bhf_[A-Za-z0-9]{20,}\b"),
}


def _run(*args: str) -> bytes:
    return subprocess.check_output(args, cwd=ROOT)


def _tracked_paths() -> list[str]:
    raw = _run("git", "ls-files", "-z")
    return sorted(part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\0") if part)


def _looks_textual(data: bytes) -> bool:
    return b"\0" not in data[:8192]


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    tracked = _tracked_paths()
    tracked_set = set(tracked)
    errors: list[str] = []

    for required in manifest["required_paths"]:
        if required not in tracked_set:
            errors.append(f"required path is not tracked: {required}")

    for path in tracked:
        for pattern in manifest["forbidden_tracked_globs"]:
            if fnmatch.fnmatchcase(path, pattern):
                errors.append(f"forbidden tracked path: {path} (pattern: {pattern})")
                break

    max_bytes = int(manifest["max_text_scan_bytes"])
    forbidden_literals = [literal.encode() for literal in manifest["forbidden_literals"]]

    for path in tracked:
        file_path = ROOT / path
        if not file_path.is_file() or file_path.is_symlink() or file_path.stat().st_size > max_bytes:
            continue
        data = file_path.read_bytes()
        if not _looks_textual(data):
            continue

        if path != MANIFEST_REL:
            for literal in forbidden_literals:
                if literal in data:
                    errors.append(f"forbidden literal {literal.decode()!r} in {path}")

        for label, pattern in CREDENTIAL_PATTERNS.items():
            if pattern.search(data):
                errors.append(f"credential-shaped {label} in {path}")

    if errors:
        print("Public tree check failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Public tree check passed: {len(tracked)} tracked paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
