#!/usr/bin/env python3
"""
Scheduled scraper that runs on a cron schedule to fetch tracked queries
and post results to the Supabase Edge Function for AI enrichment.
"""

import os
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json

# Environment variables - make lazy to avoid startup crashes
def get_scraper_base_url():
    return os.getenv("SCRAPER_BASE_URL")

def get_supabase_function_url():
    return os.getenv("SUPABASE_FUNCTION_URL")

def get_supabase_function_token():
    return os.getenv("SUPABASE_FUNCTION_TOKEN")

def get_supabase_url():
    return os.getenv("SUPABASE_URL")

def get_supabase_service_role_key():
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def get_batch_limit():
    return int(os.getenv("BATCH_LIMIT", "20"))

def get_sleep_jitter_secs():
    return float(os.getenv("SLEEP_JITTER_SECS", "2.0"))

def get_request_timeout_secs():
    return int(os.getenv("REQUEST_TIMEOUT_SECS", "60"))

# Scraping settings - use lazy functions
BATCH_LIMIT = get_batch_limit()
SLEEP_JITTER_SECS = get_sleep_jitter_secs()
REQUEST_TIMEOUT_SECS = get_request_timeout_secs()

def now_iso() -> str:
    """Get current time in ISO format"""
    return datetime.now(timezone.utc).isoformat()

async def scrape(query: str) -> Dict[str, Any]:
    """Scrape a single query using the external scraper"""
    if not get_scraper_base_url():
        raise ValueError("SCRAPER_BASE_URL not configured")
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
        response = await client.get(f"{get_scraper_base_url()}/scrape", params={"query": query})
        response.raise_for_status()
        
        scraper_data = response.json()
        
        # Transform scraper output to new AI-driven structure
        items = []
        
        # Handle different response formats from the scraper
        if "items" in scraper_data and isinstance(scraper_data["items"], list):
            for item_data in scraper_data["items"]:
                # Map to new structure
                item = {
                    # Raw listing details (for AI extraction)
                    "raw_title": item_data.get("title", ""),
                    "raw_description": item_data.get("description"),
                    "source": item_data.get("source", "ebay"),
                    "source_listing_id": item_data.get("id") or item_data.get("source_listing_id"),
                    "url": item_data.get("url"),
                    
                    # Pricing and availability
                    "currency": item_data.get("currency"),
                    "price": item_data.get("price"),
                    "ended_at": item_data.get("ended_at"),
                    
                    # Media
                    "images": [item_data.get("image_url")] if item_data.get("image_url") else None,
                    
                    # Initial parsed fields (if easily extractable during scraping)
                    "franchise": item_data.get("franchise"),
                    "set_name": item_data.get("set_name"),
                    "edition": item_data.get("edition"),
                    "number": item_data.get("number"),
                    "year": item_data.get("year"),
                    "language": item_data.get("language"),
                    "grading_company": item_data.get("grading_company"),
                    "grade": item_data.get("grade"),
                    "rarity": item_data.get("rarity"),
                    "is_holo": item_data.get("is_holo"),
                    
                    # Tags (pre-filled if certain)
                    "tags": item_data.get("tags"),
                    
                    # Metadata for enrichment
                    "raw_query": query,
                    "category_guess": item_data.get("category_guess"),
                    
                    # Legacy fields for backward compatibility
                    "title": item_data.get("title"),
                    "id": item_data.get("id"),
                    "sold": item_data.get("sold"),
                    "image_url": item_data.get("image_url"),
                    "shipping_price": item_data.get("shipping_price"),
                    "total_price": item_data.get("total_price"),
                    "bids": item_data.get("bids"),
                    "condition": item_data.get("condition"),
                    "canonical_key": item_data.get("canonical_key"),
                    "set": item_data.get("set"),
                    "edition": item_data.get("edition"),
                    "year": item_data.get("year"),
                    "language": item_data.get("language"),
                    "grader": item_data.get("grader"),
                    "grade_value": item_data.get("grade_value")
                }
                items.append(item)
        
        elif "price_entries" in scraper_data and isinstance(scraper_data["price_entries"], list):
            # Handle price entries format
            for entry in scraper_data["price_entries"]:
                title = entry.get("title", query)
                item = {
                    "raw_title": title,
                    "raw_description": None,
                    "source": "ebay",
                    "source_listing_id": None,
                    "url": None,
                    "currency": "USD",
                    "price": entry.get("price"),
                    "ended_at": None,
                    "images": None,
                    "raw_query": query,
                    "franchise": None,
                    "set_name": None,
                    "edition": None,
                    "number": None,
                    "year": None,
                    "language": None,
                    "grading_company": None,
                    "grade": None,
                    "rarity": None,
                    "is_holo": None,
                    "tags": None,
                    "category_guess": None,
                    "title": title,
                    "id": None,
                    "sold": None,
                    "image_url": None,
                    "shipping_price": None,
                    "total_price": None,
                    "bids": None,
                    "condition": None,
                    "canonical_key": None,
                    "set": None,
                    "edition": None,
                    "year": None,
                    "language": None,
                    "grader": None,
                    "grade_value": None
                }
                items.append(item)
        
        elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
            # Handle prices array format
            for price in scraper_data["prices"]:
                if isinstance(price, (int, float)):
                    title = query
                    item = {
                        "raw_title": title,
                        "raw_description": None,
                        "source": "ebay",
                        "source_listing_id": None,
                        "url": None,
                        "currency": "USD",
                        "price": float(price),
                        "ended_at": None,
                        "images": None,
                        "raw_query": query,
                        "franchise": None,
                        "set_name": None,
                        "edition": None,
                        "number": None,
                        "year": None,
                        "language": None,
                        "grading_company": None,
                        "grade": None,
                        "rarity": None,
                        "is_holo": None,
                        "tags": None,
                        "category_guess": None,
                        "title": title,
                        "id": None,
                        "sold": None,
                        "image_url": None,
                        "shipping_price": None,
                        "total_price": None,
                        "bids": None,
                        "condition": None,
                        "canonical_key": None,
                        "set": None,
                        "edition": None,
                        "year": None,
                        "language": None,
                        "grader": None,
                        "grade_value": None
                    }
                    items.append(item)
        
        elif "average" in scraper_data:
            # Handle average price format
            title = query
            item = {
                "raw_title": title,
                "raw_description": None,
                "source": "ebay",
                "source_listing_id": None,
                "url": None,
                "currency": "USD",
                "price": scraper_data.get("average"),
                "ended_at": None,
                "images": None,
                "raw_query": query,
                "franchise": None,
                "set_name": None,
                "edition": None,
                "number": None,
                "year": None,
                "language": None,
                "grading_company": None,
                "grade": None,
                "rarity": None,
                "is_holo": None,
                "tags": None,
                "category_guess": None,
                "title": title,
                "id": None,
                "sold": None,
                "image_url": None,
                "shipping_price": None,
                "total_price": None,
                "bids": None,
                "condition": None,
                "canonical_key": None,
                "set": None,
                "edition": None,
                "year": None,
                "language": None,
                "grader": None,
                "grade_value": None
            }
            items.append(item)
        
        return {
            "query": query,
            "items": items,
            "scraped_at": now_iso()
        }

