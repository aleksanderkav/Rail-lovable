import os
import json
import time
import httpx
import uuid
import asyncio
import traceback
from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass
from fastapi import FastAPI, HTTPException, Request, Response, Header, Depends, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import random
import re

# Import the existing scraper functions - only import functions, not environment variables
# from scheduled_scraper import now_iso

# Helper functions for robust error handling
def _trace() -> str:
    """Generate a trace ID for logging and debugging"""
    return uuid.uuid4().hex[:8]

def json_with_trace(payload: dict, status: int = 200, trace: Optional[str] = None):
    """Create JSON response with x-trace-id header"""
    trace = trace or _trace()
    resp = JSONResponse(payload, status_code=status)
    resp.headers["x-trace-id"] = trace
    return resp, trace

# Enhanced eBay URL and ID extraction utilities
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

EBAY_ID_REGEXES = [
    re.compile(r"/itm/(\d{6,})(?:[/?#]|$)"),  # /itm/123456789 or /itm/123456789?param=value
    re.compile(r"[?&]itm=(\d{6,})(?:&|#|$)"),  # ?itm=123456789&other=value or ?itm=123456789#fragment
    re.compile(r"/p/(\d{6,})(?:[/?#]|$)"),  # /p/123456789 or /p/123456789?param=value
    re.compile(r"/\d{6,}(?:\?|$)"),  # Fallback for other numeric patterns
]

def extract_ebay_id(url: str) -> str | None:
    """Extract eBay item ID from various URL formats"""
    if not url:
        return None
    try:
        for rx in EBAY_ID_REGEXES:
            m = rx.search(url)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None

def canonicalize_ebay_url(url: str) -> str:
    """
    Normalize eBay listing URLs:
      - keep scheme + netloc + path
      - drop tracking params
      - keep `itm` param if present
    """
    if not url:
        return url
    try:
        u = urlparse(url)
        # Keep only essential query params (itm if present)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        keep = {}
        if "itm" in q:
            keep["itm"] = q["itm"]
        # Rebuild
        return urlunparse((u.scheme, u.netloc, u.path, "", urlencode(keep), ""))
    except Exception:
        return url

# Enhanced price parsing utility
def parse_price(s: str) -> tuple[Optional[float], Optional[str]]:
    """Parse price and detect currency from string with improved parsing"""
    if not s:
        return None, None
    
    # Enhanced currency detection
    PRICE_CURRENCY_MAP = {
        "$": "USD", "US$": "USD", "USD": "USD",
        "£": "GBP", "GBP": "GBP",
        "€": "EUR", "EUR": "EUR",
        "kr": "NOK", "NOK": "NOK",
        "¥": "JPY", "JPY": "JPY",
        "₹": "INR",
        "₽": "RUB"
    }
    
    s = s.strip()
    
    # Try symbol first
    currency = None
    for sym, iso in PRICE_CURRENCY_MAP.items():
        if s.startswith(sym) or s.upper().startswith(sym):
            currency = iso
            break
    
    # Normalize decimal/thousands (very simple heuristic)
    # Remove spaces
    ns = re.sub(r"\s+", "", s)
    # Remove currency tokens and non-numeric except separators
    ns = re.sub(r"[^\d,.\-]", "", ns)
    # If both comma and dot present, assume comma = thousands, dot = decimal
    if "," in ns and "." in ns:
        ns = ns.replace(",", "")
    else:
        # If only comma and looks like decimal, convert to dot
        if "," in ns and re.search(r",\d{1,2}$", ns):
            ns = ns.replace(",", ".")
        else:
            ns = ns.replace(",", "")
    
    try:
        value = float(ns)
        return value, currency
    except Exception:
        return None, currency

# Safe normalizer import with fallback
# try:
#     from normalizer import normalizer, NormalizedItem, ParsedHints
# except Exception as e:

# --- CORS Configuration ---
def get_allowed_origins():
    raw_origins = os.getenv("ALLOW_ORIGINS", "").strip()
    if raw_origins:
        # Parse comma-separated origins from environment
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        print(f"✅ Loaded ALLOW_ORIGINS: {origins}")
        return origins
    else:
        # Default origins if env not set - support wildcard subdomains for Lovable
        default_origins = [
            "https://*.lovable.app",
            "https://*.lovableproject.com",
            "https://card-pulse-watch.lovable.app",
            "http://localhost:3000",
            "http://localhost:5173",
        ]
        print(f"✅ Loaded ALLOW_ORIGINS (defaults with wildcards): {default_origins}")
        return default_origins

ALLOWED_ORIGINS = get_allowed_origins()
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
SCRAPER_TIMEOUT = 25.0
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

# Global CORS middleware - ensure Lovable origins are explicitly allowed
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://card-pulse-watch.lovable.app",
        "https://*.lovable.app",
        "https://*.lovableproject.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*", "X-Admin-Token", "Content-Type"],
    expose_headers=["X-Trace-Id"],
    allow_credentials=True,
)

# Create router for main endpoints
router = APIRouter()

# --- Safe, lazy clients (don't create at import time) ---
def get_scraper_base():
    """Get external scraper base URL - returns empty string if not configured to prevent HTTP 502 errors"""
    scraper_url = os.getenv("SCRAPER_BASE_URL", "").strip()
    if not scraper_url:
        print("[api] SCRAPER_BASE_URL not configured - external scraper disabled")
    return scraper_url

def get_ef_url():
    return os.getenv("SUPABASE_FUNCTION_URL", "").strip()

# Mock fallback functionality removed - not needed in production

# --- BEGIN CORS GUARD ---

def _is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return False
    
    # Check exact matches first
    if origin in ALLOWED_ORIGINS:
        return True
    
    # Check wildcard patterns for Lovable domains
    if origin.endswith(".lovable.app") or origin.endswith(".lovableproject.com"):
        return True
    
    # Check if origin matches any wildcard patterns in ALLOWED_ORIGINS
    for pattern in ALLOWED_ORIGINS:
        if pattern.startswith("https://*."):
            domain = pattern[8:]  # Remove "https://*."
            if origin.endswith(domain):
                return True
    
    return False

