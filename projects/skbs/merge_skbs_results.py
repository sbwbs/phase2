#!/usr/bin/env python3
"""
Merge SKBS Parallel Translation Results
Combines range-based output files into final merged Excel files
"""

import os
import sys
import pandas as pd
from datetime import datetime
import glob

# Paths
OUTPUT_DIR = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Output"
ADULT_FILE = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Bilingual/별첨 1-1) NBP608_004_시험대상자설명서 및 서면 동의서_V1.0.xlsx"
CHILD_FILE = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Bilingual/별첨 1-3) NBP608_004_소아용 연구참여 승낙서_V1.0.xlsx"


def merge_form_results(form_type: str, original_file: str):
    """Merge range files for a form type"""
    print(f"\n{'='*60}")
    print(f"Merging {form_type} form results...")
    print(f"{'='*60}")

    # Find range files for this form
    pattern = os.path.join(OUTPUT_DIR, f"SKBS_{form_type}_range_*.xlsx")
    range_files = sorted(glob.glob(pattern))

    if not range_files:
        print(f"❌ No range files found for {form_type}")
        return None

    print(f"Found {len(range_files)} range files:")
    for f in range_files:
        print(f"  - {os.path.basename(f)}")

    # Load and combine all range translations
    all_translations = []
    for f in range_files:
        df = pd.read_excel(f)
        print(f"  Loaded {len(df)} segments from {os.path.basename(f)}")
        all_translations.append(df)

    combined_df = pd.concat(all_translations, ignore_index=True)
    print(f"\nTotal translated segments: {len(combined_df)}")

    # Load original file
    print(f"\nLoading original file: {os.path.basename(original_file)}")
    original_df = pd.read_excel(original_file)

    # Strip whitespace from Segment status
    original_df['Segment status'] = original_df['Segment status'].str.strip()

    print(f"Original file has {len(original_df)} segments")

    # Create translation lookup
    trans_lookup = {}
    for _, row in combined_df.iterrows():
        seg_id = row['Segment ID']
        translation = row.get('Target segment', '')
        if translation and not str(translation).startswith('[ERROR'):
            trans_lookup[seg_id] = translation

    print(f"Valid translations: {len(trans_lookup)}")

    # Merge into original
    output_df = original_df.copy()
    merged_count = 0

    for idx, row in output_df.iterrows():
        seg_id = row['Segment ID']
        if seg_id in trans_lookup:
            output_df.at[idx, 'Target segment'] = trans_lookup[seg_id]
            output_df.at[idx, 'Segment status'] = 'Translated (AI)'
            merged_count += 1

    print(f"Merged {merged_count} translations into original")

    # Calculate coverage
    translated_count = output_df['Target segment'].notna().sum()
    total_count = len(output_df)
    coverage_pct = (translated_count / total_count * 100) if total_count > 0 else 0

    print(f"Translation coverage: {translated_count}/{total_count} ({coverage_pct:.1f}%)")

    # Save merged file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    form_name = "adult_consent" if form_type == "adult" else "child_assent"
    output_file = os.path.join(OUTPUT_DIR, f"SKBS_{form_name}_FINAL_{timestamp}.xlsx")

    output_df.to_excel(output_file, index=False, engine='openpyxl')
    print(f"\n✅ Saved merged file: {output_file}")

    # File size
    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"   File size: {file_size_mb:.2f} MB")

    return output_file


def main():
    """Merge all SKBS results"""
    print("\n" + "=" * 60)
    print("🔄 SKBS Results Merger")
    print("=" * 60)

    # Merge adult form
    adult_result = merge_form_results("adult", ADULT_FILE)

    # Merge child form
    child_result = merge_form_results("child", CHILD_FILE)

    print("\n" + "=" * 60)
    print("📋 Summary")
    print("=" * 60)

    if adult_result:
        print(f"✅ Adult form: {os.path.basename(adult_result)}")
    else:
        print("❌ Adult form: Not merged")

    if child_result:
        print(f"✅ Child form: {os.path.basename(child_result)}")
    else:
        print("❌ Child form: Not merged")


if __name__ == "__main__":
    main()