async def post_to_edge_function(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Post scraped data to the Supabase Edge Function for AI enrichment"""
    if not get_supabase_function_url() or not get_supabase_function_token():
        raise ValueError("Edge Function not configured")
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
        response = await client.post(
            get_supabase_function_url(),
            json=payload,
            headers={"Authorization": f"Bearer {get_supabase_function_token()}"}
        )
        response.raise_for_status()
        
        return {
            "status": response.status_code,
            "body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
        }

async def get_tracked_queries() -> List[str]:
    """Get list of queries to track from Supabase or fallback to hardcoded"""
    if not get_supabase_url() or not get_supabase_service_role_key():
        # Fallback to hardcoded queries
        return [
            "Pikachu Base Set 1st Edition PSA 10",
            "Charizard Base Set 1st Edition PSA 10",
            "Blastoise Base Set 1st Edition PSA 10",
            "Venusaur Base Set 1st Edition PSA 10",
            "Magic: The Gathering Black Lotus Alpha",
            "Yu-Gi-Oh! Blue-Eyes White Dragon 1st Edition",
            "Michael Jordan 1986 Fleer Rookie Card PSA 10"
        ]
    
    # TODO: Implement Supabase query fetching
    # For now, return hardcoded queries
    return [
        "Pikachu Base Set 1st Edition PSA 10",
        "Charizard Base Set 1st Edition PSA 10",
        "Blastoise Base Set 1st Edition PSA 10",
        "Venusaur Base Set 1st Edition PSA 10",
        "Magic: The Gathering Black Lotus Alpha",
        "Yu-Gi-Oh! Blue-Eyes White Dragon 1st Edition",
        "Michael Jordan 1986 Fleer Rookie Card PSA 10"
    ]

async def process_query(query: str):
    """Process a single query: scrape and post to Edge Function"""
    started = now_iso()
    print(f"[cron] {started} scraping: {query}")
    
    try:
        payload = await scrape(query)
        print(f"[cron] scraped: {query} -> {len(payload.get('items', []))} items")
        
        # Ensure payload includes raw_query for AI enrichment
        if "raw_query" not in payload:
            payload["raw_query"] = query
        
        # Only post to Edge Function if configured
        if get_supabase_function_url() and get_supabase_function_token():
            result = await post_to_edge_function(payload)
            print(f"[cron] stored: {query} -> {result}")
        else:
            print(f"[cron] skipped storage (Edge Function not configured)")
            
    except Exception as e:
        print(f"[cron] error: {query} -> {e}")

async def main():
    """Main scraping function"""
    print(f"[cron] {now_iso()} Starting scheduled scraper")
    print(f"[cron] Configuration:")
    print(f"   SCRAPER_BASE_URL: {'✅ Set' if get_scraper_base_url() else '❌ Not set'}")
    print(f"   SUPABASE_FUNCTION_URL: {'✅ Set' if get_supabase_function_url() else '❌ Not set'}")
    print(f"   SUPABASE_FUNCTION_TOKEN: {'✅ Set' if get_supabase_function_token() else '❌ Not set'}")
    print(f"   BATCH_LIMIT: {BATCH_LIMIT}")
    print(f"   SLEEP_JITTER_SECS: {SLEEP_JITTER_SECS}")
    
    # Get queries to process
    queries = await get_tracked_queries()
    print(f"[cron] Processing {len(queries)} queries")
    
    # Process queries in batches
    for i in range(0, len(queries), BATCH_LIMIT):
        batch = queries[i:i + BATCH_LIMIT]
        print(f"[cron] Processing batch {i//BATCH_LIMIT + 1}: {len(batch)} queries")
        
        # Process batch concurrently
        tasks = [process_query(query) for query in batch]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Sleep between batches (with jitter)
        if i + BATCH_LIMIT < len(queries):
            sleep_time = SLEEP_JITTER_SECS + (hash(str(i)) % 1000) / 1000.0
            print(f"[cron] Sleeping {sleep_time:.2f}s before next batch")
            await asyncio.sleep(sleep_time)
    
    print(f"[cron] {now_iso()} Scheduled scraper completed")

if __name__ == "__main__":
    asyncio.run(main()) 