def cors_guard(origin: str = Header(None), response: Response = None, request: Request = None):
    try:
        # Always set trace ID for CORS tracking
        trace_id = str(uuid.uuid4())[:8]
        response.headers["X-Trace-Id"] = trace_id
        
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
        
        if origin and _is_allowed_origin(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
        else:
            print(f"[api] CORS guard denied origin={origin} path={request.url.path if request else 'unknown'} trace={trace_id}")
    except Exception as e:
        print(f"[api] CORS guard error: {e}")
# --- END CORS GUARD ---

# --- BEGIN CONSISTENT BEHAVIOR UTILITIES ---

# Universal CORS helpers for consistent CORS handling across all responses
def _origin_allowed(origin: str) -> bool:
    """Check if origin is allowed (exact match or wildcard)"""
    if not origin:
        return False
    
    # Exact matches
    allow = [
        "https://card-pulse-watch.lovable.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    
    # Wildcard patterns
    wildcards = [
        ".lovable.app",
        ".lovableproject.com",
    ]
    
    if origin in allow:
        return True
    
    return any(origin.endswith(w) for w in wildcards)

def corsify(response: Response, request: Request) -> Response:
    """Add CORS headers to any response if origin is allowed"""
    origin = request.headers.get("origin", "")
    if _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    return response

def create_success_response(payload: dict, trace: str, request: Request, status_code: int = 200) -> Response:
    """Create success response with CORS headers"""
    resp = JSONResponse({"ok": True, "trace": trace, **payload}, status_code=status_code)
    resp.headers["X-Trace-Id"] = trace
    return corsify(resp, request)

def create_error_response(detail: str, status_code: int, trace: str, request: Request, extra: dict | None = None) -> Response:
    """Create error response with CORS headers"""
    body = {"ok": False, "detail": detail, "trace": trace}
    if extra:
        body.update(extra)
    resp = JSONResponse(body, status_code=status_code)
    resp.headers["X-Trace-Id"] = trace
    return corsify(resp, request)

def generate_trace_id() -> str:
    """Generate a consistent trace ID for all endpoints"""
    try:
        return str(uuid.uuid4())[:8]
    except Exception as e:
        print(f"[generate_trace_id] Error: {e}")
        return str(uuid.uuid4())[:8] if 'uuid' in globals() else "00000000"

# Legacy functions - kept for backward compatibility
def create_error_response_legacy(detail: str, status_code: int = 400, trace_id: str = None) -> JSONResponse:
    """Create consistent error responses with ok, detail, and trace"""
    trace_id = trace_id or generate_trace_id()
    return JSONResponse(
        content={
            "ok": False,
            "detail": detail,
            "trace": trace_id
        },
        status_code=status_code,
        headers={"X-Trace-Id": trace_id}
    )

def create_success_response_legacy(data: dict, trace_id: str = None) -> JSONResponse:
    """Create consistent success responses with ok, data, and trace"""
    trace_id = trace_id or generate_trace_id()
    response_data = {"ok": True, "trace": trace_id}
    response_data.update(data)
    return JSONResponse(
        content=response_data,
        headers={"X-Trace-Id": trace_id}
    )

def validate_admin_token(request: Request) -> tuple[bool, str, str]:
    """
    Validate admin token and return (is_valid, trace_id, error_message)
    Use this in all admin endpoints for consistent validation
    """
    try:
        trace_id = generate_trace_id()
        admin_token = request.headers.get("X-Admin-Token")
        expected_token = get_admin_proxy_token()
        
        if not admin_token or admin_token != expected_token:
            return False, trace_id, "Unauthorized - missing or invalid admin token"
        
        return True, trace_id, ""
    except Exception as e:
        print(f"[validate_admin_token] Error: {e}")
        # Fallback to basic validation
        trace_id = str(uuid.uuid4())[:8]
        admin_token = request.headers.get("X-Admin-Token")
        expected_token = os.getenv("ADMIN_PROXY_TOKEN", "").strip()
        
        if not admin_token or admin_token != expected_token:
            return False, trace_id, "Unauthorized - missing or invalid admin token"
        
        return True, trace_id, ""

def normalize_item_fields(item: dict, item_index: int = 0, trace_id: str = None) -> tuple[dict, dict]:
    """
    Apply consistent normalization to item fields
    Returns (normalized_item, skip_reason) where skip_reason is None if item is valid
    
    This ensures all endpoints use the same normalization logic
    """
    trace_id = trace_id or generate_trace_id()
    
    # Define field mappings - centralized for consistency
    URL_SOURCES = ['url', 'permalink', 'href', 'link', 'debug_url', 'viewItemURL', 'itemWebUrl', 'item_url', 'productUrl', 'linkHref']
    ID_SOURCES = ['source_listing_id', 'listing_id', 'id', 'itemId', 'item_id', 'ebay_id', 'itemIdStr']
    
    # Find URL from multiple sources
    url = None
    url_source_used = None
    for source in URL_SOURCES:
        if item.get(source):
            url = item.get(source)
            url_source_used = source
            if item_index < 3:  # Log first 3 items
                print(f"[normalize] item#{item_index+1} using url={source}")
            break
    
    # Find ID from multiple sources
    source_listing_id = None
    id_source_used = None
    for source in ID_SOURCES:
        if item.get(source):
            source_listing_id = str(item.get(source))
            id_source_used = source
            if item_index < 3:  # Log first 3 items
                print(f"[normalize] item#{item_index+1} using id={source}")
            break
    
    # Derive source_listing_id from URL if still empty
    if not source_listing_id and url:
        ebay_id = extract_ebay_id(url)
        if ebay_id:
            source_listing_id = ebay_id
            if item_index < 3:
                print(f"[normalize] item#{item_index+1} derived id from URL: {source_listing_id}")
    
    # Synthesize URL from ID if missing but ID present
    if not url and source_listing_id:
        url = f"https://www.ebay.com/itm/{source_listing_id}"
        if item_index < 3:
            print(f"[normalize] item#{item_index+1} synthesized URL from ID: {url}")
    
    # Check for required fields AFTER applying all fallbacks
    if not url:
        return None, {"reason": "no_url", "item_index": item_index, "title": item.get('title', 'unknown')}
    
    if not source_listing_id:
        return None, {"reason": "no_id", "item_index": item_index, "title": item.get('title', 'unknown')}
    
    # Create normalized item with consistent field names
    normalized_item = {
        "title": item.get("title") or item.get("name") or "",
        "url": url,
        "source_listing_id": source_listing_id,
        "price": parse_price(str(item.get("price") or item.get("amount") or ""))[0],
        "currency": parse_price(str(item.get("price") or item.get("amount") or ""))[1] or "USD",
        "sold": bool(item.get("sold") or item.get("is_sold")),
        "ended_at": item.get("ended_at") or item.get("endTime"),
        # Preserve original sources for debugging
        "_normalization_debug": {
            "url_source": url_source_used,
            "id_source": id_source_used,
            "url_derived": url_source_used is None,
            "id_derived": id_source_used is None
        }
    }
    
    return normalized_item, None

def apply_normalization_safety_net(items: list, trace_id: str = None) -> tuple[list, dict]:
    """
    Apply normalization safety-net to a list of items
    Returns (normalized_items, skip_stats)
    
    This ensures consistent normalization across all endpoints
    """
    trace_id = trace_id or generate_trace_id()
    normalized_items = []
    skip_stats = {"no_url": 0, "no_id": 0, "total_processed": len(items)}
    
    for i, item in enumerate(items):
        normalized_item, skip_reason = normalize_item_fields(item, i, trace_id)
        
        if skip_reason:
            skip_stats[skip_reason["reason"]] += 1
            if i < 3:  # Log first 3 skips
                print(f"[normalize] SKIP {skip_reason['reason']} item#{i+1} '{skip_reason['title']}' (trace: {trace_id})")
            continue
        
        normalized_items.append(normalized_item)
    
    print(f"[normalize] Safety-net applied: accepted={len(normalized_items)} no_url={skip_stats['no_url']} no_id={skip_stats['no_id']} (trace: {trace_id})")
    return normalized_items, skip_stats

# --- END CONSISTENT BEHAVIOR UTILITIES ---

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
    dryRun: Optional[bool] = False
    instant: Optional[bool] = False
    ingest: Optional[bool] = False

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

# New models for Lovable integration
class IngestRequest(BaseModel):
    """Request for /ingest endpoint"""
    query: str
    marketplace: str = "ebay"
    items: List[Dict[str, Any]]

class IngestItem(BaseModel):
    """Individual item for ingestion"""
    title: str
    url: str
    source_listing_id: str
    price: Optional[float] = None
    currency: Optional[str] = "USD"
    sold: bool = False
    ended_at: Optional[str] = None

class IngestResponse(BaseModel):
    """Response for /ingest endpoint"""
    status: str
    card_id: Optional[str] = None
    inserted: int
    trace_id: str

class AdminCardsResponse(BaseModel):
    """Response for /admin/cards endpoint"""
    cards: List[Dict[str, Any]]
    count: int
    trace_id: str

class AdminListingsResponse(BaseModel):
    """Response for /admin/listings endpoint"""
    listings: List[Dict[str, Any]]
    count: int
    trace_id: str

class ErrorResponse(BaseModel):
    """Error response format"""
    error: str
    trace_id: str

def normalize_scraper_response(scraper_data: Dict[str, Any]) -> NormalizedResponse:
    """Normalize scraper response into expected format with enriched fields"""
    items = []
    
    # Helper function to extract URL and listing ID from various field names
    def extract_url_and_id(entry: Dict[str, Any]) -> tuple[str | None, str | None]:
        """Extract URL and source_listing_id from item data"""
        try:
            url = (entry.get("url") or "").strip() or None
            sid = (entry.get("source_listing_id") or "").strip() or None
            
            # fallback patterns if missing:
            if (not sid) and url:
                # try /itm/ or /p/ patterns
                import re
                m = re.search(r"/itm/(\d{6,})", url) or re.search(r"/p/(\d{6,})", url)
                if m:
                    sid = m.group(1)
            
            return (url, sid)
        except Exception:
            return (None, None)
    
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
                    franchise=None,
                    set_name=None,
                    edition=None,
                    number=None,
                    year=None,
                    language=None,
                    grading_company=None,
                    grade=None,
                    rarity=None,
                    is_holo=None,
                    
                    # Tags (pre-filled if certain)
                    tags=None,
                    
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
                    parsed=None
                ))
    elif "price_entries" in scraper_data and isinstance(scraper_data["price_entries"], list):
        # Convert price entries to items
        for entry in scraper_data["price_entries"]:
            if isinstance(entry, dict):
                title = scraper_data.get("query", "")
                
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
                    franchise=None,
                    set_name=None,
                    edition=None,
                    number=None,
                    year=None,
                    language=None,
                    grading_company=None,
                    grade=None,
                    rarity=None,
                    is_holo=None,
                    
                    # Tags (pre-filled if certain)
                    tags=None,
                    
                    # Metadata for enrichment
                    raw_query=scraper_data.get("query"),
                    category_guess=None,
                    
                    # Legacy fields for backward compatibility
                    title=title,
                    id=source_listing_id,
                    sold=False,
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
                    parsed=None
                ))
    elif "prices" in scraper_data and isinstance(scraper_data["prices"], list):
        # Convert prices array to items
        for price in scraper_data["prices"]:
            if isinstance(price, (int, float)):
                title = scraper_data.get("query", "")
                # For simple price arrays, URL/ID might not be directly available, keep as None
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
                    franchise=None,
                    set_name=None,
                    edition=None,
                    number=None,
                    year=None,
                    language=None,
                    grading_company=None,
                    grade=None,
                    rarity=None,
                    is_holo=None,
                    
                    # Tags (pre-filled if certain)
                    tags=None,
                    
                    # Metadata for enrichment
                    raw_query=scraper_data.get("query"),
                    category_guess=None,
                    
                    # Legacy fields for backward compatibility
                    title=title,
                    id=None,
                    sold=False,
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
                    parsed=None
                ))
    
    # If no items found, create a default item with query info
    if not items:
        title = scraper_data.get("query", "")
        items.append(Item(
            # Raw listing details (for AI extraction)
            raw_title=title,
            raw_description=None,
            source="ebay",
            source_listing_id=None,  # No ID available for default items
            url=None,  # No URL available for default items
            
            # Pricing and availability
            currency="USD",
            price=None,
            ended_at=None,
            
            # Media
            images=None,
            
            # Initial parsed fields (if easily extractable during scraping)
            franchise=None,
            set_name=None,
            edition=None,
            number=None,
            year=None,
            language=None,
            grading_company=None,
            grade=None,
            rarity=None,
            is_holo=None,
            
            # Tags (pre-filled if certain)
            tags=None,
            
            # Metadata for enrichment
            raw_query=title,
            category_guess=None,
            
            # Legacy fields for backward compatibility
            title=title,
            id=None,
            sold=False,
            image_url=None,
            shipping_price=None,
            total_price=None,
            bids=None,
            condition=None,
            canonical_key=None,
            set=None,
            grader=None,
            grade_value=None,
            
            # Parsed hints subobject
            parsed=None
        ))
    
    return NormalizedResponse(items=items)

async def call_scraper(query: str) -> Dict[str, Any]:
    """Call external scraper or generate fallback data"""
    scraper_base = get_scraper_base()
    
    if not scraper_base:
        print(f"[api] No scraper configured - using eBay HTML scraper for query: '{query}'")
        try:
            # Use new eBay scraper for both active and sold listings
            active_items = await scrape_ebay(query, "active")
            sold_items = await scrape_ebay(query, "sold")
            
            # Merge and de-duplicate by source_listing_id
            all_items = []
            seen_ids = set()
            
            # Add active items first
            for item in active_items:
                if item.get("source_listing_id") and item["source_listing_id"] not in seen_ids:
                    all_items.append(item)
                    seen_ids.add(item["source_listing_id"])
            
            # Add sold items (they might override active ones with same ID)
            for item in sold_items:
                if item.get("source_listing_id"):
                    # Remove existing item with same ID if present
                    all_items = [existing for existing in all_items if existing.get("source_listing_id") != item["source_listing_id"]]
                    all_items.append(item)
                    seen_ids.add(item["source_listing_id"])
            
            print(f"[api] eBay scraper returned {len(active_items)} active + {len(sold_items)} sold = {len(all_items)} unique items")
            
            return {
                "query": query,
                "items": all_items,
                "source": "ebay_scraper"
            }
            
        except Exception as e:
            print(f"[api] eBay scraper failed: {e} - raising error")
            raise Exception(f"eBay scraper failed: {e}")
    
    # Original external scraper logic
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            scraper_start = time.time()
            response = await asyncio.wait_for(
                http_client.get(
                    f"{scraper_base}/scrape",
                    params={"query": query},
                    timeout=SCRAPER_TIMEOUT
                ),
                timeout=SCRAPER_TIMEOUT
            )
            scraper_time = time.time() - scraper_start
            print(f"[api] Step 1: Scraper completed in {scraper_time:.2f}s")
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Scraper returned {response.status_code}")
                
        except asyncio.TimeoutError:
            if attempt == max_retries:
                print(f"[api] Scraper timeout after {max_retries + 1} attempts - using eBay scraper")
                try:
                    return await call_scraper(query)  # Recursive call to eBay scraper
                except Exception:
                    print(f"[api] eBay scraper failed - raising error")
                    raise Exception("eBay scraper failed")
            else:
                print(f"[api] Scraper timeout, attempt {attempt + 1}/{max_retries + 1}")
                
        except Exception as e:
            if attempt == max_retries:
                print(f"[api] Scraper failed after {max_retries + 1} attempts - using eBay scraper")
                try:
                    return await call_scraper(query)  # Recursive call to eBay scraper
                except Exception:
                    print(f"[api] eBay scraper failed - raising error")
                    raise Exception("eBay scraper failed")
            else:
                print(f"[api] Scraper error, attempt {attempt + 1}/{max_retries + 1}: {e}")
    
    # Final fallback
    print(f"[api] All scraper attempts failed - raising error")
    raise Exception("All scraper attempts failed")

