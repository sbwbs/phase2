#!/usr/bin/env python3
"""
SKBS Excel I/O Handler
Load segments from SK Bioscience bilingual Excel files and save translated results
Filters by 'Segment status' column (Not Translated / Translated (100%) / Translated (CM))
"""

import pandas as pd
from typing import Optional, Dict, Any
import logging
import os


class SKBSExcelHandler:
    """Handle Excel I/O for SKBS translation segments"""

    def __init__(self):
        self.setup_logging()
        self.original_df = None  # Store original Excel for merging results

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_segments_for_translation(self, excel_path: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Load segments from Excel file that need translation (Segment status == 'Not Translated')

        Args:
            excel_path: Path to Excel file
            limit: Maximum number of segments to load (None = all)

        Returns:
            DataFrame with columns: Segment ID, Segment status, Source segment, Target segment

        Column structure (SKBS bilingual format):
        - Column 1: Segment ID (UUID format)
        - Column 2: Segment status ('Not Translated' | 'Translated (100%)' | 'Translated (CM)')
        - Column 3: Source segment (Korean)
        - Column 4: Target segment (English - to be filled)
        """
        self.logger.info(f"📂 Loading SKBS segments from: {excel_path}")

        try:
            # Verify file exists
            if not os.path.exists(excel_path):
                raise FileNotFoundError(f"Excel file not found: {excel_path}")

            # Read Excel file
            df = pd.read_excel(excel_path)
            self.original_df = df.copy()  # Keep original for merging

            self.logger.info(f"  Total rows in file: {len(df)}")
            self.logger.info(f"  Columns: {list(df.columns)}")

            # Strip whitespace from Segment status column
            if 'Segment status' in df.columns:
                df['Segment status'] = df['Segment status'].str.strip()

            # Log segment status distribution
            if 'Segment status' in df.columns:
                status_counts = df['Segment status'].value_counts()
                self.logger.info(f"  Segment status distribution:")
                for status, count in status_counts.items():
                    self.logger.info(f"    - {status}: {count}")

            # Filter to segments with 'Not Translated' status
            not_translated_mask = df['Segment status'] == 'Not Translated'
            segments_to_translate = df[not_translated_mask].copy()

            self.logger.info(f"  Segments with 'Not Translated' status: {len(segments_to_translate)}")

            # Apply limit if specified
            if limit is not None:
                segments_to_translate = segments_to_translate.head(limit)
                self.logger.info(f"  Applied limit: {limit} segments")

            # Reset index for easier iteration
            segments_to_translate = segments_to_translate.reset_index(drop=True)

            self.logger.info(f"✅ Loaded {len(segments_to_translate)} segments for processing")

            # Validate required columns
            required_columns = ['Segment ID', 'Source segment']
            for col in required_columns:
                if col not in segments_to_translate.columns:
                    raise ValueError(f"Required column missing: {col}")

            return segments_to_translate

        except Exception as e:
            self.logger.error(f"❌ Error loading segments: {e}")
            raise

    def save_translated_segments(self,
                                translations_df: pd.DataFrame,
                                output_path: str,
                                original_df: Optional[pd.DataFrame] = None) -> None:
        """
        Save translated segments back to Excel file with original structure preserved

        Args:
            translations_df: DataFrame with translations
                            Must contain: Segment ID, Target segment
            output_path: Output Excel file path
            original_df: Original DataFrame to merge translations into (uses stored if None)
        """
        self.logger.info(f"💾 Saving translations to: {output_path}")

        try:
            # Use stored original or provided one
            base_df = original_df if original_df is not None else self.original_df

            if base_df is None:
                raise ValueError("No original DataFrame available for merging")

            # Create output DataFrame by copying original
            output_df = base_df.copy()

            # Create lookup of translations by Segment ID
            trans_lookup = {}
            for _, row in translations_df.iterrows():
                seg_id = row['Segment ID']
                translation = row.get('Target segment', row.get('translation', ''))
                trans_lookup[seg_id] = translation

            # Merge translations into output DataFrame
            translations_added = 0
            for idx, row in output_df.iterrows():
                seg_id = row['Segment ID']
                if seg_id in trans_lookup and trans_lookup[seg_id]:
                    output_df.at[idx, 'Target segment'] = trans_lookup[seg_id]
                    # Update status to reflect translation
                    output_df.at[idx, 'Segment status'] = 'Translated (AI)'
                    translations_added += 1

            self.logger.info(f"  Merged {translations_added} translations")

            # Create output directory if needed
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # Save to Excel
            output_df.to_excel(output_path, index=False, engine='openpyxl')

            self.logger.info(f"✅ Saved {len(output_df)} segments to: {output_path}")

            # Log file size
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            self.logger.info(f"  File size: {file_size_mb:.2f} MB")

            # Log translation coverage
            total_segments = len(output_df)
            translated_count = output_df['Target segment'].notna().sum()
            coverage_pct = (translated_count / total_segments * 100) if total_segments > 0 else 0
            self.logger.info(f"  Translation coverage: {translated_count}/{total_segments} ({coverage_pct:.1f}%)")

        except Exception as e:
            self.logger.error(f"❌ Error saving translations: {e}")
            raise

    def get_segment_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get statistics about loaded segments

        Args:
            df: Segments DataFrame

        Returns:
            Dictionary with segment statistics
        """
        stats = {
            'total_segments': len(df),
            'average_source_length': df['Source segment'].str.len().mean() if len(df) > 0 else 0,
            'max_source_length': df['Source segment'].str.len().max() if len(df) > 0 else 0,
            'min_source_length': df['Source segment'].str.len().min() if len(df) > 0 else 0,
        }

        # Count segments with CAT tags
        if 'Source segment' in df.columns:
            has_tags = df['Source segment'].str.contains(r'<\d+/?>', regex=True, na=False)
            stats['segments_with_tags'] = has_tags.sum()

        # Status distribution if available
        if 'Segment status' in df.columns:
            stats['status_distribution'] = df['Segment status'].value_counts().to_dict()

        return stats


# Test function
if __name__ == "__main__":
    # Test with adult consent form
    handler = SKBSExcelHandler()

    adult_file = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Bilingual/별첨 1-1) NBP608_004_시험대상자설명서 및 서면 동의서_V1.0.xlsx"
    child_file = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Bilingual/별첨 1-3) NBP608_004_소아용 연구참여 승낙서_V1.0.xlsx"

    print("\n=== Testing Adult Consent Form ===")
    adult_df = handler.load_segments_for_translation(adult_file, limit=5)
    print(f"\nFirst 5 segments:")
    print(adult_df[['Segment ID', 'Segment status', 'Source segment']].head())
    print(f"\nStatistics: {handler.get_segment_statistics(adult_df)}")

    print("\n=== Testing Children's Assent Form ===")
    child_df = handler.load_segments_for_translation(child_file, limit=5)
    print(f"\nFirst 5 segments:")
    print(child_df[['Segment ID', 'Segment status', 'Source segment']].head())
    print(f"\nStatistics: {handler.get_segment_statistics(child_df)}")
