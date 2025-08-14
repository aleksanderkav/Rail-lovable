-- Create cards and listings tables for Rail-lovable service
-- Run this in Supabase SQL editor

-- Create cards table
CREATE TABLE IF NOT EXISTS cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    marketplace TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (marketplace, query)
);

-- Create listings table
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

-- Create index on listings for efficient querying
CREATE INDEX IF NOT EXISTS idx_listings_card_id_created_at 
ON listings (card_id, created_at DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;

-- RLS Policies for cards table
-- Allow reading for anonymous users (temporary, can be restricted by domain later)
CREATE POLICY "Allow anonymous read access to cards" ON cards
    FOR SELECT USING (true);

-- RLS Policies for listings table
-- Allow reading for anonymous users (temporary, can be restricted by domain later)
CREATE POLICY "Allow anonymous read access to listings" ON listings
    FOR SELECT USING (true);

-- Note: Insert/Update/Delete operations will be handled by the backend service
-- using service role key, so no RLS policies are needed for those operations

-- Insert/Update/Delete permissions are controlled by the service role key
-- which bypasses RLS policies

-- Seed data for testing
INSERT INTO cards (marketplace, query) VALUES 
    ('ebay', 'Gengar Fossil 1st Edition PSA 10')
ON CONFLICT (marketplace, query) DO NOTHING;

-- Get the card_id for the seed data
DO $$
DECLARE
    card_uuid UUID;
BEGIN
    SELECT id INTO card_uuid FROM cards WHERE marketplace = 'ebay' AND query = 'Gengar Fossil 1st Edition PSA 10';
    
    -- Insert sample listing
    INSERT INTO listings (card_id, title, url, source_listing_id, price, currency, sold, ended_at) VALUES 
        (card_uuid, 'Gengar Fossil 1st Edition PSA 10 - Pokemon Card', 'https://www.ebay.com/itm/306444665735', '306444665735', 1400.00, 'USD', FALSE, NULL)
    ON CONFLICT (card_id, source_listing_id) DO NOTHING;
END $$;

-- Verify the data was inserted
SELECT 
    c.id as card_id,
    c.marketplace,
    c.query,
    c.created_at as card_created,
    l.id as listing_id,
    l.title,
    l.url,
    l.source_listing_id,
    l.price,
    l.currency,
    l.sold,
    l.created_at as listing_created
FROM cards c
LEFT JOIN listings l ON c.id = l.card_id
WHERE c.marketplace = 'ebay' AND c.query = 'Gengar Fossil 1st Edition PSA 10';
