#!/usr/bin/env bash

# Comprehensive test script for CORS + Database functionality
# Tests: OPTIONS preflight, CORS headers on all responses, database operations

set -euo pipefail

# Configuration
BASE="https://rail-lovable-production.up.railway.app"
TOKEN="c0bfbad7-33f4-4d8a-b5e0-77f0b5af98a1"
ORIGIN="https://card-pulse-watch.lovable.app"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

pass() {
    echo -e "${GREEN}✅ PASS${NC} $1"
}

fail() {
    echo -e "${RED}❌ FAIL${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠️  WARN${NC} $1"
}

# Test function
test_endpoint() {
    local method="$1"
    local endpoint="$2"
    local description="$3"
    local expected_status="${4:-200}"
    local extra_headers="${5:-}"
    local data="${6:-}"
    
    log "Testing: $description"
    log "  $method $endpoint"
    
    # Build curl command
    local curl_cmd="curl -s -i -X $method"
    
    if [[ -n "$extra_headers" ]]; then
        curl_cmd="$curl_cmd $extra_headers"
    fi
    
    if [[ -n "$data" ]]; then
        curl_cmd="$curl_cmd -d '$data'"
    fi
    
    curl_cmd="$curl_cmd '$BASE$endpoint'"
    
    # Execute and capture response
    local response
    response=$(eval "$curl_cmd")
    
    # Extract status code
    local status_code
    status_code=$(echo "$response" | head -n 1 | grep -o '[0-9][0-9][0-9]' | head -n 1)
    
    # Extract CORS headers
    local acao
    acao=$(echo "$response" | grep -i "access-control-allow-origin" | head -n 1 | sed 's/^[^:]*: *//')
    
    local aceh
    aceh=$(echo "$response" | grep -i "access-control-expose-headers" | head -n 1 | sed 's/^[^:]*: *//')
    
    local trace_id
    trace_id=$(echo "$response" | grep -i "x-trace-id" | head -n 1 | sed 's/^[^:]*: *//')
    
    # Check status code
    if [[ "$status_code" == "$expected_status" ]]; then
        pass "Status code: $status_code (expected: $expected_status)"
    else
        fail "Status code: $status_code (expected: $expected_status)"
    fi
    
    # Check CORS headers
    if [[ -n "$acao" ]]; then
        if [[ "$acao" == "$ORIGIN" ]] || [[ "$acao" == "*" ]]; then
            pass "CORS Origin: $acao"
        else
            fail "CORS Origin mismatch: got '$acao', expected '$ORIGIN' or '*'"
        fi
    else
        warn "No Access-Control-Allow-Origin header found"
    fi
    
    if [[ -n "$aceh" ]]; then
        if echo "$aceh" | grep -qi "x-trace-id"; then
            pass "CORS Expose Headers: $aceh"
        else
            warn "CORS Expose Headers missing X-Trace-Id: $aceh"
        fi
    else
        warn "No Access-Control-Expose-Headers found"
    fi
    
    if [[ -n "$trace_id" ]]; then
        pass "X-Trace-Id: $trace_id"
    else
        warn "No X-Trace-Id header found"
    fi
    
    echo
}

echo "🚀 Testing Railway + Lovable Integration (CORS + Database)"
echo "=========================================================="
echo "Base URL: $BASE"
echo "Origin: $ORIGIN"
echo "Admin Token: ${TOKEN:0:10}..."
echo

# Test 1: Health endpoint (should work without CORS issues)
test_endpoint "GET" "/health" "Health endpoint"

# Test 2: OPTIONS preflight for /ingest
test_endpoint "OPTIONS" "/ingest" "OPTIONS preflight for /ingest" "200" \
    "-H 'Origin: $ORIGIN' -H 'Access-Control-Request-Method: POST'"

# Test 3: OPTIONS preflight for /admin/cards
test_endpoint "OPTIONS" "/admin/cards" "OPTIONS preflight for /admin/cards" "200" \
    "-H 'Origin: $ORIGIN' -H 'Access-Control-Request-Method: GET'"

# Test 4: OPTIONS preflight for /scrape-now
test_endpoint "OPTIONS" "/scrape-now" "OPTIONS preflight for /scrape-now" "200" \
    "-H 'Origin: $ORIGIN' -H 'Access-Control-Request-Method: POST'"

# Test 5: Dry run ingest (should work and include CORS)
test_endpoint "POST" "/ingest?dryRun=true" "Dry run ingest (CORS test)" "200" \
    "-H 'Origin: $ORIGIN' -H 'Content-Type: application/json' -H 'X-Admin-Token: $TOKEN'" \
    '{"query":"Test CORS","marketplace":"ebay","items":[{"title":"Test","debug_url":"https://www.ebay.com/itm/123456789","price":"100 USD"}]}'

# Test 6: Real ingest (should fail with 500 but include CORS)
test_endpoint "POST" "/ingest" "Real ingest (should fail with 500 + CORS)" "500" \
    "-H 'Origin: $ORIGIN' -H 'Content-Type: application/json' -H 'X-Admin-Token: $TOKEN'" \
    '{"query":"Test Real Save","marketplace":"ebay","items":[{"title":"Test","debug_url":"https://www.ebay.com/itm/123456789","price":"100 USD"}]}'

# Test 7: Admin endpoint with token (should work + CORS)
test_endpoint "GET" "/admin/diag-db" "Admin diagnostics (CORS test)" "200" \
    "-H 'Origin: $ORIGIN' -H 'X-Admin-Token: $TOKEN'"

# Test 8: Admin endpoint without token (should fail with 401 + CORS)
test_endpoint "GET" "/admin/diag-db" "Admin diagnostics without token (401 + CORS)" "401" \
    "-H 'Origin: $ORIGIN'"

# Test 9: Scraping endpoint (should work + CORS)
test_endpoint "POST" "/scrape-now" "Scraping endpoint (CORS test)" "200" \
    "-H 'Origin: $ORIGIN' -H 'Content-Type: application/json'" \
    '{"query":"Test Scrape","dryRun":true}'

echo "🎯 Test Summary"
echo "==============="
echo "All tests completed. Check the results above."
echo
echo "🔍 Key things to verify:"
echo "1. All OPTIONS requests return 200"
echo "2. All responses include CORS headers (even 500 errors)"
echo "3. X-Trace-Id is present in all responses"
echo "4. Access-Control-Allow-Origin echoes the request origin"
echo
echo "💡 If CORS is working but you still get 500s, the issue is:"
echo "   - Missing database tables (run create_cards_and_listings_tables.sql)"
echo "   - Database connection issues"
echo "   - Code errors in the ingest logic"

