#!/usr/bin/env python3
"""
Test script for Supabase Edge Function integration with AI-driven canonical matching.
Tests the new structure that supports AI enrichment and canonicalization.
"""

import os
import asyncio
import httpx
from typing import Dict, Any, Optional
import json

# Configuration
SUPABASE_FUNCTION_URL = os.getenv("SUPABASE_FUNCTION_URL")
SUPABASE_FUNCTION_TOKEN = os.getenv("SUPABASE_FUNCTION_TOKEN")

# Test data with new AI-driven structure
TEST_ITEM = {
    # Raw listing details (for AI extraction)
    "raw_title": "Pikachu Base Set 1st Edition PSA 10 - Pokemon Card",
    "raw_description": "Rare Pikachu card from the original Base Set, 1st Edition, professionally graded PSA 10. Mint condition with perfect centering.",
    "source": "ebay",
    "source_listing_id": "ebay_123456789",
    "url": "https://www.ebay.com/itm/123456789",
    
    # Pricing and availability
    "currency": "USD",
    "price": 1500.00,
    "ended_at": "2025-08-08T16:30:00Z",
    
    # Media
    "images": [
        "https://example.com/pikachu_front.jpg",
        "https://example.com/pikachu_back.jpg"
    ],
    
    # Initial parsed fields (if easily extractable during scraping)
    "franchise": "Pokemon",
    "set_name": "Base Set",
    "edition": "1st Edition",
    "number": "58",
    "year": 1999,
    "language": "English",
    "grading_company": "PSA",
    "grade": "10",
    "rarity": "Common",
    "is_holo": True,
    
    # Tags (pre-filled if certain)
    "tags": ["PSA 10", "1st Edition", "Base Set", "Holo", "Common"],
    
    # Metadata for enrichment
    "raw_query": "Pikachu Base Set 1st Edition PSA 10",
    "category_guess": "Trading Cards > Pokemon > Base Set",
    
    # Legacy fields for backward compatibility
    "title": "Pikachu Base Set 1st Edition PSA 10 - Pokemon Card",
    "id": "ebay_123456789",
    "sold": True,
    "image_url": "https://example.com/pikachu_front.jpg",
    "shipping_price": 5.99,
    "total_price": 1505.99,
    "bids": 12,
    "condition": "Mint",
    "canonical_key": "pikachu_base_set_1st_edition_psa_10",
    "set": "Base Set",
    "edition": "1st Edition",
    "year": 1999,
    "language": "English",
    "grader": "PSA",
    "grade_value": 10
}

