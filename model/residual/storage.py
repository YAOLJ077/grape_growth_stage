"""Exclusive atomic publication and fingerprint checks for long-running pilots."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def publish(path, writer):
    """Complete artifact first, then publish without replacing any destination."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".publishing-", dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        writer(temporary)
        if path.exists():
            if digest(path) != digest(temporary):
                raise ValueError(f"Existing artifact differs: {path}")
        else:
            os.link(temporary, path)


def json_once(path, value):
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    publish(path, lambda temp: temp.write_text(text))


def table_once(path, frame):
    publish(path, lambda temp: frame.to_csv(temp, index=False, date_format="%Y-%m-%d"))


def check_hashes(mapping):
    for name, expected in mapping.items():
        path = Path(name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"Input/artifact fingerprint checksum mismatch: {path}")


@contextmanager
def run_lock(output):
    # flock is released by the OS after interruption; stale files are harmless.
    with (Path(output) / ".run.lock").open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another process is writing this pilot directory") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
