import os
import json
import time
import httpx
import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# Import the existing scraper functions
from scheduled_scraper import (
    SCRAPER_BASE_URL, SUPABASE_FUNCTION_URL, SUPABASE_FUNCTION_TOKEN,
    now_iso
)

# Import the normalizer
from normalizer import normalizer, NormalizedItem

# Timeout constants
SCRAPER_TIMEOUT = 12.0
EF_TIMEOUT = 8.0
GLOBAL_TIMEOUT = 60.0

# Global HTTP client with strict timeouts
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=5.0,
        read=12.0,
        write=12.0,
        pool=30.0
    )
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

@app.on_event("startup")
async def startup_event():
    """Initialize HTTP client on startup"""
    print(f"[api] Starting up with strict timeouts: connect=5s, read={SCRAPER_TIMEOUT}s, write={SCRAPER_TIMEOUT}s")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up HTTP client on shutdown"""
    await http_client.aclose()
    print(f"[api] Shutdown complete")

class ScrapeRequest(BaseModel):
    query: str

class Item(BaseModel):
    """Scraped item with AI enrichment support"""
    # Raw listing details (for AI extraction)
    raw_title: str
    raw_description: Optional[str] = None
    source: str = "ebay"
    source_listing_id: Optional[str] = None
    url: Optional[str] = None
    
    # Pricing and availability
    currency: Optional[str] = None
    price: Optional[float] = None
    ended_at: Optional[str] = None
    
    # Media
    images: Optional[List[str]] = None
    
    # Initial parsed fields (if easily extractable during scraping)
    franchise: Optional[str] = None
    set_name: Optional[str] = None
    edition: Optional[str] = None
    number: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    grading_company: Optional[str] = None
    grade: Optional[str] = None
    rarity: Optional[str] = None
    is_holo: Optional[bool] = None
    
    # Tags (pre-filled if certain)
    tags: Optional[List[str]] = None
    
    # Metadata for enrichment
    raw_query: Optional[str] = None
    category_guess: Optional[str] = None
    
    # Legacy fields for backward compatibility
    title: Optional[str] = None
    id: Optional[str] = None
    sold: Optional[bool] = None
    image_url: Optional[str] = None
    shipping_price: Optional[float] = None
    total_price: Optional[float] = None
    bids: Optional[int] = None
    condition: Optional[str] = None
    canonical_key: Optional[str] = None
    set: Optional[str] = None
    grader: Optional[str] = None
    grade_value: Optional[int] = None
    
    # Parsed hints subobject
    parsed: Optional[ParsedHints] = None

class NormalizedResponse(BaseModel):
    items: List[Item]

class NormalizeTestRequest(BaseModel):
    """Request for /normalize-test endpoint"""
    items: Optional[List[Dict[str, Any]]] = None
    query: Optional[str] = None
    limit: Optional[int] = 10

class IngestItemsRequest(BaseModel):
    """Request for /ingest-items endpoint"""
    raw_query: Optional[str] = None
    items: List[Dict[str, Any]]
    dry_run: bool = True

class ParsedHints(BaseModel):
    """Parsed hints from card titles"""
    set_name: Optional[str] = None
    edition: Optional[str] = None
    number: Optional[str] = None
    year: Optional[int] = None
    grading_company: Optional[str] = None
    grade: Optional[str] = None
    is_holo: Optional[bool] = None
    franchise: str = "pokemon"
    # New canonicalized fields
    canonical_key: Optional[str] = None
    rarity: Optional[str] = None
    tags: Optional[List[str]] = None
    sold: Optional[bool] = None
    # Normalized fields
    set: Optional[str] = None
    language: Optional[str] = None
    grader: Optional[str] = None
    grade_value: Optional[int] = None

class NormalizedTestItem(BaseModel):
    """Normalized item for test endpoint"""
    title: str
    url: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    ended_at: Optional[str] = None
    id: Optional[str] = None
    source: str = "ebay"
    parsed: ParsedHints
    canonical_key: str
    confidence: Dict[str, float]

class NormalizeTestResponse(BaseModel):
    """Response for /normalize-test endpoint"""
    ok: bool
    source: str  # "items" or "scraper"
    count: int
    items: List[NormalizedTestItem]
    trace: str

class IngestItemsResponse(BaseModel):
    """Response for /ingest-items endpoint"""
    ok: bool
    externalOk: bool
    count: int
    items: List[Dict[str, Any]]  # Per-item results from EF
    trace: str

def normalize_scraper_response(scraper_data: Dict[str, Any]) -> NormalizedResponse:
    """Normalize scraper response into expected format with enriched fields"""
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
                
                # Parse title for hints
                title = item.get("title", "")
                parsed_hints = normalizer.parse_title(title) if title else None
                
                # Calculate total price
                price = item.get("price")
                shipping_price = item.get("shipping_price")
                total_price = None
                if price is not None and shipping_price is not None:
                    total_price = price + shipping_price
                elif price is not None:
                    total_price = price
                
                items.append(Item(
                    raw_title=title,
                    raw_description=item.get("description"),
                    source=item.get("source", "ebay"),
                    source_listing_id=item.get("id"),
                    url=item.get("url"),
                    currency=item.get("currency"),
                    price=price,
                    ended_at=item.get("ended_at"),
                    images=[item.get("image_url")] if item.get("image_url") else None,
                    raw_query=scraper_data.get("query"),
                    franchise=parsed_hints.franchise if parsed_hints else None,
                    set_name=parsed_hints.set_name if parsed_hints else None,
                    edition=parsed_hints.edition if parsed_hints else None,
                    number=parsed_hints.number if parsed_hints else None,
                    year=parsed_hints.year if parsed_hints else None,
                    language=parsed_hints.language if parsed_hints else None,
                    grading_company=parsed_hints.grading_company if parsed_hints else None,
                    grade=parsed_hints.grade if parsed_hints else None,
                    rarity=parsed_hints.rarity if parsed_hints else None,
                    is_holo=parsed_hints.is_holo if parsed_hints else None,
                    tags=parsed_hints.tags if parsed_hints else None,
                    sold=sold,
                    canonical_key=item.get("canonical_key"),
                    set=item.get("set"),
                    grader=item.get("grader"),
                    grade_value=item.get("grade_value")
                ))
    elif "price_entries" in scraper_data and isinstance(scraper_data["price_entries"], list):
        # Convert price entries to items
        for entry in scraper_data["price_entries"]:
            if isinstance(entry, dict):
                title = scraper_data.get("query", "")
                parsed_hints = normalizer.parse_title(title) if title else None
                
                items.append(Item(
                    raw_title=title,
                    raw_description=None,
                    source="ebay",
                    source_listing_id=None,
                    url=None,
                    currency="USD",
                    price=entry.get("price"),
                    ended_at=None,
                    images=None,
                    raw_query=scraper_data.get("query"),
                    franchise=parsed_hints.franchise if parsed_hints else None,
                    set_name=parsed_hints.set_name if parsed_hints else None,
                    edition=parsed_hints.edition if parsed_hints else None,
                    number=parsed_hints.number if parsed_hints else None,
                    year=parsed_hints.year if parsed_hints else None,
                    language=parsed_hints.language if parsed_hints else None,
                    grading_company=parsed_hints.grading_company if parsed_hints else None,
                    grade=parsed_hints.grade if parsed_hints else None,
                    rarity=parsed_hints.rarity if parsed_hints else None,
                    is_holo=parsed_hints.is_holo if parsed_hints else None,
                    tags=parsed_hints.tags if parsed_hints else None,
                    sold=None,
                    canonical_key=None,
                    set=None,
                    grader=None,
                    grade_value=None
                ))
    elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
        # Convert prices array to items
        for price in scraper_data["prices"]:
            if isinstance(price, (int, float)):
                title = scraper_data.get("query", "")
                parsed_hints = normalizer.parse_title(title) if title else None
                
                items.append(Item(
                    raw_title=title,
                    raw_description=None,
                    source="ebay",
                    source_listing_id=None,
                    url=None,
                    currency="USD",
                    price=float(price),
                    ended_at=None,
                    images=None,
                    raw_query=scraper_data.get("query"),
                    franchise=parsed_hints.franchise if parsed_hints else None,
                    set_name=parsed_hints.set_name if parsed_hints else None,
                    edition=parsed_hints.edition if parsed_hints else None,
                    number=parsed_hints.number if parsed_hints else None,
                    year=parsed_hints.year if parsed_hints else None,
                    language=parsed_hints.language if parsed_hints else None,
                    grading_company=parsed_hints.grading_company if parsed_hints else None,
                    grade=parsed_hints.grade if parsed_hints else None,
                    rarity=parsed_hints.rarity if parsed_hints else None,
                    is_holo=parsed_hints.is_holo if parsed_hints else None,
                    tags=parsed_hints.tags if parsed_hints else None,
                    sold=None,
                    canonical_key=None,
                    set=None,
                    grader=None,
                    grade_value=None
                ))
    
    # If no items found, create a default item with query info
    if not items:
        title = scraper_data.get("query", "")
        parsed_hints = normalizer.parse_title(title) if title else None
        
        items.append(Item(
            raw_title=title,
            raw_description=None,
            source="ebay",
            source_listing_id=None,
            url=None,
            currency="USD",
            price=scraper_data.get("average"),
            ended_at=None,
            images=None,
            raw_query=scraper_data.get("query"),
            franchise=parsed_hints.franchise if parsed_hints else None,
            set_name=parsed_hints.set_name if parsed_hints else None,
            edition=parsed_hints.edition if parsed_hints else None,
            number=parsed_hints.number if parsed_hints else None,
            year=parsed_hints.year if parsed_hints else None,
            language=parsed_hints.language if parsed_hints else None,
            grading_company=parsed_hints.grading_company if parsed_hints else None,
            grade=parsed_hints.grade if parsed_hints else None,
            rarity=parsed_hints.rarity if parsed_hints else None,
            is_holo=parsed_hints.is_holo if parsed_hints else None,
            tags=parsed_hints.tags if parsed_hints else None,
            sold=None,
            canonical_key=None,
            set=None,
            grader=None,
            grade_value=None
        ))
    
    return NormalizedResponse(items=items)

async def call_scraper(query: str) -> Dict[str, Any]:
    """Call the external scraper and return raw response with retry logic"""
    max_retries = 2
    base_delay = 0.5
    
    for attempt in range(max_retries + 1):
        try:
            response = await http_client.get(f"{SCRAPER_BASE_URL}/scrape", params={"query": query})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt == max_retries:
                # Last attempt failed, re-raise
                raise e
            
            # Add jitter to delay
            delay = base_delay * (2 ** attempt) + (0.1 * attempt)
            print(f"[api] Scraper attempt {attempt + 1} failed, retrying in {delay:.2f}s: {str(e)}")
            await asyncio.sleep(delay)

async def post_to_edge_function(payload: Dict[str, Any]) -> tuple[int, str]:
    """Post payload to Supabase Edge Function and return status and body"""
    headers = {
        "Authorization": f"Bearer {SUPABASE_FUNCTION_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    response = await http_client.post(
        SUPABASE_FUNCTION_URL, 
        headers=headers, 
        json=payload
    )
    return response.status_code, response.text

async def check_scraper_reachable() -> bool:
    """Check if scraper is reachable without running a full scrape"""
    try:
        # Quick health check to scraper
        response = await asyncio.wait_for(
            http_client.get(f"{SCRAPER_BASE_URL}/", timeout=3.0),
            timeout=3.0
        )
        return response.status_code < 500
    except Exception:
        return False

async def check_dns_resolution() -> bool:
    """Check if we can resolve external domains"""
    try:
        # Try to resolve a common domain
        await asyncio.wait_for(
            http_client.get("https://httpbin.org/get", timeout=3.0),
            timeout=3.0
        )
        return True
    except Exception:
        return False

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "ok": True,
        "service": "rail-lovable"
    }

@app.get("/health")
async def health_check():
    """Detailed health check with network connectivity"""
    dns_ok = await check_dns_resolution()
    scraper_reachable = await check_scraper_reachable()
    
    return {
        "ok": True,
        "time": now_iso(),
        "env": {
            "scraper": bool(SCRAPER_BASE_URL),
            "ef": bool(SUPABASE_FUNCTION_URL)
        },
        "net": {
            "dns": dns_ok,
            "scraperReachable": scraper_reachable
        },
        "endpoints": ["/scrape-now", "/normalize-test", "/ingest-items"]
    }

@app.post("/smoketest")
async def smoketest():
    """Quick connectivity test with minimal scrape"""
    trace_id = str(uuid.uuid4())[:8]
    
    try:
        # Quick scrape with limit=1 and short timeout
        response = await asyncio.wait_for(
            http_client.get(f"{SCRAPER_BASE_URL}/scrape", params={"query": "test", "limit": 1}),
            timeout=6.0
        )
        
        if response.status_code == 200:
            return JSONResponse(
                content={
                    "ok": True,
                    "message": "Scraper connectivity test passed",
                    "trace": trace_id
                },
                headers={"X-Trace-Id": trace_id}
            )
        else:
            return JSONResponse(
                content={
                    "ok": False,
                    "error": f"Scraper returned status {response.status_code}",
                    "trace": trace_id
                },
                status_code=502,
                headers={"X-Trace-Id": trace_id}
            )
            
    except asyncio.TimeoutError:
        return JSONResponse(
            content={
                "ok": False,
                "error": "Scraper timeout (6s)",
                "trace": trace_id
            },
            status_code=502,
            headers={"X-Trace-Id": trace_id}
        )
    except Exception as e:
        return JSONResponse(
            content={
                "ok": False,
                "error": f"Scraper error: {str(e)}",
                "trace": trace_id
            },
            status_code=502,
            headers={"X-Trace-Id": trace_id}
        )

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

@app.options("/normalize-test")
async def normalize_test_options():
    """Handle CORS preflight for /normalize-test"""
    return JSONResponse(
        content={"ok": True},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "X-Trace-Id": str(uuid.uuid4())[:8]
        }
    )

@app.options("/ingest-items")
async def ingest_items_options():
    """Handle CORS preflight for /ingest-items"""
    return JSONResponse(
        content={"ok": True},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "X-Trace-Id": str(uuid.uuid4())[:8]
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
    
    # Global timeout for entire request (25 seconds max)
    async with asyncio.timeout(GLOBAL_TIMEOUT):
        try:
            # Step 1: Call scraper with timeout
            print(f"[api] Step 1: Starting scraper call (trace: {trace_id})")
            scraper_start = time.time()
            
            try:
                scraper_response = await asyncio.wait_for(
                    call_scraper(query),
                    timeout=SCRAPER_TIMEOUT
                )
                scraper_time = time.time() - scraper_start
                print(f"[api] Step 1: Scraper completed in {scraper_time:.2f}s (trace: {trace_id})")
                
            except asyncio.TimeoutError:
                error_msg = f"Scraper timeout ({SCRAPER_TIMEOUT}s)"
                print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
                return JSONResponse(
                    content={
                        "ok": False,
                        "step": "scraper",
                        "error": "timeout",
                        "trace": trace_id
                    },
                    status_code=502,
                    headers={
                        "X-Trace-Id": trace_id,
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                        "Access-Control-Allow-Headers": "*"
                    }
                )
            except Exception as e:
                error_msg = f"Scraper error: {str(e)}"
                print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
                return JSONResponse(
                    content={
                        "ok": False,
                        "step": "scraper",
                        "error": str(e),
                        "trace": trace_id
                    },
                    status_code=502,
                    headers={
                        "X-Trace-Id": trace_id,
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                        "Access-Control-Allow-Headers": "*"
                    }
                )
            
            # Step 2: Normalize response
            print(f"[api] Step 2: Normalizing response (trace: {trace_id})")
            normalize_start = time.time()
            normalized_data = normalize_scraper_response(scraper_response)
            normalize_time = time.time() - normalize_start
            
            # Log item count and field presence rates
            item_count = len(normalized_data.items)
            ended_at_count = sum(1 for item in normalized_data.items if item.ended_at)
            url_count = sum(1 for item in normalized_data.items if item.url)
            sold_count = sum(1 for item in normalized_data.items if item.sold is True)
            image_url_count = sum(1 for item in normalized_data.items if item.image_url)
            shipping_price_count = sum(1 for item in normalized_data.items if item.shipping_price is not None)
            total_price_count = sum(1 for item in normalized_data.items if item.total_price is not None)
            bids_count = sum(1 for item in normalized_data.items if item.bids is not None)
            condition_count = sum(1 for item in normalized_data.items if item.condition)
            parsed_count = sum(1 for item in normalized_data.items if item.parsed)
            
            print(f"[api] Step 2: Normalized {item_count} items in {normalize_time:.2f}s (trace: {trace_id})")
            print(f"[api]   - ended_at: {ended_at_count}/{item_count} ({ended_at_count/item_count*100:.1f}%)")
            print(f"[api]   - url: {url_count}/{item_count} ({url_count/item_count*100:.1f}%)")
            print(f"[api]   - sold: {sold_count}/{item_count} ({sold_count/item_count*100:.1f}%)")
            print(f"[api]   - image_url: {image_url_count}/{item_count} ({image_url_count/item_count*100:.1f}%)")
            print(f"[api]   - shipping_price: {shipping_price_count}/{item_count} ({shipping_price_count/item_count*100:.1f}%)")
            print(f"[api]   - total_price: {total_price_count}/{item_count} ({total_price_count/item_count*100:.1f}%)")
            print(f"[api]   - bids: {bids_count}/{item_count} ({bids_count/item_count*100:.1f}%)")
            print(f"[api]   - condition: {condition_count}/{item_count} ({condition_count/item_count*100:.1f}%)")
            print(f"[api]   - parsed: {parsed_count}/{item_count} ({parsed_count/item_count*100:.1f}%)")
            
            # Log first 1-2 item titles
            item_titles = [item.title for item in normalized_data.items[:2]]
            print(f"[api] First titles: {item_titles}")
            
            # Step 3: Post to Edge Function (optional - don't fail if this times out)
            ef_status = None
            ef_body = ""
            external_ok = False
            
            if SUPABASE_FUNCTION_URL and SUPABASE_FUNCTION_TOKEN:
                print(f"[api] Step 3: Starting Edge Function call (trace: {trace_id})")
                ef_start = time.time()
                
                try:
                    ef_status, ef_body = await asyncio.wait_for(
                        post_to_edge_function(normalized_data.dict()),
                        timeout=EF_TIMEOUT
                    )
                    ef_time = time.time() - ef_start
                    
                    # Truncate body for logging (max 300 chars)
                    ef_body_truncated = ef_body[:300] + "..." if len(ef_body) > 300 else ef_body
                    print(f"[api] Step 3: Edge Function completed in {ef_time:.2f}s (status: {ef_status}) (trace: {trace_id})")
                    print(f"[api] Edge Function response: {ef_body_truncated}")
                    
                    external_ok = ef_status == 200
                    
                except asyncio.TimeoutError:
                    print(f"[api] WARNING: Edge Function timeout ({EF_TIMEOUT}s) - continuing with partial results (trace: {trace_id})")
                    ef_status = 408
                    ef_body = "timeout"
                    external_ok = False
                except Exception as e:
                    print(f"[api] WARNING: Edge Function failed: {e} - continuing with partial results (trace: {trace_id})")
                    ef_status = 500
                    ef_body = str(e)
                    external_ok = False
            else:
                print(f"[api] Step 3: Edge Function not configured - skipping (trace: {trace_id})")
                ef_status = None
                ef_body = "Edge Function not configured"
                external_ok = False
            
            # Prepare response
            total_time = time.time() - scraper_start
            response = {
                "ok": True,
                "items": [item.dict() for item in normalized_data.items],
                "externalOk": external_ok,
                "efStatus": ef_status,
                "efBody": ef_body
            }
            
            print(f"[api] scrape-now q=\"{query}\" items={len(normalized_data.items)} dur={total_time:.1f}s (trace: {trace_id})")
            return JSONResponse(
                content=response,
                headers={
                    "X-Trace-Id": trace_id,
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                }
            )
            
        except asyncio.TimeoutError:
            error_msg = f"Global request timeout ({GLOBAL_TIMEOUT}s)"
            print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
            return JSONResponse(
                content={
                    "ok": False,
                    "step": "global",
                    "error": "timeout",
                    "trace": trace_id
                },
                status_code=502,
                headers={
                    "X-Trace-Id": trace_id,
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                    "Access-Control-Allow-Headers": "*"
                }
            )

@app.post("/scrape-now/")
async def scrape_now_trailing(request: ScrapeRequest, http_request: Request):
    """Handle /scrape-now/ (with trailing slash) - redirect to main handler"""
    return await scrape_now(request, http_request)

@app.post("/normalize-test")
async def normalize_test(request: NormalizeTestRequest, http_request: Request):
    """Normalize items locally without calling Edge Function"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    print(f"[api] normalize-test request from {client_ip} (trace: {trace_id})")
    
    try:
        start_time = time.time()
        items = []
        source = "items"
        
        if request.items:
            # Normalize provided items
            print(f"[api] Normalizing {len(request.items)} provided items (trace: {trace_id})")
            for item in request.items:
                normalized = normalizer.normalize_item(item)
                items.append(NormalizedTestItem(
                    title=normalized.title,
                    url=normalized.url,
                    price=normalized.price,
                    currency=normalized.currency,
                    ended_at=normalized.ended_at,
                    id=normalized.id,
                    source=normalized.source,
                    parsed=ParsedHints(
                        set_name=normalized.parsed.set_name,
                        edition=normalized.parsed.edition,
                        number=normalized.parsed.number,
                        year=normalized.parsed.year,
                        grading_company=normalized.parsed.grading_company,
                        grade=normalized.parsed.grade,
                        is_holo=normalized.parsed.is_holo,
                        franchise=normalized.parsed.franchise,
                        canonical_key=normalized.canonical_key,
                        rarity=normalized.rarity,
                        tags=normalized.tags,
                        sold=normalized.sold,
                        set=normalized.set,
                        language=normalized.language,
                        grader=normalized.grader,
                        grade_value=normalized.grade_value
                    ),
                    canonical_key=normalized.canonical_key,
                    confidence=normalized.confidence
                ))
        elif request.query:
            # Call scraper and normalize results
            print(f"[api] Scraping query '{request.query}' with limit {request.limit} (trace: {trace_id})")
            source = "scraper"
            
            scraper_start = time.time()
            scraper_data = await asyncio.wait_for(
                call_scraper(request.query),
                timeout=SCRAPER_TIMEOUT
            )
            scraper_time = time.time() - scraper_start
            
            print(f"[api] Scraper completed in {scraper_time:.2f}s (trace: {trace_id})")
            
            # Extract items from scraper response
            raw_items = []
            if "items" in scraper_data and isinstance(scraper_data["items"], list):
                raw_items = scraper_data["items"][:request.limit]
            elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
                # Handle legacy format
                raw_items = scraper_data["prices"][:request.limit]
            
            # Normalize items
            for item in raw_items:
                if isinstance(item, dict):
                    normalized = normalizer.normalize_item(item)
                    items.append(NormalizedTestItem(
                        title=normalized.title,
                        url=normalized.url,
                        price=normalized.price,
                        currency=normalized.currency,
                        ended_at=normalized.ended_at,
                        id=normalized.id,
                        source=normalized.source,
                        parsed=ParsedHints(
                            set_name=normalized.parsed.set_name,
                            edition=normalized.parsed.edition,
                            number=normalized.parsed.number,
                            year=normalized.parsed.year,
                            grading_company=normalized.parsed.grading_company,
                            grade=normalized.parsed.grade,
                            is_holo=normalized.parsed.is_holo,
                            franchise=normalized.parsed.franchise,
                            canonical_key=normalized.canonical_key,
                            rarity=normalized.rarity,
                            tags=normalized.tags,
                            sold=normalized.sold,
                            set=normalized.set,
                            language=normalized.language,
                            grader=normalized.grader,
                            grade_value=normalized.grade_value
                        ),
                        canonical_key=normalized.canonical_key,
                        confidence=normalized.confidence
                    ))
        else:
            raise HTTPException(status_code=400, detail="Either 'items' or 'query' must be provided")
        
        total_time = time.time() - start_time
        
        print(f"[api] normalize-test q=\"{request.query or 'items'}\" items={len(items)} dur={total_time:.1f}s (trace: {trace_id})")
        
        return JSONResponse(
            content=NormalizeTestResponse(
                ok=True,
                source=source,
                count=len(items),
                items=items,
                trace=trace_id
            ).dict(),
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except asyncio.TimeoutError:
        error_msg = f"Scraper timeout ({SCRAPER_TIMEOUT}s)"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "scraper",
                "error": "timeout",
                "trace": trace_id
            },
            status_code=502,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    except Exception as e:
        error_msg = f"Normalization failed: {str(e)}"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "scraper",
                "error": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )

