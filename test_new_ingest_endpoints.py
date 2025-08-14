#!/usr/bin/env python3
"""
Test script for the new ingest and admin endpoints in Rail-lovable.
Tests the /ingest, /admin/cards, and /admin/listings endpoints.
"""

import os
import asyncio
import httpx
from typing import Dict, Any, Optional
import json

# Configuration
BASE_URL = os.getenv("RAIL_LOVABLE_URL", "http://localhost:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "test-admin-token")

# Test data for ingest endpoint
TEST_INGEST_DATA = {
    "query": "Gengar Fossil 1st Edition PSA 10",
    "marketplace": "ebay",
    "items": [
        {
            "title": "Gengar Fossil 1st Edition PSA 10 - Pokemon Card",
            "url": "https://www.ebay.com/itm/306444665735",
            "source_listing_id": "306444665735",
            "price": 1400.0,
            "currency": "USD",
            "sold": False,
            "ended_at": None
        },
        {
            "title": "Gengar Fossil 1st Edition PSA 10 - Mint Condition",
            "url": "https://www.ebay.com/itm/306444665736",
            "source_listing_id": "306444665736",
            "price": 1500.0,
            "currency": "USD",
            "sold": True,
            "ended_at": "2025-01-15T00:00:00Z"
        }
    ]
}

async def test_ingest_dry_run():
    """Test the /ingest endpoint with dryRun=true"""
    print("🧪 Testing /ingest with dryRun=true")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/ingest?dryRun=true",
                json=TEST_INGEST_DATA,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure
                    assert data.get("ok") == True
                    assert "ingestSummary" in data
                    assert data["ingestSummary"]["total"] == 2
                    assert data["ingestSummary"]["accepted"] == 2
                    assert data["ingestSummary"]["skipped"] == 0
                    assert data.get("card_id") == "dry-run-simulation"
                    assert "trace" in data
                    
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
                
    except httpx.TimeoutException:
        print("❌ Request timed out")
        return False
    except httpx.RequestError as e:
        print(f"❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_ingest_real():
    """Test the /ingest endpoint without dryRun (actually persists data)"""
    print("\n🧪 Testing /ingest without dryRun (real ingestion)")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/ingest",
                json=TEST_INGEST_DATA,
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure
                    assert data.get("ok") == True
                    assert "ingestSummary" in data
                    assert data["ingestSummary"]["total"] == 2
                    assert data["ingestSummary"]["accepted"] == 2
                    assert data["ingestSummary"]["skipped"] == 0
                    assert data.get("card_id") is not None
                    assert data.get("card_id") != "dry-run-simulation"
                    assert "trace" in data
                    
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
                
    except httpx.TimeoutException:
        print("❌ Request timed out")
        return None
    except httpx.RequestError as e:
        print(f"❌ Request failed: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

async def test_admin_cards():
    """Test the /admin/cards endpoint"""
    print("\n🧪 Testing /admin/cards")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Admin-Token": ADMIN_TOKEN}
            response = await client.get(
                f"{BASE_URL}/admin/cards?limit=10",
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
                    assert data.get("ok") == True
                    assert "cards" in data
                    assert "count" in data
                    assert "trace" in data
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

async def test_admin_listings(card_id: str = None):
    """Test the /admin/listings endpoint"""
    print(f"\n🧪 Testing /admin/listings (card_id: {card_id})")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"X-Admin-Token": ADMIN_TOKEN}
            url = f"{BASE_URL}/admin/listings?limit=10"
            if card_id:
                url += f"&card_id={card_id}"
            
            response = await client.get(url, headers=headers, timeout=30.0)
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure
                    assert data.get("ok") == True
                    assert "listings" in data
                    assert "count" in data
                    assert "trace" in data
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
                
    except httpx.TimeoutException:
        print("❌ Request timed out")
        return []
    except httpx.RequestError as e:
        print(f"❌ Request failed: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return []

async def test_instant_ingest():
    """Test the instant ingest functionality in /scrape-now"""
    print("\n🧪 Testing instant ingest in /scrape-now")
    
    try:
        async with httpx.AsyncClient() as client:
            # Test with instant=true and ingest=true
            scrape_data = {
                "query": "Charizard Base Set Unlimited PSA 9",
                "instant": True,
                "ingest": True
            }
            
            response = await client.post(
                f"{BASE_URL}/scrape-now",
                json=scrape_data,
                timeout=60.0  # Longer timeout for scraping
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Check if instantIngest is present
                    if "instantIngest" in data:
                        instant_data = data["instantIngest"]
                        print(f"✅ Instant ingest data found: {instant_data}")
                        
                        if instant_data.get("ok"):
                            print(f"✅ Instant ingest successful: {instant_data.get('ingestSummary')}")
                        else:
                            print(f"⚠️  Instant ingest failed: {instant_data.get('error')}")
                    else:
                        print("⚠️  No instantIngest data in response")
                    
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
                
    except httpx.TimeoutException:
        print("❌ Request timed out")
        return False
    except httpx.RequestError as e:
        print(f"❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def main():
    """Main test function"""
    print("🚀 Testing new Rail-lovable endpoints")
    print("=" * 50)
    
    print(f"🔧 Configuration:")
    print(f"   BASE_URL: {BASE_URL}")
    print(f"   ADMIN_TOKEN: {'✅ Set' if ADMIN_TOKEN != 'test-admin-token' else '❌ Using test token'}")
    
    # Test 1: Dry run ingest
    dry_run_success = await test_ingest_dry_run()
    
    # Test 2: Real ingest
    card_id = None
    if dry_run_success:
        card_id = await test_ingest_real()
    
    # Test 3: Admin cards
    cards = await test_admin_cards()
    
    # Test 4: Admin listings (with card_id if available)
    if card_id:
        listings = await test_admin_listings(card_id)
    else:
        listings = await test_admin_listings()
    
    # Test 5: Instant ingest
    instant_success = await test_instant_ingest()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    print(f"   Dry Run Ingest: {'✅ Passed' if dry_run_success else '❌ Failed'}")
    print(f"   Real Ingest: {'✅ Passed' if card_id else '❌ Failed'}")
    print(f"   Admin Cards: {'✅ Passed' if cards else '❌ Failed'}")
    print(f"   Admin Listings: {'✅ Passed' if listings else '❌ Failed'}")
    print(f"   Instant Ingest: {'✅ Passed' if instant_success else '❌ Failed'}")
    
    if card_id:
        print(f"   Created Card ID: {card_id}")
    
    print("\n✅ Testing complete!")

if __name__ == "__main__":
    asyncio.run(main())
