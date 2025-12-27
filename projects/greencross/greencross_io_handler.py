#!/usr/bin/env python3
"""
GreenCross Excel I/O Handler
Load segments from review Excel file and save translated results
Handles Excel file structure preservation and segment filtering
"""

import pandas as pd
from typing import Optional
import logging
import os


class GreenCrossExcelHandler:
    """Handle Excel I/O for GreenCross translation segments"""

    def __init__(self):
        self.setup_logging()
        self.original_df = None  # Store original Excel for merging results

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_segments_for_translation(self, excel_path: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Load segments from Excel file that need translation (empty Target segment)

        Args:
            excel_path: Path to Excel file
            limit: Maximum number of segments to load (None = all)

        Returns:
            DataFrame with columns: Segment ID, Segment status, Source segment
        """
        self.logger.info(f"📂 Loading segments from: {excel_path}")

        try:
            # Verify file exists
            if not os.path.exists(excel_path):
                raise FileNotFoundError(f"Excel file not found: {excel_path}")

            # Read Excel file
            df = pd.read_excel(excel_path)
            self.original_df = df.copy()  # Keep original for merging

            self.logger.info(f"  Total rows in file: {len(df)}")
            self.logger.info(f"  Columns: {list(df.columns)}")

            # Filter to segments with empty Target segment (need translation)
            empty_target = df['Target segment'].isna()
            segments_to_translate = df[empty_target].copy()

            self.logger.info(f"  Segments needing translation: {len(segments_to_translate)}")

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
                translation = row['Target segment']
                trans_lookup[seg_id] = translation

            # Merge translations into output DataFrame
            translations_added = 0
            for idx, row in output_df.iterrows():
                seg_id = row['Segment ID']
                if seg_id in trans_lookup:
                    output_df.at[idx, 'Target segment'] = trans_lookup[seg_id]
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

        except Exception as e:
            self.logger.error(f"❌ Error saving translations: {e}")
            raise

    def get_segment_statistics(self, df: pd.DataFrame) -> dict:
        """
        Get statistics about loaded segments

        Args:
            df: Segments DataFrame

        Returns:
            Dictionary with segment statistics
        """
        return {
            'total_segments': len(df),
            'average_source_length': df['Source segment'].str.len().mean(),
            'max_source_length': df['Source segment'].str.len().max(),
            'min_source_length': df['Source segment'].str.len().min(),
        }
