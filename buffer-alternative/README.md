# BUFFER — Self-hosted IG Publisher (~80 lines Python)

**Replaces:** Buffer Pro ($15/mo), Later Growth ($25/mo), Metricool Small ($22/mo)
**Cost:** $0/mo forever (uses free Meta Graph API + your own hardware)
**Setup:** 3 steps, ~20 minutes

---

## Why this exists

Buffer + similar SaaS tools charge $15-40/mo to schedule Instagram posts.

The actual work — POST /media, wait for FINISHED, POST /media_publish — is 30 lines of Python calling Meta's free Graph API.

This repo is that Python.

- `publish.py` — the ~80-line single-image publisher
- `queue_watcher.py` — polls `queue.json`, publishes anything due
- `docker-compose.yml` — optional 1-service deploy
- Zero external Python dependencies (stdlib only)

**No API subscription needed** on top of what you already have (Meta accounts are free).

---

## What it does

- Publishes single-image posts to Instagram at scheduled times
- Zero cloud dependency after setup (your machine, your data)
- Simple JSON queue file — no database, no admin UI
- Works with any hosting: your laptop, a mini-PC, a $5/mo VPS, a homelab NUC

**What it does NOT do (yet):**
- Carousels, reels, stories (single image only for v1 simplicity)
- Multi-account (one account per instance)
- Analytics (use IG's built-in insights)
- Approval UI (add your own Telegram-bot in front)

Want carousels/reels? See the [full ZeroClaw stack](https://aipresentsig.github.io/homelab_starter_280eur.pdf) that this was extracted from.

---

## Setup — 3 steps

### 1. Get your Meta credentials (~10 min one-time)

**You need:**
- **Instagram Business Account** (convert from Personal in IG app if needed)
- A **Facebook Page** connected to that IG account
- A **Meta App** with `instagram_content_publish` permission

**Quick path:**
1. Create app: https://developers.facebook.com/apps/ → Business type → your Business Portfolio
2. Add product: **Instagram** → Instagram API setup
3. Add permission: `instagram_basic` + `instagram_content_publish`
4. Generate long-lived token (60 days): https://developers.facebook.com/tools/explorer
5. Find your IG-account ID:
   ```bash
   curl "https://graph.facebook.com/v22.0/me/accounts?access_token=YOUR_TOKEN"
   # Get page-id, then:
   curl "https://graph.facebook.com/v22.0/{page-id}?fields=instagram_business_account&access_token=YOUR_TOKEN"
   ```

**Not familiar with any of this?** Meta's docs are labyrinthine. The [Homelab Starter PDF](https://aipresentsig.github.io/homelab_starter_280eur.pdf) has a clearer walkthrough.

### 2. Configure

```bash
cp .env.example .env
# Edit .env — paste your IG_TOKEN and IG_ACCOUNT_ID
```

### 3. Test with one post

```bash
python3 publish.py \
  --image-url https://raw.githubusercontent.com/aipresentsig/aipresentsig.github.io/main/buffer-alternative/test-image.jpg \
  --caption "Testing my new self-hosted publisher. #selfhosted"
```

You should see:
```
→ Creating container for https://...
→ Waiting for container XXXX to finish processing...
→ Publishing container XXXX...
✓ Published: https://www.instagram.com/p/XXXX/
```

Check IG in a few seconds — post should be live.

---

## Scheduling posts

### Option A: Simple cron

```bash
# Add to crontab (every 10 min)
*/10 * * * * cd /path/to/buffer-alternative && python3 queue_watcher.py >> watcher.log 2>&1
```

Then edit `queue.json` (see `queue.json.example`) to add posts:
```json
[
  {
    "scheduled_at": "2026-08-05T10:00:00+00:00",
    "image_url": "https://your-cdn.com/pic.jpg",
    "caption": "Scheduled post text"
  }
]
```

Watcher publishes each post at its `scheduled_at`, then removes it from the queue.

### Option B: Docker

```bash
docker-compose up -d
# Container polls queue every 5 min, restarts automatically on reboot
```

### Option C: Systemd timer

```ini
# /etc/systemd/system/ig-publisher.service
[Unit]
Description=IG Publisher queue watcher

[Service]
Type=oneshot
WorkingDirectory=/path/to/buffer-alternative
ExecStart=/usr/bin/python3 queue_watcher.py
EnvironmentFile=/path/to/buffer-alternative/.env

# /etc/systemd/system/ig-publisher.timer
[Unit]
Description=Run IG Publisher every 10 min

[Timer]
OnCalendar=*:0/10
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl enable --now ig-publisher.timer
```

---

## Where to host images

Meta's `/media` endpoint needs a **public HTTPS URL** for the image. Cheap options:

- **GitHub Pages** — free, no traffic limits practical, this repo uses it
- **Cloudflare R2** — free 10 GB, S3-compatible
- **imgbb** — free image-only host with API
- **Your own server** — if you have one

Do NOT use temporary URLs (bit.ly, expiring signed URLs).

---

## FAQ

**Q: Why not just use Buffer?**
A: You can. Buffer is fine. This exists for people who prefer owning the stack, or want zero recurring cost, or want to learn the Meta API.

**Q: Token expires in 60 days — is that a problem?**
A: Refresh it. Meta lets you exchange a long-lived token for a fresh one before expiry — one API call, doable via cron. This repo doesn't ship a refresher (yet), but the pattern is simple: `GET /oauth/access_token?grant_type=fb_exchange_token&client_id=...&client_secret=...&fb_exchange_token=OLD_TOKEN`.

**Q: What if Meta changes the API?**
A: They will. This repo pins v22.0. Read [changelog](https://developers.facebook.com/docs/graph-api/changelog) when updating.

**Q: Can I add approval-before-publish?**
A: Yes — wrap `publish()` in a Telegram-bot inline-button flow. Not shipped here to keep the core minimal. The [full ZeroClaw stack](https://aipresentsig.github.io/homelab_starter_280eur.pdf) has that pattern.

**Q: Rate limits?**
A: Meta allows 25 posts per 24h per Instagram Business Account. This publisher doesn't enforce — you should stay below.

---

## License

MIT — do whatever, no warranty. Fork it, extend it, sell services around it. Just don't blame me if Meta suspends your app.

---

## More resources

- **[€280 Homelab Starter Kit (PDF)](https://aipresentsig.github.io/homelab_starter_280eur.pdf)** — 4-weekend guide from bare parts to first self-hosted service
- **Follow the build:**
  - Instagram [@zeroclaw.build](https://instagram.com/zeroclaw.build)
  - X [@zeroclaw_build](https://x.com/zeroclaw_build)
  - Bluesky [@zeroclawbuild.bsky.social](https://bsky.app/profile/zeroclawbuild.bsky.social)
