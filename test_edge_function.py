#!/usr/bin/env python3
"""
Test script to call Supabase Edge Function ai-parser with a single normalized item.
This will help verify the EF integration and response format.
"""

import os
import json
import httpx
import asyncio
from datetime import datetime, timezone

# Test item with all required fields
TEST_ITEM = {
    "raw_query": "Pikachu Base Set 1st Edition PSA 10",
    "title": "Pikachu Base Set 1st Edition PSA 10 - Pokemon Card",
    "price": 1500.00,
    "currency": "USD",
    "url": "https://www.ebay.com/itm/123456789",
    "ended_at": "2025-08-08T16:30:00Z",
    "source": "ebay",
    "source_listing_id": "ebay_123456789",
    # New canonicalized fields from Lovable
    "canonical_key": "pikachu_base_set_1st_edition_psa_10",
    "rarity": "Common",
    "grading_company": "PSA",
    "grade": "10",
    "tags": ["holo", "1st edition", "base set"],
    "sold": True,
    # Normalized fields
    "set": "Base Set",
    "edition": "1st Edition",
    "year": 1999,
    "language": "English",
    "grader": "PSA",
    "grade_value": 10,
    # Additional enriched fields
    "image_url": "https://example.com/pikachu.jpg",
    "shipping_price": 5.99,
    "total_price": 1505.99,
    "bids": 12,
    "condition": "Mint"
}

async def test_edge_function():
    """Test the Supabase Edge Function ai-parser with a single item"""
    
    # Get environment variables
    ef_url = os.getenv("SUPABASE_FUNCTION_URL")
    ef_token = os.getenv("SUPABASE_FUNCTION_TOKEN")
    
    if not ef_url or ef_url == "<your-supabase-edge-function-url>":
        print("❌ ERROR: SUPABASE_FUNCTION_URL not set or is placeholder")
        print("Please set SUPABASE_FUNCTION_URL in your environment")
        print("\n🔧 To set up the Edge Function:")
        print("1. Go to your Supabase project dashboard")
        print("2. Navigate to Edge Functions")
        print("3. Create a new Edge Function called 'ai-parser'")
        print("4. Copy the function URL (e.g., https://your-project.supabase.co/functions/v1/ai-parser)")
        print("5. Set SUPABASE_FUNCTION_URL environment variable")
        return
    
    if not ef_token or ef_token == "<anon-or-service-role-key>":
        print("❌ ERROR: SUPABASE_FUNCTION_TOKEN not set or is placeholder")
        print("Please set SUPABASE_FUNCTION_TOKEN in your environment")
        print("\n🔧 To get the token:")
        print("1. Go to your Supabase project dashboard")
        print("2. Navigate to Settings → API")
        print("3. Copy either the 'anon' key or 'service_role' key")
        print("4. Set SUPABASE_FUNCTION_TOKEN environment variable")
        return
    
    print(f"🚀 Testing Edge Function: {ef_url}")
    print(f"🔑 Token: {ef_token[:10]}...{ef_token[-10:] if len(ef_token) > 20 else 'short'}")
    print(f"📦 Test item: {TEST_ITEM['title']}")
    print("-" * 80)
    
    # Prepare the payload
    payload = {
        "items": [TEST_ITEM]
    }
    
    headers = {
        "Authorization": f"Bearer {ef_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        # Make the HTTP call
        print(f"📤 Sending POST request to Edge Function...")
        start_time = datetime.now()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ef_url,
                headers=headers,
                json=payload
            )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Log the full HTTP exchange
        print(f"⏱️  Request duration: {duration:.2f}s")
        print(f"📊 Response status: {response.status_code}")
        print(f"📋 Response headers:")
        for key, value in response.headers.items():
            print(f"   {key}: {value}")
        
        print(f"\n📄 Response body (first 300 chars):")
        response_text = response.text
        print(f"   {response_text[:300]}{'...' if len(response_text) > 300 else ''}")
        
        # Try to parse JSON response
        try:
            response_json = response.json()
            print(f"\n✅ Parsed JSON response:")
            print(json.dumps(response_json, indent=2))
            
            # Check for expected fields
            print(f"\n🔍 Checking for expected fields in response:")
            
            # Check if response has items
            if "items" in response_json and isinstance(response_json["items"], list) and len(response_json["items"]) > 0:
                first_item = response_json["items"][0]
                
                # Core database IDs
                card_id = first_item.get("card_id")
                listing_id = first_item.get("listing_id") 
                price_entry_id = first_item.get("price_entry_id")
                
                print(f"   card_id: {'✅ Present' if card_id else '❌ Missing'} - {card_id}")
                print(f"   listing_id: {'✅ Present' if listing_id else '❌ Missing'} - {listing_id}")
                print(f"   price_entry_id: {'✅ Present' if price_entry_id else '❌ Missing'} - {price_entry_id}")
                
                # Check for new canonicalized fields
                canonical_key = first_item.get("canonical_key")
                rarity = first_item.get("rarity")
                grading_company = first_item.get("grading_company")
                grade = first_item.get("grade")
                tags = first_item.get("tags")
                sold = first_item.get("sold")
                
                print(f"\n🔍 Checking for new canonicalized fields:")
                print(f"   canonical_key: {'✅ Present' if canonical_key else '❌ Missing'} - {canonical_key}")
                print(f"   rarity: {'✅ Present' if rarity else '❌ Missing'} - {rarity}")
                print(f"   grading_company: {'✅ Present' if grading_company else '❌ Missing'} - {grading_company}")
                print(f"   grade: {'✅ Present' if grade else '❌ Missing'} - {grade}")
                print(f"   tags: {'✅ Present' if tags else '❌ Missing'} - {tags}")
                print(f"   sold: {'✅ Present' if sold is not None else '❌ Missing'} - {sold}")
                
                # Check for normalized fields
                set_name = first_item.get("set")
                edition = first_item.get("edition")
                year = first_item.get("year")
                language = first_item.get("language")
                grader = first_item.get("grader")
                grade_value = first_item.get("grade_value")
                
                print(f"\n🔍 Checking for normalized fields:")
                print(f"   set: {'✅ Present' if set_name else '❌ Missing'} - {set_name}")
                print(f"   edition: {'✅ Present' if edition else '❌ Missing'} - {edition}")
                print(f"   year: {'✅ Present' if year else '❌ Missing'} - {year}")
                print(f"   language: {'✅ Present' if language else '❌ Missing'} - {language}")
                print(f"   grader: {'✅ Present' if grader else '❌ Missing'} - {grader}")
                print(f"   grade_value: {'✅ Present' if grade_value else '❌ Missing'} - {grade_value}")
                
                # Log all fields in the first item
                print(f"\n📋 All fields in first item:")
                for key, value in first_item.items():
                    print(f"   {key}: {value}")
            else:
                print("   ❌ No items array found in response")
                
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON response: {e}")
            print(f"   Raw response: {response_text}")
            
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e.response.status_code}")
        print(f"   Response text: {e.response.text}")
        print(f"   Headers: {dict(e.response.headers)}")
        
    except httpx.RequestError as e:
        print(f"❌ Request Error: {e}")
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

