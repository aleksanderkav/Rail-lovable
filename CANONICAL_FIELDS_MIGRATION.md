# Canonical Fields Migration Guide

This document outlines the changes made to support Lovable's canonicalization and backfill migration for the Supabase schema.

## Overview

Lovable has implemented AI-assisted normalization and deduplication for our card database. This means the scraper will now receive and process enriched, canonicalized card data instead of just raw listings.

## New Canonicalized Fields

### Core Canonical Fields
- **`canonical_key`**: Unique identifier for canonical card representation
- **`rarity`**: Card rarity (e.g., "Common", "Uncommon", "Rare", "Holo Rare")
- **`grading_company`**: Grading company abbreviation (e.g., "PSA", "BGS", "CGC")
- **`grade`**: Grade value as string (e.g., "10", "9.5", "Mint")
- **`tags`**: Array of descriptive tags (e.g., ["holo", "1st edition", "base set"])
- **`sold`**: Boolean indicating if the listing was sold

### Normalized Fields
- **`set`**: Normalized set name (e.g., "Base Set", "Jungle")
- **`edition`**: Normalized edition (e.g., "1st Edition", "Unlimited")
- **`year`**: Release year as integer
- **`language`**: Card language (e.g., "English", "Japanese")
- **`grader`**: Normalized grader name
- **`grade_value`**: Grade as numeric value for sorting

## Required Fields for AI Enrichment

The scraper continues to send these essential fields so ai-parser can enrich and normalize consistently:

- **`raw_query`**: Original search query (renamed from `query`)
- **`title`**: Listing title
- **`price`**: Listing price
- **`currency`**: Price currency
- **`ended_at`**: Auction end time
- **`source`**: Data source (e.g., "ebay")
- **`source_listing_id`**: Unique identifier from source

## System Updates Made

### 1. Test Edge Function (`test_edge_function.py`)
- Updated test data to include new canonicalized fields
- Enhanced response validation to check for new fields
- Added comprehensive field checking for migration readiness

### 2. Main Scraper (`main.py`)
- Updated `Item` model to include new canonicalized fields
- Enhanced `ParsedHints` model with new fields
- Updated response handling for enriched data

### 3. Normalizer (`normalizer.py`)
- Extended `ParsedHints` and `NormalizedItem` dataclasses
- Updated `normalize_item` method to handle new fields
- Maintained backward compatibility with existing parsing logic

### 4. Scheduled Scraper (`scheduled_scraper.py`)
- Updated field names from `query` to `raw_query`
- Enhanced payload handling to ensure required fields are present
- Maintained existing functionality while supporting new data structure

## Data Flow After Migration

```
Scraper → Raw Listings → AI-Parser → Canonicalized Data → Database
   ↓           ↓           ↓              ↓              ↓
raw_query   title      canonical_key   rarity        card_id
title      price      rarity          grade         listing_id
price      currency   grading_company tags          price_entry_id
currency   ended_at   grade           sold
ended_at   source     tags            set
source     source_id  sold            edition
source_id             set             year
                       edition        language
                       year           grader
                       language       grade_value
                       grader
                       grade_value
```

## Handling Card ID Changes

**Important**: After Lovable runs the backfill migration, card IDs for some existing listings/price entries may change due to merges of near-duplicate cards.

### Downstream System Preparation
- Ensure all systems can handle updated `card_id` references
- Implement proper error handling for missing card IDs
- Use `canonical_key` as a stable identifier when possible
- Monitor for any broken references after migration

### Recommended Approach
1. **Before Migration**: Document all current card ID references
2. **During Migration**: Monitor for any data inconsistencies
3. **After Migration**: Update any hardcoded card ID references
4. **Ongoing**: Use `canonical_key` for stable card identification

## Testing the Migration

### 1. Run Test Edge Function
```bash
cd Rail-lovable
python test_edge_function.py
```

### 2. Verify Field Presence
The test will check for:
- ✅ Core database IDs (card_id, listing_id, price_entry_id)
- ✅ New canonicalized fields (canonical_key, rarity, grading_company, grade, tags, sold)
- ✅ Normalized fields (set, edition, year, language, grader, grade_value)

### 3. Check Data Consistency
- Ensure all required fields are present
- Verify field types match expected formats
- Test with various card types and conditions

## Benefits of the New System

1. **Better Deduplication**: AI-assisted fuzzy matching prevents duplicate cards
2. **Consistent Normalization**: Standardized field values across all sources
3. **Enhanced Search**: Rich metadata enables better filtering and sorting
4. **Improved Analytics**: Structured data supports advanced reporting
5. **Future-Proof**: Extensible schema for additional card attributes

## Migration Checklist

- [ ] Update scraper to handle new canonicalized fields
- [ ] Test edge function integration with new data structure
- [ ] Verify downstream systems can handle card ID changes
- [ ] Monitor data consistency during and after migration
- [ ] Update any hardcoded card references
- [ ] Document new field usage for development team

## Support

For questions about the canonicalization migration:
1. Check this documentation first
2. Review the test edge function output
3. Contact the Lovable team for schema-specific questions
4. Check system logs for any data processing errors

## Future Enhancements

The new canonicalized structure enables:
- Advanced card similarity search using embeddings
- Machine learning-based price prediction
- Automated condition assessment
- Multi-language card support
- Enhanced rarity classification 