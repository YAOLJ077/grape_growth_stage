#!/usr/bin/env python3
"""Download only the two canonical phenology LFS objects into a local cache.

Uses the configured GitHub Git credential without printing it. Original pointer
files remain unchanged. Downloaded bytes must match each pointer's size and SHA256.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[2] / 'data/phenology'
NAMES = ("france_grape_phenology_complete.csv", "germany_grape_phenology_complete.csv")


def main():
    remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=ROOT, text=True
    ).strip()
    if remote != "https://github.com/YAOLJ077/grape_growth_stage.git":
        raise RuntimeError("Unexpected remote; refusing automatic credential use")
    cache = ROOT / ".source_cache"
    cache.mkdir(exist_ok=True)
    pending = []
    for name in NAMES:
        source = ROOT / "processed" / name
        with source.open("rb") as stream:
            header = stream.read(512)
        if not header.startswith(b"version https://git-lfs.github.com/spec/v1"):
            continue
        lines = header.decode("ascii").splitlines()
        oid = next(line.split("sha256:")[1] for line in lines if line.startswith("oid "))
        size = int(next(line.split()[1] for line in lines if line.startswith("size ")))
        target = cache / name
        if target.exists() and target.stat().st_size == size:
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() == oid:
                print(f"Verified cached input: {name}", flush=True)
                continue
        pending.append((name, oid, size))
    if not pending:
        return
    credentials = subprocess.run(
        ["git", "credential", "fill"], cwd=ROOT,
        input="protocol=https\nhost=github.com\n\n", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, check=False,
    )
    headers = {"Accept": "application/vnd.git-lfs+json", "Content-Type": "application/vnd.git-lfs+json"}
    if credentials.returncode == 0:
        fields = dict(line.split("=", 1) for line in credentials.stdout.splitlines() if "=" in line)
        if fields.get("username") and fields.get("password"):
            auth = (fields["username"] + ":" + fields["password"]).encode()
            headers["Authorization"] = "Basic " + base64.b64encode(auth).decode()
    body = json.dumps({"operation": "download", "transfers": ["basic"],
                       "objects": [{"oid": oid, "size": size} for _, oid, size in pending]}).encode()
    request = urllib.request.Request(remote + "/info/lfs/objects/batch", data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            objects = json.load(response)["objects"]
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"LFS batch request failed with HTTP {error.code}") from None
    actions = {obj["oid"]: obj for obj in objects}
    for name, oid, size in pending:
        obj = actions[oid]
        if "error" in obj:
            raise RuntimeError(f"LFS object unavailable for {name}: code {obj['error'].get('code')}")
        action = obj["actions"]["download"]
        if not action["href"].startswith("https://"):
            raise RuntimeError("Refusing a non-HTTPS download")
        request = urllib.request.Request(action["href"], headers=action.get("header", {}))
        target = cache / name
        temporary = target.with_suffix(".csv.part")
        digest = hashlib.sha256()
        total = 0
        print(f"Downloading {name} ({size:,} bytes)", flush=True)
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                digest.update(block)
                total += len(block)
                output.write(block)
        if total != size or digest.hexdigest() != oid:
            raise RuntimeError(f"Integrity check failed for {name}; partial file retained")
        temporary.replace(target)
        print(f"SHA256 verified: {name}", flush=True)


if __name__ == "__main__":
    main()
