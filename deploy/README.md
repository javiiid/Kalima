# KALIMA — deployment

One host, one container for the app, Caddy in front for TLS. The Python server
binds a private interface and is **never** published directly to the internet;
Caddy is the only thing on ports 80/443.

## Bring-up (< 30 minutes)

1. **DNS.** Point `books.example.com` (A/AAAA) at the host. Caddy needs this to
   issue the certificate; without it the first request stalls on ACME.
2. **Docker.** Install Docker Engine + Compose v2, open 80/443 in the firewall.
3. **Provider key.** Create `config/config.yaml` next to this file's parent
   (`../config/config.yaml`) with the OpenAI-compatible block from `readme.md`:

   ```yaml
   openai:
     api_key: "sk-..."
     base_url: "https://api.openai.com/v1"
   translation:
     default_model: "gpt-5.6-luna"
   ```

   It is mounted read-write at `/app/config` so the admin `/account` page can
   update it. It is gitignored: never commit it.
4. **Start.**

   ```bash
   cd deploy
   KALIMA_DOMAIN=books.example.com docker compose up -d --build
   ```

5. **Verify.**

   ```bash
   curl -fsS https://books.example.com/api/version
   curl -fsSI https://books.example.com/ | grep -i strict-transport-security
   ```

## Environment

| Variable | Purpose |
| --- | --- |
| `KALIMA_DOMAIN` | Public hostname. Feeds `KALIMA_ALLOWED_HOSTS` and CORS. |
| `KALIMA_ALLOWED_HOSTS` | Host header allowlist (DNS-rebinding guard). No `*`. |
| `KALIMA_CORS_ORIGINS` | Explicit origin allowlist for cross-origin calls. No `*`. |
| `KALIMA_SECURE_COOKIES` | `1` adds `Secure` to session/CSRF cookies. |
| `KALIMA_USER_QUOTA_BYTES` | Per-user storage cap (default 5 GiB). |
| `KALIMA_UI_DIST` | Where the built React bundle lives (set in the image). |
| `KALIMA_SERVE_SPA` | `0` disables SPA serving (keeps legacy pages). |
| `KALIMA_ENV` | `production` turns on secure cookies + the non-loopback warning. |

Adding an origin is an allowlist edit, never a wildcard: the old local
single-user build used `*` and that assumption dies at launch.

## Backups

`data/kalima.db` uses WAL; a raw `cp` can catch a mid-write state. Take copies
with the SQLite backup API, which is WAL-safe (`app/storage/database.py`):

```bash
docker compose exec app python -c \
  "from app.storage.database import db; print(db.backup_database('cron'))"
```

The app also takes a once-a-day safety copy at startup when the newest backup
is older than 24h, keeping the last 5 under `data/backups/`. A container that
runs for weeks should add the cron above as a host timer or a sidecar.

**Restore drill** (do this before launch, on a copy):

```bash
docker compose down
docker compose run --rm app python - <<'PY'
from app.storage.database import db
print(db.list_backups()[:3])   # newest first
PY
# stop the app, replace data/kalima.db with the chosen backup, start it again
# and confirm /api/jobs lists the expected jobs.
```

## Observability

- **Counters:** `GET /api/metrics` (JSON) and `GET /api/metrics?format=prometheus`.
  Admin-only. `kalima_http_requests_total{status_class="5xx"}` is the 5xx rate.
- **Structured logs:** `data/logs/app.jsonl`, one JSON object per request with
  `method`, `path`, `status`, `duration_ms`; 5xx lines are `level:"ERROR"`.
- **Alerts:** `deploy/alert.rules.yml` ships a 5xx-rate page, a 5xx warning and
  an `up == 0` page for a Prometheus that scrapes `/api/metrics?format=prometheus`.

## Acceptance checklist

- [ ] Fresh host → product reachable in under 30 minutes from this file.
- [ ] `curl -I https://.../` shows HSTS + `X-Content-Type-Options: nosniff`.
- [ ] Port 8765 is not reachable from the internet (`expose`, not `ports`).
- [ ] `kill -9` the app container mid-book → on restart the job resumes from the
      last committed chunk (`restore_jobs`), never re-marked complete.
- [ ] Restore-from-backup drill passes (jobs list matches the backup).
