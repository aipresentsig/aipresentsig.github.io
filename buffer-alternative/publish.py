#!/usr/bin/env python3
"""
Minimal IG single-image publisher — replaces $15/mo Buffer for one account.

Requires:
  - Instagram Business Account
  - Meta App with instagram_content_publish permission
  - Long-lived IG access token
  - Public URL for your image (imgbb, github-pages, cloudflare-r2, etc.)

Usage (one-off):
  IG_TOKEN=xxx IG_ACCOUNT_ID=xxx python3 publish.py \\
    --image-url https://example.com/pic.jpg \\
    --caption "Your caption with #hashtags"

Or with .env file:
  cp .env.example .env  # then edit with your tokens
  python3 publish.py --image-url URL --caption "text"

Zero external dependencies — Python stdlib only.
Total lines: ~80. Runs anywhere Python 3.9+ runs.
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# Load .env if present (simple key=value parser, no python-dotenv needed)
if os.path.exists(".env"):
    for line in open(".env"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

IG_TOKEN = os.environ.get("IG_TOKEN", "")
IG_ACCOUNT_ID = os.environ.get("IG_ACCOUNT_ID", "")
API = "https://graph.facebook.com/v22.0"


def post(path, data, max_retries=3):
    """POST helper — sends form-encoded body to Meta Graph API.

    Retries on transient errors (5xx, timeouts) with exponential backoff.
    Does NOT retry on 4xx (bad request / auth = permanent).
    """
    data["access_token"] = IG_TOKEN
    body = urllib.parse.urlencode(data).encode()
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(f"{API}/{path}", data=body, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last_err = e
            # 4xx = client error (bad token, malformed request) — do not retry
            if 400 <= e.code < 500:
                raise
            # 5xx = server error — retry with backoff
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    if last_err:
        raise last_err


def wait_finished(container_id, max_wait=60):
    """Poll container until FINISHED (2-15s typical). Meta needs time to process."""
    for _ in range(max_wait // 3):
        url = f"{API}/{container_id}?fields=status_code&access_token={IG_TOKEN}"
        with urllib.request.urlopen(url, timeout=10) as r:
            status = json.loads(r.read()).get("status_code")
        if status == "FINISHED":
            return True
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container failed: {status}")
        time.sleep(3)
    raise TimeoutError(f"container not FINISHED after {max_wait}s")


def publish(image_url, caption, alt_text=""):
    """Publish single image to IG. Returns permalink."""
    if not IG_TOKEN or not IG_ACCOUNT_ID:
        raise RuntimeError("Set IG_TOKEN and IG_ACCOUNT_ID in .env or environment")

    print(f"→ Creating container for {image_url[:60]}...")
    container = post(f"{IG_ACCOUNT_ID}/media", {
        "image_url": image_url,
        "caption": caption,
        "alt_text": alt_text[:1000] if alt_text else "",
    })
    container_id = container["id"]

    print(f"→ Waiting for container {container_id} to finish processing...")
    wait_finished(container_id)

    print(f"→ Publishing container {container_id}...")
    result = post(f"{IG_ACCOUNT_ID}/media_publish", {"creation_id": container_id})
    media_id = result["id"]

    # Fetch permalink for confirmation
    url = f"{API}/{media_id}?fields=permalink&access_token={IG_TOKEN}"
    with urllib.request.urlopen(url, timeout=10) as r:
        permalink = json.loads(r.read()).get("permalink", f"(media_id: {media_id})")

    print(f"✓ Published: {permalink}")
    return permalink


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Post to Instagram (replaces Buffer $15/mo)")
    p.add_argument("--image-url", required=True, help="Public image URL")
    p.add_argument("--caption", required=True, help="Post caption with hashtags")
    p.add_argument("--alt-text", default="", help="Accessibility alt-text (optional)")
    args = p.parse_args()
    publish(args.image_url, args.caption, args.alt_text)
