"""
Shared normalizer module for canonical field parsing and canonical_key generation.
Mirrors the canonical fields Lovable will use for AI-assisted deduping.
"""

import re
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

@dataclass
class ParsedHints:
    """Parsed hints from card titles and metadata"""
    set_name: Optional[str] = None
    edition: Optional[str] = None
    number: Optional[str] = None
    year: Optional[int] = None
    grading_company: Optional[str] = None
    grade: Optional[str] = None
    is_holo: Optional[bool] = None
    franchise: str = "pokemon"
    # New canonicalized fields
    canonical_key: Optional[str] = None
    rarity: Optional[str] = None
    tags: Optional[list] = None
    sold: Optional[bool] = None
    # Normalized fields
    set: Optional[str] = None
    language: Optional[str] = None
    grader: Optional[str] = None
    grade_value: Optional[int] = None

@dataclass
class NormalizedItem:
    """Normalized item with canonical fields"""
    title: str
    canonical_key: str
    confidence: Dict[str, float]
    parsed: ParsedHints
    url: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    ended_at: Optional[str] = None
    id: Optional[str] = None
    source: str = "ebay"
    # New canonicalized fields
    rarity: Optional[str] = None
    grading_company: Optional[str] = None
    grade: Optional[str] = None
    tags: Optional[list] = None
    sold: Optional[bool] = None
    # Normalized fields
    set: Optional[str] = None
    edition: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    grader: Optional[str] = None
    grade_value: Optional[int] = None

