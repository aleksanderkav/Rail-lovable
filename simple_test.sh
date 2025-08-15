#!/usr/bin/env bash

# Simple test script for Railway + Lovable integration
BASE="https://rail-lovable-production.up.railway.app"
TOKEN="c0bfbad7-33f4-4d8a-b5e0-77f0b5af98a1"
ORIGIN="https://card-pulse-watch.lovable.app"

echo "🚀 Testing Railway + Lovable Integration"
echo "=========================================="

# Test 1: Health endpoint
echo -e "\n🔍 Test 1: Health endpoint"
response=$(curl -s "$BASE/health")
echo "Response: $response"

# Test 2: CORS Preflight
echo -e "\n🔍 Test 2: CORS Preflight (OPTIONS)"
response=$(curl -s -X OPTIONS "$BASE/admin/logs" \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: GET" \
  -w "%{http_code}")
echo "Status: $response"

# Test 3: Admin endpoint with token
echo -e "\n🔍 Test 3: Admin endpoint with token"
response=$(curl -s -H "X-Admin-Token: $TOKEN" "$BASE/admin/diag-db")
echo "Response: $response"

# Test 4: Ingest with normalization
echo -e "\n🔍 Test 4: Ingest with normalization (dry run)"
payload='{"query":"Test Normalization","marketplace":"ebay","items":[{"title":"Test Item","debug_url":"https://www.ebay.com/itm/123456789","price":"100 USD"}]}'
response=$(curl -s -X POST "$BASE/ingest?dryRun=true" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $TOKEN" \
  -d "$payload")
echo "Response: $response"

# Test 5: Ingest with ID only (URL synthesis)
echo -e "\n🔍 Test 5: Ingest with ID only (URL synthesis)"
payload='{"query":"Only ID","marketplace":"ebay","items":[{"title":"OnlyID","itemId":"306444665735"}]}'
response=$(curl -s -X POST "$BASE/ingest?dryRun=true" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $TOKEN" \
  -d "$payload")
echo "Response: $response"

# Test 6: Auth negative (missing token)
echo -e "\n🔍 Test 6: Auth negative (missing token)"
response=$(curl -s -X POST "$BASE/ingest?dryRun=true" \
  -H "Content-Type: application/json" \
  -d '{"query":"No token","marketplace":"ebay","items":[]}')
echo "Response: $response"

# Test 7: Method enforcement (GET on POST-only)
echo -e "\n🔍 Test 7: Method enforcement (GET on POST-only)"
response=$(curl -s "$BASE/scrape-now-fast")
echo "Response: $response"

# Test 8: Scraping endpoint
echo -e "\n🔍 Test 8: Scraping endpoint (dry run)"
payload='{"query":"Charizard Test","dryRun":true}'
response=$(curl -s -X POST "$BASE/scrape-now" \
  -H "Content-Type: application/json" \
  -d "$payload")
echo "Response: $response"

echo -e "\n✅ Test run complete!"