# Mock fallback function removed - not needed in production
# Use ALLOW_MOCK_INSTANT=true environment variable if mock data is required for development

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
    scraper_base = get_scraper_base()
    if not scraper_base:
        print("[api] Scraper not configured - skipping reachability check")
        return True  # Return True to indicate no external dependency
    
    try:
        # Quick health check to scraper
        response = await asyncio.wait_for(
            http_client.get(f"{scraper_base}/", timeout=3.0),
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
        ef_configured = bool(get_ef_url() and get_service_role_key())
    except Exception:
        ef_url = "ERROR"
        ef_configured = False
    
    # Get git version if available
    git_version = "unknown"
    try:
        import subprocess
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            git_version = result.stdout.strip()
    except Exception:
        pass
    
    return JSONResponse({
        "ok": True,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": git_version,
        "ef": ef_configured,
        "env": {
            "scraper": bool(get_scraper_base()),
            "supabase": bool(supabase_url),
            "ef_url": ef_url
        }
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
            "title": "diag",
            "source": "ebay",
            "url": "https://www.ebay.com/itm/123456789012",
            "source_listing_id": "123456789012",
            "price": 1.0,
            "currency": "USD",
            "sold": False
        }]
        validated_items = validate_edge_function_payload(test_items)
        test_payload = {
            "query": "diag",
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

@router.post("/admin/merge-cards")
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

@router.post("/smoketest")
async def smoketest():
    """Quick connectivity test with minimal scrape"""
    trace_id = str(uuid.uuid4())[:8]
    
    try:
        scraper_base = get_scraper_base()
        if not scraper_base:
            return JSONResponse(
                content={
                    "ok": True,
                    "message": "External scraper not configured - skipping test",
                    "trace": trace_id
                },
                headers={"X-Trace-Id": trace_id}
            )
        
        # Quick scrape with limit=1 and short timeout
        response = await asyncio.wait_for(
            http_client.get(f"{scraper_base}/scrape", params={"query": "test", "limit": 1}),
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
                    "detail": f"Scraper returned status {response.status_code}",
                    "trace": trace_id
                },
                status_code=502,
                headers={"X-Trace-Id": trace_id}
            )
            
    except asyncio.TimeoutError:
        return JSONResponse(
            content={
                "ok": False,
                "detail": "Scraper timeout (6s)",
                "trace": trace_id
            },
            status_code=502,
            headers={"X-Trace-Id": trace_id}
        )
    except Exception as e:
        return JSONResponse(
            content={
                "ok": False,
                "detail": f"Scraper error: {str(e)}",
                "trace": trace_id
            },
            status_code=500,
            headers={"X-Trace-Id": trace_id}
        )

@router.options("/scrape-now")
def scrape_now_options(request: Request, response: Response):
    """OPTIONS handler for scrape-now endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.get("/scrape-now")
async def scrape_now_get():
    """GET method not allowed for scrape endpoint"""
    return JSONResponse(
        content={
            "ok": False,
            "detail": "Method not allowed. Use POST for scraping.",
            "trace": _trace()
        },
        status_code=405,
        headers={"X-Trace-Id": _trace()}
    )

@router.options("/scrape-now/")
def scrape_now_trailing_options(request: Request, response: Response):
    """OPTIONS handler for scrape-now trailing slash endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/scrape-now-fast")
def scrape_now_fast_options(request: Request, response: Response):
    """OPTIONS handler for scrape-now-fast endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.get("/scrape-now-fast")
async def scrape_now_fast_get():
    """GET method not allowed for fast scrape endpoint"""
    return JSONResponse(
        content={
            "ok": False,
            "detail": "Method not allowed. Use POST for fast scraping.",
            "trace": _trace()
        },
        status_code=405,
        headers={"X-Trace-Id": _trace()}
    )

@router.options("/admin/diag-ef")
def diag_ef_options(request: Request, response: Response):
    """OPTIONS handler for admin diag-ef endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/diag-db")
def diag_db_options(request: Request, response: Response):
    """OPTIONS handler for admin diag-db endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/logs")
def logs_options(request: Request, response: Response):
    """OPTIONS handler for admin logs endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/tracked-queries")
def tq_options(request: Request, response: Response):
    """OPTIONS handler for admin tracked-queries endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/health")
def health_options(request: Request, response: Response):
    """OPTIONS handler for admin health endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/merge-cards")
def merge_cards_options(request: Request, response: Response):
    """OPTIONS handler for admin merge-cards endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.get("/admin/logs")
async def admin_logs(request: Request, limit: int = 200):
    """Admin endpoint to proxy logs requests to Supabase REST API"""
    # Use consistent admin token validation
    is_valid, trace_id, error_message = validate_admin_token(request)
    if not is_valid:
        return create_error_response(error_message, 401, trace_id)
    
    client_ip = request.client.host if request.client else "unknown"
    
    # Validate limit parameter
    if limit > 1000:
        limit = 1000
    elif limit < 1:
        limit = 1
    
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
            return create_success_response({
                "logs": logs,
                "count": len(logs)
            }, trace_id)
        else:
            # Return empty array with error details
            sb_request_id = response.headers.get("sb-request-id", "unknown")
            print(f"[api] Supabase REST error: {response.status_code} - {response.text} (sb-request-id: {sb_request_id}, trace: {trace_id})")
            return create_success_response({
                "logs": [],
                "error": f"Supabase REST error: {response.status_code}",
                "sb_request_id": sb_request_id
            }, trace_id)
        
    except Exception as e:
        print(f"[api] /admin/logs error: {e} (trace: {trace_id})")
        return create_success_response({
            "logs": [],
            "error": str(e),
            "sb_request_id": "unknown"
        }, trace_id)

@router.get("/admin/tracked-queries")
async def admin_tracked_queries(request: Request, limit: int = 200):
    """Admin endpoint to proxy tracked-queries requests to Supabase REST API"""
    # Use consistent admin token validation
    is_valid, trace_id, error_message = validate_admin_token(request)
    if not is_valid:
        return create_error_response(error_message, 401, trace_id)
    
    client_ip = request.client.host if request.client else "unknown"
    
    # Validate limit parameter
    if limit > 1000:
        limit = 1000
    elif limit < 1:
        limit = 1
    
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
            return create_success_response({
                "queries": queries,
                "count": len(queries)
            }, trace_id)
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
                headers={
                    "x-trace-id": trace_id,
                    "Content-Type": "application/json"
                },
                status_code=200  # Always 200 to prevent UI crashes
            )
        
    except Exception as e:
        print(f"[api] /admin/tracked-queries error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "queries": [],
                "error": str(e),
                "sb_request_id": "unknown",
                "trace": trace_id
            },
            headers={
                "x-trace-id": trace_id,
                "Content-Type": "application/json"
            },
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
        
        # Test with minimal query - use a harmless select
        rest_url = f"{supabase_url}/rest/v1/tracked_queries"
        params = {"select": "id", "limit": "1"}
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json",
            "Prefer": "count=exact"
        }
        
        print(f"[api] Testing Supabase REST: {rest_url} (trace: {trace_id})")
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        # Parse response for count
        count = 0
        try:
            if response.status_code < 400:
                data = response.json()
                count = len(data) if isinstance(data, list) else 0
        except:
            pass
        
        # Return detailed response information
        return JSONResponse(
            content={
                "ok": response.status_code < 400,
                "status": response.status_code,
                "count": count,
                "sb_request_id": response.headers.get("sb-request-id", "unknown"),
                "trace": trace_id
            },
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"}
        )
        
    except Exception as e:
        print(f"[api] /admin/diag-supabase error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "error": str(e),
                "sb_request_id": "unknown",
                "trace": trace_id
            },
            headers={
                "x-trace-id": trace_id,
                "Content-Type": "application/json"
            },
            status_code=200  # Always 200 to prevent UI crashes
        )

@router.post("/scrape-now")
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
    
    # Handle dryRun mode for health checks
    if request.dryRun:
        print(f"[api] DRY RUN mode - skipping actual processing (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": True,
                "dryRun": True,
                "query": query,
                "message": "Health check completed successfully",
                "trace": trace_id
            },
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    
    # Robust instant mode detection (from query string and/or X-Instant header)
    qs_instant = http_request.query_params.get("instant", "").lower()
    header_instant = http_request.headers.get("X-Instant", "").lower()
    
    # Accept truthy values (case-insensitive): 1, true, t, yes, on
    instant_mode = (
        qs_instant in ["1", "true", "t", "yes", "on"] or
        header_instant in ["1", "true", "t", "yes", "on"]
    )
    
    print(f"[DEBUG] instant_mode={instant_mode} (qs='{qs_instant}', header='{header_instant}') trace={trace_id}")
    
    if instant_mode:
        print(f"[instant] start real_ebay_scraper q='{query}' trace={trace_id}")
        
        try:
            t0 = time.time()
            
            # STEP 1: Fetch active and sold pages using the exact same helpers as /debug/scrape-ebay
            print(f"[instant] STEP 1: Fetching eBay listings trace={trace_id}")
            active_items = []
            sold_items = []
            
            try:
                print(f"[fetch] ebay GET active mode q='{query}' trace={trace_id}")
                active_items = await scrape_ebay(query, mode="active")
                print(f"[api] Active listings: {len(active_items)} items (trace: {trace_id})")
                if active_items:
                    print(f"[api] First active item sample: url={active_items[0].get('url')}, id={active_items[0].get('source_listing_id')} trace={trace_id}")
            except Exception as e:
                print(f"[api] Active listings failed: {e} (trace: {trace_id})")
                print(f"[api] Active listings exception type: {type(e).__name__} trace={trace_id}")
                active_items = []
            
            try:
                print(f"[fetch] ebay GET sold mode q='{query}' trace={trace_id}")
                sold_items = await scrape_ebay(query, mode="sold")
                print(f"[api] Sold listings: {len(sold_items)} items (trace: {trace_id})")
                if sold_items:
                    print(f"[api] First sold item sample: url={sold_items[0].get('url')}, id={sold_items[0].get('source_listing_id')} trace={trace_id}")
            except Exception as e:
                print(f"[api] Sold listings failed: {e} (trace: {trace_id})")
                print(f"[api] Sold listings exception type: {type(e).__name__} trace={trace_id}")
                sold_items = []
            
            # STEP 2: Process and validate items using the same logic as debug endpoint
            print(f"[instant] STEP 2: Processing and validating items trace={trace_id}")
            print(f"[parse] Processing items: active={len(active_items)} sold={len(sold_items)} trace={trace_id}")
            
            merged = []
            skipped = {"no_url": 0, "no_id": 0, "duplicate": 0}
            seen = set()
            
            for lst in (active_items, sold_items):
                for it in lst or []:
                    # Check if item has required fields
                    has_url = bool(it.get("url"))
                    has_id = bool(it.get("source_listing_id"))
                    
                    if not has_url:
                        skipped["no_url"] += 1
                        print(f"[parse] SKIP reason=no-url item={it.get('title', 'unknown')} trace={trace_id}")
                        continue
                    
                    if not has_id:
                        skipped["no_id"] += 1
                        print(f"[parse] SKIP reason=no-id item={it.get('title', 'unknown')} trace={trace_id}")
                        continue
                    
                    # Check for duplicates
                    k = (it.get("source_listing_id") or "").strip() or (it.get("url") or "").strip().lower()
                    if k in seen:
                        skipped["duplicate"] += 1
                        print(f"[parse] SKIP reason=duplicate id={k} trace={trace_id}")
                        continue
                    
                    # Item is valid
                    seen.add(k)
                    merged.append(it)
                    print(f"[parse] ACCEPTED url={it.get('url')} id={it.get('source_listing_id')} trace={trace_id}")
            
            print(f"[parse] found_cards={len(active_items) + len(sold_items)} accepted={len(merged)} skipped={skipped} trace={trace_id}")
            
            # STEP 3: HARD VALIDATION GATE - Ensure no items without URL/ID are returned
            print(f"[instant] STEP 3: Validating final results trace={trace_id}")
            if not merged:
                print(f"[instant] VALIDATION FAILED: No valid items after filtering - returning error trace={trace_id}")
                error_payload = {
                    "ok": False,
                    "detail": "all_items_missing_url_or_id",
                    "counts": {
                        "total": len(active_items) + len(sold_items),
                        "withUrl": len([i for i in (active_items + sold_items) if i.get("url")]),
                        "withId": len([i for i in (active_items + sold_items) if i.get("source_listing_id")])
                    },
                    "trace": trace_id,
                    "where": "instant"
                }
                resp, trace = json_with_trace(error_payload, 502, trace_id)
                print(f"[instant] ERROR returned: {error_payload} trace={trace}")
                return resp
            
            # STEP 4: Return instant results (no Edge Function ingestion)
            print(f"[instant] STEP 4: Returning instant results trace={trace_id}")
            print(f"[parse] accepted={len(merged)}, skipped.no_url={skipped['no_url']}, skipped.no_id={skipped['no_id']}, skipped.duplicate={skipped['duplicate']} trace={trace_id}")
            
            payload = {
                "ok": True,
                "items": merged,
                "skipped": skipped,
                "ingestMode": "instant-results",
                "trace": trace_id
            }
            
            resp, trace = json_with_trace(payload, 200, trace_id)
            print(f"[instant] done accepted={len(merged)} trace={trace}")
            return resp
            
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[instant] ERROR: {e}\n{tb}")
            resp, trace = json_with_trace(
                {"ok": False, "detail": str(e), "where": "instant-path", "trace": trace_id},
                500
            )
            return resp
    
    # Log summary for every /scrape-now response
    print(f"[scrape-now] mode={'instant' if instant_mode else 'queued'} items=0 accepted=0 trace={trace_id}")
    
    if not instant_mode:
        print(f"[DEBUG] NOT instant mode - going through normal scraping path trace={trace_id}")
    
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
            
            # Step 2.5: Apply normalization safety-net (server-side too)
            print(f"[api] Step 2.5: Applying normalization safety-net (trace: {trace_id})")
            missing_url_count = 0
            missing_id_count = 0
            
            for item in normalized_data.items:
                # Apply the same normalization logic as /ingest
                url_sources = ['url', 'permalink', 'href', 'link', 'debug_url', 'viewItemURL', 'itemWebUrl', 'item_url', 'productUrl', 'linkHref']
                id_sources = ['source_listing_id', 'listing_id', 'id', 'itemId', 'item_id', 'ebay_id', 'itemIdStr']
                
                # Find URL from multiple sources
                url = None
                for source in url_sources:
                    if getattr(item, source, None):
                        url = getattr(item, source)
                        break
                
                # Find ID from multiple sources
                source_listing_id = None
                for source in id_sources:
                    if getattr(item, source, None):
                        source_listing_id = getattr(item, source)
                        break
                
                # Derive source_listing_id from URL if still empty
                if not source_listing_id and url:
                    ebay_id = extract_ebay_id(url)
                    if ebay_id:
                        source_listing_id = ebay_id
                        # Update the item with derived ID
                        item.source_listing_id = ebay_id
                
                # Synthesize URL from ID if missing but ID present
                if not url and source_listing_id:
                    url = f"https://www.ebay.com/itm/{source_listing_id}"
                    # Update the item with synthesized URL
                    item.url = url
                
                # Count missing fields after normalization
                if not url:
                    missing_url_count += 1
                
                if not source_listing_id:
                    missing_id_count += 1
            
            print(f"[api] Safety-net applied: missing_url={missing_url_count} missing_id={missing_id_count} (trace: {trace_id})")
            
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
                        has_title = bool(item.get("title"))
                        has_url = bool(item.get("url"))
                        has_id = bool(item.get("source_listing_id"))
                        
                        if has_title and (has_url or has_id):
                            filtered_items.append(item)
                    
                    ef_payload = {
                        "query": query,
                        "items": filtered_items
                    }
                    
                    # Log filtering results with comprehensive stats
                    total_items = len(validated_items)
                    with_url = len([item for item in validated_items if item.get("url")])
                    with_id = len([item for item in validated_items if item.get("source_listing_id")])
                    accepted = len(filtered_items)
                    
                    print(f"[api] EF ready: total={total_items}, with_url={with_url}, with_id={with_id}, accepted={accepted} (trace={trace_id})")
                    
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
                        
                        print(f"[api] scrape-now q=\"{query}\" items={len(normalized_data.items)} missing_url={missing_url_count} missing_id={missing_id_count} dur={total_time:.1f}s (trace: {trace_id})")
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
            
            # Check if instant ingest is requested
            instant_ingest = (
                request.ingest or 
                http_request.headers.get("X-Ingest", "").lower() in ["1", "true", "t", "yes", "on"]
            )
            
            if instant_mode and instant_ingest and merged:
                print(f"[api] Instant ingest requested - calling internal ingest routine (trace: {trace_id})")
                try:
                    # Prepare items for ingestion
                    ingest_items = []
                    for item in merged:
                        if item.get("url") and item.get("source_listing_id"):
                            ingest_items.append({
                                "title": item.get("title", ""),
                                "url": item.get("url"),
                                "source_listing_id": item.get("source_listing_id"),
                                "price": item.get("price"),
                                "currency": item.get("currency", "USD"),
                                "sold": item.get("sold", False),
                                "ended_at": item.get("ended_at")
                            })
                    
                    if ingest_items:
                        # Call internal ingest
                        ingest_response = await ingest_internal(query, "ebay", ingest_items, trace_id)
                        if ingest_response.get("ok"):
                            print(f"[api] Instant ingest successful: {ingest_response.get('ingestSummary', {})} (trace: {trace_id})")
                            response["instantIngest"] = ingest_response
                        else:
                            print(f"[api] Instant ingest failed: {ingest_response.get('error')} (trace: {trace_id})")
                            response["instantIngest"] = {"ok": False, "error": ingest_response.get("error")}
                except Exception as e:
                    print(f"[api] Instant ingest error: {e} (trace: {trace_id})")
                    response["instantIngest"] = {"ok": False, "error": str(e)}
            
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
            
            print(f"[api] scrape-now q=\"{query}\" items={len(normalized_data.items)} missing_url={missing_url_count} missing_id={missing_id_count} dur={total_time:.1f}s (trace: {trace_id})")
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

@app.post("/scrape-now-fast")
async def scrape_now_fast(request: ScrapeRequest, http_request: Request):
    """Fast scraping endpoint for instant results"""
    query = request.query.strip()
    
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Get client IP and generate trace ID
    client_ip = http_request.client.host if http_request.client else "unknown"
    trace_id = str(uuid.uuid4())[:8]
    
    # Log the incoming request
    print(f"[api] {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} Fast scrape request from {client_ip}: '{query}' (trace: {trace_id})")
    
    # Handle dryRun mode for health checks
    if request.dryRun:
        print(f"[api] DRY RUN mode - skipping actual processing (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": True,
                "dryRun": True,
                "query": query,
                "message": "Health check completed successfully",
                "trace": trace_id
            },
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
    
    # Always use instant mode for fast endpoint
    instant_mode = True
    print(f"[instant] start real_ebay_scraper q='{query}' trace={trace_id}")
    
    try:
        t0 = time.time()
        
        # STEP 1: Fetch active and sold pages using the exact same helpers as /debug/scrape-ebay
        print(f"[instant] STEP 1: Fetching eBay listings trace={trace_id}")
        active_items = []
        sold_items = []
        
        try:
            print(f"[fetch] ebay GET active mode q='{query}' trace={trace_id}")
            active_items = await scrape_ebay(query, mode="active")
            print(f"[api] Active listings: {len(active_items)} items (trace: {trace_id})")
            if active_items:
                print(f"[api] First active item sample: url={active_items[0].get('url')}, id={active_items[0].get('source_listing_id')} trace={trace_id}")
        except Exception as e:
            print(f"[api] Active listings failed: {e} (trace: {trace_id})")
            print(f"[api] Active listings exception type: {type(e).__name__} trace={trace_id}")
            active_items = []
        
        try:
            print(f"[fetch] ebay GET sold mode q='{query}' trace={trace_id}")
            sold_items = await scrape_ebay(query, mode="sold")
            print(f"[api] Sold listings: {len(sold_items)} items (trace: {trace_id})")
            if sold_items:
                print(f"[api] First sold item sample: url={active_items[0].get('url')}, id={active_items[0].get('source_listing_id')} trace={trace_id}")
        except Exception as e:
            print(f"[api] Sold listings failed: {e} (trace: {trace_id})")
            print(f"[api] Sold listings exception type: {type(e).__name__} trace={trace_id}")
            sold_items = []
        
        # STEP 2: Process and validate items using the same logic as debug endpoint
        print(f"[instant] STEP 2: Processing and validating items trace={trace_id}")
        print(f"[parse] Processing items: active={len(active_items)} sold={len(sold_items)} trace={trace_id}")
        
        merged = []
        skipped = {"no_url": 0, "no_id": 0, "duplicate": 0}
        seen = set()
        
        for lst in (active_items, sold_items):
            for it in lst or []:
                # Check if item has required fields
                has_url = bool(it.get("url"))
                has_id = bool(it.get("source_listing_id"))
                
                if not has_url:
                    skipped["no_url"] += 1
                    print(f"[parse] SKIP reason=no-url item={it.get('title', 'unknown')} trace={trace_id}")
                    continue
                
                if not has_id:
                    skipped["no_id"] += 1
                    print(f"[parse] SKIP reason=no-id item={it.get('title', 'unknown')} trace={trace_id}")
                    continue
                
                # Check for duplicates
                item_key = f"{it.get('url')}_{it.get('source_listing_id')}"
                if item_key in seen:
                    skipped["duplicate"] += 1
                    print(f"[parse] SKIP reason=duplicate item={it.get('title', 'unknown')} trace={trace_id}")
                    continue
                
                seen.add(item_key)
                merged.append(it)
        
        # STEP 3: Apply normalization safety-net
        print(f"[instant] STEP 3: Applying normalization safety-net trace={trace_id}")
        normalized_items = []
        missing_url_count = 0
        missing_id_count = 0
        
        for item in merged:
            # Apply the same normalization logic as /ingest
            url_sources = ['url', 'permalink', 'href', 'link', 'debug_url', 'viewItemURL', 'itemWebUrl', 'item_url', 'productUrl', 'linkHref']
            id_sources = ['source_listing_id', 'listing_id', 'id', 'itemId', 'item_id', 'ebay_id', 'itemIdStr']
            
            # Find URL from multiple sources
            url = None
            for source in url_sources:
                if item.get(source):
                    url = item.get(source)
                    break
            
            # Find ID from multiple sources
            source_listing_id = None
            for source in id_sources:
                if item.get(source):
                    source_listing_id = item.get(source)
                    break
            
            # Derive source_listing_id from URL if still empty
            if not source_listing_id and url:
                ebay_id = extract_ebay_id(url)
                if ebay_id:
                    source_listing_id = ebay_id
            
            # Synthesize URL from ID if missing but ID present
            if not url and source_listing_id:
                url = f"https://www.ebay.com/itm/{source_listing_id}"
            
            # Only accept items with both URL and ID after normalization
            if not url:
                missing_url_count += 1
                continue
            
            if not source_listing_id:
                missing_id_count += 1
                continue
            
            # Create normalized item
            normalized_item = {
                "title": item.get("title") or item.get("name") or "",
                "url": url,
                "source_listing_id": source_listing_id,
                "price": parse_price(str(item.get("price") or item.get("amount") or ""))[0],
                "currency": parse_price(str(item.get("price") or item.get("amount") or ""))[1] or "USD",
                "sold": bool(item.get("sold") or item.get("is_sold")),
                "ended_at": item.get("ended_at") or item.get("endTime")
            }
            
            normalized_items.append(normalized_item)
        
        total_time = time.time() - t0
        
        # Log observability metrics
        print(f"[api] scrape-now-fast q=\"{query}\" items={len(normalized_items)} missing_url={missing_url_count} missing_id={missing_id_count} dur={total_time:.1f}s (trace: {trace_id})")
        
        return JSONResponse(
            content={
                "ok": True,
                "items": normalized_items,
                "count": len(normalized_items),
                "query": query,
                "trace": trace_id,
                "upstream": "ebay-scraper"
            },
            headers={
                "X-Trace-Id": trace_id,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except asyncio.TimeoutError:
        error_msg = f"Scraper timeout ({SCRAPER_TIMEOUT}s)"
        print(f"[api] {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "detail": "upstream timeout",
                "trace": trace_id,
                "upstream": "external-scraper"
            },
            status_code=502,
            headers={"X-Trace-Id": trace_id}
        )
    except Exception as e:
        error_msg = f"Scraper error: {str(e)}"
        print(f"[api] {error_msg} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "detail": "upstream bad gateway",
                "trace": trace_id,
                "upstream": "external-scraper"
            },
            status_code=502,
            headers={"X-Trace-Id": trace_id}
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



@router.post("/ingest-items")
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

@router.get("/admin/diag-db")
async def admin_diag_db(request: Request):
    """Quick diagnostics endpoint to test Supabase REST API connectivity"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        return JSONResponse(
            content={"ok": False, "error": "Unauthorized", "trace": trace_id},
            status_code=401,
            headers={"x-trace-id": trace_id}
        )
    
    print(f"[api] /admin/diag-db called from {client_ip} (trace: {trace_id})")
    
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
        rest_url = f"{supabase_url}/rest/v1/tracked_queries"
        params = {"select": "id", "limit": "1"}
        
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
                "count": len(response.json()) if response.status_code < 400 else 0,
                "status": response.status_code,
                "sb_request_id": response.headers.get("sb-request-id", "unknown"),
                "trace": trace_id
            },
            headers={"x-trace-id": trace_id, "Content-Type": "application/json"}
        )
        
    except Exception as e:
        print(f"[api] /admin/diag-db error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "error": str(e),
                "sb_request_id": "unknown",
                "trace": trace_id
            },
            headers={
                "x-trace-id": trace_id,
                "Content-Type": "application/json"
            },
            status_code=200  # Always 200 to prevent UI crashes
        )



