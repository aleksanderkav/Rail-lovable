import os
import asyncio
import json
import time
import httpx
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import the existing scraper functions
from scheduled_scraper import (
    SCRAPER_BASE_URL, SUPABASE_FUNCTION_URL, SUPABASE_FUNCTION_TOKEN,
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, REQUEST_TIMEOUT_SECS,
    scrape, post_to_edge_function, now_iso
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

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Rail-lovable Scraper",
        "timestamp": now_iso(),
        "endpoints": {
            "scrape_now": "/scrape-now",
            "health": "/"
        }
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
        # Scrape the query
        print(f"[api] Starting scrape for: {query}")
        scrape_start = time.time()
        
        payload = await scrape(query)
        scrape_time = time.time() - scrape_start
        
        print(f"[api] Scrape completed in {scrape_time:.2f}s: {query}")
        
        # Post to Edge Function if configured
        storage_result = None
        if SUPABASE_FUNCTION_URL and SUPABASE_FUNCTION_TOKEN:
            try:
                storage_start = time.time()
                storage_result = await post_to_edge_function(payload)
                storage_time = time.time() - storage_start
                print(f"[api] Storage completed in {storage_time:.2f}s: {query}")
            except Exception as e:
                print(f"[api] Storage failed for {query}: {e}")
                storage_result = {"error": str(e)}
        else:
            print(f"[api] Storage skipped (Edge Function not configured): {query}")
            storage_result = {"skipped": "Edge Function not configured"}
        
        # Prepare response
        response = {
            "success": True,
            "query": query,
            "scrape_data": payload,
            "storage_result": storage_result,
            "timing": {
                "scrape_time_seconds": round(scrape_time, 2),
                "total_time_seconds": round(time.time() - scrape_start, 2)
            },
            "timestamp": now_iso()
        }
        
        print(f"[api] Request completed successfully: {query}")
        return response
        
    except Exception as e:
        error_msg = f"Scraping failed for '{query}': {str(e)}"
        print(f"[api] ERROR: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/health")
async def health_check():
    """Detailed health check with configuration status"""
    return {
        "status": "healthy",
        "timestamp": now_iso(),
        "configuration": {
            "scraper_base_url": SCRAPER_BASE_URL,
            "supabase_function_url": SUPABASE_FUNCTION_URL is not None,
            "supabase_function_token": SUPABASE_FUNCTION_TOKEN is not None,
            "supabase_url": SUPABASE_URL is not None,
            "supabase_service_role_key": SUPABASE_SERVICE_ROLE_KEY is not None
        }
    }

if __name__ == "__main__":
    # Get port from environment (Railway sets PORT)
    port = int(os.getenv("PORT", 8000))
    
    print(f"[api] Starting FastAPI server on port {port}")
    print(f"[api] Scraper base URL: {SCRAPER_BASE_URL}")
    print(f"[api] Supabase Function URL configured: {SUPABASE_FUNCTION_URL is not None}")
    
    uvicorn.run(app, host="0.0.0.0", port=port) 