import os
import asyncio
import json
import time
import httpx
from datetime import datetime, timezone

# Required environment variables
SCRAPER_BASE_URL = os.getenv("SCRAPER_BASE_URL")
SUPABASE_FUNCTION_URL = os.getenv("SUPABASE_FUNCTION_URL")
SUPABASE_FUNCTION_TOKEN = os.getenv("SUPABASE_FUNCTION_TOKEN")

# Validate required environment variables
if not SCRAPER_BASE_URL:
    print("ERROR: SCRAPER_BASE_URL environment variable is required")
    print("Please set it in Railway dashboard: Variables → Add Variable")
    exit(1)

# Make Edge Function optional for testing
if not SUPABASE_FUNCTION_URL or SUPABASE_FUNCTION_URL == "<your-supabase-edge-function-url>":
    print("WARNING: SUPABASE_FUNCTION_URL not set or is placeholder - will only scrape, not store results")
    SUPABASE_FUNCTION_URL = None

if not SUPABASE_FUNCTION_TOKEN or SUPABASE_FUNCTION_TOKEN == "<anon-or-service-role-key>":
    print("WARNING: SUPABASE_FUNCTION_TOKEN not set or is placeholder - will only scrape, not store results")
    SUPABASE_FUNCTION_TOKEN = None

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

BATCH_LIMIT = int(os.getenv("BATCH_LIMIT", "20"))
SLEEP_JITTER_SECS = float(os.getenv("SLEEP_JITTER_SECS", "2.0"))
REQUEST_TIMEOUT_SECS = float(os.getenv("REQUEST_TIMEOUT_SECS", "60"))

# For first runs without DB, you can hardcode sample queries:
HARDCODED_QUERIES = [
    "Pikachu Base Set 1st Edition PSA 10",
    "Charizard Base Set Unlimited Holo PSA 8",
    "Blastoise Base Set Unlimited Holo PSA 9",
    "Venusaur Base Set Unlimited Holo PSA 7",
]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

async def fetch_tracked_queries():
    """Fetch active tracked queries from Supabase REST if credentials provided; otherwise use fallback hardcoded list."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        print("[cron] No Supabase credentials - using hardcoded queries")
        return [{"query": q} for q in HARDCODED_QUERIES]

    try:
        # Try a simpler query first to test connection
        endpoint = f"{SUPABASE_URL}/rest/v1/tracked_queries?select=query&limit={BATCH_LIMIT}"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
            r = await client.get(endpoint, headers=headers)
            if r.status_code == 404:
                print("[cron] tracked_queries table not found - using hardcoded queries")
                return [{"query": q} for q in HARDCODED_QUERIES]
            r.raise_for_status()
            queries = r.json()
            if queries:
                print(f"[cron] Found {len(queries)} queries from database")
                return queries
            else:
                print("[cron] No queries in database - using hardcoded queries")
                return [{"query": q} for q in HARDCODED_QUERIES]
    except Exception as e:
        print(f"[cron] Database query failed: {e} - using hardcoded queries")
        return [{"query": q} for q in HARDCODED_QUERIES]

async def scrape(query: str):
    """Call the external scraper: /scrape?query=..."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
            r = await client.get(f"{SCRAPER_BASE_URL}/scrape", params={"query": query})
            r.raise_for_status()
            return r.json()  # expected: { raw_query, prices[], average, timestamp, items?[] }
    except httpx.HTTPStatusError as e:
        print(f"[cron] Scraper HTTP error for '{query}': {e.response.status_code}")
        return {"raw_query": query, "error": f"HTTP {e.response.status_code}", "prices": [], "average": 0}
    except Exception as e:
        print(f"[cron] Scraper error for '{query}': {e}")
        return {"raw_query": query, "error": str(e), "prices": [], "average": 0}

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
        print(f"[cron] scraped: {query} -> {payload}")
        
        # Ensure payload includes raw_query for AI enrichment
        if "raw_query" not in payload:
            payload["raw_query"] = query
        
        # Only post to Edge Function if configured
        if SUPABASE_FUNCTION_URL and SUPABASE_FUNCTION_TOKEN:
            result = await post_to_edge_function(payload)
            print(f"[cron] stored: {query} -> {result}")
        else:
            print(f"[cron] skipped storage (Edge Function not configured)")
            
    except Exception as e:
        print(f"[cron] error: {query} -> {e}")

async def main():
    print(f"[cron] started {now_iso()}")
    print(f"[cron] SCRAPER_BASE_URL: {SCRAPER_BASE_URL}")
    print(f"[cron] SUPABASE_FUNCTION_URL: {SUPABASE_FUNCTION_URL}")
    print(f"[cron] SUPABASE_URL: {SUPABASE_URL or 'Not set (using hardcoded queries)'}")
    
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