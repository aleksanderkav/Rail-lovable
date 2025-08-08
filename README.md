# Rail-lovable (Scheduler)

Lightweight Railway worker that:
1) Fetches tracked queries from Supabase (optional), or uses a hardcoded list.
2) Calls your external scraper at `$SCRAPER_BASE_URL/scrape?query=...`
3) Posts the payload to your Supabase Edge Function (`$SUPABASE_FUNCTION_URL`) for storage.

## Env vars (set in Railway)
- SCRAPER_BASE_URL: https://scraper-production-22f6.up.railway.app
- SUPABASE_FUNCTION_URL: <Edge Function URL>
- SUPABASE_FUNCTION_TOKEN: <Anon or Service Role key for EF auth>
- SUPABASE_URL (optional): <Supabase base URL>
- SUPABASE_SERVICE_ROLE_KEY (optional): <Service role key>
- BATCH_LIMIT (default 20)
- SLEEP_JITTER_SECS (default 2.0)
- REQUEST_TIMEOUT_SECS (default 60)

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit values
python scheduled_scraper.py
```

## Deploy on Railway
1. Create a new Service → Python → connect this GitHub repo.
2. Set Variables from .env.example (never commit secrets).
3. The service will automatically start with the worker command defined in `railway.json` and `Procfile`.
4. Create a Cron Job:
   - Command: `python scheduled_scraper.py`
   - Schedule: `*/30 * * * *` (every 30 minutes) or `0 * * * *` (hourly)
5. Run the job manually once to test and check logs.

## Notes
- If you don't want DB lookups yet, use HARDCODED_QUERIES in scheduled_scraper.py.
- CORS doesn't apply (server-to-server).
- If the Edge Function requires auth, pass SUPABASE_FUNCTION_TOKEN in the Authorization header. 