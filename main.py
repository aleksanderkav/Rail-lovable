import os
import json
import time
import httpx
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Import the existing scraper functions
from scheduled_scraper import (
    SCRAPER_BASE_URL, SUPABASE_FUNCTION_URL, SUPABASE_FUNCTION_TOKEN,
    REQUEST_TIMEOUT_SECS, now_iso
)

app = FastAPI(title="Rail-lovable Scraper", version="1.0.0")

# Enable CORS for Lovable frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this more restrictively in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    query: str

class Item(BaseModel):
    title: str
    url: Optional[str] = None
    id: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    ended_at: Optional[str] = None
    source: str = "ebay"

class NormalizedResponse(BaseModel):
    items: List[Item]

def normalize_scraper_response(scraper_data: Dict[str, Any]) -> NormalizedResponse:
    """Normalize scraper response into expected format"""
    items = []
    
    # Handle different response formats
    if "items" in scraper_data and isinstance(scraper_data["items"], list):
        # Already has items array
        for item in scraper_data["items"]:
            if isinstance(item, dict):
                items.append(Item(
                    title=item.get("title", ""),
                    url=item.get("url"),
                    id=item.get("id"),
                    price=item.get("price"),
                    currency=item.get("currency"),
                    ended_at=item.get("ended_at"),
                    source=item.get("source", "ebay")
                ))
    elif "price_entries" in scraper_data and isinstance(scraper_data["price_entries"], list):
        # Convert price entries to items
        for entry in scraper_data["price_entries"]:
            if isinstance(entry, dict):
                items.append(Item(
                    title=scraper_data.get("query", ""),
                    price=entry.get("price"),
                    currency="USD",
                    source="ebay"
                ))
    elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
        # Convert prices array to items
        for price in scraper_data["prices"]:
            if isinstance(price, (int, float)):
                items.append(Item(
                    title=scraper_data.get("query", ""),
                    price=float(price),
                    currency="USD",
                    source="ebay"
                ))
    
    # If no items found, create a default item with query info
    if not items:
        items.append(Item(
            title=scraper_data.get("query", ""),
            price=scraper_data.get("average"),
            currency="USD",
            source="ebay"
        ))
    
    return NormalizedResponse(items=items)

async def call_scraper(query: str) -> Dict[str, Any]:
    """Call the external scraper and return raw response"""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
        response = await client.get(f"{SCRAPER_BASE_URL}/scrape", params={"query": query})
        response.raise_for_status()
        return response.json()

async def post_to_edge_function(payload: Dict[str, Any]) -> tuple[int, str]:
    """Post payload to Supabase Edge Function and return status and body"""
    headers = {
        "Authorization": f"Bearer {SUPABASE_FUNCTION_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECS) as client:
        response = await client.post(
            SUPABASE_FUNCTION_URL, 
            headers=headers, 
            json=payload
        )
        return response.status_code, response.text

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "ok": True,
        "service": "rail-lovable"
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "ok": True,
        "time": now_iso()
    }

@app.post("/scrape-now")
async def scrape_now(request: ScrapeRequest):
    """
    On-demand scraping endpoint for Lovable.
    Immediately scrapes the provided query and stores results.
    """
    query = request.query.strip()
    
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Log the incoming request
    print(f"[api] {now_iso()} Manual scrape request: '{query}'")
    
    try:
        # Step 1: Call scraper
        print(f"[api] Calling scraper: {SCRAPER_BASE_URL}/scrape?query={query}")
        scraper_start = time.time()
        
        scraper_response = await call_scraper(query)
        scraper_time = time.time() - scraper_start
        
        print(f"[api] Scraper completed in {scraper_time:.2f}s (status: 200)")
        
        # Step 2: Normalize response
        normalized_data = normalize_scraper_response(scraper_response)
        
        # Log first 1-2 item titles
        item_titles = [item.title for item in normalized_data.items[:2]]
        print(f"[api] Normalized {len(normalized_data.items)} items. First titles: {item_titles}")
        
        # Step 3: Post to Edge Function
        ef_status = None
        ef_body = ""
        external_ok = False
        
        if SUPABASE_FUNCTION_URL and SUPABASE_FUNCTION_TOKEN:
            try:
                print(f"[api] Posting to Edge Function: {SUPABASE_FUNCTION_URL}")
                ef_start = time.time()
                
                ef_status, ef_body = await post_to_edge_function(normalized_data.dict())
                ef_time = time.time() - ef_start
                
                # Truncate body for logging (max 300 chars)
                ef_body_truncated = ef_body[:300] + "..." if len(ef_body) > 300 else ef_body
                print(f"[api] Edge Function completed in {ef_time:.2f}s (status: {ef_status})")
                print(f"[api] Edge Function response: {ef_body_truncated}")
                
                external_ok = ef_status == 200
                
            except Exception as e:
                print(f"[api] Edge Function failed: {e}")
                ef_status = 500
                ef_body = str(e)
                external_ok = False
        else:
            print(f"[api] Edge Function not configured - skipping storage")
            ef_status = None
            ef_body = "Edge Function not configured"
            external_ok = False
        
        # Prepare response
        response = {
            "ok": True,
            "items": [item.dict() for item in normalized_data.items],
            "externalOk": external_ok,
            "efStatus": ef_status,
            "efBody": ef_body
        }
        
        print(f"[api] Request completed successfully: {query}")
        return response
        
    except httpx.HTTPStatusError as e:
        error_msg = f"Scraper HTTP error: {e.response.status_code}"
        print(f"[api] ERROR: {error_msg}")
        raise HTTPException(
            status_code=502, 
            detail={
                "ok": False,
                "error": error_msg,
                "step": "scraper"
            }
        )
    except Exception as e:
        error_msg = f"Scraping failed: {str(e)}"
        print(f"[api] ERROR: {error_msg}")
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": error_msg,
                "step": "scraper"
            }
        )

if __name__ == "__main__":
    # Get port from environment (Railway sets PORT)
    port = int(os.getenv("PORT", 8000))
    
    print(f"[api] Starting FastAPI server on port {port}")
    print(f"[api] Scraper base URL: {SCRAPER_BASE_URL}")
    print(f"[api] Supabase Function URL configured: {SUPABASE_FUNCTION_URL is not None}")
    
    # Print deployment info
    railway_url = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_url:
        print(f"[api] Deployed at: https://{railway_url}")
        print(f"[api] Scrape endpoint: https://{railway_url}/scrape-now")
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port) 