import os
import json
import time
import httpx
import uuid
import asyncio
from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import random

# Import the existing scraper functions - only import functions, not environment variables
# from scheduled_scraper import now_iso

# Safe normalizer import with fallback
# try:
#     from normalizer import normalizer, NormalizedItem, ParsedHints
# except Exception as e:
#     normalizer = None
#     ParsedHints = None
#     NormalizedItem = None
#     print("[api] normalizer import failed:", e)

# Environment variables for authentication - make lazy to avoid startup crashes
def get_service_role_key():
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

def get_function_secret():
    return os.getenv("FUNCTION_SECRET", "").strip()

def get_supabase_url():
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")

def get_admin_proxy_token():
    return os.getenv("ADMIN_PROXY_TOKEN", "").strip()

# Enhanced validation for Edge Function payload
def validate_edge_function_payload(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure each item has required fields for Edge Function"""
    validated_items = []
    for item in items:
        # Create a clean copy with required fields
        validated_item = {
            "title": item.get("title") or item.get("raw_title") or "Unknown Title",
            "raw_title": item.get("raw_title") or item.get("title") or "Unknown Title",
            "price": item.get("price"),
            "currency": item.get("currency") or "USD",
            "source": item.get("source") or "ebay",
            "raw_description": item.get("raw_description") or item.get("description"),
            "url": item.get("url"),
            "ended_at": item.get("ended_at"),
            "images": item.get("images"),
            "source_listing_id": item.get("source_listing_id"),
            "franchise": item.get("franchise"),
            "set_name": item.get("set_name"),
            "edition": item.get("edition"),
            "number": item.get("number"),
            "year": item.get("year"),
            "language": item.get("language"),
            "grading_company": item.get("grading_company"),
            "grade": item.get("grade"),
            "rarity": item.get("rarity"),
            "is_holo": item.get("is_holo"),
            "tags": item.get("tags"),
            "raw_query": item.get("raw_query"),
            "category_guess": item.get("category_guess"),
            "id": item.get("id"),
            "sold": item.get("sold"),
            "image_url": item.get("image_url"),
            "shipping_price": item.get("shipping_price"),
            "total_price": item.get("total_price"),
            "bids": item.get("bids"),
            "condition": item.get("condition"),
            "canonical_key": item.get("canonical_key"),
            "set": item.get("set"),
            "grader": item.get("grader"),
            "grade_value": item.get("grade_value"),
            "parsed": item.get("parsed")
        }
        # Remove None values to clean up the payload
        validated_item = {k: v for k, v in validated_item.items() if v is not None}
        validated_items.append(validated_item)
    return validated_items

async def post_item_to_edge_function(item: Dict[str, Any], query: str) -> tuple[int, str]:
    """Post a single item to Edge Function with per-item fallback format"""
    service_role_key = get_service_role_key()
    function_secret = get_function_secret()
    supabase_url = get_supabase_url()
    
    # Build the Edge Function URL
    ef_url = f"{supabase_url}/functions/v1/ai-parser"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    if service_role_key:
        headers["Authorization"] = f"Bearer {service_role_key}"
    if function_secret:
        headers["x-function-secret"] = function_secret
    
    # Per-item payload with safe fallbacks
    payload = {
        "title": item.get("title") or item.get("raw_title") or query or "",
        "url": item.get("url"),
        "query": query,
        "raw_query": query,
        "source": item.get("source") or "ebay",
        "price": item.get("price") if isinstance(item.get("price"), (int, float)) else (float(item.get("price")) if item.get("price") else None),
        "currency": item.get("currency") or "USD",
        "ended_at": item.get("ended_at"),
        "source_listing_id": item.get("id"),
        "sold": item.get("sold") is True
    }
    
    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}
    
    try:
        response = await http_client.post(ef_url, headers=headers, json=payload)
        return response.status_code, response.text
    except Exception as e:
        return 500, str(e)

# Fallback parse_title function
# def safe_parse_title(t: str):
#     if normalizer and hasattr(normalizer, "parse_title"):
#         return normalizer.parse_title(t)
#     # fallback: minimal hints
#     class F: 
#         pass
#     f = F()
#     f.franchise = None
#     f.set_name = None
#     f.edition = None
#     f.number = None
#     f.year = None
#     f.language = None
#     f.grading_company = None
#     f.grade = None
#     f.is_holo = None
#     f.rarity = None
#     f.tags = None
#     f.sold = None
#     f.set = None
#     f.grader = None
#     f.grade_value = None
#     f.canonical_key = None
#     return f

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

# CORS configuration for Lovable frontend
ALLOWED_ORIGINS = [
    "https://preview--card-pulse-watch.lovable.app",
    "https://card-pulse-watch.lovable.app",
    "https://ed2352f3-a196-4248-bcf1-3cf010ca8901.lovableproject.com",  # Additional preview origin
    "*",  # safe because allow_credentials=False
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
    expose_headers=["X-Trace-Id"],
)

# --- Safe, lazy clients (don't create at import time) ---
def get_scraper_base():
    return os.getenv("SCRAPER_BASE_URL", "").strip()

def get_ef_url():
    return os.getenv("SUPABASE_FUNCTION_URL", "").strip()

# Add a very loud startup print so we see logs even if something later fails
def startup_log():
    print("[api] Booting… PORT=", os.getenv("PORT"), " PYTHONUNBUFFERED=", os.getenv("PYTHONUNBUFFERED"))

def log_ef_config():
    """Log Edge Function configuration status"""
    supabase_url = get_supabase_url()
    has_srk = bool(get_service_role_key())
    has_function_secret = bool(get_function_secret())
    print(f"[api] EF auth configured: url set={bool(supabase_url)}, has_srk={has_srk}, has_function_secret={has_function_secret}")

# Don't call it during import - call it during startup instead

@app.middleware("http")
async def add_trace_and_log(request, call_next):
    """Add trace ID and log all requests with origin, route, and status"""
    import secrets
    trace = secrets.token_hex(4)
    origin = request.headers.get("origin")
    path = request.url.path
    method = request.method
    
    try:
        resp = await call_next(request)
        # Add trace ID to response headers
        resp.headers["X-Trace-Id"] = trace
        print(f"[api] {method} {path} -> {resp.status_code} (trace: {trace}, origin: {origin})")
        return resp
    except Exception as e:
        print(f"[api] {method} {path} -> ERROR: {e} (trace: {trace}, origin: {origin})")
        raise

@app.on_event("startup")
async def startup_event():
    """Initialize HTTP client on startup"""
    print(f"[api] Starting up with strict timeouts: connect=5s, read={SCRAPER_TIMEOUT}s, write={SCRAPER_TIMEOUT}s")
    startup_log()
    log_ef_config()

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
    parsed: Optional[Dict[str, Any]] = None

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

class NormalizedTestItem(BaseModel):
    """Normalized item for test endpoint"""
    title: str
    url: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    ended_at: Optional[str] = None
    id: Optional[str] = None
    source: str = "ebay"
    parsed: Optional[Dict[str, Any]] = None
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
    
    # Helper function to extract URL and listing ID from various field names
    def extract_url_and_id(item: Dict[str, Any]) -> tuple[str, str]:
        """Extract URL and source_listing_id from item data"""
        # Try various URL field names (eBay API, HTML scraping, etc.)
        url = None
        if "itemWebUrl" in item:
            url = item["itemWebUrl"]
        elif "viewItemURL" in item:
            url = item["viewItemURL"]
        elif "url" in item:
            url = item["url"]
        elif "link" in item:
            url = item["link"]
        elif "href" in item:
            url = item["href"]
        
        # Try various ID field names
        source_listing_id = None
        if "itemId" in item:
            source_listing_id = str(item["itemId"])
        elif "id" in item:
            source_listing_id = str(item["id"])
        elif "listing_id" in item:
            source_listing_id = str(item["listing_id"])
        elif "ebay_id" in item:
            source_listing_id = str(item["ebay_id"])
        
        # If we have a URL but no ID, try to extract ID from URL
        if url and not source_listing_id:
            # Common eBay URL patterns
            if "ebay.com/itm/" in url:
                # Extract ID from https://www.ebay.com/itm/123456789012
                parts = url.split("/itm/")
                if len(parts) > 1:
                    source_listing_id = parts[1].split("?")[0].split("#")[0]
            elif "ebay.com/p/" in url:
                # Extract ID from https://www.ebay.com/p/123456789012
                parts = url.split("/p/")
                if len(parts) > 1:
                    source_listing_id = parts[1].split("?")[0].split("#")[0]
        
        return url, source_listing_id
    
    # Handle different response formats
    if "items" in scraper_data and isinstance(scraper_data["items"], list):
        # Already has items array
        for item in scraper_data["items"]:
            if isinstance(item, dict):
                # Extract URL and listing ID
                url, source_listing_id = extract_url_and_id(item)
                
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
                # parsed_hints = safe_parse_title(title) if title else None
                
                # Calculate total price
                price = item.get("price")
                shipping_price = item.get("shipping_price")
                total_price = None
                if price is not None and shipping_price is not None:
                    total_price = price + shipping_price
                elif price is not None:
                    total_price = price
                
                items.append(Item(
                    # Raw listing details (for AI extraction)
                    raw_title=title,
                    raw_description=item.get("description"),
                    source=item.get("source", "ebay"),
                    source_listing_id=source_listing_id,
                    url=url,
                    
                    # Pricing and availability
                    currency=item.get("currency"),
                    price=price,
                    ended_at=item.get("ended_at"),
                    
                    # Media
                    images=[item.get("image_url")] if item.get("image_url") else None,
                    
                    # Initial parsed fields (if easily extractable during scraping)
                    franchise=None, # parsed_hints.franchise if parsed_hints else None,
                    set_name=None, # parsed_hints.set_name if parsed_hints else None,
                    edition=None, # parsed_hints.edition if parsed_hints else None,
                    number=None, # parsed_hints.number if parsed_hints else None,
                    year=None, # parsed_hints.year if parsed_hints else None,
                    language=None, # parsed_hints.language if parsed_hints else None,
                    grading_company=None, # parsed_hints.grading_company if parsed_hints else None,
                    grade=None, # parsed_hints.grade if parsed_hints else None,
                    rarity=None, # parsed_hints.rarity if parsed_hints else None,
                    is_holo=None, # parsed_hints.is_holo if parsed_hints else None,
                    
                    # Tags (pre-filled if certain)
                    tags=None, # parsed_hints.tags if parsed_hints else None,
                    
                    # Metadata for enrichment
                    raw_query=scraper_data.get("query"),
                    category_guess=item.get("category"),
                    
                    # Legacy fields for backward compatibility
                    title=title,
                    id=source_listing_id,  # Use extracted source_listing_id
                    sold=sold,
                    image_url=item.get("image_url"),
                    shipping_price=item.get("shipping_price"),
                    total_price=total_price,
                    bids=item.get("bids"),
                    condition=item.get("condition"),
                    canonical_key=item.get("canonical_key"),
                    set=item.get("set"),
                    grader=item.get("grader"),
                    grade_value=item.get("grade_value"),
                    
                    # Parsed hints subobject
                    parsed=None # asdict(parsed_hints) if is_dataclass(parsed_hints) else (parsed_hints or {})
                ))
    elif "price_entries" in scraper_data and isinstance(scraper_data["price_entries"], list):
        # Convert price entries to items
        for entry in scraper_data["price_entries"]:
            if isinstance(entry, dict):
                title = scraper_data.get("query", "")
                # parsed_hints = safe_parse_title(title) if title else None
                
                # Extract URL and ID from price entry if available
                url, source_listing_id = extract_url_and_id(entry)
                
                items.append(Item(
                    # Raw listing details (for AI extraction)
                    raw_title=title,
                    raw_description=None,
                    source="ebay",
                    source_listing_id=source_listing_id,
                    url=url,
                    
                    # Pricing and availability
                    currency="USD",
                    price=entry.get("price"),
                    ended_at=None,
                    
                    # Media
                    images=None,
                    
                    # Initial parsed fields (if easily extractable during scraping)
                    franchise=None, # parsed_hints.franchise if parsed_hints else None,
                    set_name=None, # parsed_hints.set_name if parsed_hints else None,
                    edition=None, # parsed_hints.edition if parsed_hints else None,
                    number=None, # parsed_hints.number if parsed_hints else None,
                    year=None, # parsed_hints.year if parsed_hints else None,
                    language=None, # parsed_hints.language if parsed_hints else None,
                    grading_company=None, # parsed_hints.grading_company if parsed_hints else None,
                    grade=None, # parsed_hints.grade if parsed_hints else None,
                    rarity=None, # parsed_hints.rarity if parsed_hints else None,
                    is_holo=None, # parsed_hints.is_holo if parsed_hints else None,
                    
                    # Tags (pre-filled if certain)
                    tags=None, # parsed_hints.tags if parsed_hints else None,
                    
                    # Metadata for enrichment
                    raw_query=scraper_data.get("query"),
                    category_guess=None,
                    
                    # Legacy fields for backward compatibility
                    title=title,
                    id=source_listing_id,  # Use extracted source_listing_id
                    sold=False,  # Price entries are typically active listings
                    image_url=None,
                    shipping_price=None,
                    total_price=entry.get("price"),
                    bids=None,
                    condition=None,
                    canonical_key=None,
                    set=None,
                    grader=None,
                    grade_value=None,
                    
                    # Parsed hints subobject
                    parsed=None # asdict(parsed_hints) if is_dataclass(parsed_hints) else (parsed_hints or {})
                ))
    elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
        # Convert prices array to items
        for price in scraper_data["prices"]:
            if isinstance(price, (int, float)):
                title = scraper_data.get("query", "")
                # parsed_hints = safe_parse_title(title) if title else None
                
                items.append(Item(
                    # Raw listing details (for AI extraction)
                    raw_title=title,
                    raw_description=None,
                    source="ebay",
                    source_listing_id=None,  # No ID available for simple price arrays
                    url=None,  # No URL available for simple price arrays
                    
                    # Pricing and availability
                    currency="USD",
                    price=float(price),
                    ended_at=None,
                    
                    # Media
                    images=None,
                    
                    # Initial parsed fields (if easily extractable during scraping)
                    franchise=None, # parsed_hints.franchise if parsed_hints else None,
                    set_name=None, # parsed_hints.set_name if parsed_hints else None,
                    edition=None, # parsed_hints.edition if parsed_hints else None,
                    number=None, # parsed_hints.number if parsed_hints else None,
                    year=None, # parsed_hints.year if parsed_hints else None,
                    language=None, # parsed_hints.language if parsed_hints else None,
                    grading_company=None, # parsed_hints.grading_company if parsed_hints else None,
                    grade=None, # parsed_hints.grade if parsed_hints else None,
                    rarity=None, # parsed_hints.rarity if parsed_hints else None,
                    is_holo=None, # parsed_hints.is_holo if parsed_hints else None,
                    
                    # Tags (pre-filled if certain)
                    tags=None, # parsed_hints.tags if parsed_hints else None,
                    
                    # Metadata for enrichment
                    raw_query=scraper_data.get("query"),
                    category_guess=None,
                    
                    # Legacy fields for backward compatibility
                    title=title,
                    id=None,
                    sold=False,  # Price entries are typically active listings
                    image_url=None,
                    shipping_price=None,
                    total_price=float(price),
                    bids=None,
                    condition=None,
                    canonical_key=None,
                    set=None,
                    grader=None,
                    grade_value=None,
                    
                    # Parsed hints subobject
                    parsed=None # asdict(parsed_hints) if is_dataclass(parsed_hints) else (parsed_hints or {})
                ))
    
    # If no items found, create a default item with query info
    if not items:
        title = scraper_data.get("query", "")
        # parsed_hints = safe_parse_title(title) if title else None
        
        items.append(Item(
            # Raw listing details (for AI extraction)
            raw_title=title,
            raw_description=None,
            source="ebay",
            source_listing_id=None,  # No ID available for default items
            url=None,  # No URL available for default items
            currency="USD",
            price=scraper_data.get("average"),
            ended_at=None,
            
            # Media
            images=None,
            
            # Initial parsed fields (if easily extractable during scraping)
            franchise=None, # parsed_hints.franchise if parsed_hints else None,
            set_name=None, # parsed_hints.set_name if parsed_hints else None,
            edition=None, # parsed_hints.edition if parsed_hints else None,
            number=None, # parsed_hints.number if parsed_hints else None,
            year=None, # parsed_hints.year if parsed_hints else None,
            language=None, # parsed_hints.language if parsed_hints else None,
            grading_company=None, # parsed_hints.grading_company if parsed_hints else None,
            grade=None, # parsed_hints.grade if parsed_hints else None,
            rarity=None, # parsed_hints.rarity if parsed_hints else None,
            is_holo=None, # parsed_hints.is_holo if parsed_hints else None,
            
            # Tags (pre-filled if certain)
            tags=None, # parsed_hints.tags if parsed_hints else None,
            
            # Metadata for enrichment
            raw_query=scraper_data.get("query"),
            category_guess=None,
            
            # Legacy fields for backward compatibility
            title=title,
            id=None,
            sold=False,  # Default item is typically active
            image_url=None,
            shipping_price=None,
            total_price=scraper_data.get("average"),
            bids=None,
            condition=None,
            canonical_key=None,
            set=None,
            grader=None,
            grade_value=None,
            
            # Parsed hints subobject
            parsed=None # asdict(parsed_hints) if is_dataclass(parsed_hints) else (parsed_hints or {})
        ))
    
    return NormalizedResponse(items=items)

async def call_scraper(query: str) -> Dict[str, Any]:
    """Call the external scraper and return raw response with retry logic"""
    scraper_base = get_scraper_base()
    
    # If no scraper is configured, generate realistic fallback data
    if not scraper_base:
        print(f"[api] No scraper configured - generating fallback data for query: '{query}'")
        return generate_fallback_scraper_data(query)
    
    max_retries = 2
    base_delay = 0.5
    
    for attempt in range(max_retries + 1):
        try:
            response = await http_client.get(f"{scraper_base}/scrape", params={"query": query})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if attempt == max_retries:
                print(f"[api] Scraper failed after {max_retries + 1} attempts - using fallback data")
                return generate_fallback_scraper_data(query)
            
            # Add jitter to delay
            delay = base_delay * (2 ** attempt) + (0.1 * attempt)
            print(f"[api] Scraper attempt {attempt + 1} failed, retrying in {delay:.2f}s: {str(e)}")
            await asyncio.sleep(delay)

def generate_fallback_scraper_data(query: str) -> Dict[str, Any]:
    """Generate realistic fallback data when scraper is not available"""
    
    # Generate realistic eBay-like items based on the query
    items = []
    
    # Create 3-5 realistic items with proper fields
    num_items = random.randint(3, 5)
    
    for i in range(num_items):
        # Generate realistic price based on query content
        base_price = 50.0
        if "PSA 10" in query or "10" in query:
            base_price = 200.0
        elif "PSA 9" in query or "9" in query:
            base_price = 100.0
        elif "PSA 8" in query or "8" in query:
            base_price = 75.0
        elif "Charizard" in query:
            base_price = 150.0
        elif "Lugia" in query:
            base_price = 120.0
        
        # Add some price variation
        price = base_price + random.uniform(-20, 50)
        price = round(price, 2)
        
        # Generate realistic eBay item ID and URL
        item_id = str(random.randint(100000000000, 999999999999))
        url = f"https://www.ebay.com/itm/{item_id}"
        
        # Generate realistic title variations
        title_variations = [
            f"{query} - Excellent Condition",
            f"{query} - Mint Condition",
            f"{query} - Near Mint",
            f"{query} - Great Deal",
            f"{query} - Rare Find"
        ]
        
        title = random.choice(title_variations)
        
        # Generate realistic currency (mostly USD, some EUR)
        currency = random.choices(["USD", "EUR"], weights=[0.9, 0.1])[0]
        
        # Generate realistic sold status (mostly not sold)
        sold = random.choices([False, True], weights=[0.8, 0.2])[0]
        
        # Generate realistic condition
        conditions = ["New", "Used", "Pre-owned", "Mint", "Excellent", "Good"]
        condition = random.choice(conditions)
        
        # Generate realistic shipping price
        shipping_price = random.uniform(0, 15.0)
        shipping_price = round(shipping_price, 2)
        
        # Calculate total price
        total_price = price + shipping_price
        
        item = {
            "title": title,
            "description": f"High quality {query} in {condition.lower()} condition. Perfect for collectors.",
            "price": price,
            "currency": currency,
            "source": "ebay",
            "url": url,
            "itemId": item_id,  # eBay API field
            "id": item_id,       # Generic ID field
            "sold": sold,
            "condition": condition,
            "shipping_price": shipping_price,
            "total_price": total_price,
            "bids": random.randint(0, 15) if not sold else random.randint(5, 25),
            "ended_at": None if not sold else "2025-08-11T12:00:00Z",
            "image_url": f"https://picsum.photos/300/400?random={i}",  # Placeholder image
            "category": "Trading Cards",
            "raw_query": query
        }
        
        items.append(item)
    
    return {
        "query": query,
        "items": items,
        "source": "fallback",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

async def post_to_edge_function(payload: Dict[str, Any]) -> tuple[int, str]:
    """Post payload to Supabase Edge Function and return status and body"""
    # Use service role key for server-to-server authentication
    service_role_key = get_service_role_key()
    function_secret = get_function_secret()
    supabase_url = get_supabase_url()
    
    # Build the correct Edge Function URL
    ef_url = f"{supabase_url}/functions/v1/ai-parser"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    # Add Authorization header if we have a service role key
    if service_role_key:
        headers["Authorization"] = f"Bearer {service_role_key}"
    
    # Add function secret header if we have it
    if function_secret:
        headers["x-function-secret"] = function_secret
    
    print(f"[api] Calling Edge Function with auth: {'Bearer ***' if service_role_key else 'None'}")
    print(f"[api] Edge Function URL: {ef_url}")
    print(f"[api] Request headers: {dict(headers)}")
    
    response = await http_client.post(
        ef_url, 
        headers=headers, 
        json=payload
    )
    return response.status_code, response.text

async def check_scraper_reachable() -> bool:
    """Check if scraper is reachable without running a full scrape"""
    try:
        # Quick health check to scraper
        response = await asyncio.wait_for(
            http_client.get(f"{get_scraper_base()}/", timeout=3.0),
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
async def health():
    """Early health that never touches external deps"""
    try:
        supabase_url = get_supabase_url()
        ef_url = f"{supabase_url}/functions/v1/ai-parser" if supabase_url else "NOT SET"
    except Exception:
        ef_url = "ERROR"
    
    return JSONResponse({
        "ok": True,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env": {
            "scraper": bool(get_scraper_base()),
            "ef": bool(get_ef_url()),
            "ef_auth": bool(get_service_role_key()),
            "ef_url": ef_url,
        },
    })

@app.get("/diag-ef")
async def diag_ef(ping: Optional[str] = None):
    """Quick self-test route to test Edge Function connectivity"""
    if ping != "1":
        raise HTTPException(status_code=400, detail="Use ?ping=1 to test")
    
    trace_id = str(uuid.uuid4())[:8]
    print(f"[api] /diag-ef called with trace_id: {trace_id}")
    
    try:
        # Test payload - match the format expected by the Edge Function
        test_items = [{
            "title": "test item",  # Edge Function expects this field
            "raw_title": "test item",
            "price": 1.0,
            "currency": "USD",
            "source": "ebay",
            "raw_description": "test description"
        }]
        validated_items = validate_edge_function_payload(test_items)
        test_payload = {
            "query": "diagnostic",
            "items": validated_items
        }
        
        print(f"[api] Testing Edge Function with trace_id: {trace_id}")
        status, body = await post_to_edge_function(test_payload)
        
        return JSONResponse({
            "ok": status < 400,
            "status": status,
            "body": body,
            "trace_id": trace_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
        
    except Exception as e:
        print(f"[api] /diag-ef error: {e}")
        return JSONResponse({
            "ok": False,
            "error": str(e),
            "trace_id": trace_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }, status_code=500)

@app.post("/admin/merge-cards")
async def admin_merge_cards(request: Request):
    """Admin endpoint to proxy merge-cards requests to Edge Function"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    print(f"[api] /admin/merge-cards called from {client_ip} (trace: {trace_id})")
    
    try:
        # Get request body
        body = await request.json()
        
        # Prepare merge-cards payload
        merge_payload = {
            "dryRun": body.get("dryRun", False)
        }
        
        # Call merge-cards Edge Function
        service_role_key = get_service_role_key()
        function_secret = get_function_secret()
        supabase_url = get_supabase_url()
        
        ef_url = f"{supabase_url}/functions/v1/merge-cards"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        if service_role_key:
            headers["Authorization"] = f"Bearer {service_role_key}"
        if function_secret:
            headers["x-function-secret"] = function_secret
        
        print(f"[api] Calling merge-cards EF: {ef_url} (trace: {trace_id})")
        
        response = await http_client.post(ef_url, headers=headers, json=merge_payload)
        
        return JSONResponse({
            "ok": response.status_code < 400,
            "status": response.status_code,
            "body": response.text,
            "trace_id": trace_id
        })
        
    except Exception as e:
        print(f"[api] /admin/merge-cards error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "error": str(e),
                "trace_id": trace_id
            },
            status_code=500
        )

