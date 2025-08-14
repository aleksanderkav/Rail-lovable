#!/usr/bin/env python3
"""
Test script for Lovable integration endpoints in Rail-lovable.
Tests the exact specifications for /ingest, /admin/cards, and /admin/listings endpoints.
"""

import os
import asyncio
import httpx
from typing import Dict, Any, Optional
import json

# Configuration
BASE_URL = os.getenv("RAIL_LOVABLE_URL", "http://localhost:8000")
ADMIN_TOKEN = os.getenv("ADMIN_PROXY_TOKEN", "test-admin-token")

# Test data for ingest endpoint (exact format from specifications)
TEST_INGEST_DATA = {
    "query": "Charizard Base Set Unlimited PSA 9",
    "marketplace": "ebay",
    "items": [
        {
            "title": "Charizard Base Set Unlimited PSA 9 - Pokemon Card",
            "url": "https://www.ebay.com/itm/306444665735",
            "source_listing_id": "306444665735",
            "price": 450.0,
            "currency": "USD",
            "sold": False
        },
        {
            "title": "Charizard Base Set Unlimited PSA 9 - Mint Condition",
            "url": "https://www.ebay.com/itm/306444665736",
            "source_listing_id": "306444665736",
            "price": 500.0,
            "currency": "USD",
            "sold": True
        }
    ]
}