@router.get("/admin/health")
async def admin_health(request: Request):
    """Comprehensive health check endpoint for admin monitoring"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    origin = request.headers.get("origin", "unknown")
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        # Log failed attempt for security review
        print(f"[api] SECURITY: Unauthorized health check attempt from {client_ip} (origin: {origin}) at {time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return JSONResponse(
            content={"error": "Unauthorized"},
            status_code=401,
            headers={"x-trace-id": trace_id}
        )
    
    print(f"[api] /admin/health called from {client_ip} (trace: {trace_id})")
    
    # Check cache first
    cached_result = get_cached_health()
    if cached_result:
        print(f"[api] Returning cached health result (trace: {trace_id})")
        cached_result["trace"] = trace_id  # Update trace ID for this request
        return JSONResponse(
            content=cached_result,
            headers={
                "x-trace-id": trace_id,
                "Content-Type": "application/json",
                "X-Cache": "HIT"
            }
        )
    
    print(f"[api] Cache miss, running health checks (trace: {trace_id})")
    
    # Run all health checks in parallel with timeout
    async def check_supabase() -> dict:
        """Check Supabase REST API connectivity"""
        start_time = time.time()
        try:
            service_role_key = get_service_role_key()
            supabase_url = get_supabase_url()
            
            if not service_role_key or not supabase_url:
                return {"status": "fail", "error": "Service not configured", "latency_ms": 0}
            
            rest_url = f"{supabase_url}/rest/v1/tracked_queries"
            params = {"select": "1", "limit": "1"}
            
            headers = {
                "Authorization": f"Bearer {service_role_key}",
                "apikey": service_role_key,
                "Content-Type": "application/json"
            }
            
            response = await asyncio.wait_for(
                http_client.get(rest_url, headers=headers, params=params),
                timeout=3.0
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code < 400:
                return {"status": "ok", "latency_ms": latency_ms}
            else:
                return {"status": "fail", "error": f"HTTP {response.status_code}", "latency_ms": latency_ms}
                
        except asyncio.TimeoutError:
            return {"status": "fail", "error": "timeout", "latency_ms": int((time.time() - start_time) * 1000)}
        except Exception as e:
            return {"status": "fail", "error": str(e), "latency_ms": int((time.time() - start_time) * 1000)}
    
    async def check_edge_function() -> dict:
        """Check Edge Function connectivity via /scrape-now"""
        start_time = time.time()
        try:
            # Create a minimal health check request
            health_request = ScrapeRequest(query="health-check")
            
            # Call the scrape-now endpoint with dryRun
            response = await scrape_now(health_request, request)
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            if hasattr(response, 'status_code') and response.status_code == 200:
                return {"status": "ok", "latency_ms": latency_ms}
            else:
                return {"status": "fail", "error": "scrape-now failed", "latency_ms": latency_ms}
                
        except asyncio.TimeoutError:
            return {"status": "fail", "error": "timeout", "latency_ms": int((time.time() - start_time) * 1000)}
        except Exception as e:
            return {"status": "fail", "error": str(e), "latency_ms": int((time.time() - start_time) * 1000)}
    
    # Run all checks concurrently
    try:
        supabase_result, ef_result = await asyncio.gather(
            check_supabase(),
            check_edge_function(),
            return_exceptions=True
        )
        
        # Handle exceptions gracefully
        if isinstance(supabase_result, Exception):
            supabase_result = {"status": "fail", "error": str(supabase_result), "latency_ms": 0}
        if isinstance(ef_result, Exception):
            ef_result = {"status": "fail", "error": str(ef_result), "latency_ms": 0}
        
        # Build response
        response = {
            "supabase": supabase_result,
            "edge_function": ef_result,
            "proxy": {
                "status": "ok",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            },
            "trace": trace_id
        }
        
        # Cache the successful result
        set_health_cache(response)
        
        return JSONResponse(
            content=response,
            headers={
                "x-trace-id": trace_id,
                "Content-Type": "application/json",
                "X-Cache": "MISS"
            }
        )
        
    except Exception as e:
        print(f"[api] /admin/health error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "supabase": {"status": "fail", "error": "health_check_failed", "latency_ms": 0},
                "edge_function": {"status": "fail", "error": "health_check_failed", "latency_ms": 0},
                "proxy": {
                    "status": "fail",
                    "error": str(e),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                },
                "trace": trace_id
            },
            headers={
                "x-trace-id": trace_id,
                "Content-Type": "application/json"
            },
            status_code=200  # Always 200 to prevent UI crashes
        )



# Global health check cache
_health_cache = {
    "last_check": 0,
    "cache_duration": 30,  # 30 seconds
    "result": None
}

def get_cached_health() -> Optional[dict]:
    """Get cached health check result if still valid"""
    current_time = time.time()
    if current_time - _health_cache["last_check"] < _health_cache["cache_duration"]:
        return _health_cache["result"]
    return None

def set_health_cache(result: dict):
    """Cache health check result with timestamp"""
    _health_cache["last_check"] = time.time()
    _health_cache["result"] = result

# eBay scraper configuration
EBAY_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]



async def scrape_ebay(query: str, mode: str = "active") -> List[Dict[str, Any]]:
    """Scrape eBay listings with robust parsing and anti-bot measures"""
    import re
    import random
    import time
    
    print(f"[scraper] ENTRY: scrape_ebay called with query='{query}' mode='{mode}'")
    
    # Build eBay URL based on mode
    if mode == "active":
        url = f"https://www.ebay.com/sch/i.html?_nkw={query}&_sop=10&rt=nc"
    elif mode == "sold":
        url = f"https://www.ebay.com/sch/i.html?_nkw={query}&LH_Sold=1&LH_Complete=1&rt=nc"
    else:
        raise ValueError(f"Invalid mode: {mode}")
    
    print(f"[scraper] Scraping eBay {mode} mode: {url}")
    print(f"[fetch] ebay GET {url}")
    
    # Rotate User-Agent
    user_agent = random.choice(EBAY_USER_AGENTS)
    
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.ebay.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    # Retry logic with jitter and backoff
    max_retries = 3
    base_delay = 0.2  # 200ms base
    
    for attempt in range(max_retries):
        try:
            # Add jitter to delay
            jitter = random.uniform(0.8, 1.2)
            delay = base_delay * jitter
            
            if attempt > 0:
                # Exponential backoff
                delay = delay * (1.6 ** attempt)
                print(f"[scraper] Retry {attempt + 1}/{max_retries} after {delay:.2f}s delay")
            
            # Random sleep between requests
            sleep_time = random.uniform(1.0, 2.0)
            print(f"[scraper] Sleeping {sleep_time:.2f}s before request")
            await asyncio.sleep(sleep_time)
            
            # Make request with timeouts
            response = await asyncio.wait_for(
                http_client.get(url, headers=headers),
                timeout=17.0  # connect=5s + read=12s
            )
            
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            print(f"[fetch] ebay GET {url} status={response.status_code} bytes={len(response.content)}")
            result = parse_ebay_listings(response.text, query, mode)
            print(f"[scraper] EXIT: scrape_ebay returning {len(result)} items for mode='{mode}'")
            return result
            
        except asyncio.TimeoutError:
            print(f"[scraper] Timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                raise Exception("All retry attempts timed out")
        except Exception as e:
            print(f"[scraper] Error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                raise Exception(f"All retry attempts failed: {e}")
    
    raise Exception("Unexpected retry loop exit")

def parse_ebay_listings(html: str, query: str, mode: str) -> List[Dict[str, Any]]:
    """Parse eBay HTML listings with robust CSS selectors and fallbacks"""
    try:
        from selectolax.parser import HTMLParser
        parser = HTMLParser(html)
    except ImportError:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            # Convert to selectolax-like interface for compatibility
            class BS4Wrapper:
                def css(self, selector):
                    return soup.select(selector)
                
                def text(self):
                    return soup.get_text()
                
                def attributes(self):
                    return soup.attrs
                
                def get(self, attr):
                    return soup.get(attr)
            parser = BS4Wrapper()
        except ImportError:
            raise Exception("Neither selectolax nor BeautifulSoup4 available")
    
    print(f"[scraper] Parsing {mode} listings with {len(html)} bytes")
    
    # Try multiple selectors for listing cards
    selectors = [
        "li.s-item",
        ".s-item",
        "[data-testid='listing-card']",
        ".srp-results .s-item"
    ]
    
    cards = []
    for selector in selectors:
        cards = parser.css(selector)
        if cards:
            print(f"[parse] found_cards={len(cards)} selector={selector}")
            break
    
    if not cards:
        print(f"[scraper] WARNING: No cards found with any selector")
        # Log first 2 raw HTML lengths for debugging
        lines = html.split('\n')
        for i, line in enumerate(lines[:2]):
            if line.strip():
                print(f"[scraper] Raw HTML line {i}: {len(line)} chars")
        return []
    
    items = []
    for i, card in enumerate(cards[:50]):  # Limit to first 50 items
        try:
            item = parse_ebay_card(card, query, mode)
            if item:
                items.append(item)
        except Exception as e:
            print(f"[api] Error parsing card {i}: {e}")
            continue
    
    # Log comprehensive extraction results
    total_cards = len(cards)
    parsed_items = len(items)
    with_url = sum(1 for item in items if item.get("url"))
    with_id = sum(1 for item in items if item.get("source_listing_id"))
    
    print(f"[parse] found_cards={total_cards} parsed={parsed_items} with_url={with_url} with_id={with_id}")
    print(f"[parse] anchors={with_url} trace={trace_id if 'trace_id' in locals() else 'unknown'}")
    
    if parsed_items == 0:
        print(f"[api] WARNING: No items parsed successfully. First 2 raw card HTML lengths:")
        for i, card in enumerate(cards[:2]):
            try:
                if hasattr(card, 'text'):
                    card_text = card.text()
                else:
                    card_text = card.get_text()
                print(f"[api] Card {i}: {len(card_text)} chars")
                print(f"[api] Selectors used: {selectors}")
            except Exception as e:
                print(f"[api] Card {i}: Error getting text: {e}")
    
    print(f"[api] Successfully parsed {len(items)} valid items from {len(cards)} cards")
    return items

def parse_ebay_card(card, query: str, mode: str) -> Optional[Dict[str, Any]]:
    """Parse individual eBay listing card with bulletproof URL/ID extraction"""
    try:
        # Extract URL with comprehensive fallback strategies
        url = None
        
        # Strategy 1: Primary selectors for eBay listing links
        primary_selectors = [
            "a.s-item__link@href",
            "a[href*='/itm/']@href", 
            "a[href*='/p/']@href",
            "a.s-item__image-link@href",
            "a[data-testid='listing-link']@href"
        ]
        
        for selector in primary_selectors:
            try:
                if '@' in selector:
                    attr_selector, attr = selector.split('@')
                    elements = card.css(attr_selector)
                    if elements:
                        # Handle both selectolax and BeautifulSoup objects
                        if hasattr(elements[0], 'attributes'):
                            url = elements[0].attributes.get(attr)
                        else:
                            url = elements[0].get(attr)
                        
                        if url and ('/itm/' in url or '/p/' in url):
                            print(f"[debug] Found URL with {selector}: {url}")
                            break
                else:
                    elements = card.css(selector)
                    if elements:
                        # Handle both selectolax and BeautifulSoup objects
                        if hasattr(elements[0], 'attributes'):
                            url = elements[0].attributes.get('href')
                        else:
                            url = elements[0].get('href')
                        
                        if url and ('/itm/' in url or '/p/' in url):
                            print(f"[debug] Found URL with {selector}: {url}")
                            break
            except Exception as e:
                print(f"[debug] Selector {selector} failed: {e}")
                continue
        
        # Strategy 2: Fallback to any anchor with eBay-like URL
        if not url:
            try:
                all_links = card.css("a")
                for link in all_links:
                    try:
                        if hasattr(link, 'attributes'):
                            href = link.attributes.get('href')
                        else:
                            href = link.get('href')
                        
                        if href and ('/itm/' in href or '/p/' in href):
                            url = href
                            print(f"[debug] Found URL in fallback anchor: {url}")
                            break
                    except Exception:
                        continue
            except Exception as e:
                print(f"[debug] Fallback anchor search failed: {e}")
        
        # Strategy 3: Data attributes as last resort
        if not url:
            data_attrs = ["data-viewitemurl", "data-href", "data-url", "data-link"]
            for attr in data_attrs:
                try:
                    if hasattr(card, 'attributes'):
                        data_url = card.attributes.get(attr)
                    else:
                        data_url = card.get(attr)
                    
                    if data_url and ('/itm/' in data_url or '/p/' in data_url):
                        url = data_url
                        print(f"[debug] Found URL in data attribute {attr}: {url}")
                        break
                except Exception:
                    continue
        
        # Strategy 4: Direct href attribute on the card element
        if not url:
            try:
                if hasattr(card, 'attributes'):
                    href_attr = card.attributes.get("href")
                else:
                    href_attr = card.get("href")
                if href_attr and ('/itm/' in href_attr or '/p/' in href_attr):
                    url = href_attr
                    print(f"[debug] Found URL in direct href: {url}")
            except Exception as e:
                print(f"[debug] Direct href check failed: {e}")
        
        # Ensure URL is absolute
        if url and not url.startswith('http'):
            if url.startswith('/'):
                url = f"https://www.ebay.com{url}"
            else:
                url = f"https://www.ebay.com/{url}"
        
        # Canonicalize URL and extract ID
        if url:
            url = canonicalize_ebay_url(url)
            source_listing_id = extract_ebay_id(url)
        else:
            source_listing_id = None
        
        # If still no ID, try data attributes as last resort
        if not source_listing_id and hasattr(card, 'attributes'):
            id_attrs = ["data-view", "data-id", "data-listingid", "data-itemid", "itemid", "ebay-id"]
            for key in id_attrs:
                try:
                    maybe = card.attributes.get(key)
                    if maybe and re.fullmatch(r"\d{6,}", str(maybe)):
                        source_listing_id = str(maybe)
                        print(f"[debug] Found ID in data attribute {key}: {source_listing_id}")
                        break
                except Exception:
                    continue
        
        # Final fallback: search for any numeric ID in the card's HTML
        if not source_listing_id:
            try:
                # Get the card's HTML content and search for eBay-like IDs
                if hasattr(card, 'text'):
                    card_html = card.text()
                else:
                    card_html = card.get_text()
                
                # Look for patterns like /itm/123456789 or similar
                id_patterns = [
                    r"/itm/(\d{6,})",
                    r"/p/(\d{6,})",
                    r"[?&]itm=(\d{6,})",
                    r"[?&]itemId=(\d{6,})",
                    r"itemId=(\d{6,})",
                    r"(\d{6,})"  # Any 6+ digit number as last resort
                ]
                
                for pattern in id_patterns:
                    match = re.search(pattern, card_html)
                    if match:
                        source_listing_id = match.group(1)
                        print(f"[debug] Found ID with pattern {pattern}: {source_listing_id}")
                        break
            except Exception as e:
                print(f"[debug] HTML pattern search failed: {e}")
        
        # CRITICAL: Require both URL and ID for valid items
        if not url or not source_listing_id:
            print(f"[debug] REJECTED: Missing URL ({bool(url)}) or ID ({bool(source_listing_id)})")
            print(f"[debug] URL: {url}")
            print(f"[debug] ID: {source_listing_id}")
            return None
        
        print(f"[debug] ACCEPTED: URL={url}, ID={source_listing_id}")
        
        # Extract title with fallbacks
        title = None
        title_selectors = [
            ".s-item__title",
            ".s-item__title span",
            "[data-testid='item-title']",
            "h3",
            "h2"
        ]
        
        for selector in title_selectors:
            try:
                elements = card.css(selector)
                if elements:
                    # Handle both selectolax and BeautifulSoup objects
                    if hasattr(elements[0], 'text'):
                        title_text = elements[0].text().strip()
                    else:
                        title_text = elements[0].get_text().strip()
                    
                    # Skip "Shop on eBay" placeholders
                    if title_text and "Shop on eBay" not in title_text and len(title_text) > 5:
                        title = title_text
                        break
            except Exception:
                continue
        
        if not title:
            return None
        
        # Extract price with fallbacks
        price_text = None
        price_selectors = [
            ".s-item__price",
            ".s-item__price span",
            "[data-testid='price']",
            ".price"
        ]
        
        for selector in price_selectors:
            try:
                elements = card.css(selector)
                if elements:
                    # Handle both selectolax and BeautifulSoup objects
                    if hasattr(elements[0], 'text'):
                        price_text = elements[0].text().strip()
                    else:
                        price_text = elements[0].get_text().strip()
                    
                    if price_text:
                        break
            except Exception:
                continue
        
        # Parse price and currency using enhanced parser
        price, currency = parse_price(price_text) if price_text else (None, "USD")
        
        # Extract image URL
        image_url = None
        img_selectors = [
            ".s-item__image-img@src",
            ".s-item__image-img@data-src",
            "img@src",
            "img@data-src"
        ]
        
        for selector in img_selectors:
            try:
                if '@' in selector:
                    img_selector, attr = selector.split('@')
                    elements = card.css(img_selector)
                    if elements:
                        # Handle both selectolax and BeautifulSoup objects
                        if hasattr(elements[0], 'attributes'):
                            image_url = elements[0].attributes.get(attr)
                        else:
                            image_url = elements[0].get(attr)
                        
                        if image_url:
                            break
            except Exception:
                continue
        
        # Extract bids count
        bids = None
        bid_selectors = [
            ".s-item__bidCount",
            ".s-item__bidCount span"
        ]
        
        for selector in bid_selectors:
            try:
                elements = card.css(selector)
                if elements:
                    # Handle both selectolax and BeautifulSoup objects
                    if hasattr(elements[0], 'text'):
                        bid_text = elements[0].text().strip()
                    else:
                        bid_text = elements[0].get_text().strip()
                    
                    bid_match = re.search(r'(\d+)', bid_text)
                    if bid_match:
                        bids = int(bid_match.group(1))
                        break
            except Exception:
                continue
        
        # Extract ended date for sold items
        ended_at = None
        if mode == "sold":
            date_selectors = [
                ".s-item__ended-date",
                ".s-item__ended-date span"
            ]
            
            for selector in date_selectors:
                try:
                    elements = card.css(selector)
                    if elements:
                        # Handle both selectolax and BeautifulSoup objects
                        if hasattr(elements[0], 'text'):
                            date_text = elements[0].text().strip()
                        else:
                            date_text = elements[0].get_text().strip()
                        
                        # Try to parse common date formats
                        if "Sold" in date_text:
                            # Extract date part after "Sold"
                            date_part = date_text.split("Sold")[-1].strip()
                            # Simple date parsing (you might want to use dateutil for more robust parsing)
                            ended_at = date_part
                            break
                except Exception:
                    continue
        
        # Extract shipping info
        shipping_text = None
        shipping_selectors = [
            ".s-item__shipping",
            ".s-item__shipping span"
        ]
        
        for selector in shipping_selectors:
            try:
                elements = card.css(selector)
                if elements:
                    # Handle both selectolax and BeautifulSoup objects
                    if hasattr(elements[0], 'text'):
                        shipping_text = elements[0].text().strip()
                    else:
                        shipping_text = elements[0].get_text().strip()
                    
                    if shipping_text:
                        break
            except Exception:
                continue
        
        # Calculate total price
        total_price = price
        if shipping_text and price:
            # Try to extract shipping cost
            shipping_match = re.search(r'[\d,]+\.?\d*', shipping_text.replace(',', ''))
            if shipping_match:
                try:
                    shipping_cost = float(shipping_match.group())
                    if shipping_cost > 0:
                        total_price = price + shipping_cost
                except ValueError:
                    pass
        
        # Build item - now guaranteed to have url + source_listing_id
        item = {
            "title": title,
            "raw_title": title,
            "price": price,
            "currency": currency,
            "total_price": total_price,
            "source": "ebay",
            "url": url,
            "source_listing_id": source_listing_id,
            "sold": mode == "sold",
            "ended_at": ended_at,
            "image_url": image_url,
            "bids": bids,
            "raw_query": query
        }
        
        return item
        
    except Exception as e:
        print(f"[scraper] Error parsing card: {e}")
        return None

@router.get("/admin/diag-ef")
async def admin_diag_ef(request: Request):
    """Quick diagnostics endpoint to test Edge Function connectivity via ingest path"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        return JSONResponse(
            content={"error": "Unauthorized"},
            status_code=401,
            headers={"x-trace-id": trace_id}
        )
    
    print(f"[api] /admin/diag-ef called from {client_ip} (trace: {trace_id})")
    
    try:
        # Create a health check request with dryRun
        health_request = ScrapeRequest(query="health-check", dryRun=True)
        
        # Call the scrape-now endpoint (same code path as real ingest)
        response = await scrape_now(health_request, request)
        
        # Extract status from response
        if hasattr(response, 'status_code'):
            ef_status = response.status_code
            if ef_status < 400:
                return JSONResponse(
                    content={
                        "ok": True,
                        "ef_status": ef_status,
                        "trace": trace_id
                    },
                    headers={
                        "x-trace-id": trace_id,
                        "Content-Type": "application/json"
                    }
                )
            else:
                return JSONResponse(
                    content={
                        "ok": False,
                        "detail": f"HTTP {ef_status}",
                        "ef_status": ef_status,
                        "trace": trace_id
                    },
                    headers={
                        "x-trace-id": trace_id,
                        "Content-Type": "application/json"
                    },
                    status_code=200  # Always 200 to prevent UI crashes
                )
        else:
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": "Invalid response format",
                    "ef_status": 0,
                    "trace": trace_id
                },
                headers={
                    "x-trace-id": trace_id,
                    "Content-Type": "application/json"
                },
                status_code=200  # Always 200 to prevent UI crashes
            )
        
    except Exception as e:
        print(f"[api] /admin/diag-ef error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "detail": str(e),
                "ef_status": 0,
                "trace_id": trace_id
            },
            headers={
                "x-trace-id": trace_id,
                "Content-Type": "application/json"
            },
            status_code=200  # Always 200 to prevent UI crashes
        )



