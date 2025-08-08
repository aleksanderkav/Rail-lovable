import os
import json
import time
import httpx
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
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
    sold: Optional[bool] = None

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
                # Determine if item is sold based on various indicators
                sold = None
                if "sold" in item:
                    sold = bool(item["sold"])
                elif "status" in item:
                    status = str(item["status"]).lower()
                    sold = any(keyword in status for keyword in ["sold", "completed", "ended"])
                elif "ended_at" in item and item["ended_at"]:
                    sold = True  # If it has an end date, it's likely sold/ended
                
                items.append(Item(
                    title=item.get("title", ""),
                    url=item.get("url"),
                    id=item.get("id"),
                    price=item.get("price"),
                    currency=item.get("currency"),
                    ended_at=item.get("ended_at"),
                    source=item.get("source", "ebay"),
                    sold=sold
                ))
    elif "price_entries" in scraper_data and isinstance(scraper_data["price_entries"], list):
        # Convert price entries to items
        for entry in scraper_data["price_entries"]:
            if isinstance(entry, dict):
                items.append(Item(
                    title=scraper_data.get("query", ""),
                    price=entry.get("price"),
                    currency="USD",
                    source="ebay",
                    sold=None  # Price entries don't typically indicate sold status
                ))
    elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
        # Convert prices array to items
        for price in scraper_data["prices"]:
            if isinstance(price, (int, float)):
                items.append(Item(
                    title=scraper_data.get("query", ""),
                    price=float(price),
                    currency="USD",
                    source="ebay",
                    sold=None  # Price arrays don't typically indicate sold status
                ))
    
    # If no items found, create a default item with query info
    if not items:
        items.append(Item(
            title=scraper_data.get("query", ""),
            price=scraper_data.get("average"),
            currency="USD",
            source="ebay",
            sold=None
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
        "time": now_iso(),
        "env": {
            "scraper": bool(SCRAPER_BASE_URL),
            "ef": bool(SUPABASE_FUNCTION_URL)
        }
    }

@app.options("/scrape-now")
async def scrape_now_options():
    """CORS preflight handler for /scrape-now"""
    trace_id = str(uuid.uuid4())[:8]
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "X-Trace-Id": trace_id
        }
    )

@app.options("/scrape-now/")
async def scrape_now_options_trailing():
    """CORS preflight handler for /scrape-now/ (with trailing slash)"""
    trace_id = str(uuid.uuid4())[:8]
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "X-Trace-Id": trace_id
        }
    )

@app.post("/scrape-now")
async def scrape_now(request: ScrapeRequest, http_request: Request):
    """
    On-demand scraping endpoint for Lovable.
    Immediately scrapes the provided query and stores results.
    """
    query = request.query.strip()
    
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Get client IP and generate trace ID
    client_ip = http_request.client.host if http_request.client else "unknown"
    trace_id = str(uuid.uuid4())[:8]
    
    # Log the incoming request
    print(f"[api] {now_iso()} Manual scrape request from {client_ip}: '{query}' (trace: {trace_id})")
    
    try:
        # Step 1: Call scraper
        print(f"[api] Calling scraper: {SCRAPER_BASE_URL}/scrape?query={query}")
        scraper_start = time.time()
        
        scraper_response = await call_scraper(query)
        scraper_time = time.time() - scraper_start
        
        print(f"[api] Scraper completed in {scraper_time:.2f}s (status: 200) (trace: {trace_id})")
        
        # Step 2: Normalize response
        normalized_data = normalize_scraper_response(scraper_response)
        
        # Log item count and field presence rates
        item_count = len(normalized_data.items)
        ended_at_count = sum(1 for item in normalized_data.items if item.ended_at)
        url_count = sum(1 for item in normalized_data.items if item.url)
        sold_count = sum(1 for item in normalized_data.items if item.sold is True)
        
        print(f"[api] Normalized {item_count} items:")
        print(f"[api]   - ended_at: {ended_at_count}/{item_count} ({ended_at_count/item_count*100:.1f}%)")
        print(f"[api]   - url: {url_count}/{item_count} ({url_count/item_count*100:.1f}%)")
        print(f"[api]   - sold: {sold_count}/{item_count} ({sold_count/item_count*100:.1f}%)")
        
        # Log first 1-2 item titles
        item_titles = [item.title for item in normalized_data.items[:2]]
        print(f"[api] First titles: {item_titles}")
        
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
                print(f"[api] Edge Function completed in {ef_time:.2f}s (status: {ef_status}) (trace: {trace_id})")
                print(f"[api] Edge Function response: {ef_body_truncated}")
                
                external_ok = ef_status == 200
                
            except Exception as e:
                print(f"[api] Edge Function failed: {e} (trace: {trace_id})")
                ef_status = 500
                ef_body = str(e)
                external_ok = False
        else:
            print(f"[api] Edge Function not configured - skipping storage (trace: {trace_id})")
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
        
        print(f"[api] Request completed successfully: {query} (client: {client_ip}, trace: {trace_id})")
        return JSONResponse(
            content=response,
            headers={"X-Trace-Id": trace_id}
        )
        
    except httpx.HTTPStatusError as e:
        error_msg = f"Scraper HTTP error: {e.response.status_code}"
        print(f"[api] ERROR: {error_msg} (client: {client_ip}, trace: {trace_id})")
        raise HTTPException(
            status_code=502, 
            detail={
                "ok": False,
                "error": error_msg,
                "step": "scraper"
            },
            headers={"X-Trace-Id": trace_id}
        )
    except Exception as e:
        error_msg = f"Scraping failed: {str(e)}"
        print(f"[api] ERROR: {error_msg} (client: {client_ip}, trace: {trace_id})")
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": error_msg,
                "step": "scraper"
            },
            headers={"X-Trace-Id": trace_id}
        )

@app.post("/scrape-now/")
async def scrape_now_trailing(request: ScrapeRequest, http_request: Request):
    """Handle /scrape-now/ (with trailing slash) - redirect to main handler"""
    return await scrape_now(request, http_request)

if __name__ == "__main__":
    # Get port from environment (Railway sets PORT)
    port = int(os.getenv("PORT", 8000))
    
    print(f"[api] Starting FastAPI server on port {port}")
    print(f"[api] Scraper base URL: {'SET' if SCRAPER_BASE_URL else 'NOT SET'}")
    print(f"[api] Supabase Function URL: {'SET' if SUPABASE_FUNCTION_URL else 'NOT SET'}")
    
    # Print deployment info
    railway_url = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_url:
        base_url = f"https://{railway_url}"
        print(f"[api] Base URL: {base_url}")
        print(f"[api] Scrape endpoint: {base_url}/scrape-now")
        print(f"[api] Health endpoint: {base_url}/health")
    else:
        print(f"[api] Local development - no Railway URL available")
        print(f"[api] Local endpoints:")
        print(f"[api]   - Health: http://localhost:{port}/health")
        print(f"[api]   - Scrape: http://localhost:{port}/scrape-now")
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port) 