class CardNormalizer:
    """Normalizes card listings and generates canonical keys"""
    
    # Common Pokemon sets and their variations
    POKEMON_SETS = {
        "base set": ["base", "base set", "base set unlimited"],
        "base set 1st edition": ["base set 1st edition", "1st edition base set", "base 1st"],
        "jungle": ["jungle", "jungle unlimited"],
        "fossil": ["fossil", "fossil unlimited"],
        "team rocket": ["team rocket", "team rocket unlimited"],
        "gym heroes": ["gym heroes", "gym heroes unlimited"],
        "gym challenge": ["gym challenge", "gym challenge unlimited"],
        "neo genesis": ["neo genesis", "neo genesis unlimited"],
        "neo discovery": ["neo discovery", "neo discovery unlimited"],
        "neo revelation": ["neo revelation", "neo revelation unlimited"],
        "neo destiny": ["neo destiny", "neo destiny unlimited"],
        "legendary collection": ["legendary collection", "lc"],
        "expedition base set": ["expedition base set", "expedition"],
        "aquapolis": ["aquapolis"],
        "skyridge": ["skyridge"],
        "ex ruby & sapphire": ["ex ruby & sapphire", "ex ruby and sapphire", "ex rs"],
        "ex sandstorm": ["ex sandstorm"],
        "ex dragon": ["ex dragon"],
        "ex team magma vs team aqua": ["ex team magma vs team aqua", "ex tmta"],
        "ex hidden legends": ["ex hidden legends"],
        "ex fire red & leaf green": ["ex fire red & leaf green", "ex frlg"],
        "ex team rocket returns": ["ex team rocket returns", "ex trr"],
        "ex deoxys": ["ex deoxys"],
        "ex emerald": ["ex emerald"],
        "ex unseen forces": ["ex unseen forces"],
        "ex delta species": ["ex delta species"],
        "ex legend maker": ["ex legend maker"],
        "ex holon phantoms": ["ex holon phantoms"],
        "ex crystal guardians": ["ex crystal guardians"],
        "ex dragon frontiers": ["ex dragon frontiers"],
        "ex power keepers": ["ex power keepers"],
        "diamond & pearl": ["diamond & pearl", "diamond and pearl", "dp"],
        "mysterious treasures": ["mysterious treasures"],
        "secret wonders": ["secret wonders"],
        "great encounters": ["great encounters"],
        "majestic dawn": ["majestic dawn"],
        "legends awakened": ["legends awakened"],
        "stormfront": ["stormfront"],
        "platinum": ["platinum"],
        "rising rivals": ["rising rivals"],
        "supreme victors": ["supreme victors"],
        "arceus": ["arceus"],
        "heartgold & soulsilver": ["heartgold & soulsilver", "hgss"],
        "unleashed": ["unleashed"],
        "undaunted": ["undaunted"],
        "triumphant": ["triumphant"],
        "call of legends": ["call of legends"],
        "black & white": ["black & white", "bw"],
        "emerging powers": ["emerging powers"],
        "noble victories": ["noble victories"],
        "next destinies": ["next destinies"],
        "dark explorers": ["dark explorers"],
        "dragons exalted": ["dragons exalted"],
        "boundaries crossed": ["boundaries crossed"],
        "plasma storm": ["plasma storm"],
        "plasma freeze": ["plasma freeze"],
        "plasma blast": ["plasma blast"],
        "legendary treasures": ["legendary treasures"],
        "xy": ["xy"],
        "flashfire": ["flashfire"],
        "furious fists": ["furious fists"],
        "phantom forces": ["phantom forces"],
        "primal clash": ["primal clash"],
        "roaring skies": ["roaring skies"],
        "ancient origins": ["ancient origins"],
        "breakthrough": ["breakthrough"],
        "breakpoint": ["breakpoint"],
        "generations": ["generations"],
        "fates collide": ["fates collide"],
        "steam siege": ["steam siege"],
        "evolutions": ["evolutions"],
        "sun & moon": ["sun & moon", "sm"],
        "guardians rising": ["guardians rising"],
        "burning shadows": ["burning shadows"],
        "shining legends": ["shining legends"],
        "crimson invasion": ["crimson invasion"],
        "ultra prism": ["ultra prism"],
        "forbidden light": ["forbidden light"],
        "celestial storm": ["celestial storm"],
        "dragon majesty": ["dragon majesty"],
        "lost thunder": ["lost thunder"],
        "team up": ["team up"],
        "detective pikachu": ["detective pikachu"],
        "unbroken bonds": ["unbroken bonds"],
        "unified minds": ["unified minds"],
        "hidden fates": ["hidden fates"],
        "cosmic eclipse": ["cosmic eclipse"],
        "sword & shield": ["sword & shield", "ss"],
        "rebel clash": ["rebel clash"],
        "darkness ablaze": ["darkness ablaze"],
        "champions path": ["champions path"],
        "vivid voltage": ["vivid voltage"],
        "shining fates": ["shining fates"],
        "battle styles": ["battle styles"],
        "chilling reign": ["chilling reign"],
        "evolving skies": ["evolving skies"],
        "celebrations": ["celebrations"],
        "fusion strike": ["fusion strike"],
        "brilliant stars": ["brilliant stars"],
        "astral radiance": ["astral radiance"],
        "lost origin": ["lost origin"],
        "silver tempest": ["silver tempest"],
        "crown zenith": ["crown zenith"],
        "scarlet & violet": ["scarlet & violet", "sv"],
        "paldea evolved": ["paldea evolved"],
        "obsidian flames": ["obsidian flames"],
        "151": ["151"],
        "paradigm rift": ["paradigm rift"],
        "temporal forces": ["temporal forces"],
        "twilight masquerade": ["twilight masquerade"],
        "ancient roar": ["ancient roar"],
        "future flash": ["future flash"],
    }
    
    # Grading companies
    GRADING_COMPANIES = {
        "psa": ["psa", "professional sports authenticator"],
        "bgs": ["bgs", "beckett grading services", "beckett"],
        "cgc": ["cgc", "certified guarantee company"],
        "sgc": ["sgc", "sportscard guarantee"],
        "hga": ["hga", "hybrid grading approach"],
        "ace": ["ace", "ace grading"],
        "gma": ["gma", "gem mint authentication"],
    }
    
    # Editions/prints
    EDITIONS = {
        "1st edition": ["1st edition", "1st ed", "first edition", "first ed"],
        "unlimited": ["unlimited", "unl", "unltd"],
        "shadowless": ["shadowless", "shadow less"],
        "reverse holo": ["reverse holo", "reverse holographic", "rev holo"],
        "holo": ["holo", "holographic", "holographic"],
        "non-holo": ["non-holo", "non holo", "non-holographic"],
    }
    
    def __init__(self):
        # Build reverse lookup maps
        self._set_lookup = {}
        for canonical, variants in self.POKEMON_SETS.items():
            for variant in variants:
                self._set_lookup[variant.lower()] = canonical
        
        self._grading_lookup = {}
        for canonical, variants in self.GRADING_COMPANIES.items():
            for variant in variants:
                self._grading_lookup[variant.lower()] = canonical
        
        self._edition_lookup = {}
        for canonical, variants in self.EDITIONS.items():
            for variant in variants:
                self._edition_lookup[variant.lower()] = canonical
    
    def parse_title(self, title: str) -> ParsedHints:
        """Parse card title to extract hints"""
        if not title:
            return ParsedHints()
        
        title_lower = title.lower()
        hints = ParsedHints()
        
        # Extract set name
        for variant, canonical in self._set_lookup.items():
            if variant in title_lower:
                hints.set_name = canonical
                break
        
        # Extract edition
        for variant, canonical in self._edition_lookup.items():
            if variant in title_lower:
                hints.edition = canonical
                break
        
        # Extract grading company and grade
        for variant, canonical in self._grading_lookup.items():
            if variant in title_lower:
                hints.grading_company = canonical
                # Look for grade after grading company
                grade_match = re.search(rf'{re.escape(variant)}\s*(\d+)', title_lower)
                if grade_match:
                    hints.grade = grade_match.group(1)
                break
        
        # Extract year (4-digit year)
        year_match = re.search(r'\b(19[89]\d|20[0-2]\d)\b', title)
        if year_match:
            hints.year = int(year_match.group(1))
        
        # Extract card number
        number_match = re.search(r'\b(\d{1,3})\b', title)
        if number_match:
            hints.number = number_match.group(1)
        
        # Check for holographic indicators
        holo_indicators = ["holo", "holographic", "holographic", "reverse holo", "reverse holographic"]
        hints.is_holo = any(indicator in title_lower for indicator in holo_indicators)
        
        return hints
    
    def generate_canonical_key(self, title: str, parsed: ParsedHints) -> str:
        """Generate deterministic canonical key"""
        parts = ["pokemon"]
        
        # Add set name (normalized)
        if parsed.set_name:
            parts.append(parsed.set_name.lower().replace(" ", "_"))
        else:
            parts.append("unknown_set")
        
        # Add card name (extract from title)
        card_name = self._extract_card_name(title, parsed.set_name)
        parts.append(card_name.lower().replace(" ", "_"))
        
        # Add edition
        if parsed.edition:
            parts.append(parsed.edition.lower().replace(" ", "_"))
        else:
            parts.append("unknown_edition")
        
        # Add number
        if parsed.number:
            parts.append(parsed.number)
        else:
            parts.append("unknown_number")
        
        # Add year
        if parsed.year:
            parts.append(str(parsed.year))
        else:
            parts.append("unknown_year")
        
        # Add grading company
        if parsed.grading_company:
            parts.append(parsed.grading_company.lower())
        else:
            parts.append("ungraded")
        
        # Add grade
        if parsed.grade:
            parts.append(parsed.grade)
        else:
            parts.append("ungraded")
        
        return "|".join(parts)
    
    def _extract_card_name(self, title: str, set_name: Optional[str]) -> str:
        """Extract card name from title, removing set info"""
        if not title:
            return "unknown"
        
        # Remove common set indicators
        title_clean = title.lower()
        if set_name:
            title_clean = title_clean.replace(set_name.lower(), "")
        
        # Remove common words
        common_words = ["pokemon", "card", "trading", "game", "holo", "holographic", "1st", "edition", "unlimited"]
        for word in common_words:
            title_clean = title_clean.replace(word, "")
        
        # Clean up extra spaces and punctuation
        title_clean = re.sub(r'\s+', ' ', title_clean).strip()
        title_clean = re.sub(r'[^\w\s]', '', title_clean)
        
        if not title_clean:
            return "unknown"
        
        return title_clean
    
    def compute_confidence(self, title: str, parsed: ParsedHints) -> Dict[str, float]:
        """Compute confidence scores for parsing"""
        confidence = {"title_parse": 0.0, "overall": 0.0}
        
        if not title:
            return confidence
        
        # Title parse confidence based on how many fields we extracted
        extracted_fields = 0
        total_fields = 4  # set_name, edition, grading_company, grade
        
        if parsed.set_name:
            extracted_fields += 1
        if parsed.edition:
            extracted_fields += 1
        if parsed.grading_company:
            extracted_fields += 1
        if parsed.grade:
            extracted_fields += 1
        
        confidence["title_parse"] = extracted_fields / total_fields
        
        # Overall confidence (can be enhanced with more factors)
        confidence["overall"] = confidence["title_parse"] * 0.8 + 0.2
        
        return confidence
    
    def normalize_item(self, item: Dict[str, Any]) -> NormalizedItem:
        """Normalize a single item"""
        title = item.get("title", "")
        
        # Parse hints from title
        parsed = self.parse_title(title)
        
        # Generate canonical key
        canonical_key = self.generate_canonical_key(title, parsed)
        
        # Compute confidence
        confidence = self.compute_confidence(title, parsed)
        
        # Extract new canonicalized fields from item
        rarity = item.get("rarity")
        grading_company = item.get("grading_company")
        grade = item.get("grade")
        tags = item.get("tags")
        sold = item.get("sold")
        
        # Extract normalized fields
        set_name = item.get("set")
        edition = item.get("edition")
        year = item.get("year")
        language = item.get("language")
        grader = item.get("grader")
        grade_value = item.get("grade_value")
        
        return NormalizedItem(
            title=title,
            url=item.get("url"),
            price=item.get("price"),
            currency=item.get("currency", "USD"),
            ended_at=item.get("ended_at"),
            id=item.get("id"),
            source=item.get("source", "ebay"),
            parsed=parsed,
            canonical_key=canonical_key,
            confidence=confidence,
            # New canonicalized fields
            rarity=rarity,
            grading_company=grading_company,
            grade=grade,
            tags=tags,
            sold=sold,
            # Normalized fields
            set=set_name,
            edition=edition,
            year=year,
            language=language,
            grader=grader,
            grade_value=grade_value
        )

# Global instance
normalizer = CardNormalizer() 