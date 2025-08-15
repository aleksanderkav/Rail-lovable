-- Simple schema fix for Rail-lovable ingest functionality
-- Run this in Supabase SQL Editor

-- Create cards table if it doesn't exist
CREATE TABLE IF NOT EXISTS cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    marketplace TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (marketplace, query)
);

-- Create listings table if it doesn't exist
CREATE TABLE IF NOT EXISTS listings (
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

-- Add missing columns to existing tables if needed
DO $$
BEGIN
    -- Add marketplace column to cards if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'cards' AND column_name = 'marketplace') THEN
        ALTER TABLE cards ADD COLUMN marketplace TEXT NOT NULL DEFAULT 'ebay';
        ALTER TABLE cards ALTER COLUMN marketplace DROP DEFAULT;
    END IF;
    
    -- Add query column to cards if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'cards' AND column_name = 'query') THEN
        ALTER TABLE cards ADD COLUMN query TEXT NOT NULL DEFAULT '';
        ALTER TABLE cards ALTER COLUMN query DROP DEFAULT;
    END IF;
    
    -- Add card_id column to listings if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'card_id') THEN
        ALTER TABLE listings ADD COLUMN card_id UUID REFERENCES cards(id) ON DELETE CASCADE;
    END IF;
    
    -- Add source_listing_id column to listings if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'source_listing_id') THEN
        ALTER TABLE listings ADD COLUMN source_listing_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE listings ALTER COLUMN source_listing_id DROP DEFAULT;
    END IF;
    
    -- Add url column to listings if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'url') THEN
        ALTER TABLE listings ADD COLUMN url TEXT NOT NULL DEFAULT '';
        ALTER TABLE listings ALTER COLUMN url DROP DEFAULT;
    END IF;
    
    -- Add price column to listings if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'price') THEN
        ALTER TABLE listings ADD COLUMN price NUMERIC;
    END IF;
    
    -- Add currency column to listings if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'currency') THEN
        ALTER TABLE listings ADD COLUMN currency TEXT;
    END IF;
    
    -- Add sold column to listings if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'sold') THEN
        ALTER TABLE listings ADD COLUMN sold BOOLEAN DEFAULT FALSE;
    END IF;
    
    -- Add ended_at column to listings if missing
    IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'listings' AND column_name = 'ended_at') THEN
        ALTER TABLE listings ADD COLUMN ended_at TIMESTAMPTZ;
    END IF;
END $$;

-- Enable RLS on both tables
ALTER TABLE cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for read access
DROP POLICY IF EXISTS "Allow anonymous read access to cards" ON cards;
CREATE POLICY "Allow anonymous read access to cards" ON cards
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow anonymous read access to listings" ON listings;
CREATE POLICY "Allow anonymous read access to listings" ON listings
    FOR SELECT USING (true);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_listings_card_id ON listings (card_id);
CREATE INDEX IF NOT EXISTS idx_listings_source_listing_id ON listings (source_listing_id);
CREATE INDEX IF NOT EXISTS idx_listings_card_id_created_at ON listings (card_id, created_at DESC);

-- Reload PostgREST schema cache
SELECT pg_notify('pgrst', 'reload schema');

-- Show final schema
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