async def test_edge_function():
    """Test the Edge Function with the new AI-driven structure"""
    
    if not SUPABASE_FUNCTION_URL:
        print("❌ SUPABASE_FUNCTION_URL not set - running in mock mode")
        print("\n🔍 Mock test output:")
        print("   This would send the following data to the Edge Function:")
        print(f"   raw_title: {TEST_ITEM['raw_title']}")
        print(f"   raw_description: {TEST_ITEM['raw_description']}")
        print(f"   source: {TEST_ITEM['source']}")
        print(f"   source_listing_id: {TEST_ITEM['source_listing_id']}")
        print(f"   franchise: {TEST_ITEM['franchise']}")
        print(f"   set_name: {TEST_ITEM['set_name']}")
        print(f"   edition: {TEST_ITEM['edition']}")
        print(f"   number: {TEST_ITEM['number']}")
        print(f"   year: {TEST_ITEM['year']}")
        print(f"   grading_company: {TEST_ITEM['grading_company']}")
        print(f"   grade: {TEST_ITEM['grade']}")
        print(f"   rarity: {TEST_ITEM['rarity']}")
        print(f"   is_holo: {TEST_ITEM['is_holo']}")
        print(f"   tags: {TEST_ITEM['tags']}")
        print(f"   raw_query: {TEST_ITEM['raw_query']}")
        print(f"   category_guess: {TEST_ITEM['category_guess']}")
        print("\n✅ Mock test complete!")
        return
    
    if not SUPABASE_FUNCTION_TOKEN:
        print("❌ SUPABASE_FUNCTION_TOKEN not set")
        return
    
    print(f"🚀 Testing Edge Function at: {SUPABASE_FUNCTION_URL}")
    
    try:
        async with httpx.AsyncClient() as client:
            # Send test data
            response = await client.post(
                SUPABASE_FUNCTION_URL,
                json={"items": [TEST_ITEM]},
                headers={"Authorization": f"Bearer {SUPABASE_FUNCTION_TOKEN}"},
                timeout=30.0
            )
            
            print(f"📡 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print("✅ Success! Response data:")
                    print(json.dumps(data, indent=2))
                    
                    # Validate response structure
                    await validate_response(data)
                    
                except json.JSONDecodeError:
                    print("⚠️  Response is not valid JSON:")
                    print(response.text)
            else:
                print(f"❌ Error response:")
                print(f"   Status: {response.status_code}")
                print(f"   Body: {response.text}")
                
    except httpx.TimeoutException:
        print("❌ Request timed out")
    except httpx.RequestError as e:
        print(f"❌ Request failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

async def validate_response(data: Dict[str, Any]):
    """Validate the Edge Function response structure"""
    print("\n🔍 Validating response structure...")
    
    # Check for success indicator
    if "success" in data:
        print(f"   success: {'✅ Present' if data['success'] else '❌ False'} - {data['success']}")
    
    # Check for items array
    if "items" in data and isinstance(data["items"], list):
        items = data["items"]
        print(f"   items: ✅ Present - {len(items)} items")
        
        if items:
            first_item = items[0]
            await validate_item_structure(first_item)
    else:
        print("   items: ❌ Missing or not an array")
    
    # Check for other common fields
    for field in ["card_id", "listing_id", "price_entry_id", "message"]:
        if field in data:
            print(f"   {field}: ✅ Present - {data[field]}")

async def validate_item_structure(item: Dict[str, Any]):
    """Validate individual item structure"""
    print(f"\n🔍 Validating first item structure:")
    
    # Core database IDs
    card_id = item.get("card_id")
    listing_id = item.get("listing_id") 
    price_entry_id = item.get("price_entry_id")
    
    print(f"   card_id: {'✅ Present' if card_id else '❌ Missing'} - {card_id}")
    print(f"   listing_id: {'✅ Present' if listing_id else '❌ Missing'} - {listing_id}")
    print(f"   price_entry_id: {'✅ Present' if price_entry_id else '❌ Missing'} - {price_entry_id}")
    
    # Check for raw listing details
    raw_title = item.get("raw_title")
    raw_description = item.get("raw_description")
    source = item.get("source")
    source_listing_id = item.get("source_listing_id")
    url = item.get("url")
    
    print(f"\n🔍 Checking raw listing details:")
    print(f"   raw_title: {'✅ Present' if raw_title else '❌ Missing'} - {raw_title}")
    print(f"   raw_description: {'✅ Present' if raw_description else '❌ Missing'} - {raw_description}")
    print(f"   source: {'✅ Present' if source else '❌ Missing'} - {source}")
    print(f"   source_listing_id: {'✅ Present' if source_listing_id else '❌ Missing'} - {source_listing_id}")
    print(f"   url: {'✅ Present' if url else '❌ Missing'} - {url}")
    
    # Check for initial parsed fields
    franchise = item.get("franchise")
    set_name = item.get("set_name")
    edition = item.get("edition")
    number = item.get("number")
    year = item.get("year")
    language = item.get("language")
    grading_company = item.get("grading_company")
    grade = item.get("grade")
    rarity = item.get("rarity")
    is_holo = item.get("is_holo")
    
    print(f"\n🔍 Checking initial parsed fields:")
    print(f"   franchise: {'✅ Present' if franchise else '❌ Missing'} - {franchise}")
    print(f"   set_name: {'✅ Present' if set_name else '❌ Missing'} - {set_name}")
    print(f"   edition: {'✅ Present' if edition else '❌ Missing'} - {edition}")
    print(f"   number: {'✅ Present' if number else '❌ Missing'} - {number}")
    print(f"   year: {'✅ Present' if year else '❌ Missing'} - {year}")
    print(f"   language: {'✅ Present' if language else '❌ Missing'} - {language}")
    print(f"   grading_company: {'✅ Present' if grading_company else '❌ Missing'} - {grading_company}")
    print(f"   grade: {'✅ Present' if grade else '❌ Missing'} - {grade}")
    print(f"   rarity: {'✅ Present' if rarity else '❌ Missing'} - {rarity}")
    print(f"   is_holo: {'✅ Present' if is_holo is not None else '❌ Missing'} - {is_holo}")
    
    # Check for tags and metadata
    tags = item.get("tags")
    raw_query = item.get("raw_query")
    category_guess = item.get("category_guess")
    
    print(f"\n🔍 Checking tags and metadata:")
    print(f"   tags: {'✅ Present' if tags else '❌ Missing'} - {tags}")
    print(f"   raw_query: {'✅ Present' if raw_query else '❌ Missing'} - {raw_query}")
    print(f"   category_guess: {'✅ Present' if category_guess else '❌ Missing'} - {category_guess}")
    
    # Check for pricing and media
    price = item.get("price")
    currency = item.get("currency")
    ended_at = item.get("ended_at")
    images = item.get("images")
    
    print(f"\n🔍 Checking pricing and media:")
    print(f"   price: {'✅ Present' if price else '❌ Missing'} - {price}")
    print(f"   currency: {'✅ Present' if currency else '❌ Missing'} - {currency}")
    print(f"   ended_at: {'✅ Present' if ended_at else '❌ Missing'} - {ended_at}")
    print(f"   images: {'✅ Present' if images else '❌ Missing'} - {images}")
    
    # Check for legacy fields (backward compatibility)
    title = item.get("title")
    sold = item.get("sold")
    canonical_key = item.get("canonical_key")
    
    print(f"\n🔍 Checking legacy fields (backward compatibility):")
    print(f"   title: {'✅ Present' if title else '❌ Missing'} - {title}")
    print(f"   sold: {'✅ Present' if sold is not None else '❌ Missing'} - {sold}")
    print(f"   canonical_key: {'✅ Present' if canonical_key else '❌ Missing'} - {canonical_key}")

def print_migration_benefits():
    """Print information about the AI-driven migration benefits"""
    print("\n" + "="*80)
    print("🚀 AI-DRIVEN CANONICAL MATCHING & ENRICHMENT MIGRATION")
    print("="*80)
    print("\n📋 What's New:")
    print("   • Raw listing details preserved for AI extraction")
    print("   • Initial parsed fields for immediate categorization")
    print("   • Pre-filled tags for certain card characteristics")
    print("   • Metadata for AI enrichment (raw_query, category_guess)")
    print("   • Support for multiple franchises (Pokemon, Magic, Yu-Gi-Oh!, Sports)")
    print("   • Enhanced grading company and condition detection")
    print("   • Backward compatibility with existing systems")
    
    print("\n🎯 Benefits:")
    print("   • Instant aggregation of prices across marketplaces")
    print("   • AI-powered filtering by tags and characteristics")
    print("   • Category browsing with intelligent grouping")
    print("   • Reduced manual data entry and categorization")
    print("   • Better search and discovery for users")
    print("   • Consistent data structure across all sources")
    
    print("\n🔧 Technical Features:")
    print("   • Pydantic models with comprehensive validation")
    print("   • Dataclass-based normalizer for performance")
    print("   • Confidence scoring for parsing accuracy")
    print("   • Canonical key generation for deduplication")
    print("   • Flexible field mapping for different data sources")
    
    print("\n" + "="*80)

async def main():
    """Main test function"""
    print_migration_benefits()
    
    print(f"\n🔧 Configuration:")
    print(f"   SUPABASE_FUNCTION_URL: {'✅ Set' if SUPABASE_FUNCTION_URL else '❌ Not set'}")
    print(f"   SUPABASE_FUNCTION_TOKEN: {'✅ Set' if SUPABASE_FUNCTION_TOKEN else '❌ Not set'}")
    
    if not SUPABASE_FUNCTION_URL or not SUPABASE_FUNCTION_TOKEN:
        print("\n💡 To run the real test:")
        print("   1. Set SUPABASE_FUNCTION_URL environment variable")
        print("   2. Set SUPABASE_FUNCTION_TOKEN environment variable")
        print("   3. Run: python test_edge_function.py")
    
    await test_edge_function()
    
    print("\n✅ Test complete!")

if __name__ == "__main__":
    asyncio.run(main()) 