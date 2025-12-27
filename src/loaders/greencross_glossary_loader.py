#!/usr/bin/env python3
"""
GreenCross Glossary Loader
Loads and processes GreenCross Cell KOKR-ENUS glossary from Excel
Extracts 789 terms with Priority 1 ranking for regulatory translation
"""

import pandas as pd
from typing import List, Dict
import logging


class GreenCrossGlossaryLoader:
    """Load and process GreenCross 2025 glossary for clinical translation"""

    def __init__(self):
        self.setup_logging()

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_glossary(self, file_path: str) -> List[Dict]:
        """
        Load GreenCross glossary from Excel file

        Args:
            file_path: Path to GreenCross glossary Excel file

        Returns:
            List of glossary term dictionaries with format:
            {
                'korean': str,
                'english': str,
                'source': 'GreenCross_2025',
                'priority': 1,
                'alternative': str (optional),
                'context': str (optional)
            }
        """
        self.logger.info(f"📚 Loading GreenCross glossary from: {file_path}")

        try:
            # Read Excel file - skip first 2 rows (formatting/headers)
            # Column structure: Col 0 (blank), Col 1 (Korean), Col 2 (English),
            #                  Col 3 (Alternative), Col 4 (Comments), Col 5 (Context), Col 6 (Project No.)
            df = pd.read_excel(file_path, sheet_name='Glossary of Terms', header=None)

            self.logger.info(f"  Total rows in file: {len(df)}")
            self.logger.info(f"  Columns: {list(df.columns)}")

            glossary_terms = []
            seen_terms = set()  # Track for deduplication

            # Start from row 2 (skip first 2 header rows)
            for idx in range(2, len(df)):
                row = df.iloc[idx]

                # Extract columns
                korean = str(row[1]).strip() if pd.notna(row[1]) else None
                english = str(row[2]).strip() if pd.notna(row[2]) else None
                alternative = str(row[3]).strip() if pd.notna(row[3]) and len(row) > 3 else None
                context = str(row[5]).strip() if pd.notna(row[5]) and len(row) > 5 else None

                # Validate term has both Korean and English
                if not korean or not english or korean == 'nan' or english == 'nan':
                    continue

                # Skip if we've already seen this term
                term_key = f"{korean}|{english}"
                if term_key in seen_terms:
                    continue

                seen_terms.add(term_key)

                # Create term entry
                term_entry = {
                    'korean': korean,
                    'english': english,
                    'source': 'GreenCross_2025',
                    'priority': 1,  # Priority 1 - highest priority for GreenCross terms
                }

                # Add optional fields if available
                if alternative and alternative != 'nan':
                    term_entry['alternative'] = alternative
                if context and context != 'nan':
                    term_entry['context'] = context

                glossary_terms.append(term_entry)

                # Log sample of first few terms
                if len(glossary_terms) <= 5:
                    self.logger.debug(f"  Sample term {len(glossary_terms)}: {korean} → {english}")

            self.logger.info(f"✅ Loaded {len(glossary_terms)} unique GreenCross terms (Priority 1)")

            if len(glossary_terms) == 0:
                self.logger.warning("⚠️  No glossary terms extracted! Check file format.")

            return glossary_terms

        except Exception as e:
            self.logger.error(f"❌ Error loading GreenCross glossary: {e}")
            raise

    def merge_with_existing_glossary(self, greencross_terms: List[Dict],
                                     existing_terms: List[Dict]) -> List[Dict]:
        """
        Merge GreenCross glossary with existing combined glossary
        GreenCross terms (Priority 1) take precedence over existing terms (Priority 2)

        Args:
            greencross_terms: List of GreenCross terms (Priority 1)
            existing_terms: List of existing combined glossary terms (Priority 2)

        Returns:
            Merged list with deduplication (GreenCross preferred)
        """
        self.logger.info(f"🔀 Merging glossaries: {len(greencross_terms)} GreenCross + {len(existing_terms)} existing")

        # Create lookup of Korean terms from GreenCross (for deduplication)
        gc_korean_terms = {term['korean'] for term in greencross_terms}

        # Combine: GreenCross first, then existing terms not in GreenCross
        merged = greencross_terms.copy()
        added_count = 0

        for term in existing_terms:
            # Only add if not already in GreenCross glossary
            if term.get('korean') not in gc_korean_terms:
                merged.append(term)
                added_count += 1

        self.logger.info(f"✅ Merged result: {len(merged)} total terms")
        self.logger.info(f"  - GreenCross (Priority 1): {len(greencross_terms)}")
        self.logger.info(f"  - Existing (Priority 2): {added_count} (avoiding duplicates)")

        return merged
