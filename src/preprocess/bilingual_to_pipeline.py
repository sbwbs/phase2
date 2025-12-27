#!/usr/bin/env python3
"""
Bilingual Excel Preprocessor for Translation Pipeline

Validates and prepares bilingual Excel files for the translation pipeline.
Supports filtering by segment status and generating statistics.

Usage:
    python src/preprocess/bilingual_to_pipeline.py <input_file> [--output <output_file>] [--filter-untranslated]
"""

import os
import sys
import argparse
import uuid
from datetime import datetime
from typing import Optional, List, Dict
import pandas as pd

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BilingualPreprocessor:
    """Preprocess bilingual Excel files for translation pipeline."""

    # Expected column names (flexible matching)
    COLUMN_MAPPINGS = {
        'segment_id': ['Segment ID', 'SegmentID', 'ID', 'segment_id'],
        'segment_status': ['Segment status', 'Status', 'segment_status'],
        'source_segment': ['Source segment', 'Source', 'Korean', 'source_segment', 'KO'],
        'target_segment': ['Target segment', 'Target', 'English', 'target_segment', 'EN']
    }

    # Pipeline-required column names
    OUTPUT_COLUMNS = ['Segment ID', 'Segment status', 'Source segment', 'Target segment']

    def __init__(self, input_file: str):
        """
        Initialize preprocessor with input file.

        Args:
            input_file: Path to bilingual Excel file
        """
        self.input_file = input_file
        self.df = None
        self.column_map = {}

    def load(self) -> pd.DataFrame:
        """Load and validate the Excel file."""
        print(f"Loading: {self.input_file}")

        # Load Excel
        self.df = pd.read_excel(self.input_file)
        print(f"  Rows: {len(self.df)}")
        print(f"  Columns: {self.df.columns.tolist()}")

        # Map columns to standard names
        self._map_columns()

        return self.df

    def _map_columns(self):
        """Map input columns to standard column names."""
        for std_name, variants in self.COLUMN_MAPPINGS.items():
            for variant in variants:
                if variant in self.df.columns:
                    self.column_map[std_name] = variant
                    break

        # Check required columns
        required = ['source_segment']
        missing = [r for r in required if r not in self.column_map]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        print(f"  Column mapping: {self.column_map}")

    def validate(self) -> Dict:
        """
        Validate data quality and return statistics.

        Returns:
            Dict with validation statistics
        """
        stats = {
            'total_segments': len(self.df),
            'source_col': self.column_map.get('source_segment'),
            'target_col': self.column_map.get('target_segment'),
            'has_segment_id': 'segment_id' in self.column_map,
            'has_status': 'segment_status' in self.column_map,
        }

        # Count empty source/target
        source_col = self.column_map.get('source_segment')
        target_col = self.column_map.get('target_segment')

        if source_col:
            stats['empty_source'] = self.df[source_col].isna().sum()

        if target_col:
            stats['empty_target'] = self.df[target_col].isna().sum()
            stats['has_translation'] = len(self.df) - stats['empty_target']

        # Segment status breakdown
        status_col = self.column_map.get('segment_status')
        if status_col:
            stats['status_breakdown'] = self.df[status_col].value_counts().to_dict()

        # Detect language direction
        if source_col:
            sample = str(self.df[source_col].iloc[0])
            stats['source_language'] = 'Korean' if self._is_korean(sample) else 'English'

        if target_col and not self.df[target_col].isna().all():
            sample = str(self.df[target_col].dropna().iloc[0])
            stats['target_language'] = 'Korean' if self._is_korean(sample) else 'English'

        return stats

    def _is_korean(self, text: str) -> bool:
        """Check if text contains Korean characters."""
        for char in text:
            if '\uAC00' <= char <= '\uD7A3':  # Korean syllable block
                return True
        return False

    def normalize(self, generate_ids: bool = True) -> pd.DataFrame:
        """
        Normalize to pipeline-compatible format.

        Args:
            generate_ids: Generate UUIDs for missing Segment IDs

        Returns:
            Normalized DataFrame with standard columns
        """
        result = pd.DataFrame()

        # Segment ID
        if 'segment_id' in self.column_map:
            result['Segment ID'] = self.df[self.column_map['segment_id']]
        elif generate_ids:
            result['Segment ID'] = [str(uuid.uuid4()) for _ in range(len(self.df))]
        else:
            result['Segment ID'] = range(1, len(self.df) + 1)

        # Segment status
        if 'segment_status' in self.column_map:
            result['Segment status'] = self.df[self.column_map['segment_status']]
        else:
            result['Segment status'] = 'Not Translated'

        # Source segment
        result['Source segment'] = self.df[self.column_map['source_segment']]

        # Target segment
        if 'target_segment' in self.column_map:
            result['Target segment'] = self.df[self.column_map['target_segment']]
        else:
            result['Target segment'] = ''

        return result

    def filter_by_status(self, df: pd.DataFrame, statuses: List[str] = None,
                         untranslated_only: bool = False) -> pd.DataFrame:
        """
        Filter segments by status.

        Args:
            df: DataFrame to filter
            statuses: List of status values to include
            untranslated_only: Only include segments without translations

        Returns:
            Filtered DataFrame
        """
        if untranslated_only:
            # Filter where Target segment is empty/NaN
            mask = df['Target segment'].isna() | (df['Target segment'].astype(str).str.strip() == '')
            return df[mask].copy()

        if statuses:
            return df[df['Segment status'].isin(statuses)].copy()

        return df

    def save(self, df: pd.DataFrame, output_file: str):
        """Save processed DataFrame to Excel."""
        df.to_excel(output_file, index=False)
        print(f"Saved: {output_file} ({len(df)} segments)")


