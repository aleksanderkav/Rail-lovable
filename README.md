# Rail-lovable (Scheduler + API)

Lightweight Railway service that provides:
1) **Scheduled scraping**: Fetches tracked queries from Supabase and runs them on a cron schedule
2) **On-demand scraping API**: FastAPI endpoint for immediate scraping requests from Lovable
3) **External scraper integration**: Calls your scraper at `$SCRAPER_BASE_URL/scrape?query=...`
4) **Supabase storage**: Posts results to your Supabase Edge Function for storage

## Env vars (set in Railway)
**Required:**
- `SCRAPER_BASE_URL`: https://scraper-production-22f6.up.railway.app
- `SUPABASE_FUNCTION_URL`: Your Supabase Edge Function URL
- `SUPABASE_FUNCTION_TOKEN`: Anon or Service Role key for Edge Function auth

**Optional:**
- `SUPABASE_URL`: https://zuhazlfmgcrmajnxijsm.supabase.co (for database queries)
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key (for database access)
- `BATCH_LIMIT`: 20 (default)
- `SLEEP_JITTER_SECS`: 2.0 (default)
- `REQUEST_TIMEOUT_SECS`: 60 (default)

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit values

# Start the FastAPI server
python main.py

# Or run the cron scraper directly
python cron_scraper.py
```

## Deploy on Railway
1. Create a new Service → Python → connect this GitHub repo.
2. Set Variables from .env.example (never commit secrets).
3. The service will automatically start the FastAPI server on the configured port.
4. Create a Cron Job for scheduled scraping:
   - Command: `python cron_scraper.py`
   - Schedule: `*/30 * * * *` (every 30 minutes) or `0 * * * *` (hourly)
5. Test the API endpoints and cron job manually.

## API Endpoints

### POST /scrape-now
On-demand scraping endpoint for Lovable integration.

**Request:**
```json
{
  "query": "Pikachu Base Set 1st Edition PSA 10"
}
```

**Response:**
```json
{
  "ok": true,
  "items": [
    {
      "title": "Pikachu Base Set 1st Edition PSA 10",
      "url": "https://ebay.com/...",
      "id": "123456789",
      "price": 1500.0,
      "currency": "USD",
      "ended_at": "2025-08-15T00:00:00Z",
      "source": "ebay"
    }
  ],
  "externalOk": true,
  "efStatus": 200,
  "efBody": "{\"success\": true}"
}
```

**Error Response:**
```json
{
  "ok": false,
  "error": "Scraper HTTP error: 500",
  "step": "scraper"
}
```

### GET /
Health check endpoint.
```json
{
  "ok": true,
  "service": "rail-lovable"
}
```

### GET /health
Detailed health check.
```json
{
  "ok": true,
  "time": "2025-08-08T16:30:00.000000Z",
  "env": {
    "scraper": true,
    "ef": true
  },
  "net": {
    "dns": true,
    "scraperReachable": true
  },
  "endpoints": ["/scrape-now", "/normalize-test", "/ingest-items"]
}
```

### POST /normalize-test
Normalize items locally without calling the Edge Function. Can either normalize provided items or scrape and normalize based on a query.

**Request (with items):**
```json
{
  "items": [
    {
      "title": "Charizard Base Set Unlimited Holo PSA 9",
      "price": 450.00,
      "currency": "USD",
      "source": "ebay"
    }
  ]
}
```

**Request (with query):**
```json
{
  "query": "Blastoise Base Set Unlimited PSA 9",
  "limit": 10
}
```

**Response:**
```json
{
  "ok": true,
  "source": "items",
  "count": 1,
  "items": [
    {
      "title": "Charizard Base Set Unlimited Holo PSA 9",
      "price": 450.00,
      "currency": "USD",
      "source": "ebay",
      "parsed": {
        "set_name": "base set",
        "edition": "unlimited",
        "number": null,
        "year": null,
        "grading_company": "psa",
        "grade": "9",
        "is_holo": true,
        "franchise": "pokemon"
      },
      "canonical_key": "pokemon|base_set|charizard|unlimited|unknown_number|unknown_year|psa|9",
      "confidence": {
        "title_parse": 0.75,
        "overall": 0.8
      }
    }
  ],
  "trace": "abcd1234"
}
```

### POST /ingest-items
Forward normalized (or raw) items to the Supabase Edge Function. **Defaults to dry_run=true for safety.**

**Request:**
```json
{
  "raw_query": "Blastoise Base Set Unlimited PSA 9",
  "items": [
    {
      "title": "Blastoise Base Set Unlimited Holo PSA 9",
      "price": 350.00,
      "currency": "USD",
      "canonical_key": "pokemon|base_set|blastoise|unlimited|unknown_number|unknown_year|psa|9"
    }
  ],
  "dry_run": true
}
```

**Response:**
```json
{
  "ok": true,
  "externalOk": true,
  "count": 1,
  "items": [
    {
      "card_id": "uuid-here",
      "created": true,
      "price_entry_id": "uuid-here",
      "canonical_key": "pokemon|base_set|blastoise|unlimited|unknown_number|unknown_year|psa|9",
      "decision": "created",
      "confidence": 0.8
    }
  ],
  "trace": "abcd1234"
}
```

## cURL Examples

### Test normalization with items
```bash
curl -X POST http://localhost:8000/normalize-test \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "title": "Charizard Base Set Unlimited Holo PSA 9",
        "price": 450.00,
        "currency": "USD",
        "source": "ebay"
      }
    ]
  }'
```

### Test normalization with query (scrapes and normalizes)
```bash
curl -X POST http://localhost:8000/normalize-test \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Blastoise Base Set Unlimited PSA 9",
    "limit": 5
  }'
```

### Test ingestion with dry_run (safe)
```bash
curl -X POST http://localhost:8000/ingest-items \
  -H "Content-Type: application/json" \
  -d '{
    "raw_query": "Blastoise Base Set Unlimited PSA 9",
    "items": [
      {
        "title": "Blastoise Base Set Unlimited Holo PSA 9",
        "price": 350.00,
        "currency": "USD",
        "canonical_key": "pokemon|base_set|blastoise|unlimited|unknown_number|unknown_year|psa|9"
      }
    ],
    "dry_run": true
  }'
```

### Test ingestion without dry_run (actually persists)
```bash
curl -X POST http://localhost:8000/ingest-items \
  -H "Content-Type: application/json" \
  -d '{
    "raw_query": "Blastoise Base Set Unlimited PSA 9",
    "items": [
      {
        "title": "Blastoise Base Set Unlimited Holo PSA 9",
        "price": 350.00,
        "currency": "USD",
        "canonical_key": "pokemon|base_set|blastoise|unlimited|unknown_number|unknown_year|psa|9"
      }
    ],
    "dry_run": false
  }'
```

## Notes
- If you don't want DB lookups yet, use HARDCODED_QUERIES in scheduled_scraper.py.
- CORS doesn't apply (server-to-server).
- If the Edge Function requires auth, pass SUPABASE_FUNCTION_TOKEN in the Authorization header.
- **Important**: `/ingest-items` defaults to `dry_run: true` for safety. You must explicitly set `dry_run: false` to actually persist data.

## Troubleshooting

**Container crashes on startup:**
- Check that all required environment variables are set in Railway dashboard
- Look for "ERROR:" messages in the logs for specific missing variables

**No queries running:**
- If using database: Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
- If not using database: The script will use hardcoded sample queries 