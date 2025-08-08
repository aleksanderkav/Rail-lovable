import os
import asyncio
import json
import time
import httpx
from datetime import datetime, timezone

SCRAPER_BASE_URL = os.environ["SCRAPER_BASE_URL"]
SUPABASE_FUNCTION_URL = os.environ["SUPABASE_FUNCTION_URL"]
SUPABASE_FUNCTION_TOKEN = os.environ["SUPABASE_FUNCTION_TOKEN"]

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

BATCH_LIMIT = int(os.getenv("BATCH_LIMIT", "20"))
SLEEP_JITTER_SECS = float(os.getenv("SLEEP_JITTER_SECS", "2.0"))
REQUEST_TIMEOUT_SECS = float(os.getenv("REQUEST_TIMEOUT_SECS", "60"))

# For first runs without DB, you can hardcode sample queries:
HARDCODED_QUERIES = [
    # "Pikachu Base Set 1st Edition PSA 10",
    # "Charizard Base Set Unlimited Holo PSA 8",
]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

async def fetch_tracked_queries():
    """Fetch active tracked queries from Supabase REST if credentials provided; otherwise use fallback hardcoded list."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return [{"query": q} for q in HARDCODED_QUERIES]

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/tracked_queries"
        f"?select=*&is_active=eq.true"
        f"&order=last_scraped_at.nullsfirst().order=created_at.asc"
        f"&limit={BATCH_LIMIT}"
    )
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
        r = await client.get(endpoint, headers=headers)
        r.raise_for_status()
        return r.json()

async def scrape(query: str):
    """Call the external scraper: /scrape?query=..."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
        r = await client.get(f"{SCRAPER_BASE_URL}/scrape", params={"query": query})
        r.raise_for_status()
        return r.json()  # expected: { query, prices[], average, timestamp, items?[] }

async def post_to_edge_function(payload: dict):
    """Post payload to the Supabase Edge Function (server-side) for storage."""
    headers = {
        "Authorization": f"Bearer {SUPABASE_FUNCTION_TOKEN}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
        r = await client.post(SUPABASE_FUNCTION_URL, headers=headers, content=json.dumps(payload))
        r.raise_for_status()
        return r.json()

async def process_query(query: str):
    started = now_iso()
    print(f"[cron] {started} scraping: {query}")
    try:
        payload = await scrape(query)
        result = await post_to_edge_function(payload)
        print(f"[cron] ok: {query} -> {result}")
    except Exception as e:
        print(f"[cron] error: {query} -> {e}")

async def main():
    print(f"[cron] started {now_iso()}")
    queries = await fetch_tracked_queries()
    if not queries:
        print("[cron] no queries to run (enable SUPABASE_URL/SERVICE_ROLE_KEY or set HARDCODED_QUERIES).")
        return
    for q in queries:
        query = q["query"] if isinstance(q, dict) else str(q)
        await process_query(query)
        time.sleep(SLEEP_JITTER_SECS)

if __name__ == "__main__":
    asyncio.run(main()) 