def print_stats(stats: Dict):
    """Pretty print validation statistics."""
    print("\n" + "=" * 50)
    print("Validation Statistics")
    print("=" * 50)

    print(f"\nTotal segments: {stats['total_segments']}")

    if 'source_language' in stats:
        print(f"Source language: {stats['source_language']}")
    if 'target_language' in stats:
        print(f"Target language: {stats['target_language']}")

    if 'empty_source' in stats:
        print(f"Empty source: {stats['empty_source']}")
    if 'empty_target' in stats:
        print(f"Empty target: {stats['empty_target']}")
    if 'has_translation' in stats:
        print(f"Has translation: {stats['has_translation']}")

    if 'status_breakdown' in stats:
        print("\nStatus breakdown:")
        for status, count in stats['status_breakdown'].items():
            print(f"  - {status}: {count}")


def main():
    parser = argparse.ArgumentParser(description='Preprocess bilingual Excel for translation pipeline')
    parser.add_argument('input_file', help='Input bilingual Excel file')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--filter-untranslated', action='store_true',
                        help='Only include segments without translations')
    parser.add_argument('--validate-only', action='store_true',
                        help='Only validate, do not output')
    args = parser.parse_args()

    # Initialize preprocessor
    preprocessor = BilingualPreprocessor(args.input_file)

    # Load and validate
    preprocessor.load()
    stats = preprocessor.validate()
    print_stats(stats)

    if args.validate_only:
        return

    # Normalize to pipeline format
    df = preprocessor.normalize()

    # Filter if requested
    if args.filter_untranslated:
        df = preprocessor.filter_by_status(df, untranslated_only=True)
        print(f"\nFiltered to {len(df)} untranslated segments")

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        base = os.path.splitext(args.input_file)[0]
        output_file = f"{base}_pipeline.xlsx"

    # Save
    preprocessor.save(df, output_file)

    print("\n✓ Preprocessing complete!")
    print(f"  Input: {args.input_file}")
    print(f"  Output: {output_file}")
    print(f"  Segments: {len(df)}")


if __name__ == "__main__":
    main()
