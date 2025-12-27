#!/usr/bin/env python3
"""
TMX Translation Memory Loader for EN-KO Direction
Loads and processes TMX files for English → Korean translation
Provides fuzzy matching for similar segment retrieval
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
import logging
from rapidfuzz import fuzz


class TMXMemoryLoaderENKO:
    """Load and search TMX translation memory files with fuzzy matching for EN-KO direction"""

    def __init__(self, tmx_file_paths: List[str], enable_cache: bool = True):
        """
        Initialize TMX Memory Loader for EN-KO

        Args:
            tmx_file_paths: List of paths to TMX files (supports multiple TMX files)
            enable_cache: Cache parsed TUs for faster subsequent access
        """
        self.setup_logging()
        self.tmx_file_paths = tmx_file_paths if isinstance(tmx_file_paths, list) else [tmx_file_paths]
        self.translation_units = []  # List of all TUs (EN→KO pairs)
        self.english_index = {}  # Quick lookup: english_text -> korean_translation
        self.enable_cache = enable_cache
        self.load_all_tmx()

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_all_tmx(self):
        """Load and merge multiple TMX files"""
        total_units = 0

        for tmx_file_path in self.tmx_file_paths:
            try:
                units = self._load_tmx_file(tmx_file_path)
                total_units += units
            except Exception as e:
                self.logger.warning(f"⚠️  Error loading {tmx_file_path}: {e}")
                continue

        self.logger.info(f"✅ Total loaded: {total_units} EN-Ko translation pairs across {len(self.tmx_file_paths)} files")
        self.logger.info(f"  Created index with {len(self.english_index)} unique English terms")

    def _load_tmx_file(self, tmx_file_path: str) -> int:
        """
        Load and parse single TMX file
        Extract translation units with English (en-US/en) and Korean (ko-KR/ko) segments

        Returns:
            Number of translation units loaded from this file
        """
        self.logger.info(f"📚 Loading TMX file: {tmx_file_path}")

        try:
            # Parse XML
            tree = ET.parse(tmx_file_path)
            root = tree.getroot()

            # Find all translation units
            tu_elements = root.findall('.//tu')
            self.logger.info(f"  Found {len(tu_elements)} translation units")

            loaded_count = 0

            # Extract En-Ko pairs
            for tu in tu_elements:
                tuvs = tu.findall('.//tuv')

                english_text = None
                korean_text = None

                # Extract language variants
                for tuv in tuvs:
                    # Get language code (try both xml:lang and lang attributes)
                    lang = tuv.get('{http://www.w3.org/XML/1998/namespace}lang')
                    if not lang:
                        lang = tuv.get('lang')

                    seg = tuv.find('.//seg')
                    if seg is not None and seg.text:
                        text = seg.text.strip()

                        if lang == 'en-US' or lang == 'en':
                            english_text = text
                        elif lang == 'ko-KR' or lang == 'ko':
                            korean_text = text

                # Store valid EN-KO pairs
                if english_text and korean_text:
                    tu_dict = {
                        'source': english_text,  # English source
                        'target': korean_text,   # Korean target
                        'id': tu.get('id', ''),
                    }
                    self.translation_units.append(tu_dict)

                    # Build quick lookup index (exact matches only)
                    # Note: Multiple EN texts might map to different KO, we keep first
                    if english_text not in self.english_index:
                        self.english_index[english_text] = korean_text

                    loaded_count += 1

            self.logger.info(f"  ✅ Loaded {loaded_count} EN-Ko pairs from {tmx_file_path}")
            return loaded_count

        except Exception as e:
            self.logger.error(f"❌ Error loading TMX file {tmx_file_path}: {e}")
            raise

    def find_similar_segments(self,
                            query_english: str,
                            top_k: int = 3,
                            threshold: float = 0.75) -> List[Dict]:
        """
        Find similar segments in translation memory using fuzzy matching

        Args:
            query_english: English text to search for
            top_k: Number of top matches to return (default: 3)
            threshold: Minimum similarity score (0.0-1.0, default: 0.75 = 75%)

        Returns:
            List of similar matches sorted by similarity score (highest first)
            Format: [{
                'source': english_text,
                'target': korean_text,
                'similarity': float (0.0-1.0),
                'method': 'exact' | 'fuzzy'
            }]
        """
        if not query_english or not self.translation_units:
            return []

        query_clean = query_english.strip()
        matches = []

        # First, check for exact match in index
        if query_clean in self.english_index:
            matches.append({
                'source': query_clean,
                'target': self.english_index[query_clean],
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
            self.logger.debug(f"Found {len(result)} TM matches for: {query_english[:50]}...")
            for i, match in enumerate(result, 1):
                sim_pct = int(match['similarity'] * 100)
                self.logger.debug(f"  {i}. [{sim_pct}%] EN: {match['source'][:60]}... → KO: {match['target'][:60]}...")

        return result

    def get_exact_match(self, english_text: str) -> Optional[str]:
        """
        Get exact match for English text (fast lookup)

        Args:
            english_text: English text to lookup

        Returns:
            Korean translation if exact match found, None otherwise
        """
        return self.english_index.get(english_text.strip())

    def get_statistics(self) -> Dict:
        """
        Get statistics about loaded translation memory

        Returns:
            Dictionary with TM statistics
        """
        return {
            'total_units': len(self.translation_units),
            'unique_english_terms': len(self.english_index),
            'file_count': len(self.tmx_file_paths),
            'file_paths': self.tmx_file_paths,
        }


# Test functionality
if __name__ == "__main__":
    # Example usage
    tmx_files = [
        "/Users/won.suh/Downloads/linguistic asset/AVK_83-0060-002_Protocol v1.2_EN-KO.tmx",
        "/Users/won.suh/Downloads/linguistic asset/Avance Clinical CRO_ENUS-KOKR.tmx"
    ]

    print("🚀 Testing TMXMemoryLoaderENKO...")
    print("=" * 70)

    loader = TMXMemoryLoaderENKO(tmx_files)
    stats = loader.get_statistics()

    print(f"\n📊 Statistics:")
    print(f"  Total TU pairs: {stats['total_units']}")
    print(f"  Unique EN terms: {stats['unique_english_terms']}")
    print(f"  Files loaded: {stats['file_count']}")

    # Test exact match
    print(f"\n🔍 Testing exact match...")
    sample_en = list(loader.english_index.keys())[0] if loader.english_index else None
    if sample_en:
        result = loader.get_exact_match(sample_en)
        print(f"  EN: {sample_en}")
        print(f"  KO: {result}")

    # Test fuzzy matching
    print(f"\n🔎 Testing fuzzy matching...")
    if loader.translation_units:
        test_segment = loader.translation_units[0]['source'][:30] + "..."
        matches = loader.find_similar_segments(test_segment, top_k=3, threshold=0.70)
        print(f"  Query: {test_segment}")
        print(f"  Found {len(matches)} matches:")
        for i, match in enumerate(matches, 1):
            print(f"    {i}. [{int(match['similarity']*100)}%] {match['target'][:60]}")
