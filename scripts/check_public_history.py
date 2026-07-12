#!/usr/bin/env python3
"""Scan every reachable Git object for paths or text outside public scope."""

from __future__ import annotations

import fnmatch
import io
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


def _run(*args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.check_output(args, cwd=ROOT, input=input_bytes)


def _looks_textual(data: bytes) -> bool:
    return b"\0" not in data[:8192]


def _small_blob_ids(object_ids: list[str], max_bytes: int) -> list[str]:
    request = "".join(f"{object_id}\n" for object_id in object_ids).encode()
    output = _run(
        "git",
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=request,
    )
    blobs: list[str] = []
    for line in output.splitlines():
        object_id, object_type, raw_size = line.decode().split()
        if object_type == "blob" and int(raw_size) <= max_bytes:
            blobs.append(object_id)
    return blobs


def _blob_contents(object_ids: list[str]):
    request = "".join(f"{object_id}\n" for object_id in object_ids).encode()
    output = _run("git", "cat-file", "--batch", input_bytes=request)
    stream = io.BytesIO(output)
    for expected_id in object_ids:
        header = stream.readline().decode().strip().split()
        if len(header) != 3:
            raise RuntimeError(f"Unexpected git cat-file header for {expected_id}: {header!r}")
        object_id, object_type, raw_size = header
        if object_id != expected_id or object_type != "blob":
            raise RuntimeError(f"Unexpected git object response for {expected_id}: {header!r}")
        data = stream.read(int(raw_size))
        if stream.read(1) != b"\n":
            raise RuntimeError(f"Missing git cat-file delimiter after {expected_id}")
        yield object_id, data


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    patterns = manifest["forbidden_tracked_globs"]
    forbidden_literals = [literal.encode() for literal in manifest["forbidden_literals"]]
    max_bytes = int(manifest["max_text_scan_bytes"])
    errors: list[str] = []

    raw_objects = _run("git", "rev-list", "--objects", "--all").decode(
        "utf-8", errors="surrogateescape"
    )
    object_paths: dict[str, str] = {}
    for line in raw_objects.splitlines():
        object_id, separator, path = line.partition(" ")
        if not separator:
            continue
        object_paths.setdefault(object_id, path)
        for pattern in patterns:
            if fnmatch.fnmatchcase(path, pattern):
                errors.append(f"forbidden historical path: {path} (object {object_id[:12]})")
                break

    blob_ids = _small_blob_ids(list(object_paths), max_bytes)
    for object_id, data in _blob_contents(blob_ids):
        path = object_paths[object_id]
        if not _looks_textual(data):
            continue

        if path != MANIFEST_REL:
            for literal in forbidden_literals:
                if literal in data:
                    errors.append(
                        f"forbidden historical literal {literal.decode()!r} in {path} "
                        f"(object {object_id[:12]})"
                    )

        for label, pattern in CREDENTIAL_PATTERNS.items():
            if pattern.search(data):
                errors.append(f"historical credential-shaped {label} in {path} (object {object_id[:12]})")

    if errors:
        print("Public history check failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Public history check passed: {len(blob_ids)} reachable blobs scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
