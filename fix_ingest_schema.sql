-- Fix database schema for Rail-lovable ingest functionality
-- Run this in Supabase SQL editor to fix the "marketplace column not found" error

-- First, check if tables exist
DO $$
BEGIN
    -- Check if cards table exists
    IF NOT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'cards') THEN
        RAISE NOTICE 'Creating cards table...';
        
        CREATE TABLE cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            marketplace TEXT NOT NULL,
            query TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (marketplace, query)
        );
        
        -- Enable RLS
        ALTER TABLE cards ENABLE ROW LEVEL SECURITY;
        
        -- Allow anonymous read access
        CREATE POLICY "Allow anonymous read access to cards" ON cards
            FOR SELECT USING (true);
            
        RAISE NOTICE 'Cards table created successfully';
    ELSE
        RAISE NOTICE 'Cards table already exists';
        
        -- Check if marketplace column exists
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'cards' AND column_name = 'marketplace') THEN
            RAISE NOTICE 'Adding marketplace column to cards table...';
            ALTER TABLE cards ADD COLUMN marketplace TEXT NOT NULL DEFAULT 'ebay';
            ALTER TABLE cards ALTER COLUMN marketplace DROP DEFAULT;
            
            -- Add unique constraint if it doesn't exist
            IF NOT EXISTS (SELECT FROM pg_constraint WHERE conname = 'cards_marketplace_query_key') THEN
                ALTER TABLE cards ADD CONSTRAINT cards_marketplace_query_key UNIQUE (marketplace, query);
            END IF;
            
            RAISE NOTICE 'Marketplace column added successfully';
        ELSE
            RAISE NOTICE 'Marketplace column already exists in cards table';
        END IF;
    END IF;
    
    -- Check if listings table exists
    IF NOT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'listings') THEN
        RAISE NOTICE 'Creating listings table...';
        
        CREATE TABLE listings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            card_id UUID REFERENCES cards(id) ON DELETE CASCADE,
            title TEXT,
            url TEXT NOT NULL,
            source_listing_id TEXT NOT NULL,
            price NUMERIC,
            currency TEXT,
            sold BOOLEAN DEFAULT FALSE,
            ended_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (card_id, source_listing_id)
        );
        
        -- Enable RLS
        ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
        
        -- Allow anonymous read access
        CREATE POLICY "Allow anonymous read access to listings" ON listings
            FOR SELECT USING (true);
            
        RAISE NOTICE 'Listings table created successfully';
    ELSE
        RAISE NOTICE 'Listings table already exists';
        
        -- Check if required columns exist
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'card_id') THEN
            RAISE NOTICE 'Adding card_id column to listings table...';
            ALTER TABLE listings ADD COLUMN card_id UUID REFERENCES cards(id) ON DELETE CASCADE;
            RAISE NOTICE 'Card_id column added successfully';
        END IF;
        
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'source_listing_id') THEN
            RAISE NOTICE 'Adding source_listing_id column to listings table...';
            ALTER TABLE listings ADD COLUMN source_listing_id TEXT NOT NULL DEFAULT '';
            ALTER TABLE listings ALTER COLUMN source_listing_id DROP DEFAULT;
            RAISE NOTICE 'Source_listing_id column added successfully';
        END IF;
        
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'url') THEN
            RAISE NOTICE 'Adding url column to listings table...';
            ALTER TABLE listings ADD COLUMN url TEXT NOT NULL DEFAULT '';
            ALTER TABLE listings ALTER COLUMN url DROP DEFAULT;
            RAISE NOTICE 'Url column added successfully';
        END IF;
        
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'price') THEN
            RAISE NOTICE 'Adding price column to listings table...';
            ALTER TABLE listings ADD COLUMN price NUMERIC;
            RAISE NOTICE 'Price column added successfully';
        END IF;
        
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'currency') THEN
            RAISE NOTICE 'Adding currency column to listings table...';
            ALTER TABLE listings ADD COLUMN currency TEXT;
            RAISE NOTICE 'Currency column added successfully';
        END IF;
        
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'sold') THEN
            RAISE NOTICE 'Adding sold column to listings table...';
            ALTER TABLE listings ADD COLUMN sold BOOLEAN DEFAULT FALSE;
            RAISE NOTICE 'Sold column added successfully';
        END IF;
        
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'ended_at') THEN
            RAISE NOTICE 'Adding ended_at column to listings table...';
            ALTER TABLE listings ADD COLUMN ended_at TIMESTAMPTZ;
            RAISE NOTICE 'Ended_at column added successfully';
        END IF;
        
        -- Add unique constraint if it doesn't exist
        IF NOT EXISTS (SELECT FROM pg_constraint WHERE conname = 'listings_card_id_source_listing_id_key') THEN
            ALTER TABLE listings ADD CONSTRAINT listings_card_id_source_listing_id_key UNIQUE (card_id, source_listing_id);
        END IF;
    END IF;
END $$;

-- Create useful indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_listings_card_id ON listings (card_id);
CREATE INDEX IF NOT EXISTS idx_listings_source_listing_id ON listings (source_listing_id);
CREATE INDEX IF NOT EXISTS idx_listings_card_id_created_at ON listings (card_id, created_at DESC);

-- Verify the schema
SELECT 
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_schema = 'public' 
AND table_name IN ('cards', 'listings')
ORDER BY table_name, ordinal_position;

-- Test insert to verify everything works
DO $$
DECLARE
    test_card_id UUID;
BEGIN
    -- Try to insert a test card
    INSERT INTO cards (marketplace, query) VALUES ('test', 'schema-test') 
    ON CONFLICT (marketplace, query) DO NOTHING
    RETURNING id INTO test_card_id;
    
    IF test_card_id IS NOT NULL THEN
        RAISE NOTICE 'Test card inserted successfully with ID: %', test_card_id;
        
        -- Try to insert a test listing
        INSERT INTO listings (card_id, title, url, source_listing_id, price, currency, sold) 
        VALUES (test_card_id, 'Test Listing', 'https://test.com', 'test123', 100.00, 'USD', false);
        
        RAISE NOTICE 'Test listing inserted successfully';
        
        -- Clean up test data
        DELETE FROM listings WHERE card_id = test_card_id;
        DELETE FROM cards WHERE id = test_card_id;
        
        RAISE NOTICE 'Test data cleaned up successfully';
    ELSE
        RAISE NOTICE 'Test card already exists, schema verification complete';
    END IF;
END $$;

-- Reload PostgREST schema cache
SELECT pg_notify('pgrst', 'reload schema');

RAISE NOTICE 'Schema fix completed successfully!';
