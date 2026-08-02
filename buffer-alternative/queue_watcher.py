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
Failed posts stay in queue (will retry next run).
"""
import json
import os
import sys
from datetime import datetime, timezone

# Import from publish.py in same folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from publish import publish

QUEUE_FILE = os.environ.get("QUEUE_FILE", "queue.json")


def load():
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE) as f:
        return json.load(f)


def save(items):
    with open(QUEUE_FILE, "w") as f:
        json.dump(items, f, indent=2)


def main():
    queue = load()
    if not queue:
        return  # silent - nothing to do

    now = datetime.now(timezone.utc)
    print(f"[{now.isoformat()}] Checking queue ({len(queue)} items)")

    remaining = []
    published = 0
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
        except Exception as e:
            print(f"  ! Failed ({e}). Will retry next run.")
            remaining.append(item)

    save(remaining)
    print(f"  Published {published}, {len(remaining)} remaining")


if __name__ == "__main__":
    main()