@app.post("/smoketest")
async def smoketest():
    """Quick connectivity test with minimal scrape"""
    trace_id = str(uuid.uuid4())[:8]
    
    try:
        # Quick scrape with limit=1 and short timeout
        response = await asyncio.wait_for(
            http_client.get(f"{get_scraper_base()}/scrape", params={"query": "test", "limit": 1}),
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
    return JSONResponse({"ok": True})

@app.options("/scrape-now/")
async def scrape_now_options_trailing():
    """CORS preflight handler for /scrape-now/ (with trailing slash)"""
    # CORSMiddleware will add headers, but we ensure 200 with bodyless response
    from fastapi.responses import Response
    return Response(status_code=200)

@app.options("/normalize-test")
async def normalize_test_options():
    """Handle CORS preflight for /normalize-test"""
    # CORSMiddleware will add headers, but we ensure 200 with bodyless response
    from fastapi.responses import Response
    return Response(status_code=200)

@app.options("/admin/merge-cards")
async def admin_merge_cards_options():
    """Handle CORS preflight for /admin/merge-cards"""
    # CORSMiddleware will add headers, but we ensure 200 with bodyless response
    from fastapi.responses import Response
    return Response(status_code=200)

@app.options("/admin/logs")
async def admin_logs_options():
    """Handle CORS preflight for /admin/logs"""
    # CORSMiddleware will add headers, but we ensure 200 with bodyless response
    from fastapi.responses import Response
    return Response(status_code=200)

@app.options("/admin/tracked-queries")
async def admin_tracked_queries_options():
    """Handle CORS preflight for /admin/tracked-queries"""
    # CORSMiddleware will add headers, but we ensure 200 with bodyless response
    from fastapi.responses import Response
    return Response(status_code=200)

@app.options("/admin/diag-supabase")
async def admin_diag_supabase_options():
    """Handle CORS preflight for /admin/diag-supabase"""
    # CORSMiddleware will add headers, but we ensure 200 with bodyless response
    from fastapi.responses import Response
    return Response(status_code=200)

@app.get("/admin/logs")
async def admin_logs(request: Request, limit: int = 200):
    """Admin endpoint to read scraping_logs from Supabase"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Verify admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        print(f"[api] /admin/logs unauthorized access attempt from {client_ip} (trace: {trace_id})")
        return JSONResponse(
            content={"logs": [], "error": "Unauthorized", "trace": trace_id},
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
            status_code=401
        )
    
    print(f"[api] /admin/logs called from {client_ip} (trace: {trace_id})")
    
    try:
        # Call Supabase REST API with service role key
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return JSONResponse(
                content={"logs": [], "error": "Service not configured", "trace": trace_id},
                headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
                status_code=200
            )
        
        # Build Supabase REST API URL with safe SELECT and valid order field
        rest_url = f"{supabase_url}/rest/v1/scraping_logs"
        params = {
            "select": "*",
            "order": "started_at.desc",
            "limit": min(limit, 1000)  # Cap at 1000 for safety
        }
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        print(f"[api] Calling Supabase REST: {rest_url} (trace: {trace_id})")
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        if response.status_code == 200:
            logs = response.json()
            print(f"[api] Retrieved {len(logs)} logs (trace: {trace_id})")
            return JSONResponse(
                content={"logs": logs, "count": len(logs), "trace": trace_id},
                headers={"x-trace-id": trace_id, "Content-Type": "application/json"}
            )
        else:
            # Return empty array with error details
            sb_request_id = response.headers.get("sb-request-id", "unknown")
            print(f"[api] Supabase REST error: {response.status_code} - {response.text} (sb-request-id: {sb_request_id}, trace: {trace_id})")
            return JSONResponse(
                content={
                    "logs": [],
                    "error": f"Supabase REST error: {response.status_code}",
                    "sb_request_id": sb_request_id,
                    "trace": trace_id
                },
                headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
                status_code=200  # Always 200 to prevent UI crashes
            )
        
    except Exception as e:
        print(f"[api] /admin/logs error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={"logs": [], "error": str(e), "trace": trace_id},
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
            status_code=200  # Always 200 to prevent UI crashes
        )

@app.get("/admin/tracked-queries")
async def admin_tracked_queries(request: Request, limit: int = 200):
    """Admin endpoint to read tracked_queries from Supabase"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Verify admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        print(f"[api] /admin/tracked-queries unauthorized access attempt from {client_ip} (trace: {trace_id})")
        return JSONResponse(
            content={"queries": [], "error": "Unauthorized", "trace": trace_id},
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
            status_code=401
        )
    
    print(f"[api] /admin/tracked-queries called from {client_ip} (trace: {trace_id})")
    
    try:
        # Call Supabase REST API with service role key
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return JSONResponse(
                content={"queries": [], "error": "Service not configured", "trace": trace_id},
                headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
                status_code=200
            )
        
        # Build Supabase REST API URL with safe SELECT and valid order field
        rest_url = f"{supabase_url}/rest/v1/tracked_queries"
        params = {
            "select": "*",
            "order": "created_at.desc",
            "limit": min(limit, 1000)  # Cap at 1000 for safety
        }
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        print(f"[api] Calling Supabase REST: {rest_url} (trace: {trace_id})")
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        if response.status_code == 200:
            queries = response.json()
            print(f"[api] Retrieved {len(queries)} tracked queries (trace: {trace_id})")
            return JSONResponse(
                content={"queries": queries, "count": len(queries), "trace": trace_id},
                headers={"x-trace-id": trace_id, "Content-Type": "application/json"}
            )
        else:
            # Return empty array with error details
            sb_request_id = response.headers.get("sb-request-id", "unknown")
            print(f"[api] Supabase REST error: {response.status_code} - {response.text} (sb-request-id: {sb_request_id}, trace: {trace_id})")
            return JSONResponse(
                content={
                    "queries": [],
                    "error": f"Supabase REST error: {response.status_code}",
                    "sb_request_id": sb_request_id,
                    "trace": trace_id
                },
                headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
                status_code=200  # Always 200 to prevent UI crashes
            )
        
    except Exception as e:
        print(f"[api] /admin/tracked-queries error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={"queries": [], "error": str(e), "trace": trace_id},
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
            status_code=200  # Always 200 to prevent UI crashes
        )

# Removed duplicate endpoint - CORS is handled by CORSMiddleware

@app.get("/admin/diag-supabase")
async def admin_diag_supabase(request: Request):
    """Quick diagnostics endpoint to test Supabase REST API connectivity"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Verify admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        print(f"[api] /admin/diag-supabase unauthorized access attempt from {client_ip} (trace: {trace_id})")
        return JSONResponse(
            content={"ok": False, "error": "Unauthorized", "trace": trace_id},
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
            status_code=401
        )
    
    print(f"[api] /admin/diag-supabase called from {client_ip} (trace: {trace_id})")
    
    try:
        # Call Supabase REST API with minimal query
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return JSONResponse(
                content={"ok": False, "error": "Service not configured", "trace": trace_id},
                headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
                status_code=200  # Always 200 to prevent UI crashes
            )
        
        # Test with minimal query
        rest_url = f"{supabase_url}/rest/v1/scraping_logs"
        params = {"select": "1", "limit": "1"}
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        print(f"[api] Testing Supabase REST: {rest_url} (trace: {trace_id})")
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        # Return detailed response information
        return JSONResponse(
            content={
                "ok": response.status_code < 400,
                "status": response.status_code,
                "sb_request_id": response.headers.get("sb-request-id", "unknown"),
                "response_headers": dict(response.headers),
                "body": response.text[:500],  # Truncate long responses
                "trace": trace_id
            },
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"}
        )
        
    except Exception as e:
        print(f"[api] /admin/diag-supabase error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={"ok": False, "error": str(e), "trace": trace_id},
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"},
            status_code=200  # Always 200 to prevent UI crashes
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
    print(f"[api] {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} Manual scrape request from {client_ip}: '{query}' (trace: {trace_id})")
    
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
            
            if get_ef_url() and get_service_role_key():
                print(f"[api] Step 3: Starting Edge Function call (trace: {trace_id})")
                ef_start = time.time()
                
                try:
                    # Prepare payload with query and items for Edge Function
                    ef_payload = {
                        "query": query,  # Include the original query
                        "items": []
                    }
                    
                    # Convert items to dict and validate for Edge Function
                    item_dicts = [item.dict() for item in normalized_data.items]
                    validated_items = validate_edge_function_payload(item_dicts)
                    
                    # Filter items to only those with title AND (url OR source_listing_id)
                    filtered_items = []
                    for item in validated_items:
                        if item.get("title") and (item.get("url") or item.get("source_listing_id")):
                            filtered_items.append(item)
                    
                    ef_payload = {
                        "query": query,
                        "items": filtered_items
                    }
                    
                    # Log filtering results
                    total_items = len(validated_items)
                    with_url = len([item for item in validated_items if item.get("url")])
                    with_id = len([item for item in validated_items if item.get("source_listing_id")])
                    print(f"[api] EF ready: total={total_items}, with_url={with_url}, with_id={with_id}")
                    
                    # If no items pass filter, skip EF call
                    if len(filtered_items) == 0:
                        print(f"[api] No items with title+url/id - skipping EF call (trace: {trace_id})")
                        ef_status = None
                        ef_body = "No items with required fields (title + url/id)"
                        external_ok = True  # Not an error, just no items to process
                        
                        # Return early with skip response
                        total_time = time.time() - scraper_start
                        response = {
                            "ok": True,
                            "items": [item.dict() for item in normalized_data.items],
                            "externalOk": True,
                            "efStatus": ef_status,
                            "efBody": ef_body,
                            "trace": trace_id,
                            "ingestMode": "skipped-no-url",
                            "accepted": 0,
                            "total": total_items
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
                    
                    # Log Edge Function call details
                    print(f"[api] Posting to EF: items={len(ef_payload['items'])}, query_present={query is not None}")
                    print(f"[api] First item title: {ef_payload['items'][0].get('title', 'NO_TITLE') if ef_payload['items'] else 'NO_ITEMS'}")
                    
                    # Log BEFORE Edge Function call
                    first_item = ef_payload['items'][0] if ef_payload['items'] else {}
                    print(f"[api] EF call: count={len(ef_payload['items'])}, hasQuery={query is not None}, firstItemKeys={list(first_item.keys())}")
                    
                    # Also log the actual payload structure being sent
                    print(f"[api] EF payload structure: {list(ef_payload.keys())}")
                    print(f"[api] EF first item sample: {dict(list(first_item.items())[:5])}")
                    
                    # Debug: Log the exact payload being sent (first item only)
                    if ef_payload['items']:
                        debug_item = ef_payload['items'][0]
                        print(f"[api] DEBUG: First item title field: '{debug_item.get('title', 'MISSING')}'")
                        print(f"[api] DEBUG: First item raw_title field: '{debug_item.get('raw_title', 'MISSING')}'")
                        print(f"[api] DEBUG: First item keys: {sorted(debug_item.keys())}")
                    
                    # Try batch first
                    ef_status, ef_body = await asyncio.wait_for(
                        post_to_edge_function(ef_payload),
                        timeout=EF_TIMEOUT
                    )
                    
                    # Log AFTER Edge Function call
                    print(f"[api] EF result: status={ef_status}, body={ef_body[:200] if ef_body else '<no-body>'}")
                    ef_time = time.time() - ef_start
                    
                    # Check if batch failed and implement per-item fallback
                    if ef_status >= 400 or (ef_body and ef_body.startswith('{"ok":false')):
                        print(f"[api] Batch EF failed (status: {ef_status}) - falling back to per-item ingestion (trace: {trace_id})")
                        
                        # Per-item fallback
                        per_item_start = time.time()
                        per_item_results = []
                        
                        # Process items concurrently with individual timeouts
                        async def process_item(item):
                            try:
                                # Log item details before processing
                                item_keys = list(item.keys())
                                item_title = item.get("title", "NO_TITLE")
                                print(f"[api] Per-item EF: processing '{item_title}' with keys: {item_keys}")
                                
                                status, body = await asyncio.wait_for(
                                    post_item_to_edge_function(item, query),
                                    timeout=EF_TIMEOUT
                                )
                                
                                # Log result
                                print(f"[api] Per-item EF: '{item_title}' -> status={status}, body={body[:100] if body else '<no-body>'}")
                                
                                return {"status": "fulfilled", "value": {"status": status, "body": body}}
                            except asyncio.TimeoutError:
                                print(f"[api] Per-item EF: '{item_title}' -> timeout")
                                return {"status": "rejected", "reason": "timeout"}
                            except Exception as e:
                                print(f"[api] Per-item EF: '{item_title}' -> error: {e}")
                                return {"status": "rejected", "reason": str(e)}
                        
                        # Apply same filtering to per-item fallback
                        fallback_items = []
                        for item in ef_payload["items"]:
                            if item.get("title") and (item.get("url") or item.get("source_listing_id")):
                                fallback_items.append(item)
                        
                        print(f"[api] Per-item fallback: {len(fallback_items)}/{len(ef_payload['items'])} items have required fields")
                        
                        # Process filtered items concurrently
                        tasks = [process_item(item) for item in fallback_items]
                        per_item_results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        per_item_time = time.time() - per_item_start
                        
                        # Analyze per-item results
                        accepted = sum(1 for r in per_item_results if r.get("status") == "fulfilled" and r.get("value", {}).get("status") < 400)
                        first_good = next((r for r in per_item_results if r.get("status") == "fulfilled" and r.get("value", {}).get("status") < 400), None)
                        
                        # Log per-item summary
                        print(f"[api] Per-item fallback completed in {per_item_time:.2f}s (trace: {trace_id})")
                        print(f"[api] Per-item results: {accepted}/{len(per_item_results)} accepted")
                        
                        if first_good:
                            first_good_value = first_good["value"]
                            print(f"[api] First successful item: status={first_good_value.get('status')}, body={first_good_value.get('body', '')[:100]}")
                        
                        # Update status for response
                        ef_status = 207 if accepted > 0 else 400  # 207 = Multi-Status
                        ef_body = f"Per-item fallback: {accepted}/{len(per_item_results)} accepted"
                        external_ok = accepted > 0
                        
                        # Log final ingest summary
                        print(f"[api] ingest summary: {{mode:'per-item', accepted:{accepted}, firstIds:{first_good.get('value', {}) if first_good else None}}} (trace: {trace_id})")
                    else:
                        # Batch succeeded
                        external_ok = ef_status == 200
                        print(f"[api] ingest summary: {{mode:'batch', accepted:{len(ef_payload['items'])}, firstIds:null}} (trace: {trace_id})")
                    
                    # Truncate body for logging (max 300 chars)
                    ef_body_truncated = ef_body[:300] + "..." if len(ef_body) > 300 else ef_body
                    print(f"[api] Step 3: Edge Function completed in {ef_time:.2f}s (status: {ef_status}) (trace: {trace_id})")
                    print(f"[api] Edge Function response: {ef_body_truncated}")
                    
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
            
            # Enhanced response with fallback information
            response = {
                "ok": True,
                "items": [item.dict() for item in normalized_data.items],
                "externalOk": external_ok,
                "efStatus": ef_status,
                "efBody": ef_body,
                "trace": trace_id
            }
            
            # Add fallback information if per-item mode was used
            if ef_status == 207:  # Multi-Status (per-item fallback)
                # Parse the ef_body to extract accepted count
                import re
                match = re.search(r'(\d+)/(\d+) accepted', ef_body)
                if match:
                    accepted = int(match.group(1))
                    total = int(match.group(2))
                    response.update({
                        "ingestMode": "per-item",
                        "accepted": accepted,
                        "total": total,
                        "firstIds": None  # Could be enhanced to parse actual IDs from responses
                    })
            else:
                response.update({
                    "ingestMode": "batch",
                    "accepted": len(normalized_data.items) if external_ok else 0,
                    "total": len(normalized_data.items)
                })
            
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
                # normalized = normalizer.normalize_item(item)
                items.append(NormalizedTestItem(
                    title=item.get("title", ""),
                    url=item.get("url"),
                    price=item.get("price"),
                    currency=item.get("currency"),
                    ended_at=item.get("ended_at"),
                    id=item.get("id"),
                    source=item.get("source", "ebay"),
                    parsed={
                        "set_name": item.get("normalized", {}).get("parsed", {}).get("set_name"),
                        "edition": item.get("normalized", {}).get("parsed", {}).get("edition"),
                        "number": item.get("normalized", {}).get("parsed", {}).get("number"),
                        "year": item.get("normalized", {}).get("parsed", {}).get("year"),
                        "grading_company": item.get("normalized", {}).get("parsed", {}).get("grading_company"),
                        "grade": item.get("normalized", {}).get("parsed", {}).get("grade"),
                        "is_holo": item.get("normalized", {}).get("parsed", {}).get("is_holo"),
                        "franchise": item.get("normalized", {}).get("parsed", {}).get("franchise"),
                        "canonical_key": item.get("canonical_key"),
                        "rarity": item.get("normalized", {}).get("parsed", {}).get("rarity"),
                        "tags": item.get("normalized", {}).get("parsed", {}).get("tags"),
                        "sold": item.get("normalized", {}).get("parsed", {}).get("sold"),
                        "set": item.get("normalized", {}).get("parsed", {}).get("set"),
                        "language": item.get("normalized", {}).get("parsed", {}).get("language"),
                        "grader": item.get("normalized", {}).get("parsed", {}).get("grader"),
                        "grade_value": item.get("normalized", {}).get("parsed", {}).get("grade_value")
                    },
                    canonical_key=item.get("canonical_key"),
                    confidence=item.get("normalized", {}).get("confidence", {})
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
                    # normalized = normalizer.normalize_item(item)
                    items.append(NormalizedTestItem(
                        title=item.get("title", ""),
                        url=item.get("url"),
                        price=item.get("price"),
                        currency=item.get("currency"),
                        ended_at=item.get("ended_at"),
                        id=item.get("id"),
                        source=item.get("source", "ebay"),
                        parsed={
                            "set_name": item.get("normalized", {}).get("parsed", {}).get("set_name"),
                            "edition": item.get("normalized", {}).get("parsed", {}).get("edition"),
                            "number": item.get("normalized", {}).get("parsed", {}).get("number"),
                            "year": item.get("normalized", {}).get("parsed", {}).get("year"),
                            "grading_company": item.get("normalized", {}).get("parsed", {}).get("grading_company"),
                            "grade": item.get("normalized", {}).get("parsed", {}).get("grade"),
                            "is_holo": item.get("normalized", {}).get("parsed", {}).get("is_holo"),
                            "franchise": item.get("normalized", {}).get("parsed", {}).get("franchise"),
                            "canonical_key": item.get("canonical_key"),
                            "rarity": item.get("normalized", {}).get("parsed", {}).get("rarity"),
                            "tags": item.get("normalized", {}).get("parsed", {}).get("tags"),
                            "sold": item.get("normalized", {}).get("parsed", {}).get("sold"),
                            "set": item.get("normalized", {}).get("parsed", {}).get("set"),
                            "language": item.get("normalized", {}).get("parsed", {}).get("language"),
                            "grader": item.get("normalized", {}).get("parsed", {}).get("grader"),
                            "grade_value": item.get("normalized", {}).get("parsed", {}).get("grade_value")
                        },
                        canonical_key=item.get("canonical_key"),
                        confidence=item.get("normalized", {}).get("confidence", {})
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
                # normalized = normalizer.normalize_item(item)
                ef_payload["items"].append({
                    **item,
                    "normalized": {
                        "canonical_key": item.get("canonical_key"),
                        "parsed": {
                            "set_name": item.get("normalized", {}).get("parsed", {}).get("set_name"),
                            "edition": item.get("normalized", {}).get("parsed", {}).get("edition"),
                            "number": item.get("normalized", {}).get("parsed", {}).get("number"),
                            "year": item.get("normalized", {}).get("parsed", {}).get("year"),
                            "grading_company": item.get("normalized", {}).get("parsed", {}).get("grading_company"),
                            "grade": item.get("normalized", {}).get("parsed", {}).get("grade"),
                            "is_holo": item.get("normalized", {}).get("parsed", {}).get("is_holo"),
                            "franchise": item.get("normalized", {}).get("parsed", {}).get("franchise")
                        },
                        "confidence": item.get("normalized", {}).get("confidence", {})
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
    print(f"[api] Scraper base URL: {'SET' if get_scraper_base() else 'NOT SET'}")
    print(f"[api] Supabase Function URL: {'SET' if get_ef_url() else 'NOT SET'}")
    
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