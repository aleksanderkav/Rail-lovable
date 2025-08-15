# Fix POST /ingest 500 Error: "Could not find the `marketplace` column"

## Problem
POST `/ingest` returns 500 with error:
```
"Failed to create card: 400 - { ... 'Could not find the `marketplace` column of `cards` in the schema cache' }"
```

## Root Cause
The database tables `cards` and `listings` either don't exist or are missing required columns that the ingest code expects.

## Solution
Run the SQL schema fix in Supabase SQL Editor.

### Option 1: Simple Fix (Recommended)
1. Go to Supabase Dashboard → SQL Editor
2. Copy and paste the contents of `fix_schema_simple.sql`
3. Click "Run" to execute the script
4. Verify the output shows successful table creation/column addition

### Option 2: Comprehensive Fix
1. Go to Supabase Dashboard → SQL Editor
2. Copy and paste the contents of `fix_ingest_schema.sql`
3. Click "Run" to execute the script
4. Check the output for any errors or warnings

## What the Fix Does

### Creates/Updates `cards` table:
- `id` (UUID, Primary Key)
- `marketplace` (TEXT, NOT NULL) ← **This was missing!**
- `query` (TEXT, NOT NULL)
- `created_at` (TIMESTAMPTZ)
- Unique constraint on (marketplace, query)

### Creates/Updates `listings` table:
- `id` (UUID, Primary Key)
- `card_id` (UUID, Foreign Key to cards.id)
- `title` (TEXT)
- `url` (TEXT, NOT NULL)
- `source_listing_id` (TEXT, NOT NULL)
- `price` (NUMERIC)
- `currency` (TEXT)
- `sold` (BOOLEAN)
- `ended_at` (TIMESTAMPTZ)
- `created_at` (TIMESTAMPTZ)
- Unique constraint on (card_id, source_listing_id)

### Additional Features:
- Enables Row Level Security (RLS)
- Creates RLS policies for anonymous read access
- Creates performance indexes
- Reloads PostgREST schema cache

## Verification
After running the fix, test with:

```bash
# Test dry-run (should work)
curl -X POST "https://rail-lovable-production.up.railway.app/ingest?dryRun=1" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  -d '{"query":"test","marketplace":"ebay","items":[{"title":"Test","debug_url":"https://test.com","price":"100 USD"}]}'

# Test real save (should work now)
curl -X POST "https://rail-lovable-production.up.railway.app/ingest" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: YOUR_ADMIN_TOKEN" \
  -d '{"query":"test","marketplace":"ebay","items":[{"title":"Test","debug_url":"https://test.com","price":"100 USD"}]}'
```

## Expected Response
```json
{
  "ok": true,
  "card_id": "uuid-here",
  "accepted": 1,
  "skipped": {"no_url": 0, "no_id": 0, "dup": 0},
  "total": 1
}
```

## Troubleshooting
If you still get errors:
1. Check Supabase SQL Editor output for any error messages
2. Verify tables exist: `SELECT * FROM information_schema.tables WHERE table_name IN ('cards', 'listings');`
3. Verify columns exist: `SELECT column_name FROM information_schema.columns WHERE table_name = 'cards';`
4. Check RLS policies: `SELECT * FROM pg_policies WHERE tablename IN ('cards', 'listings');`

## Files
- `fix_schema_simple.sql` - Simple schema fix (recommended)
- `fix_ingest_schema.sql` - Comprehensive schema fix with validation
- `create_cards_and_listings_tables.sql` - Original table creation script
