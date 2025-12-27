#!/usr/bin/env python3
"""
TMX Translation Memory Loader
Loads and processes TMX (Translation Memory Exchange) files
Provides fuzzy matching for similar segment retrieval
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple
import logging
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein


class TMXMemoryLoader:
    """Load and search TMX translation memory files with fuzzy matching"""

    def __init__(self, tmx_file_path: str, enable_cache: bool = True):
        """
        Initialize TMX Memory Loader

        Args:
            tmx_file_path: Path to TMX file
            enable_cache: Cache parsed TUs for faster subsequent access
        """
        self.setup_logging()
        self.tmx_file_path = tmx_file_path
        self.translation_units = []  # List of all TUs
        self.korean_index = {}  # Quick lookup: korean_text -> english_translation
        self.enable_cache = enable_cache
        self.load_tmx()

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_tmx(self):
        """
        Load and parse TMX file
        Extract translation units with Korean (ko-KR) and English (en-US) segments
        """
        self.logger.info(f"📚 Loading TMX file: {self.tmx_file_path}")

        try:
            # Parse XML
            tree = ET.parse(self.tmx_file_path)
            root = tree.getroot()

            # Find all translation units
            tu_elements = root.findall('.//tu')
            self.logger.info(f"  Found {len(tu_elements)} translation units")

            # Extract Ko-En pairs
            for tu in tu_elements:
                tuvs = tu.findall('.//tuv')

                korean_text = None
                english_text = None

                # Extract language variants
                for tuv in tuvs:
                    # Get language code (try both xml:lang and lang attributes)
                    lang = tuv.get('{http://www.w3.org/XML/1998/namespace}lang')
                    if not lang:
                        lang = tuv.get('lang')

                    seg = tuv.find('.//seg')
                    if seg is not None and seg.text:
                        text = seg.text.strip()

                        if lang == 'ko-KR' or lang == 'ko':
                            korean_text = text
                        elif lang == 'en-US' or lang == 'en':
                            english_text = text

                # Store valid KO-EN pairs
                if korean_text and english_text:
                    tu_dict = {
                        'source': korean_text,
                        'target': english_text,
                        'id': tu.get('id', ''),
                    }
                    self.translation_units.append(tu_dict)

                    # Build quick lookup index (exact matches only)
                    # Note: Multiple KO texts might map to same EN, we keep first
                    if korean_text not in self.korean_index:
                        self.korean_index[korean_text] = english_text

            self.logger.info(f"✅ Loaded {len(self.translation_units)} Ko-En translation pairs")
            self.logger.info(f"  Created index with {len(self.korean_index)} unique Korean terms")

            if len(self.translation_units) == 0:
                self.logger.warning("⚠️  No translation units found! Check TMX file format.")

        except Exception as e:
            self.logger.error(f"❌ Error loading TMX file: {e}")
            raise

    def find_similar_segments(self,
                            query_korean: str,
                            top_k: int = 3,
                            threshold: float = 0.75) -> List[Dict]:
        """
        Find similar segments in translation memory using fuzzy matching

        Args:
            query_korean: Korean text to search for
            top_k: Number of top matches to return (default: 3)
            threshold: Minimum similarity score (0.0-1.0, default: 0.75 = 75%)

        Returns:
            List of similar matches sorted by similarity score (highest first)
            Format: [{
                'source': korean_text,
                'target': english_text,
                'similarity': float (0.0-1.0),
                'method': 'exact' | 'fuzzy'
            }]
        """
        if not query_korean or not self.translation_units:
            return []

        query_clean = query_korean.strip()
        matches = []

        # First, check for exact match in index
        if query_clean in self.korean_index:
            matches.append({
                'source': query_clean,
                'target': self.korean_index[query_clean],
                'similarity': 1.0,
                'method': 'exact'
            })

            if len(matches) >= top_k:
                return matches[:top_k]

        # Fuzzy matching using token set ratio (better for partial matches)
        # Token set ratio handles reordered words better than simple ratio
        for tu in self.translation_units:
            # Skip if already in exact matches
            if tu['source'] == query_clean:
                continue

            # Calculate similarity using token_set_ratio (handles reordering)
            similarity = fuzz.token_set_ratio(query_clean, tu['source']) / 100.0

            # Only include if above threshold
            if similarity >= threshold:
                matches.append({
                    'source': tu['source'],
                    'target': tu['target'],
                    'similarity': similarity,
                    'method': 'fuzzy'
                })

        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x['similarity'], reverse=True)

        # Return top K
        result = matches[:top_k]

        if result:
            self.logger.debug(f"Found {len(result)} matches for: {query_korean[:50]}...")
            for i, match in enumerate(result, 1):
                sim_pct = int(match['similarity'] * 100)
                self.logger.debug(f"  {i}. [{sim_pct}%] {match['source'][:60]}...")

        return result

    def get_exact_match(self, korean_text: str) -> str:
        """
        Get exact match for Korean text (fast lookup)

        Args:
            korean_text: Korean text to lookup

        Returns:
            English translation if exact match found, None otherwise
        """
        return self.korean_index.get(korean_text.strip())

    def get_statistics(self) -> Dict:
        """
        Get statistics about loaded translation memory

        Returns:
            Dictionary with TM statistics
        """
        return {
            'total_units': len(self.translation_units),
            'unique_korean_terms': len(self.korean_index),
            'file_path': self.tmx_file_path,
        }