@router.options("/ingest-items")
def ingest_items_options(request: Request, response: Response):
    """OPTIONS handler for ingest-items endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Admin-Token, x-function-secret"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/{rest_of_path:path}")
def admin_wildcard_options(rest_of_path: str, request: Request, response: Response):
    """OPTIONS handler for admin wildcard endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Admin-Token, x-function-secret"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.post("/ingest")
async def ingest(request: IngestRequest, http_request: Request):
    """Ingest items into the database with upsert logic - hardened for Instant drawer compatibility"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    # Log request details
    print(f"[api] /ingest request from {client_ip} query='{request.query}' marketplace='{request.marketplace}' items={len(request.items)} (trace: {trace_id})")
    
    # Use consistent admin token validation
    is_valid, trace_id, error_message = validate_admin_token(http_request)
    if not is_valid:
        return create_error_response(error_message, 401, trace_id, http_request)
    
    # Check if this is a dry run
    dry_run = http_request.query_params.get("dryRun", "").lower() in ["1", "true", "t", "yes", "on"]
    
    if dry_run:
        print(f"[ingest] DRY RUN mode - simulating ingestion (trace: {trace_id})")
    
    try:
        # Use consistent normalization utility
        normalized_items, skip_stats = apply_normalization_safety_net(request.items, trace_id)
        
        # Check for duplicates
        valid_items = []
        seen_ids = set()
        for item in normalized_items:
            if item["source_listing_id"] in seen_ids:
                skip_stats["dup"] = 1  # Add dup counter if not present
                continue
            seen_ids.add(item["source_listing_id"])
            valid_items.append(item)
        
        # Update skip counters for response
        skip_counters = {
            "no_url": skip_stats["no_url"],
            "no_id": skip_stats["no_id"], 
            "dup": skip_stats.get("dup", 0)
        }
        
        # Log completion summary
        print(f"[api] /ingest accepted={len(valid_items)} skipped={skip_counters} (trace: {trace_id})")
        
        # Enhanced logging when accepted=0 - log reason per skipped category with item samples
        if len(valid_items) == 0:
            print(f"[ingest] WARNING: No items accepted! Analyzing skipped items (trace: {trace_id})")
            
            # Collect skipped items for detailed logging
            skipped_items = {"no_url": [], "no_id": [], "dup": []}
            
            for i, item in enumerate(request.items):
                # Re-run validation logic to categorize the item
                url = None
                for url_key in ['url', 'debug_url', 'href', 'link', 'permalink']:
                    if item.get(url_key):
                        url = item.get(url_key)
                        break
                
                source_listing_id = None
                for id_key in ['source_listing_id', 'listing_id', 'id', 'itemId', 'ebay_id']:
                    if item.get(id_key):
                        source_listing_id = str(item.get(id_key))
                        break
                
                # Derive from URL if still empty
                if not source_listing_id and url:
                    match = re.search(r'/itm/(\d{6,})', url)
                    if not match:
                        match = re.search(r'[?&]itm=(\d{6,})', url)
                    if not match:
                        match = re.search(r'/p/(\d{6,})', url)
                    if match:
                        source_listing_id = match.group(1)
                
                # Categorize the item
                if not url:
                    skipped_items["no_url"].append({
                        "index": i,
                        "title": item.get('title', 'N/A'),
                        "keys_present": [k for k in ['url', 'debug_url', 'href', 'link', 'permalink'] if item.get(k)]
                    })
                elif not source_listing_id:
                    skipped_items["no_id"].append({
                        "index": i,
                        "title": item.get('title', 'N/A'),
                        "url": url[:100] + "..." if len(url) > 100 else url,
                        "keys_present": [k for k in ['source_listing_id', 'listing_id', 'id', 'itemId', 'ebay_id'] if item.get(k)]
                    })
                else:
                    # This shouldn't happen, but log it
                    print(f"[ingest] Item {i} has both url and id but wasn't accepted - investigate! (trace: {trace_id})")
            
            # Log detailed skip reasons with samples
            for reason, items in skipped_items.items():
                if items:
                    print(f"[ingest] Skipped '{reason}': {len(items)} items (trace: {trace_id})")
                    for item in items[:3]:  # Show first 3 examples
                        if reason == "no_url":
                            print(f"  - Item {item['index']}: title='{item['title'][:50]}...' missing URL (had keys: {item['keys_present']})")
                        elif reason == "no_id":
                            print(f"  - Item {item['index']}: title='{item['title'][:50]}...' url={item['url']} missing ID (had keys: {item['keys_present']})")
        
        # Always return 200 JSON with consistent format
        response_data = {
            "ok": True,
            "card_id": None,
            "accepted": len(valid_items),
            "skipped": skip_counters,
            "total": len(request.items),
            "trace": trace_id
        }
        
        if not valid_items:
            return create_success_response(response_data, trace_id, http_request)
        
        if dry_run:
            # Return summary without database operations
            response_data["card_id"] = "dry-run-simulation"
            return create_success_response(response_data, trace_id, http_request)
        
        # Database operations using service role
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return create_error_response("Service not configured", 500, trace_id, http_request)
        
        # Step 1: Upsert card
        card_id = await upsert_card(
            supabase_url, service_role_key, 
            request.marketplace, request.query, trace_id
        )
        
        if not card_id:
            return create_error_response("Failed to create/update card", 500, trace_id, http_request)
        
        # Step 2: Upsert listings
        listings_created = await upsert_listings(
            supabase_url, service_role_key,
            card_id, valid_items, trace_id
            )
        
        print(f"[ingest] DB complete: card_id={card_id}, listings_created={listings_created} (trace: {trace_id})")
        
        response_data["card_id"] = card_id
        
        return create_success_response(response_data, trace_id, http_request)
        
    except Exception as e:
        print(f"[ingest] ERROR: {e} (trace: {trace_id})")
        return create_error_response(str(e), 500, trace_id, http_request)

@router.options("/ingest")
def ingest_options(request: Request, response: Response):
    """OPTIONS handler for ingest endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/cards")
