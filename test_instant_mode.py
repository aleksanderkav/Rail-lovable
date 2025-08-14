#!/usr/bin/env python3
"""
Comprehensive test script for /scrape-now?instant=true endpoint
Tests all aspects of the instant mode functionality
"""

import asyncio
import json
import sys
import time
from typing import Dict, Any

# Test configuration
BASE_URL = "https://rail-lovable-production.up.railway.app"
TEST_QUERIES = [
    "Gengar Fossil 1st Edition PSA 10",
    "Charizard Shining Neo Destiny PSA 9",
    "Typhlosion Neo Genesis 17/111 PSA 10"
]

async def test_instant_mode(query: str) -> Dict[str, Any]:
    """Test instant mode for a specific query"""
    import httpx
    
    print(f"\n🧪 Testing instant mode with query: '{query}'")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Instant mode via query parameter
        print(f"📝 Test 1: Query parameter instant=true")
        try:
            response = await client.post(
                f"{BASE_URL}/scrape-now?instant=true",
                headers={
                    "Origin": "https://card-pulse-watch.lovable.app",
                    "Content-Type": "application/json"
                },
                json={"query": query}
            )
            
            print(f"   Status: {response.status_code}")
            print(f"   Trace ID: {response.headers.get('x-trace-id', 'N/A')}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success: {data.get('ok')}")
                print(f"   Items: {len(data.get('items', []))}")
                print(f"   Skipped: {data.get('skipped', {})}")
                
                # Validate response structure
                if data.get('ok'):
                    items = data.get('items', [])
                    if items:
                        first_item = items[0]
                        has_url = bool(first_item.get('url'))
                        has_id = bool(first_item.get('source_listing_id'))
                        print(f"   First item - URL: {has_url}, ID: {has_id}")
                        if has_url and has_id:
                            print(f"   ✅ Valid item structure")
                        else:
                            print(f"   ❌ Invalid item structure")
                    else:
                        print(f"   ⚠️  No items returned")
                else:
                    print(f"   ❌ Request failed: {data.get('detail')}")
                    
            else:
                print(f"   ❌ HTTP Error: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
        
        # Test 2: Instant mode via header
        print(f"\n📝 Test 2: Header X-Instant: true")
        try:
            response = await client.post(
                f"{BASE_URL}/scrape-now",
                headers={
                    "Origin": "https://card-pulse-watch.lovable.app",
                    "Content-Type": "application/json",
                    "X-Instant": "true"
                },
                json={"query": query}
            )
            
            print(f"   Status: {response.status_code}")
            print(f"   Trace ID: {response.headers.get('x-trace-id', 'N/A')}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success: {data.get('ok')}")
                print(f"   Items: {len(data.get('items', []))}")
                print(f"   Skipped: {data.get('skipped', {})}")
            else:
                print(f"   ❌ HTTP Error: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
        
        # Test 3: CORS preflight
        print(f"\n📝 Test 3: CORS preflight")
        try:
            response = await client.options(
                f"{BASE_URL}/scrape-now",
                headers={
                    "Origin": "https://card-pulse-watch.lovable.app",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type"
                }
            )
            
            print(f"   Status: {response.status_code}")
            print(f"   CORS Headers: {dict(response.headers)}")
            
        except Exception as e:
            print(f"   ❌ Exception: {e}")
    
    return {"query": query, "status": "completed"}

async def test_debug_endpoint(query: str) -> Dict[str, Any]:
    """Test the debug endpoint for comparison"""
    import httpx
    
    print(f"\n🔍 Testing debug endpoint with query: '{query}'")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/debug/scrape-ebay",
                params={"q": query}
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success: {data.get('ok')}")
                print(f"   Items: {len(data.get('items', []))}")
                
                if data.get('items'):
                    first_item = data['items'][0]
                    has_url = bool(first_item.get('url'))
                    has_id = bool(first_item.get('source_listing_id'))
                    print(f"   First item - URL: {has_url}, ID: {has_id}")
                    
            else:
                print(f"   ❌ HTTP Error: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
    
    return {"query": query, "status": "completed"}

async def main():
    """Run all tests"""
    print("🚀 Starting comprehensive instant mode testing")
    print(f"📍 Base URL: {BASE_URL}")
    print(f"⏰ Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    for query in TEST_QUERIES:
        # Test instant mode
        result1 = await test_instant_mode(query)
        results.append(result1)
        
        # Test debug endpoint for comparison
        result2 = await test_debug_endpoint(query)
        results.append(result2)
        
        # Small delay between tests
        await asyncio.sleep(2)
    
    print(f"\n🎯 Testing completed!")
    print(f"⏰ End time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Total tests: {len(results)}")
    
    return results

if __name__ == "__main__":
    try:
        results = asyncio.run(main())
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n⏹️  Testing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        sys.exit(1)