async def test_admin_cards():
    """Test GET /admin/cards endpoint"""
    print("🧪 Testing GET /admin/cards")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Admin-Token": ADMIN_TOKEN}
            
            # Test 1: Basic request with default limit
            response = await client.get(
                f"{BASE_URL}/admin/cards",
                headers=headers,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure
                    assert "cards" in data
                    assert "count" in data
                    assert "trace_id" in data
                    assert isinstance(data["cards"], list)
                    
                    print("✅ All validations passed!")
                    return data.get("cards", [])
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return []
            else:
                print(f"❌ Error response:")
                print(f"   Status: {response.status_code}")
                print(f"   Body: {response.text}")
                return []
                
    except httpx.TimeoutException:
        print("❌ Request timed out")
        return []
    except httpx.RequestError as e:
        print(f"❌ Request failed: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return []

async def test_admin_cards_with_search():
    """Test GET /admin/cards with search parameter"""
    print("\n🧪 Testing GET /admin/cards with search")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Admin-Token": ADMIN_TOKEN}
            
            # Test with search parameter
            response = await client.get(
                f"{BASE_URL}/admin/cards?search=Charizard&limit=5",
                headers=headers,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure
                    assert "cards" in data
                    assert "count" in data
                    assert "trace_id" in data
                    
                    print("✅ Search test passed!")
                    return True
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return False
            else:
                print(f"❌ Error response:")
                print(f"   Status: {response.status_code}")
                print(f"   Body: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_admin_cards_unauthorized():
    """Test GET /admin/cards without admin token"""
    print("\n🧪 Testing GET /admin/cards without admin token")
    
    try:
        async with httpx.AsyncClient() as client:
            # Test without admin token
            response = await client.get(
                f"{BASE_URL}/admin/cards",
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 401:
                try:
                    data = response.json()
                    print("✅ Success! Unauthorized response:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate error response structure
                    assert "error" in data
                    assert "trace_id" in data
                    assert data["error"] == "Unauthorized"
                    
                    print("✅ Unauthorized test passed!")
                    return True
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return False
            else:
                print(f"❌ Expected 401, got {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_ingest_dry_run():
    """Test POST /ingest with dryRun=true"""
    print("\n🧪 Testing POST /ingest with dryRun=true")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "X-Admin-Token": ADMIN_TOKEN,
                "Content-Type": "application/json"
            }
            
            response = await client.post(
                f"{BASE_URL}/ingest?dryRun=true",
                json=TEST_INGEST_DATA,
                headers=headers,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure (exact format from specifications)
                    assert "status" in data
                    assert "card_id" in data
                    assert "inserted" in data
                    assert "trace_id" in data
                    assert data["status"] == "success"
                    assert data["card_id"] == "dry-run-simulation"
                    assert data["inserted"] == 2
                    
                    print("✅ All validations passed!")
                    return True
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return False
            else:
                print(f"❌ Error response:")
                print(f"   Status: {response.status_code}")
                print(f"   Body: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_ingest_real():
    """Test POST /ingest without dryRun (actually persists data)"""
    print("\n🧪 Testing POST /ingest without dryRun (real ingestion)")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "X-Admin-Token": ADMIN_TOKEN,
                "Content-Type": "application/json"
            }
            
            response = await client.post(
                f"{BASE_URL}/ingest",
                json=TEST_INGEST_DATA,
                headers=headers,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure (exact format from specifications)
                    assert "status" in data
                    assert "card_id" in data
                    assert "inserted" in data
                    assert "trace_id" in data
                    assert data["status"] == "success"
                    assert data["card_id"] is not None
                    assert data["card_id"] != "dry-run-simulation"
                    assert data["inserted"] >= 0
                    
                    print("✅ All validations passed!")
                    return data.get("card_id")
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return None
            else:
                print(f"❌ Error response:")
                print(f"   Status: {response.status_code}")
                print(f"   Body: {response.text}")
                return None
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

async def test_ingest_unauthorized():
    """Test POST /ingest without admin token"""
    print("\n🧪 Testing POST /ingest without admin token")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"Content-Type": "application/json"}
            
            response = await client.post(
                f"{BASE_URL}/ingest",
                json=TEST_INGEST_DATA,
                headers=headers,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 401:
                try:
                    data = response.json()
                    print("✅ Success! Unauthorized response:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate error response structure
                    assert "error" in data
                    assert "trace_id" in data
                    assert data["error"] == "Unauthorized"
                    
                    print("✅ Unauthorized test passed!")
                    return True
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return False
            else:
                print(f"❌ Expected 401, got {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_admin_listings(card_id: str):
    """Test GET /admin/listings endpoint"""
    print(f"\n🧪 Testing GET /admin/listings with card_id: {card_id}")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Admin-Token": ADMIN_TOKEN}
            
            response = await client.get(
                f"{BASE_URL}/admin/listings?card_id={card_id}&limit=10",
                headers=headers,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure
                    assert "listings" in data
                    assert "count" in data
                    assert "trace_id" in data
                    assert isinstance(data["listings"], list)
                    
                    print("✅ All validations passed!")
                    return data.get("listings", [])
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return []
            else:
                print(f"❌ Error response:")
                print(f"   Status: {response.status_code}")
                print(f"   Body: {response.text}")
                return []
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return []

async def test_admin_listings_missing_card_id():
    """Test GET /admin/listings without card_id"""
    print("\n🧪 Testing GET /admin/listings without card_id")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Admin-Token": ADMIN_TOKEN}
            
            response = await client.get(
                f"{BASE_URL}/admin/listings",
                headers=headers,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 400:
                try:
                    data = response.json()
                    print("✅ Success! Bad request response:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate error response structure
                    assert "error" in data
                    assert "trace_id" in data
                    assert "card_id is required" in data["error"]
                    
                    print("✅ Missing card_id test passed!")
                    return True
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
                    return False
            else:
                print(f"❌ Expected 400, got {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_curl_commands():
    """Test the exact curl commands from specifications"""
    print("\n🧪 Testing exact curl commands from specifications")
    
    # Test 1: Admin cards
    print("\n📋 Test 1: curl -H \"X-Admin-Token: $ADMIN_PROXY_TOKEN\" \"https://<railway-url>/admin/cards?limit=5\"")
    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Admin-Token": ADMIN_TOKEN}
            response = await client.get(f"{BASE_URL}/admin/cards?limit=5", headers=headers, timeout=30.0)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success: {data.get('count', 0)} cards returned")
            else:
                print(f"   ❌ Failed: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Ingest
    print("\n📋 Test 2: curl -X POST \"https://<railway-url>/ingest\" -H \"X-Admin-Token: $ADMIN_PROXY_TOKEN\" -H \"Content-Type: application/json\" -d '{\"query\":\"Test\",\"marketplace\":\"ebay\",\"items\":[{\"title\":\"Item\",\"url\":\"https://example.com\",\"source_listing_id\":\"abc123\",\"price\":10,\"currency\":\"USD\"}]}'")
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "X-Admin-Token": ADMIN_TOKEN,
                "Content-Type": "application/json"
            }
            test_data = {
                "query": "Test",
                "marketplace": "ebay",
                "items": [{
                    "title": "Item",
                    "url": "https://example.com",
                    "source_listing_id": "abc123",
                    "price": 10,
                    "currency": "USD"
                }]
            }
            response = await client.post(f"{BASE_URL}/ingest", json=test_data, headers=headers, timeout=30.0)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success: card_id={data.get('card_id')}, inserted={data.get('inserted')}")
            else:
                print(f"   ❌ Failed: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

async def main():
    """Main test function"""
    print("🚀 Testing Lovable Integration Endpoints")
    print("=" * 60)
    
    print(f"🔧 Configuration:")
    print(f"   BASE_URL: {BASE_URL}")
    print(f"   ADMIN_TOKEN: {'✅ Set' if ADMIN_TOKEN != 'test-admin-token' else '❌ Using test token'}")
    
    # Test results tracking
    results = {}
    
    # Test 1: Admin cards (basic)
    results["admin_cards"] = await test_admin_cards()
    
    # Test 2: Admin cards with search
    results["admin_cards_search"] = await test_admin_cards_with_search()
    
    # Test 3: Admin cards unauthorized
    results["admin_cards_unauthorized"] = await test_admin_cards_unauthorized()
    
    # Test 4: Ingest dry run
    results["ingest_dry_run"] = await test_ingest_dry_run()
    
    # Test 5: Ingest real
    card_id = await test_ingest_real()
    results["ingest_real"] = card_id is not None
    
    # Test 6: Ingest unauthorized
    results["ingest_unauthorized"] = await test_ingest_unauthorized()
    
    # Test 7: Admin listings (if we have a card_id)
    if card_id:
        results["admin_listings"] = await test_admin_listings(card_id)
    else:
        results["admin_listings"] = False
    
    # Test 8: Admin listings missing card_id
    results["admin_listings_missing_card_id"] = await test_admin_listings_missing_card_id()
    
    # Test 9: Curl commands
    await test_curl_commands()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary:")
    print(f"   Admin Cards (Basic): {'✅ Passed' if results.get('admin_cards') else '❌ Failed'}")
    print(f"   Admin Cards (Search): {'✅ Passed' if results.get('admin_cards_search') else '❌ Failed'}")
    print(f"   Admin Cards (Unauthorized): {'✅ Passed' if results.get('admin_cards_unauthorized') else '❌ Failed'}")
    print(f"   Ingest (Dry Run): {'✅ Passed' if results.get('ingest_dry_run') else '❌ Failed'}")
    print(f"   Ingest (Real): {'✅ Passed' if results.get('ingest_real') else '❌ Failed'}")
    print(f"   Ingest (Unauthorized): {'✅ Passed' if results.get('ingest_unauthorized') else '❌ Failed'}")
    print(f"   Admin Listings: {'✅ Passed' if results.get('admin_listings') else '❌ Failed'}")
    print(f"   Admin Listings (Missing card_id): {'✅ Passed' if results.get('admin_listings_missing_card_id') else '❌ Failed'}")
    
    if card_id:
        print(f"   Created Card ID: {card_id}")
    
    # Acceptance criteria check
    print("\n🎯 Acceptance Criteria Check:")
    print(f"   ✅ /admin/cards returns filtered, paginated cards: {'PASS' if results.get('admin_cards') else 'FAIL'}")
    print(f"   ✅ /admin/listings returns listings for a specific card: {'PASS' if results.get('admin_listings') else 'FAIL'}")
    print(f"   ✅ /ingest saves cards + listings to Supabase and returns card_id: {'PASS' if results.get('ingest_real') else 'FAIL'}")
    print(f"   ✅ All routes secured with X-Admin-Token: {'PASS' if results.get('admin_cards_unauthorized') and results.get('ingest_unauthorized') else 'FAIL'}")
    print(f"   ✅ Dry run mode works for testing without writing: {'PASS' if results.get('ingest_dry_run') else 'FAIL'}")
    
    print("\n✅ Testing complete!")

if __name__ == "__main__":
    asyncio.run(main())