def admin_cards_options(request: Request, response: Response):
    """OPTIONS handler for admin cards endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.options("/admin/listings")
def admin_listings_options(request: Request, response: Response):
    """OPTIONS handler for admin listings endpoint"""
    trace_id = generate_trace_id()
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return Response(status_code=200)

@router.get("/debug/ingest-sample")
async def debug_ingest_sample():
    """Return a minimal valid item example for testing"""
    return {
        "ok": True,
        "sample": {
            "query": "Charizard Base Set Unlimited PSA 9",
            "marketplace": "ebay",
            "items": [
                {
                    "title": "Charizard Base Set Unlimited PSA 9 - Pokemon Card",
                    "debug_url": "https://www.ebay.com/itm/306444665735",
                    "price": "450.00 USD",
                    "sold": False
                }
            ]
        }
    }

@router.get("/debug/admin-token")
async def debug_admin_token():
    """Debug endpoint to check admin token configuration"""
    expected_token = get_admin_proxy_token()
    env_var = os.getenv("ADMIN_PROXY_TOKEN")
    return {
        "ok": True,
        "token_length": len(expected_token) if expected_token else 0,
        "token_preview": expected_token[:10] + "..." if expected_token and len(expected_token) > 10 else expected_token,
        "env_var_set": bool(env_var),
        "env_var_preview": env_var[:10] + "..." if env_var and len(env_var) > 10 else env_var,
        "token_matches_env": expected_token == env_var
    }

@router.get("/admin/cards")
async def admin_cards(request: Request, search: Optional[str] = None, limit: int = 50, id: Optional[str] = None):
    """Admin endpoint to list cards from database with consistent response shape"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        return create_error_response("Unauthorized", 401, trace_id, request)
    
    # Validate limit parameter
    if limit > 1000:
        limit = 1000
    elif limit < 1:
        limit = 1
    
    print(f"[admin] /admin/cards called from {client_ip} search='{search}' limit={limit} id='{id}' (trace: {trace_id})")
    
    try:
        # Call Supabase REST API with service role key
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return create_error_response("Service not configured", 500, trace_id, request)
        
        # Build Supabase REST API URL
        rest_url = f"{supabase_url}/rest/v1/cards"
        params = {
            "select": "*",
            "order": "created_at.desc",
            "limit": min(limit, 1000)
        }
        
        # Add filters
        if id:
            # Exact UUID lookup
            params["id"] = f"eq.{id}"
        elif search:
            # Full-text search on query field
            params["query"] = f"ilike.%{search}%"
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        print(f"[admin] Calling Supabase REST: {rest_url} (trace: {trace_id})")
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        if response.status_code == 200:
            cards = response.json()
            print(f"[api] Retrieved {len(cards)} cards (trace: {trace_id})")
            return create_success_response({
                "items": cards,
                "count": len(cards)
            }, trace_id, request)
        else:
            # Return error with consistent shape
            sb_request_id = response.headers.get("sb-request-id", "unknown")
            print(f"[admin] Supabase REST error: {response.status_code} - {response.text} (sb-request-id: {sb_request_id}, trace: {trace_id})")
            return create_error_response(f"Database error: {response.status_code}", 500, trace_id, request)
        
    except Exception as e:
        print(f"[admin] /admin/cards error: {e} (trace: {trace_id})")
        return create_error_response(str(e), 500, trace_id, request)

