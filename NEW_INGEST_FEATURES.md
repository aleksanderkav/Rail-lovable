# New Ingest Features for Rail-lovable

This document describes the new ingest functionality added to the Rail-lovable service.

## 🚀 New Endpoints

### 1. POST /ingest

**Purpose**: Ingest items into the database with upsert logic

**Input JSON**:
```json
{
  "query": "Gengar Fossil 1st Edition PSA 10",
  "marketplace": "ebay",
  "items": [
    {
      "title": "Gengar Fossil 1st Edition PSA 10 - Pokemon Card",
      "url": "https://www.ebay.com/itm/306444665735",
      "source_listing_id": "306444665735",
      "price": 1400.0,
      "currency": "USD",
      "sold": false,
      "ended_at": null
    }
  ]
}
```

**Validation**:
- Rejects items without `url` or `source_listing_id`
- Normalizes URLs using existing `canonicalize_ebay_url` helper
- Returns summary of accepted/skipped items

**Behavior**:
- Upserts card in `cards` table on `(marketplace, query)` → gets `card_id`
- Upserts all listings with unique key `(card_id, source_listing_id)`
- Uses service role key for database operations (server-side only)

**Response**:
```json
{
  "ok": true,
  "card_id": "uuid-here",
  "ingestSummary": {
    "accepted": 2,
    "skipped": 0,
    "total": 2
  },
  "trace": "abcd1234"
}
```

**Dry Run Mode**:
- Add `?dryRun=true` to simulate ingestion without database writes
- Returns `card_id: "dry-run-simulation"`

### 2. GET /admin/cards

**Purpose**: List cards from database (admin only)

**Headers**: `X-Admin-Token: <token>`

**Query Parameters**:
- `limit`: Maximum number of cards to return (default: 100, max: 1000)

**Response**:
```json
{
  "ok": true,
  "cards": [
    {
      "id": "uuid-here",
      "marketplace": "ebay",
      "query": "Gengar Fossil 1st Edition PSA 10",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "count": 1,
  "trace": "abcd1234"
}
```

### 3. GET /admin/listings

**Purpose**: List listings from database (admin only)

**Headers**: `X-Admin-Token: <token>`

**Query Parameters**:
- `card_id`: Filter by specific card ID (optional)
- `limit`: Maximum number of listings to return (default: 100, max: 1000)

**Response**:
```json
{
  "ok": true,
  "listings": [
    {
      "id": "uuid-here",
      "card_id": "card-uuid-here",
      "title": "Gengar Fossil 1st Edition PSA 10 - Pokemon Card",
      "url": "https://www.ebay.com/itm/306444665735",
      "source_listing_id": "306444665735",
      "price": 1400.0,
      "currency": "USD",
      "sold": false,
      "ended_at": null,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "count": 1,
  "trace": "abcd1234"
}
```

## 🔄 Enhanced /scrape-now Endpoint

### Instant Ingest Integration

**New Parameters**:
- `ingest`: Boolean flag to enable instant ingestion
- `X-Ingest`: Header alternative to `ingest` parameter

**Usage**:
```bash
# Query parameter
curl -X POST "http://localhost:8000/scrape-now?instant=true" \
  -H "Content-Type: application/json" \
  -d '{"query": "Charizard Base Set", "instant": true, "ingest": true}'

# Header alternative
curl -X POST "http://localhost:8000/scrape-now?instant=true" \
  -H "Content-Type: application/json" \
  -H "X-Ingest: true" \
  -d '{"query": "Charizard Base Set", "instant": true}'
```

**Behavior**:
- When `instant=true` AND `ingest=true` (or `X-Ingest: true`):
  - Scrapes items as usual
  - Automatically calls internal ingest routine
  - Adds `instantIngest` field to response
- Otherwise: Maintains "preview only" behavior

**Enhanced Response**:
```json
{
  "ok": true,
  "items": [...],
  "externalOk": true,
  "efStatus": 200,
  "efBody": "...",
  "trace": "abcd1234",
  "instantIngest": {
    "ok": true,
    "card_id": "uuid-here",
    "ingestSummary": {
      "accepted": 5,
      "skipped": 0,
      "total": 5
    }
  }
}
```

## 🗄️ Database Schema

### Tables

**cards**:
```sql
CREATE TABLE cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    marketplace TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (marketplace, query)
);
```

**listings**:
```sql
CREATE TABLE listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    card_id UUID REFERENCES cards(id) ON DELETE CASCADE,
    title TEXT,
    url TEXT NOT NULL,
    source_listing_id TEXT NOT NULL,
    price NUMERIC,
    currency TEXT,
    sold BOOLEAN DEFAULT FALSE,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (card_id, source_listing_id)
);
```

**Indexes**:
```sql
CREATE INDEX idx_listings_card_id_created_at 
ON listings (card_id, created_at DESC);
```

### RLS Policies

- **SELECT**: Allow reading for anonymous users (temporary)
- **INSERT/UPDATE/DELETE**: Controlled by service role key (bypasses RLS)

## 🔧 Environment Variables

**Required for database operations**:
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key for database access

**Required for admin endpoints**:
- `ADMIN_PROXY_TOKEN`: Token for admin authentication

## 🧪 Testing

### Test Script

Run the comprehensive test suite:
```bash
python test_new_ingest_endpoints.py
```

### Manual Testing

**Test ingest with dry run**:
```bash
curl -X POST "http://localhost:8000/ingest?dryRun=true" \
  -H "Content-Type: application/json" \
  -d @test_data.json
```

**Test admin endpoints**:
```bash
curl -H "X-Admin-Token: your-token" \
  "http://localhost:8000/admin/cards?limit=5"
```

## 🔒 Security Features

- **Service Role Key**: Database operations use service role (server-side only)
- **Admin Token**: Admin endpoints require `X-Admin-Token` header
- **Input Validation**: Rejects invalid items before database operations
- **URL Normalization**: Cleans and validates URLs before storage
- **Trace IDs**: All operations include trace IDs for debugging

## 📊 Logging

All endpoints include comprehensive logging:
- Client IP addresses
- Trace IDs for request tracking
- Validation results (accepted/skipped counts)
- Database operation results
- Error details with context

## 🚀 Deployment

1. **Database Setup**: Run `create_cards_and_listings_tables.sql` in Supabase
2. **Environment Variables**: Set required environment variables
3. **Deploy**: Push to Railway (automatic deployment)
4. **Test**: Run test suite to verify functionality

## 🔄 Migration Notes

- **Backward Compatible**: Existing endpoints unchanged
- **Optional Features**: Instant ingest is opt-in
- **Dry Run Default**: `/ingest` defaults to safe dry-run mode
- **Admin Access**: New admin endpoints require token authentication