def show_mock_test():
    """Show what the test would look like with mock data"""
    print("🧪 MOCK TEST MODE - Edge Function Integration Test")
    print("=" * 80)
    
    print("📤 What we would send to the Edge Function:")
    payload = {
        "items": [TEST_ITEM]
    }
    print(json.dumps(payload, indent=2))
    
    print(f"\n📋 Test item includes all required fields:")
    for key, value in TEST_ITEM.items():
        print(f"   ✅ {key}: {value}")
    
    print(f"\n🎯 Expected Edge Function response should include:")
    print(f"   ✅ card_id: UUID of the card in your database")
    print(f"   ✅ listing_id: UUID of the listing record")
    print(f"   ✅ price_entry_id: UUID of the price entry")
    print(f"   ✅ All original fields from the request")
    print(f"   ✅ New canonicalized fields (canonical_key, rarity, grading_company, grade, tags, sold)")
    print(f"   ✅ Normalized fields (set, edition, year, language, grader, grade_value)")
    
    print(f"\n🔧 To run the real test:")
    print(f"1. Set SUPABASE_FUNCTION_URL environment variable")
    print(f"2. Set SUPABASE_FUNCTION_TOKEN environment variable")
    print(f"3. Run: python test_edge_function.py")
    
    print(f"\n📝 Example .env file:")
    print(f"SUPABASE_FUNCTION_URL=https://your-project.supabase.co/functions/v1/ai-parser")
    print(f"SUPABASE_FUNCTION_TOKEN=your-anon-or-service-role-key")
    
    print(f"\n🚀 After Lovable's migration, the system will:")
    print(f"   • Send canonicalized and enriched card data")
    print(f"   • Include fuzzy matching via card_embeddings with cosine search")
    print(f"   • Handle deduplication and merging of near-duplicate cards")
    print(f"   • Provide consistent normalized fields across all sources")

if __name__ == "__main__":
    print("🧪 Testing Supabase Edge Function ai-parser")
    print("=" * 80)
    
    # Check environment
    print("🔍 Environment check:")
    print(f"   SUPABASE_FUNCTION_URL: {'✅ Set' if os.getenv('SUPABASE_FUNCTION_URL') else '❌ Not set'}")
    print(f"   SUPABASE_FUNCTION_TOKEN: {'✅ Set' if os.getenv('SUPABASE_FUNCTION_TOKEN') else '❌ Not set'}")
    print()
    
    # Check if we have real environment variables
    ef_url = os.getenv("SUPABASE_FUNCTION_URL")
    ef_token = os.getenv("SUPABASE_FUNCTION_TOKEN")
    
    if ef_url and ef_url != "<your-supabase-edge-function-url>" and ef_token and ef_token != "<anon-or-service-role-key>":
        # Run the real test
        asyncio.run(test_edge_function())
    else:
        # Show mock test
        show_mock_test()
    
    print("\n" + "=" * 80)
    print("✅ Test complete!") 