@router.get("/admin/listings")
async def admin_listings(request: Request, card_id: str, limit: int = 200):
    """Admin endpoint to list listings from database with consistent response shape"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        return JSONResponse(
            content={
                "ok": False,
                "detail": "Unauthorized",
                "trace": trace_id
            },
            status_code=401,
            headers={"X-Trace-Id": trace_id}
        )
    
    # Validate card_id is provided
    if not card_id:
        return JSONResponse(
            content={
                "ok": False,
                "detail": "card_id is required",
                "trace": trace_id
            },
            status_code=400,
            headers={"X-Trace-Id": trace_id}
        )
    
    # Validate limit parameter
    if limit > 1000:
        limit = 1000
    elif limit < 1:
        limit = 1
    
    print(f"[admin] /admin/listings called from {client_ip} card_id={card_id} limit={limit} (trace: {trace_id})")
    
    try:
        # Call Supabase REST API with service role key
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": "Service not configured",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
        # Build Supabase REST API URL with specific field selection and ordering
        rest_url = f"{supabase_url}/rest/v1/listings"
        params = {
            "select": "id,card_id,title,url,source_listing_id,price,currency,sold,ended_at,created_at",
            "order": "ended_at.desc.nulls.last,created_at.desc",
            "limit": min(limit, 1000),
            "card_id": f"eq.{card_id}"
        }
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        print(f"[admin] Calling Supabase REST: {rest_url} (trace: {trace_id})")
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        if response.status_code == 200:
            listings = response.json()
            print(f"[admin] Retrieved {len(listings)} listings (trace: {trace_id})")
            return JSONResponse(
                content={
                    "ok": True,
                    "items": listings,
                    "count": len(listings),
                    "trace": trace_id
                },
                headers={"X-Trace-Id": trace_id}
            )
        else:
            # Return error with consistent shape
            sb_request_id = response.headers.get("sb-request-id", "unknown")
            print(f"[admin] Supabase REST error: {response.status_code} - {response.text} (sb-request-id: {sb_request_id}, trace: {trace_id})")
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": f"Database error: {response.status_code}",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
    except Exception as e:
        print(f"[admin] /admin/listings error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "detail": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={"X-Trace-Id": trace_id}
        )

@router.get("/admin/diag-db")
async def admin_diag_db(request: Request):
    """Admin diagnostic endpoint to test database connectivity"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        return JSONResponse(
            content={
                "ok": False,
                "detail": "Unauthorized",
                "trace": trace_id
            },
            status_code=401,
            headers={"X-Trace-Id": trace_id}
        )
    
    print(f"[admin] /admin/diag-db called from {client_ip} (trace: {trace_id})")
    
    try:
        # Test database connectivity by calling cards and tracked_queries endpoints
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": "Service not configured",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
        # Test cards endpoint
        cards_url = f"{supabase_url}/rest/v1/cards"
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        cards_response = await http_client.get(cards_url, headers=headers, params={"select": "id", "limit": 1})
        
        # Test tracked_queries endpoint
        queries_url = f"{supabase_url}/rest/v1/tracked_queries"
        queries_response = await http_client.get(queries_url, headers=headers, params={"select": "id", "limit": 1})
        
        if cards_response.status_code == 200 and queries_response.status_code == 200:
            print(f"[admin] Database connectivity test passed (trace: {trace_id})")
            return JSONResponse(
                content={
                    "ok": True,
                    "message": "Database connectivity test passed",
                    "cards_status": "ok",
                    "queries_status": "ok",
                    "trace": trace_id
                },
                headers={"X-Trace-Id": trace_id}
            )
        else:
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": f"Database test failed: cards={cards_response.status_code}, queries={queries_response.status_code}",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
    except Exception as e:
        print(f"[admin] /admin/diag-db error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "detail": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={"X-Trace-Id": trace_id}
        )

