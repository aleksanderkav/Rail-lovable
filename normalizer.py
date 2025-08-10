"""
Shared normalizer module for canonical field parsing and canonical_key generation.
Mirrors the canonical fields Lovable will use for AI-assisted deduping.
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

@dataclass
class ParsedHints:
    """Parsed hints from title/description for AI enrichment"""
    # Core card identification
    franchise: Optional[str] = None
    set_name: Optional[str] = None
    edition: Optional[str] = None
    number: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    
    # Grading information
    grading_company: Optional[str] = None
    grade: Optional[str] = None
    grade_value: Optional[int] = None
    
    # Card characteristics
    rarity: Optional[str] = None
    is_holo: Optional[bool] = None
    
    # Legacy fields for backward compatibility
    canonical_key: Optional[str] = None
    tags: Optional[List[str]] = None
    sold: Optional[bool] = None
    set: Optional[str] = None
    grader: Optional[str] = None

@dataclass
class NormalizedItem:
    """Normalized item with AI enrichment support"""
    # Core fields
    raw_title: str
    canonical_key: str
    confidence: float
    parsed: ParsedHints
    
    # Raw listing details
    raw_description: Optional[str] = None
    source: str = "ebay"
    source_listing_id: Optional[str] = None
    url: Optional[str] = None
    
    # Pricing and availability
    currency: str = "USD"
    price: Optional[float] = None
    ended_at: Optional[str] = None
    
    # Media
    images: Optional[List[str]] = None
    
    # Initial parsed fields
    franchise: Optional[str] = None
    set_name: Optional[str] = None
    edition: Optional[str] = None
    number: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    grading_company: Optional[str] = None
    grade: Optional[str] = None
    rarity: Optional[str] = None
    is_holo: Optional[bool] = None
    
    # Tags
    tags: Optional[List[str]] = None
    
    # Metadata for enrichment
    raw_query: Optional[str] = None
    category_guess: Optional[str] = None
    
    # Legacy fields for backward compatibility
    title: Optional[str] = None
    id: Optional[str] = None
    sold: Optional[bool] = None
    image_url: Optional[str] = None
    shipping_price: Optional[float] = None
    total_price: Optional[float] = None
    bids: Optional[int] = None
    condition: Optional[str] = None
    canonical_key_legacy: Optional[str] = None
    set_legacy: Optional[str] = None
    grader: Optional[str] = None
    grade_value: Optional[int] = None

class CardNormalizer:
    """Normalizes card listings for AI enrichment"""
    
    def __init__(self):
        # Common franchises
        self.franchises = {
            "pokemon": ["pokemon", "pokémon", "pikachu", "charizard", "blastoise", "venusaur"],
            "magic": ["magic", "mtg", "planeswalker", "mana", "spell"],
            "yugioh": ["yugioh", "yu-gi-oh", "duel monster", "blue eyes", "dark magician"],
            "sports": ["basketball", "football", "baseball", "hockey", "soccer", "nba", "nfl", "mlb", "nhl"]
        }
        
        # Common grading companies
        self.grading_companies = ["psa", "bgs", "cgc", "sgc", "hga", "ace"]
        
        # Common editions
        self.editions = ["1st edition", "first edition", "unlimited", "shadowless", "limited"]
        
        # Common sets (Pokemon examples)
        self.pokemon_sets = ["base set", "jungle", "fossil", "team rocket", "gym heroes", "neo genesis"]
        
    def parse_title(self, title: str) -> ParsedHints:
        """Parse title to extract initial hints"""
        title_lower = title.lower()
        
        # Detect franchise
        franchise = None
        for name, keywords in self.franchises.items():
            if any(keyword in title_lower for keyword in keywords):
                franchise = name.title()
                break
        
        # Detect grading company
        grading_company = None
        for company in self.grading_companies:
            if company in title_lower:
                grading_company = company.upper()
                break
        
        # Detect edition
        edition = None
        for ed in self.editions:
            if ed in title_lower:
                edition = ed.title()
                break
        
        # Detect set name (Pokemon specific for now)
        set_name = None
        for set_keyword in self.pokemon_sets:
            if set_keyword in title_lower:
                set_name = set_keyword.title()
                break
        
        # Detect year (4-digit numbers that could be years)
        year = None
        year_match = re.search(r'\b(19|20)\d{2}\b', title)
        if year_match:
            year = int(year_match.group())
        
        # Detect card number
        number = None
        number_match = re.search(r'\b(\d{1,3})\b', title)
        if number_match:
            number = number_match.group()
        
        # Detect grade
        grade = None
        grade_match = re.search(r'\b(10|9|8|7|6|5|4|3|2|1|mint|gem|near mint|excellent|good|fair|poor)\b', title_lower)
        if grade_match:
            grade = grade_match.group()
        
        # Detect if holo
        is_holo = "holo" in title_lower or "holofoil" in title_lower
        
        # Generate tags
        tags = []
        if grading_company:
            tags.append(f"{grading_company} {grade}" if grade else grading_company)
        if edition:
            tags.append(edition)
        if is_holo:
            tags.append("Holo")
        if set_name:
            tags.append(set_name)
        
        return ParsedHints(
            franchise=franchise,
            set_name=set_name,
            edition=edition,
            number=number,
            year=year,
            grading_company=grading_company,
            grade=grade,
            is_holo=is_holo,
            tags=tags if tags else None
        )
    
    def generate_canonical_key(self, title: str, parsed: ParsedHints) -> str:
        """Generate a canonical key for the card"""
        if parsed.franchise and parsed.set_name and parsed.number:
            return f"{parsed.franchise.lower()}_{parsed.set_name.lower().replace(' ', '_')}_{parsed.number}"
        elif parsed.franchise and parsed.set_name:
            return f"{parsed.franchise.lower()}_{parsed.set_name.lower().replace(' ', '_')}"
        else:
            # Fallback to title-based key
            return re.sub(r'[^a-zA-Z0-9]', '_', title.lower()).strip('_')
    
    def compute_confidence(self, title: str, parsed: ParsedHints) -> float:
        """Compute confidence score for parsing"""
        score = 0.0
        
        if parsed.franchise:
            score += 0.3
        if parsed.set_name:
            score += 0.2
        if parsed.number:
            score += 0.2
        if parsed.grading_company:
            score += 0.15
        if parsed.grade:
            score += 0.15
        
        return min(score, 1.0)
    
    def normalize_item(self, item: Dict[str, Any]) -> NormalizedItem:
        """Normalize a single item"""
        raw_title = item.get("raw_title", item.get("title", ""))
        
        # Parse hints from title
        parsed = self.parse_title(raw_title)
        
        # Generate canonical key
        canonical_key = self.generate_canonical_key(raw_title, parsed)
        
        # Compute confidence
        confidence = self.compute_confidence(raw_title, parsed)
        
        # Extract fields from item
        raw_description = item.get("raw_description")
        source = item.get("source", "ebay")
        source_listing_id = item.get("source_listing_id") or item.get("id")
        url = item.get("url")
        currency = item.get("currency", "USD")
        price = item.get("price")
        ended_at = item.get("ended_at")
        images = item.get("images")
        raw_query = item.get("raw_query")
        category_guess = item.get("category_guess")
        
        # Extract initial parsed fields (override with item data if available)
        franchise = item.get("franchise") or parsed.franchise
        set_name = item.get("set_name") or parsed.set_name
        edition = item.get("edition") or parsed.edition
        number = item.get("number") or parsed.number
        year = item.get("year") or parsed.year
        language = item.get("language") or parsed.language
        grading_company = item.get("grading_company") or parsed.grading_company
        grade = item.get("grade") or parsed.grade
        rarity = item.get("rarity") or parsed.rarity
        is_holo = item.get("is_holo") if item.get("is_holo") is not None else parsed.is_holo
        
        # Extract tags
        tags = item.get("tags") or parsed.tags
        
        # Legacy fields for backward compatibility
        title = item.get("title") or raw_title
        sold = item.get("sold")
        image_url = item.get("image_url")
        shipping_price = item.get("shipping_price")
        total_price = item.get("total_price")
        bids = item.get("bids")
        condition = item.get("condition")
        canonical_key_legacy = item.get("canonical_key")
        set_legacy = item.get("set")
        grader = item.get("grader")
        grade_value = item.get("grade_value")
        
        return NormalizedItem(
            raw_title=raw_title,
            canonical_key=canonical_key,
            confidence=confidence,
            parsed=parsed,
            raw_description=raw_description,
            source=source,
            source_listing_id=source_listing_id,
            url=url,
            currency=currency,
            price=price,
            ended_at=ended_at,
            images=images,
            franchise=franchise,
            set_name=set_name,
            edition=edition,
            number=number,
            year=year,
            language=language,
            grading_company=grading_company,
            grade=grade,
            rarity=rarity,
            is_holo=is_holo,
            tags=tags,
            raw_query=raw_query,
            category_guess=category_guess,
            title=title,
            id=source_listing_id,
            sold=sold,
            image_url=image_url,
            shipping_price=shipping_price,
            total_price=total_price,
            bids=bids,
            condition=condition,
            canonical_key_legacy=canonical_key_legacy,
            set_legacy=set_legacy,
            grader=grader,
            grade_value=grade_value
        )

# Create a global instance
normalizer = CardNormalizer() 