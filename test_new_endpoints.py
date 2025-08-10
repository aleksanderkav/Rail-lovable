#!/usr/bin/env python3
"""
Test script for the new normalization and ingestion endpoints.
This will help verify the new functionality works correctly.
"""

import os
import json
import httpx
import asyncio
from datetime import datetime

# Test configuration
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")

# Test items
TEST_ITEMS = [
    {
        "title": "Charizard Base Set Unlimited Holo PSA 9",
        "price": 450.00,
        "currency": "USD",
        "source": "ebay",
        "url": "https://ebay.com/itm/charizard-psa9"
    },
    {
        "title": "Blastoise Base Set 1st Edition PSA 10",
        "price": 1200.00,
        "currency": "USD",
        "source": "ebay",
        "url": "https://ebay.com/itm/blastoise-1st-psa10"
    }
]

async def test_health_endpoint():
    """Test the updated health endpoint"""
    print("🏥 Testing /health endpoint...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BASE_URL}/health")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check passed")
            print(f"   Time: {data.get('time')}")
            print(f"   Endpoints: {data.get('endpoints', [])}")
            print(f"   Env: {data.get('env', {})}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

async def test_normalize_with_items():
    """Test normalization with provided items"""
    print("\n🧪 Testing /normalize-test with items...")
    
    payload = {
        "items": TEST_ITEMS
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{BASE_URL}/normalize-test",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Normalization with items passed")
            print(f"   Source: {data.get('source')}")
            print(f"   Count: {data.get('count')}")
            print(f"   Trace: {data.get('trace')}")
            
            # Show first item details
            if data.get('items'):
                first_item = data['items'][0]
                print(f"   First item canonical_key: {first_item.get('canonical_key')}")
                print(f"   Confidence: {first_item.get('confidence')}")
            
            return True
        else:
            print(f"❌ Normalization with items failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

async def test_normalize_with_query():
    """Test normalization with query (scrapes and normalizes)"""
    print("\n🔍 Testing /normalize-test with query...")
    
    payload = {
        "query": "Pikachu Base Set Unlimited",
        "limit": 3
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:  # Longer timeout for scraping
        response = await client.post(
            f"{BASE_URL}/normalize-test",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Normalization with query passed")
            print(f"   Source: {data.get('source')}")
            print(f"   Count: {data.get('count')}")
            print(f"   Trace: {data.get('trace')}")
            
            # Show first item details
            if data.get('items'):
                first_item = data['items'][0]
                print(f"   First item canonical_key: {first_item.get('canonical_key')}")
                print(f"   Confidence: {first_item.get('confidence')}")
            
            return True
        else:
            print(f"❌ Normalization with query failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

async def test_ingest_dry_run():
    """Test ingestion with dry_run=true (safe)"""
    print("\n🔄 Testing /ingest-items with dry_run=true...")
    
    # Use normalized items from previous test
    normalized_items = [
        {
            "title": "Charizard Base Set Unlimited Holo PSA 9",
            "price": 450.00,
            "currency": "USD",
            "source": "ebay",
            "canonical_key": "pokemon|base_set|charizard|unlimited|unknown_number|unknown_year|psa|9"
        }
    ]
    
    payload = {
        "raw_query": "Charizard Base Set Unlimited PSA 9",
        "items": normalized_items,
        "dry_run": True
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{BASE_URL}/ingest-items",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Ingestion dry_run passed")
            print(f"   External OK: {data.get('externalOk')}")
            print(f"   Count: {data.get('count')}")
            print(f"   Trace: {data.get('trace')}")
            
            # Show first item result
            if data.get('items'):
                first_item = data['items'][0]
                print(f"   First item decision: {first_item.get('decision')}")
                print(f"   Canonical key: {first_item.get('canonical_key')}")
            
            return True
        else:
            print(f"❌ Ingestion dry_run failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

async def test_cors_preflight():
    """Test CORS preflight requests"""
    print("\n🌐 Testing CORS preflight requests...")
    
    endpoints = ["/normalize-test", "/ingest-items"]
    cors_ok = True
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for endpoint in endpoints:
            response = await client.options(f"{BASE_URL}{endpoint}")
            
            if response.status_code == 200:
                print(f"✅ CORS preflight for {endpoint} passed")
            else:
                print(f"❌ CORS preflight for {endpoint} failed: {response.status_code}")
                cors_ok = False
    
    return cors_ok

async def main():
    """Run all tests"""
    print("🧪 Testing New Endpoints")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print()
    
    tests = [
        ("Health Endpoint", test_health_endpoint),
        ("CORS Preflight", test_cors_preflight),
        ("Normalize with Items", test_normalize_with_items),
        ("Normalize with Query", test_normalize_with_query),
        ("Ingest Dry Run", test_ingest_dry_run),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main()) 