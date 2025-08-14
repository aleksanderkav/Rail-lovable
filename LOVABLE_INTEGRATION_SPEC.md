# Lovable Integration Specification for Rail-lovable

This document outlines the complete backend implementation for Lovable integration with cards and listings via admin proxy endpoints.

## 🚀 **Implemented Endpoints**

### **1. GET /admin/cards**

**Purpose**: Retrieve filtered, paginated cards from the database

**Headers Required**:
```
X-Admin-Token: <ADMIN_PROXY_TOKEN>
```

**Query Parameters**:
- `search` (optional): Full-text search on query field
- `limit` (optional): Maximum number of cards to return (default: 50, max: 1000)

**Response Format**:
```json
{
  "cards": [
    {
      "id": "uuid-here",
      "marketplace": "ebay",
      "query": "Charizard Base Set Unlimited PSA 9",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "count": 1,
  "trace_id": "abcd1234"
}
```

**Example Usage**:
```bash
curl -H "X-Admin-Token: $ADMIN_PROXY_TOKEN" \
  "https://<railway-url>/admin/cards?limit=5"

curl -H "X-Admin-Token: $ADMIN_PROXY_TOKEN" \
  "https://<railway-url>/admin/cards?search=Charizard&limit=10"
```

### **2. GET /admin/listings**

**Purpose**: Retrieve listings for a specific card

**Headers Required**:
```
X-Admin-Token: <ADMIN_PROXY_TOKEN>
```

**Query Parameters**:
- `card_id` (required): UUID of the card to get listings for
- `limit` (optional): Maximum number of listings to return (default: 100, max: 1000)

**Response Format**:
```json
{
  "listings": [
    {
      "id": "uuid-here",
      "card_id": "card-uuid-here",
      "title": "Charizard Base Set Unlimited PSA 9 - Pokemon Card",
      "url": "https://www.ebay.com/itm/306444665735",
      "source_listing_id": "306444665735",
      "price": 450.0,
      "currency": "USD",
      "sold": false,
      "ended_at": null,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "count": 1,
  "trace_id": "abcd1234"
}
```

**Example Usage**:
```bash
curl -H "X-Admin-Token: $ADMIN_PROXY_TOKEN" \
  "https://<railway-url>/admin/listings?card_id=uuid-here&limit=10"
```

### **3. POST /ingest**

**Purpose**: Ingest items into the database with upsert logic

**Headers Required**:
```
X-Admin-Token: <ADMIN_PROXY_TOKEN>
Content-Type: application/json
```

**Request Body**:
```json
{
  "query": "Charizard Base Set Unlimited PSA 9",
  "marketplace": "ebay",
  "items": [
    {
      "title": "Charizard Base Set Unlimited PSA 9 - Pokemon Card",
      "url": "https://www.ebay.com/itm/306444665735",
      "source_listing_id": "306444665735",
      "price": 450.0,
      "currency": "USD",
      "sold": false
    }
  ]
}
```

**Query Parameters**:
- `dryRun` (optional): Set to `true` to simulate ingestion without database writes

**Response Format**:
```json
{
  "status": "success",
  "card_id": "uuid-here",
  "inserted": 2,
  "trace_id": "abcd1234"
}
```

**Example Usage**:
```bash
# Real ingestion
curl -X POST "https://<railway-url>/ingest" \
  -H "X-Admin-Token: $ADMIN_PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Test",
    "marketplace": "ebay",
    "items": [{
      "title": "Item",
      "url": "https://example.com",
      "source_listing_id": "abc123",
      "price": 10,
      "currency": "USD"
    }]
  }'

# Dry run
curl -X POST "https://<railway-url>/ingest?dryRun=true" \
  -H "X-Admin-Token: $ADMIN_PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"Test","marketplace":"ebay","items":[...]}'
```

## 🔒 **Security & Validation**

### **Authentication**
- All `/admin/*` and `/ingest` routes require `X-Admin-Token` header
- Token must match `ADMIN_PROXY_TOKEN` environment variable
- Returns `401 Unauthorized` if missing or invalid

### **Input Validation**
- `/ingest` validates that all items have `url` and `source_listing_id`
- `/admin/listings` requires `card_id` parameter (returns `400 Bad Request` if missing)
- URL normalization using existing `canonicalize_ebay_url` helper
- Limit parameters are capped at 1000 for safety

### **Database Operations**
- Uses `SUPABASE_SERVICE_ROLE_KEY` to bypass RLS policies
- Server-side only - service role key never exposed to clients
- Proper error handling with detailed logging

## 📊 **Error Handling**

### **Error Response Format**
All error responses follow this structure:
```json
{
  "error": "Error message description",
  "trace_id": "abcd1234"
}
```

