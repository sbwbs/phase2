#!/usr/bin/env python3
"""
Protocol Glossary Loader for EN-KO Translation
Loads and merges protocol-specific and general EN-KO glossaries
Implements priority-based deduplication
"""

import pandas as pd
import os
import logging
from typing import List, Dict, Tuple, Optional


class ProtocolGlossaryLoaderENKO:
    """Load and merge protocol-specific and general EN-KO glossaries with priority management"""

    def __init__(self):
        self.setup_logging()
        self.protocol_glossary = []
        self.combined_glossary = []
        self.merged_glossary = []

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_protocol_glossary(self, excel_path: str) -> List[Dict]:
        """
        Load protocol-specific glossary from Excel file
        Expected format: [No., English, Korean] columns

        Args:
            excel_path: Path to protocol glossary Excel file (24-term Avance glossary)

        Returns:
            List of glossary terms with metadata
        """
        self.logger.info(f"📚 Loading protocol glossary: {excel_path}")

        try:
            df = pd.read_excel(excel_path, sheet_name=0)
            self.logger.info(f"  Found {len(df)} rows, columns: {list(df.columns)}")

            terms = []

            # Expected columns: No., English, Korean
            for idx, row in df.iterrows():
                if pd.notna(row.get('English', '')) and pd.notna(row.get('Korean', '')):
                    english = str(row['English']).strip()
                    korean = str(row['Korean']).strip()

                    if english and korean:
                        terms.append({
                            'english': english,
                            'korean': korean,
                            'source': 'Protocol_Glossary',
                            'priority': 1,  # Highest priority
                            'term_id': idx,
                        })

            self.logger.info(f"✅ Loaded {len(terms)} terms from protocol glossary")
            self.protocol_glossary = terms
            return terms

        except Exception as e:
            self.logger.error(f"❌ Error loading protocol glossary: {e}")
            return []

    def load_combined_glossary(self, excel_path: str) -> List[Dict]:
        """
        Load combined EN-KO glossary from existing pipeline data
        Expected: 419-term combined glossary from multiple sources

        Args:
            excel_path: Path to combined glossary Excel file

        Returns:
            List of glossary terms with metadata
        """
        self.logger.info(f"📚 Loading combined glossary: {excel_path}")

        try:
            # Try to read the file - it might have different structures
            xls = pd.ExcelFile(excel_path)
            self.logger.info(f"  Sheets: {xls.sheet_names}")

            terms = []

            # Try to find relevant sheets
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
                self.logger.info(f"  Sheet '{sheet_name}': {len(df)} rows, columns: {list(df.columns)}")

                # Detect English and Korean columns
                en_col = None
                ko_col = None

                for col in df.columns:
                    if 'english' in str(col).lower() or col == 'English':
                        en_col = col
                    elif 'korean' in str(col).lower() or col == 'Korean':
                        ko_col = col
                    elif 'ko' in str(col).lower():
                        ko_col = col
                    elif 'en' in str(col).lower():
                        en_col = col

                if en_col and ko_col:
                    for idx, row in df.iterrows():
                        if pd.notna(row.get(en_col, '')) and pd.notna(row.get(ko_col, '')):
                            english = str(row[en_col]).strip()
                            korean = str(row[ko_col]).strip()

                            if english and korean:
                                terms.append({
                                    'english': english,
                                    'korean': korean,
                                    'source': f'Combined_{sheet_name}',
                                    'priority': 2,  # Lower priority than protocol
                                    'term_id': f"{sheet_name}_{idx}",
                                })

            self.logger.info(f"✅ Loaded {len(terms)} terms from combined glossary")
            self.combined_glossary = terms
            return terms

        except Exception as e:
            self.logger.error(f"❌ Error loading combined glossary: {e}")
            return []

    def merge_glossaries(self) -> List[Dict]:
        """
        Merge protocol and combined glossaries with priority-based deduplication

        Strategy:
        1. Protocol glossary (Priority 1) - protocol-specific 24 terms
        2. Combined glossary (Priority 2) - existing 419 terms
        3. Deduplicate by English term (Priority 1 overrides Priority 2)

        Returns:
            Merged list of unique glossary terms
        """
        self.logger.info("🔄 Merging glossaries with priority deduplication...")

        merged = {}  # Use dict with english as key for deduplication

        # First pass: Add protocol glossary (highest priority)
        for term in self.protocol_glossary:
            english = term['english'].lower()  # Case-insensitive matching
            if english not in merged:
                merged[english] = term
            else:
                self.logger.debug(f"  Skipping duplicate (lower priority): {english}")

        initial_count = len(merged)

        # Second pass: Add combined glossary (lower priority)
        for term in self.combined_glossary:
            english = term['english'].lower()
            if english not in merged:
                merged[english] = term

        added_count = len(merged) - initial_count

        self.merged_glossary = list(merged.values())

        self.logger.info(f"✅ Merged glossary statistics:")
        self.logger.info(f"  Protocol terms (Priority 1): {len(self.protocol_glossary)}")
        self.logger.info(f"  Combined terms (Priority 2): {len(self.combined_glossary)}")
        self.logger.info(f"  After deduplication: {len(self.merged_glossary)}")
        self.logger.info(f"  New terms from combined: {added_count}")

        return self.merged_glossary

    def save_merged_glossary(self, output_path: str) -> None:
        """
        Save merged glossary to Excel file

        Args:
            output_path: Output Excel file path
        """
        if not self.merged_glossary:
            self.logger.warning("⚠️  No merged glossary to save!")
            return

        self.logger.info(f"💾 Saving merged glossary to {output_path}")

        try:
            # Create DataFrame
            df_merged = pd.DataFrame(self.merged_glossary)

            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Save to Excel with multiple sheets
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Main merged glossary
                df_merged.to_excel(writer, sheet_name='Merged_Glossary', index=False)

                # Protocol terms only
                df_protocol = df_merged[df_merged['source'] == 'Protocol_Glossary']
                if len(df_protocol) > 0:
                    df_protocol.to_excel(writer, sheet_name='Protocol_Terms', index=False)

                # Combined terms only
                df_combined = df_merged[df_merged['source'].str.contains('Combined', na=False)]
                if len(df_combined) > 0:
                    df_combined.to_excel(writer, sheet_name='Combined_Terms', index=False)

                # Summary sheet
                summary_data = {
                    'Metric': [
                        'Total Terms',
                        'Protocol Terms (Priority 1)',
                        'Combined Terms (Priority 2)',
                        'Generation Timestamp'
                    ],
                    'Value': [
                        len(self.merged_glossary),
                        len(self.protocol_glossary),
                        len(self.combined_glossary),
                        pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
                    ]
                }
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, sheet_name='Summary', index=False)

            self.logger.info(f"✅ Merged glossary saved successfully")
            self.logger.info(f"  Total terms: {len(self.merged_glossary)}")
            self.logger.info(f"  File: {output_path}")

        except Exception as e:
            self.logger.error(f"❌ Error saving merged glossary: {e}")
            raise

    def get_glossary_dict(self) -> Dict[str, str]:
        """
        Get merged glossary as simple English→Korean dictionary for quick lookup

        Returns:
            Dictionary with English terms as keys and Korean translations as values
        """
        glossary_dict = {}

        for term in self.merged_glossary:
            english = term['english']
            korean = term['korean']

            # Store both exact and lowercase for flexible matching
            glossary_dict[english] = korean
            glossary_dict[english.lower()] = korean

        return glossary_dict

    def search_terms(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        Search glossary for relevant terms based on query text

        Args:
            query: Search query (English text)
            top_k: Number of top matches to return

        Returns:
            List of matching glossary terms
        """
        from rapidfuzz import fuzz

        if not query or not self.merged_glossary:
            return []

        query_clean = query.lower().strip()
        matches = []

        # Search through merged glossary
        for term in self.merged_glossary:
            english = term['english'].lower()

            # Calculate similarity
            similarity = fuzz.token_set_ratio(query_clean, english) / 100.0

            if similarity >= 0.5:  # 50% threshold for search
                matches.append({
                    **term,
                    'similarity': similarity
                })

        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x['similarity'], reverse=True)

        return matches[:top_k]

    def get_statistics(self) -> Dict:
        """Get statistics about the merged glossary"""
        return {
            'total_terms': len(self.merged_glossary),
            'protocol_terms': len(self.protocol_glossary),
            'combined_terms': len(self.combined_glossary),
            'unique_sources': len(set([t['source'] for t in self.merged_glossary])),
        }


def main():
    """Main function for testing and demonstrating glossary loading"""
    print("🚀 Protocol EN-KO Glossary Loader Test")
    print("=" * 70)

    loader = ProtocolGlossaryLoaderENKO()

    # Load glossaries
    protocol_path = "/Users/won.suh/Downloads/linguistic asset/Avance Clinical CRO_ZE46-0134-0002_EN-KO_Glossary_2025-06-10.xlsx"
    combined_path = "/Users/won.suh/Project/translate-ai/phase2/data/combined_en_ko_glossary.xlsx"

    print("\n📚 Loading glossaries...")
    protocol_terms = loader.load_protocol_glossary(protocol_path)

    # Try to load combined glossary if it exists
    if os.path.exists(combined_path):
        combined_terms = loader.load_combined_glossary(combined_path)
    else:
        print(f"⚠️  Combined glossary not found at {combined_path}")
        combined_terms = []

    # Merge glossaries
    print("\n🔄 Merging...")
    merged = loader.merge_glossaries()

    # Save merged glossary
    output_path = "/Users/won.suh/Project/translate-ai/phase2/data/protocol_merged_glossary_en_ko.xlsx"
    print(f"\n💾 Saving...")
    loader.save_merged_glossary(output_path)

    # Print statistics
    print("\n📊 Statistics:")
    stats = loader.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Print sample terms
    print("\n📝 Sample terms (first 10):")
    for i, term in enumerate(merged[:10], 1):
        print(f"  {i}. {term['english']} → {term['korean']} ({term['source']})")

    print("\n✨ Glossary loading complete!")


if __name__ == "__main__":
    main()
