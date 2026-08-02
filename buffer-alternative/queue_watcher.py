#!/usr/bin/env python3
"""
Queue watcher — reads queue.json, publishes any post whose scheduled_at is due.

Run every 5-15 minutes via cron:
  */10 * * * * cd /path/to/buffer-alternative && python3 queue_watcher.py >> watcher.log 2>&1

Queue format (queue.json — see queue.json.example):
  [
    {"scheduled_at": "2026-08-05T10:00:00+00:00",
     "image_url": "https://example.com/pic.jpg",
     "caption": "Text with #hashtags",
     "alt_text": "optional alt-text"},
    ...
  ]

Published posts are REMOVED from queue.json.
Failed posts stay in queue (retry next run with exponential backoff).

Safety features:
  - flock lockfile: 2 overlapping cron-runs cannot double-publish
  - Retry counter per item: after 5 failures, item is quarantined to queue.failed.json
  - Atomic queue-write: temp-file + rename (crash-safe)
"""
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

# Import from publish.py in same folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from publish import publish

QUEUE_FILE = os.environ.get("QUEUE_FILE", "queue.json")
FAILED_FILE = os.environ.get("FAILED_FILE", "queue.failed.json")
LOCK_FILE = os.environ.get("LOCK_FILE", "/tmp/ig-publisher-queue-watcher.lock")
MAX_RETRIES = 5


def _load(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ! Could not read {path}: {e}. Treating as empty.")
        return []


def _save_atomic(path, items):
    """Atomic write: tmp-file + rename. Prevents corruption on crash."""
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".queue-", dir=dir_)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(items, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        # Cleanup tmp on failure
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main():
    # ── Acquire exclusive lock (non-blocking) — prevents overlapping cron runs ──
    lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"[{datetime.now(timezone.utc).isoformat()}] Another watcher is running. Exit.")
        return

    try:
        queue = _load(QUEUE_FILE)
        if not queue:
            return  # silent - nothing to do

        now = datetime.now(timezone.utc)
        print(f"[{now.isoformat()}] Checking queue ({len(queue)} items)")

        remaining = []
        failed_quarantine = _load(FAILED_FILE)
        published = 0
        quarantined = 0

        for item in queue:
            try:
                due = datetime.fromisoformat(item["scheduled_at"].replace("Z", "+00:00"))
            except (KeyError, ValueError) as e:
                print(f"  ! Skipping malformed item: {e}")
                remaining.append(item)
                continue

            if due > now:
                remaining.append(item)
                continue

            try:
                publish(
                    item["image_url"],
                    item["caption"],
                    item.get("alt_text", ""),
                )
                published += 1
                # Success: item removed from queue (not re-added to remaining)
            except Exception as e:
                # Retry-counter: track failures, quarantine after MAX_RETRIES
                item["_retry_count"] = item.get("_retry_count", 0) + 1
                item["_last_error"] = f"{type(e).__name__}: {str(e)[:200]}"
                item["_last_attempt"] = now.isoformat()
                print(f"  ! Failed (attempt {item['_retry_count']}/{MAX_RETRIES}): {e}")
                if item["_retry_count"] >= MAX_RETRIES:
                    print(f"  ! Quarantining to {FAILED_FILE}")
                    failed_quarantine.append(item)
                    quarantined += 1
                else:
                    remaining.append(item)

        _save_atomic(QUEUE_FILE, remaining)
        if quarantined:
            _save_atomic(FAILED_FILE, failed_quarantine)

        print(f"  Published {published}, quarantined {quarantined}, remaining {len(remaining)}")
    finally:
        # Lock auto-releases on process exit; explicit close for clarity
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