@router.get("/admin/diag-ef")
async def admin_diag_ef(request: Request):
    """Admin diagnostic endpoint to test Edge Function pipeline"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        return JSONResponse(
            content={
                "ok": False,
                "detail": "Unauthorized",
                "trace": trace_id
            },
            status_code=401,
            headers={"X-Trace-Id": trace_id}
        )
    
    print(f"[admin] /admin/diag-ef called from {client_ip} (trace: {trace_id})")
    
    try:
        # Test Edge Function pipeline with a dry-run external fetch
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": "Service not configured",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
        # Test with a simple health check query
        test_query = "health-check"
        test_url = f"{supabase_url}/rest/v1/tracked_queries"
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        # This tests if the Edge Function pipeline is reachable
        response = await http_client.get(test_url, headers=headers, params={"select": "id", "query": f"eq.{test_query}", "limit": 1})
        
        if response.status_code == 200:
            print(f"[admin] Edge Function pipeline test passed (trace: {trace_id})")
            return JSONResponse(
                content={
                    "ok": True,
                    "message": "Edge Function pipeline test passed",
                    "trace": trace_id
                },
                headers={"X-Trace-Id": trace_id}
            )
        else:
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": f"Edge Function test failed: {response.status_code}",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
    except Exception as e:
        print(f"[admin] /admin/diag-ef error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "detail": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={"X-Trace-Id": trace_id}
        )

@router.get("/admin/logs")
async def admin_logs(request: Request, limit: int = 1):
    """Admin endpoint to view scraping logs"""
    trace_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    
    # Check admin token
    admin_token = request.headers.get("X-Admin-Token")
    expected_token = get_admin_proxy_token()
    
    if not admin_token or admin_token != expected_token:
        return JSONResponse(
            content={
                "ok": False,
                "detail": "Unauthorized",
                "trace": trace_id
            },
            status_code=401,
            headers={"X-Trace-Id": trace_id}
        )
    
    # Validate limit parameter
    if limit > 1000:
        limit = 1000
    elif limit < 1:
        limit = 1
    
    print(f"[admin] /admin/logs called from {client_ip} limit={limit} (trace: {trace_id})")
    
    try:
        # Call Supabase REST API with service role key
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": "Service not configured",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
        # Build Supabase REST API URL
        rest_url = f"{supabase_url}/rest/v1/scraping_logs"
        params = {
            "select": "*",
            "order": "created_at.desc",
            "limit": min(limit, 1000)
        }
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        print(f"[admin] Calling Supabase REST: {rest_url} (trace: {trace_id})")
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        if response.status_code == 200:
            logs = response.json()
            print(f"[admin] Retrieved {len(logs)} logs (trace: {trace_id})")
            return JSONResponse(
                content={
                    "ok": True,
                    "items": logs,
                    "count": len(logs),
                    "trace": trace_id
                },
                headers={"X-Trace-Id": trace_id}
            )
        else:
            # Return error with consistent shape
            sb_request_id = response.headers.get("sb-request-id", "unknown")
            print(f"[admin] Supabase REST error: {response.status_code} - {response.text} (sb-request-id: {sb_request_id}, trace: {trace_id})")
            return JSONResponse(
                content={
                    "ok": False,
                    "detail": f"Database error: {response.status_code}",
                    "trace": trace_id
                },
                status_code=500,
                headers={"X-Trace-Id": trace_id}
            )
        
    except Exception as e:
        print(f"[admin] /admin/logs error: {e} (trace: {trace_id})")
        return JSONResponse(
            content={
                "ok": False,
                "detail": str(e),
                "trace": trace_id
            },
            status_code=500,
            headers={"X-Trace-Id": trace_id}
        )



# Helper functions for database operations
async def upsert_card(supabase_url: str, service_role_key: str, marketplace: str, query: str, trace_id: str) -> Optional[str]:
    """Upsert a card and return the card_id"""
    try:
        # First try to find existing card
        rest_url = f"{supabase_url}/rest/v1/cards"
        params = {
            "select": "id",
            "marketplace": f"eq.{marketplace}",
            "query": f"eq.{query}"
        }
        
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        response = await http_client.get(rest_url, headers=headers, params=params)
        
        if response.status_code == 200:
            existing_cards = response.json()
            if existing_cards:
                # Card exists, return its ID
                card_id = existing_cards[0]["id"]
                print(f"[api] Found existing card: {card_id} (trace: {trace_id})")
                return card_id
        
        # Card doesn't exist, create new one
        create_payload = {
            "marketplace": marketplace,
            "query": query
        }
        
        create_response = await http_client.post(
            rest_url,
            json=create_payload,
            headers=headers
        )
        
        if create_response.status_code == 201:
            new_card = create_response.json()
            card_id = new_card[0]["id"]
            print(f"[api] Created new card: {card_id} (trace: {trace_id})")
            return card_id
        else:
            print(f"[api] Failed to create card: {create_response.status_code} - {create_response.text} (trace: {trace_id})")
            return None
            
    except Exception as e:
        print(f"[api] Error in upsert_card: {e} (trace: {trace_id})")
        return None

async def upsert_listings(supabase_url: str, service_role_key: str, card_id: str, items: List[Dict[str, Any]], trace_id: str) -> int:
    """Upsert listings and return count of created/updated items"""
    try:
        rest_url = f"{supabase_url}/rest/v1/listings"
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json"
        }
        
        created_count = 0
        
        for item in items:
            # Check if listing already exists
            check_params = {
                "select": "id",
                "card_id": f"eq.{card_id}",
                "source_listing_id": f"eq.{item['source_listing_id']}"
            }
            
            check_response = await http_client.get(rest_url, headers=headers, params=check_params)
            
            if check_response.status_code == 200:
                existing_listings = check_response.json()
                if existing_listings:
                    # Listing exists, skip
                    print(f"[api] Listing already exists: {item['source_listing_id']} (trace: {trace_id})")
                    continue
            
            # Create new listing
            listing_payload = {
                "card_id": card_id,
                "title": item["title"],
                "url": item["url"],
                "source_listing_id": item["source_listing_id"],
                "price": item["price"],
                "currency": item["currency"],
                "sold": item["sold"],
                "ended_at": item["ended_at"]
            }
            
            create_response = await http_client.post(
                rest_url,
                json=listing_payload,
                headers=headers
            )
            
            if create_response.status_code == 201:
                created_count += 1
                print(f"[api] Created listing: {item['source_listing_id']} (trace: {trace_id})")
            else:
                print(f"[api] Failed to create listing: {create_response.status_code} - {create_response.text} (trace: {trace_id})")
        
        print(f"[api] Created {created_count} new listings (trace: {trace_id})")
        return created_count
        
    except Exception as e:
        print(f"[api] Error in upsert_listings: {e} (trace: {trace_id})")
        return 0

async def ingest_internal(query: str, marketplace: str, items: List[Dict[str, Any]], trace_id: str) -> Dict[str, Any]:
    """Internal ingest function for instant mode integration"""
    try:
        # Validate items - reject items without url or source_listing_id
        valid_items = []
        skipped_items = []
        
        for item in items:
            if not item.get("url") or not item.get("source_listing_id"):
                skipped_items.append({
                    "reason": "missing_url_or_id",
                    "item": item
                })
                continue
            
            # Normalize URL using existing helper
            normalized_url = canonicalize_ebay_url(item["url"])
            
            # Create validated item
            valid_item = {
                "title": item.get("title", ""),
                "url": normalized_url,
                "source_listing_id": item["source_listing_id"],
                "price": item.get("price"),
                "currency": item.get("currency", "USD"),
                "sold": item.get("sold", False),
                "ended_at": item.get("ended_at")
            }
            valid_items.append(valid_item)
        
        if not valid_items:
            return {
                "ok": True,
                "card_id": None,
                "ingestSummary": {
                    "accepted": 0,
                    "skipped": len(skipped_items),
                    "total": len(items)
                }
            }
        
        # Database operations using service role
        service_role_key = get_service_role_key()
        supabase_url = get_supabase_url()
        
        if not service_role_key or not supabase_url:
            return {
                "ok": False,
                "error": "Service not configured"
            }
        
        # Step 1: Upsert card
        card_id = await upsert_card(
            supabase_url, service_role_key, 
            marketplace, query, trace_id
        )
        
        if not card_id:
            return {
                "ok": False,
                "error": "Failed to create/update card"
            }
        
        # Step 2: Upsert listings
        listings_created = await upsert_listings(
            supabase_url, service_role_key,
            card_id, valid_items, trace_id
        )
        
        return {
            "ok": True,
            "card_id": card_id,
            "ingestSummary": {
                "accepted": len(valid_items),
                "skipped": len(skipped_items),
                "total": len(items)
            }
        }
        
    except Exception as e:
        print(f"[api] Error in ingest_internal: {e} (trace: {trace_id})")
        return {
            "ok": False,
            "error": str(e)
        }

# Debug endpoint to test eBay scraper directly
@router.get("/debug/scrape-ebay")
async def debug_scrape_ebay(q: str, request: Request):
    """Debug endpoint to test eBay scraper without going through ingest"""
    trace_id = str(uuid.uuid4())[:8]
    print(f"[debug] /debug/scrape-ebay q='{q}' trace={trace_id}")
    
    try:
        # Test both active and sold modes
        active_items = await scrape_ebay(q, mode="active")
        sold_items = await scrape_ebay(q, mode="sold")
        
        # Count items with URL and ID
        all_items = active_items + sold_items
        with_url = sum(1 for item in all_items if item.get("url"))
        with_id = sum(1 for item in all_items if item.get("source_listing_id"))
        
        # Sample of accepted items
        sample_items = []
        for item in all_items[:3]:
            if item.get("url") and item.get("source_listing_id"):
                sample_items.append({
                    "url": item.get("url"),
                    "id": item.get("source_listing_id"),
                    "title": item.get("title"),
                    "price": item.get("price")
                })
        
        return {
            "ok": True,
            "query": q,
            "active_items": len(active_items),
            "sold_items": len(sold_items),
            "total_items": len(all_items),
            "with_url": with_url,
            "with_id": with_id,
            "sample": sample_items,
            "trace": trace_id
        }
        
    except Exception as e:
        print(f"[debug] eBay scraper failed: {e} trace={trace_id}")
        return {
            "ok": False,
            "error": str(e),
            "trace": trace_id
        }

# Catch-all OPTIONS handler for any unmatched paths
@app.options("/{path:path}")
async def options_catch_all(path: str, request: Request):
    """Catch-all OPTIONS handler for any unmatched paths"""
    trace_id = generate_trace_id()
    response = Response(status_code=200)
    response.headers["X-Trace-Id"] = trace_id
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Token"
    response.headers["Access-Control-Expose-Headers"] = "X-Trace-Id"
    # Echo the origin for CORS
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    return response

# Simple test endpoint to verify app is working
@app.get("/test")
async def test_endpoint():
    return {"ok": True, "message": "App is working"}

# Include the router with all the main endpoints
app.include_router(router)

# Quick scraper test (uncomment to test locally)
# if __name__ == "__main__":
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