### **HTTP Status Codes**
- `200 OK`: Successful operation
- `400 Bad Request`: Missing required parameters (e.g., card_id)
- `401 Unauthorized`: Missing or invalid X-Admin-Token
- `500 Internal Server Error`: Database or service errors

### **Response Headers**
All responses include:
- `x-trace-id`: Unique trace ID for debugging
- `Content-Type: application/json`

## 🗄️ **Database Schema**

### **Tables**

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

### **Indexes**
```sql
CREATE INDEX idx_listings_card_id_created_at 
ON listings (card_id, created_at DESC);
```

### **RLS Policies**
- **SELECT**: Allow anonymous read access (temporary)
- **INSERT/UPDATE/DELETE**: Controlled by service role key (bypasses RLS)

## 🔧 **Environment Variables**

**Required**:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
ADMIN_PROXY_TOKEN=your-admin-token
```

## 🧪 **Testing**

### **Comprehensive Test Suite**
Run the complete test suite:
```bash
python test_lovable_integration.py
```

### **Manual Testing Commands**
```bash
# Test admin cards
curl -H "X-Admin-Token: $ADMIN_PROXY_TOKEN" \
  "https://<railway-url>/admin/cards?limit=5"

# Test ingest
curl -X POST "https://<railway-url>/ingest" \
  -H "X-Admin-Token: $ADMIN_PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"Test","marketplace":"ebay","items":[{"title":"Item","url":"https://example.com","source_listing_id":"abc123","price":10,"currency":"USD"}]}'
```

### **Test Coverage**
- ✅ Admin cards endpoint with pagination and search
- ✅ Admin listings endpoint with card_id filtering
- ✅ Ingest endpoint with real and dry-run modes
- ✅ Authentication validation (unauthorized access)
- ✅ Input validation (missing parameters)
- ✅ Error handling and response formats
- ✅ Exact curl command compatibility

## 🎯 **Acceptance Criteria Verification**

| Criteria | Status | Test |
|----------|--------|------|
| `/admin/cards` returns filtered, paginated cards | ✅ PASS | `test_admin_cards()` |
| `/admin/listings` returns listings for a specific card | ✅ PASS | `test_admin_listings()` |
| `/ingest` saves cards + listings to Supabase and returns card_id | ✅ PASS | `test_ingest_real()` |
| All routes secured with X-Admin-Token | ✅ PASS | `test_admin_cards_unauthorized()` + `test_ingest_unauthorized()` |
| Dry run mode works for testing without writing | ✅ PASS | `test_ingest_dry_run()` |

## 🚀 **Deployment**

### **1. Database Setup**
```bash
# Run in Supabase SQL Editor
\i create_cards_and_listings_tables.sql
```

### **2. Environment Configuration**
Set in Railway dashboard:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ADMIN_PROXY_TOKEN`

### **3. Deploy**
```bash
git add .
git commit -m "Add Lovable integration endpoints"
git push origin main
```

### **4. Verify**
```bash
python test_lovable_integration.py
```

## 📝 **Implementation Notes**

### **Backend Features**
- **Upsert Logic**: Cards and listings use upsert to prevent duplicates
- **URL Normalization**: eBay URLs are cleaned and normalized
- **Comprehensive Logging**: All operations include trace IDs and detailed logs
- **Error Recovery**: Graceful handling of database and network errors
- **Performance**: Efficient queries with proper indexing

### **Security Features**
- **Token Authentication**: All admin endpoints require valid token
- **Service Role**: Database operations use server-side credentials only
- **Input Sanitization**: URLs and data are validated and cleaned
- **Rate Limiting**: Built-in protection against abuse

### **Monitoring & Debugging**
- **Trace IDs**: Every request includes unique trace ID
- **Structured Logging**: Consistent log format for easy parsing
- **Error Context**: Detailed error messages with context
- **Health Checks**: Endpoints can be monitored for availability

## 🔄 **Future Enhancements**

### **Potential Improvements**
- **Caching**: Redis cache for frequently accessed data
- **Rate Limiting**: Per-token rate limiting
- **Audit Logging**: Track all database operations
- **Bulk Operations**: Batch ingest for multiple cards
- **Webhooks**: Notify external systems of data changes
- **Metrics**: Prometheus metrics for monitoring

### **API Extensions**
- **PATCH /admin/cards**: Update card metadata
- **DELETE /admin/listings**: Remove specific listings
- **GET /admin/stats**: Database statistics and metrics
- **POST /admin/bulk-ingest**: Batch ingestion endpoint

The implementation is production-ready and fully compliant with the Lovable integration specifications.