@app.post("/ingest-items")
async def ingest_items(request: IngestItemsRequest, http_request: Request):
    """Forward normalized items to Supabase Edge Function"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    print(f"[api] ingest-items request from {client_ip} items={len(request.items)} dry_run={request.dry_run} (trace: {trace_id})")
    
    # Validate request size
    if len(request.items) > 200:
        return JSONResponse(
            content={
                "ok": False,
                "error": "Too many items (max 200)",
                "trace": trace_id
            },
            status_code=413,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    
    try:
        start_time = time.time()
        
        # Prepare payload for Edge Function
        ef_payload = {
            "raw_query": request.raw_query,
            "items": [],
            "dry_run": request.dry_run
        }
        
        # Process each item
        for item in request.items:
            if "canonical_key" in item:
                # Item already normalized, include canonical_key
                ef_payload["items"].append(item)
            else:
                # Raw item, add normalized as subobject
                normalized = normalizer.normalize_item(item)
                ef_payload["items"].append({
                    **item,
                    "normalized": {
                        "canonical_key": normalized.canonical_key,
                        "parsed": {
                            "set_name": normalized.parsed.set_name,
                            "edition": normalized.parsed.edition,
                            "number": normalized.parsed.number,
                            "year": normalized.parsed.year,
                            "grading_company": normalized.parsed.grading_company,
                            "grade": normalized.parsed.grade,
                            "is_holo": normalized.parsed.is_holo,
                            "franchise": normalized.parsed.franchise
                        },
                        "confidence": normalized.confidence
                    }
                })
        
        # Call Edge Function
        ef_start = time.time()
        ef_status, ef_body = await asyncio.wait_for(
            post_to_edge_function(ef_payload),
            timeout=EF_TIMEOUT
        )
        ef_time = time.time() - ef_start
        
        # Parse EF response
        try:
            ef_response = json.loads(ef_body) if ef_body else {}
            items_results = ef_response.get("items", [])
        except json.JSONDecodeError:
            items_results = []
        
        total_time = time.time() - start_time
        external_ok = ef_status == 200
        
        print(f"[api] ingest-items items={len(request.items)} dry_run={request.dry_run} ef={ef_status} dur={total_time:.1f}s (trace: {trace_id})")
        
        return JSONResponse(
            content=IngestItemsResponse(
                ok=True,
                externalOk=external_ok,
                count=len(request.items),
                items=items_results,
                trace=trace_id
            ).dict(),
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except asyncio.TimeoutError:
        error_msg = f"Edge Function timeout ({EF_TIMEOUT}s)"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "edge_function",
                "error": "timeout",
                "trace": trace_id
            },
            status_code=502,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    except Exception as e:
        error_msg = f"Ingest failed: {str(e)}"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "ingest",
                "error": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )

@app.options("/normalize-test")
async def normalize_test_options():
    """Handle CORS preflight for /normalize-test"""
    return JSONResponse(
        content={"ok": True},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "X-Trace-Id": str(uuid.uuid4())[:8]
        }
    )

@app.post("/normalize-test")
async def normalize_test(request: NormalizeTestRequest, http_request: Request):
    """Normalize items locally without calling Edge Function"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    print(f"[api] normalize-test request from {client_ip} (trace: {trace_id})")
    
    try:
        start_time = time.time()
        items = []
        source = "items"
        
        if request.items:
            # Normalize provided items
            print(f"[api] Normalizing {len(request.items)} provided items (trace: {trace_id})")
            for item in request.items:
                normalized = normalizer.normalize_item(item)
                items.append(NormalizedTestItem(
                    title=normalized.title,
                    url=normalized.url,
                    price=normalized.price,
                    currency=normalized.currency,
                    ended_at=normalized.ended_at,
                    id=normalized.id,
                    source=normalized.source,
                    parsed=ParsedHints(
                        set_name=normalized.parsed.set_name,
                        edition=normalized.parsed.edition,
                        number=normalized.parsed.number,
                        year=normalized.parsed.year,
                        grading_company=normalized.parsed.grading_company,
                        grade=normalized.parsed.grade,
                        is_holo=normalized.parsed.is_holo,
                        franchise=normalized.parsed.franchise,
                        canonical_key=normalized.canonical_key,
                        rarity=normalized.rarity,
                        tags=normalized.tags,
                        sold=normalized.sold,
                        set=normalized.set,
                        language=normalized.language,
                        grader=normalized.grader,
                        grade_value=normalized.grade_value
                    ),
                    canonical_key=normalized.canonical_key,
                    confidence=normalized.confidence
                ))
        elif request.query:
            # Call scraper and normalize results
            print(f"[api] Scraping query '{request.query}' with limit {request.limit} (trace: {trace_id})")
            source = "scraper"
            
            scraper_start = time.time()
            scraper_data = await asyncio.wait_for(
                call_scraper(request.query),
                timeout=SCRAPER_TIMEOUT
            )
            scraper_time = time.time() - scraper_start
            
            print(f"[api] Scraper completed in {scraper_time:.2f}s (trace: {trace_id})")
            
            # Extract items from scraper response
            raw_items = []
            if "items" in scraper_data and isinstance(scraper_data["items"], list):
                raw_items = scraper_data["items"][:request.limit]
            elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
                # Handle legacy format
                raw_items = scraper_data["prices"][:request.limit]
            
            # Normalize items
            for item in raw_items:
                if isinstance(item, dict):
                    normalized = normalizer.normalize_item(item)
                    items.append(NormalizedTestItem(
                        title=normalized.title,
                        url=normalized.url,
                        price=normalized.price,
                        currency=normalized.currency,
                        ended_at=normalized.ended_at,
                        id=normalized.id,
                        source=normalized.source,
                        parsed=ParsedHints(
                            set_name=normalized.parsed.set_name,
                            edition=normalized.parsed.edition,
                            number=normalized.parsed.number,
                            year=normalized.parsed.year,
                            grading_company=normalized.parsed.grading_company,
                            grade=normalized.parsed.grade,
                            is_holo=normalized.parsed.is_holo,
                            franchise=normalized.parsed.franchise,
                            canonical_key=normalized.canonical_key,
                            rarity=normalized.rarity,
                            tags=normalized.tags,
                            sold=normalized.sold,
                            set=normalized.set,
                            language=normalized.language,
                            grader=normalized.grader,
                            grade_value=normalized.grade_value
                        ),
                        canonical_key=normalized.canonical_key,
                        confidence=normalized.confidence
                    ))
        else:
            raise HTTPException(status_code=400, detail="Either 'items' or 'query' must be provided")
        
        total_time = time.time() - start_time
        
        print(f"[api] normalize-test q=\"{request.query or 'items'}\" items={len(items)} dur={total_time:.1f}s (trace: {trace_id})")
        
        return JSONResponse(
            content=NormalizeTestResponse(
                ok=True,
                source=source,
                count=len(items),
                items=items,
                trace=trace_id
            ).dict(),
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except asyncio.TimeoutError:
        error_msg = f"Scraper timeout ({SCRAPER_TIMEOUT}s)"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "scraper",
                "error": "timeout",
                "trace": trace_id
            },
            status_code=502,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    except Exception as e:
        error_msg = f"Normalization failed: {str(e)}"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "normalize",
                "error": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )

