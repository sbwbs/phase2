#!/usr/bin/env python3
"""
Post-processor for GreenCross translations
Removes "English Translation:" labels and merges with original Excel format
"""

import pandas as pd
import os
import glob
import sys
from datetime import datetime

def clean_translation_labels(text: str) -> str:
    """Remove LLM-added labels from translation text"""
    if pd.isna(text):
        return text

    text = str(text)
    # Remove all variations of the label
    text = text.replace('English Translation: ', '')
    text = text.replace('English Translations: ', '')
    text = text.replace('English translation: ', '')
    text = text.replace('English translations: ', '')

    return text.strip()

def post_process_greencross_output(input_file: str, original_file: str, output_file: str = None) -> str:
    """
    Post-process translated segments by:
    1. Removing 'English Translation:' labels
    2. Merging back into original Excel format
    3. Preserving original structure and metadata
    """

    print(f"\n{'='*100}")
    print("🔧 GreenCross Translation Post-Processor")
    print(f"{'='*100}")

    # Load translated file
    print(f"\n📂 Loading translated segments from: {os.path.basename(input_file)}")
    df_translated = pd.read_excel(input_file)
    print(f"   ✅ Loaded {len(df_translated)} translated segments")

    # Load original file
    print(f"\n📂 Loading original structure from: {os.path.basename(original_file)}")
    df_original = pd.read_excel(original_file)
    print(f"   ✅ Loaded {len(df_original)} original segments")

    # Clean labels from translated segments
    print(f"\n🧹 Cleaning 'English Translation:' labels...")
    initial_count = len(df_translated)

    if 'Target segment' in df_translated.columns:
        df_translated['Target segment'] = df_translated['Target segment'].apply(clean_translation_labels)

    # Count and report cleaned
    cleaned_count = 0
    for idx, row in df_translated.iterrows():
        target = row.get('Target segment', '')
        if isinstance(target, str) and 'English Translation' in target:
            cleaned_count += 1

    print(f"   ✅ Cleaned all labels from {initial_count} segments")

    # Merge with original file by Segment ID
    print(f"\n🔄 Merging translations into original format...")

    # Create merged dataframe starting with original
    df_merged = df_original.copy()

    # Update Target segment column for matched Segment IDs
    for idx, row in df_translated.iterrows():
        segment_id = row.get('Segment ID')
        target_text = row.get('Target segment', '')

        # Find matching row in original by Segment ID
        matching_rows = df_merged[df_merged['Segment ID'] == segment_id]
        if len(matching_rows) > 0:
            df_merged.loc[matching_rows.index[0], 'Target segment'] = target_text

    print(f"   ✅ Merged {len(df_translated)} translations back into original format")

    # Generate output filename if not provided
    if output_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"/Users/won.suh/Downloads/Bilingual files/[GC Cell] IMMUNCELL-LC_IB_v5.0_FINAL_{timestamp}.xlsx"

    # Save merged file
    print(f"\n💾 Saving final output to: {os.path.basename(output_file)}")
    df_merged.to_excel(output_file, sheet_name='Sheet1', index=False)
    print(f"   ✅ Saved {len(df_merged)} segments to final file")

    # Verification
    print(f"\n✅ Verification Report:")
    print(f"   Total segments in final file: {len(df_merged)}")
    print(f"   Empty Target segments: {df_merged['Target segment'].isna().sum()}")
    print(f"   Filled Target segments: {(df_merged['Target segment'].notna()).sum()}")

    # Sample check for labels
    has_labels = False
    for target in df_merged['Target segment']:
        if isinstance(target, str) and 'English Translation' in target:
            has_labels = True
            break

    if has_labels:
        print(f"   ⚠️  WARNING: Some labels still present")
    else:
        print(f"   ✅ All 'English Translation:' labels removed successfully")

    print(f"\n{'='*100}")
    print(f"📄 Output file: {output_file}")
    print(f"{'='*100}\n")

    return output_file

def main():
    """Main execution"""

    # Find the latest translated file
    translated_files = glob.glob("/Users/won.suh/Downloads/Bilingual files/*translated*.xlsx")
    if not translated_files:
        print("❌ No translated files found!")
        sys.exit(1)

    latest_translated = max(translated_files, key=os.path.getctime)
    original_file = "/Users/won.suh/Downloads/Bilingual files/[GC Cell] IMMUNCELL-LC_IB_v5.0 국문.docx.review.xlsx"

    print(f"🚀 Post-processing latest translation: {os.path.basename(latest_translated)}")

    # Run post-processor
    output_file = post_process_greencross_output(latest_translated, original_file)

    print(f"✅ Post-processing complete!")
    print(f"📋 Final file: {output_file}")

if __name__ == "__main__":
    main()