@app.options("/ingest-items")
async def ingest_items_options():
    """Handle CORS preflight for /ingest-items"""
    return JSONResponse(
        content={"ok": True},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "X-Trace-Id": str(uuid.uuid4())[:8]
        }
    )

@app.post("/ingest-items")
async def ingest_items(request: IngestItemsRequest, http_request: Request):
    """Forward normalized items to Supabase Edge Function"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    print(f"[api] ingest-items request from {client_ip} items={len(request.items)} dry_run={request.dry_run} (trace: {trace_id})")
    
    # Validate request size
    if len(request.items) > 200:
        return JSONResponse(
            content={
                "ok": False,
                "error": "Too many items (max 200)",
                "trace": trace_id
            },
            status_code=413,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    
    try:
        start_time = time.time()
        
        # Prepare payload for Edge Function
        ef_payload = {
            "raw_query": request.raw_query,
            "items": [],
            "dry_run": request.dry_run
        }
        
        # Process each item
        for item in request.items:
            if "canonical_key" in item:
                # Item already normalized, include canonical_key
                ef_payload["items"].append(item)
            else:
                # Raw item, add normalized as subobject
                normalized = normalizer.normalize_item(item)
                ef_payload["items"].append({
                    **item,
                    "normalized": {
                        "canonical_key": normalized.canonical_key,
                        "parsed": {
                            "set_name": normalized.parsed.set_name,
                            "edition": normalized.parsed.edition,
                            "number": normalized.parsed.number,
                            "year": normalized.parsed.year,
                            "grading_company": normalized.parsed.grading_company,
                            "grade": normalized.parsed.grade,
                            "is_holo": normalized.parsed.is_holo,
                            "franchise": normalized.parsed.franchise
                        },
                        "confidence": normalized.confidence
                    }
                })
        
        # Call Edge Function
        ef_start = time.time()
        ef_status, ef_body = await asyncio.wait_for(
            post_to_edge_function(ef_payload),
            timeout=EF_TIMEOUT
        )
        ef_time = time.time() - ef_start
        
        # Parse EF response
        try:
            ef_response = json.loads(ef_body) if ef_body else {}
            items_results = ef_response.get("items", [])
        except json.JSONDecodeError:
            items_results = []
        
        total_time = time.time() - start_time
        external_ok = ef_status == 200
        
        print(f"[api] ingest-items items={len(request.items)} dry_run={request.dry_run} ef={ef_status} dur={total_time:.1f}s (trace: {trace_id})")
        
        return JSONResponse(
            content=IngestItemsResponse(
                ok=True,
                externalOk=external_ok,
                count=len(request.items),
                items=items_results,
                trace=trace_id
            ).dict(),
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except asyncio.TimeoutError:
        error_msg = f"Edge Function timeout ({EF_TIMEOUT}s)"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "edge_function",
                "error": "timeout",
                "trace": trace_id
            },
            status_code=502,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    except Exception as e:
        error_msg = f"Ingest failed: {str(e)}"
        print(f"[api] ERROR: {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "step": "ingest",
                "error": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )

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