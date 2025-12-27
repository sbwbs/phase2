#!/usr/bin/env python3
"""
Excel to TMX Converter
Converts SKBS bilingual Excel files to TMX 1.4 format for CAT tool import
"""

import os
import pandas as pd
from datetime import datetime
from xml.etree import ElementTree as ET
from xml.dom import minidom
import html


def escape_xml(text: str) -> str:
    """Escape special XML characters"""
    if not text or pd.isna(text):
        return ""
    return html.escape(str(text))


def convert_excel_to_tmx(excel_path: str, output_path: str = None,
                         src_lang: str = "ko-KR", tgt_lang: str = "en-US",
                         src_col: str = "Source segment",
                         tgt_col: str = "Target segment") -> str:
    """
    Convert SKBS bilingual Excel to TMX 1.4 format

    Args:
        excel_path: Path to input Excel file
        output_path: Path for output TMX file (default: same as Excel with .tmx extension)
        src_lang: Source language code (default: ko-KR)
        tgt_lang: Target language code (default: en-US)
        src_col: Name of source column in Excel
        tgt_col: Name of target column in Excel

    Returns:
        Path to created TMX file
    """
    print(f"\n{'='*60}")
    print(f"Converting Excel to TMX")
    print(f"{'='*60}")
    print(f"Input: {os.path.basename(excel_path)}")

    # Read Excel
    df = pd.read_excel(excel_path)
    print(f"Total rows: {len(df)}")

    # Filter rows with both source and target
    valid_rows = df[
        df[src_col].notna() &
        df[tgt_col].notna() &
        (df[src_col].astype(str).str.strip() != '') &
        (df[tgt_col].astype(str).str.strip() != '')
    ]
    print(f"Valid bilingual pairs: {len(valid_rows)}")

    # Generate output path if not specified
    if output_path is None:
        output_path = os.path.splitext(excel_path)[0] + ".tmx"

    # Build TMX structure
    tmx_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE tmx SYSTEM "tmx14.dtd">
<tmx version="1.4">
  <header
    creationtool="SKBS Translation Pipeline"
    creationtoolversion="1.0"
    datatype="PlainText"
    segtype="sentence"
    adminlang="en-US"
    srclang="{src_lang}"
    o-tmf="SKBS"
    creationdate="{datetime.now().strftime('%Y%m%dT%H%M%SZ')}">
  </header>
  <body>
'''

    # Add translation units
    tu_count = 0
    for _, row in valid_rows.iterrows():
        src_text = escape_xml(str(row[src_col]).strip())
        tgt_text = escape_xml(str(row[tgt_col]).strip())

        if src_text and tgt_text:
            tmx_content += f'''    <tu>
      <tuv xml:lang="{src_lang}">
        <seg>{src_text}</seg>
      </tuv>
      <tuv xml:lang="{tgt_lang}">
        <seg>{tgt_text}</seg>
      </tuv>
    </tu>
'''
            tu_count += 1

    tmx_content += '''  </body>
</tmx>
'''

    # Write TMX file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(tmx_content)

    file_size = os.path.getsize(output_path) / 1024
    print(f"\n✅ TMX created: {os.path.basename(output_path)}")
    print(f"   Translation units: {tu_count}")
    print(f"   File size: {file_size:.1f} KB")

    return output_path


def main():
    """Convert SKBS final files to TMX"""
    OUTPUT_DIR = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Output"

    # Find the latest FINAL files
    import glob

    adult_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "SKBS_adult_consent_FINAL_*.xlsx")))
    child_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "SKBS_child_assent_FINAL_*.xlsx")))

    print("\n" + "=" * 60)
    print("SKBS Excel to TMX Converter")
    print("=" * 60)

    # Convert adult form
    if adult_files:
        adult_excel = adult_files[-1]  # Latest
        adult_tmx = convert_excel_to_tmx(adult_excel)
    else:
        print("❌ No adult consent FINAL file found")
        adult_tmx = None

    # Convert child form
    if child_files:
        child_excel = child_files[-1]  # Latest
        child_tmx = convert_excel_to_tmx(child_excel)
    else:
        print("❌ No child assent FINAL file found")
        child_tmx = None

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    if adult_tmx:
        print(f"✅ Adult: {os.path.basename(adult_tmx)}")
    if child_tmx:
        print(f"✅ Child: {os.path.basename(child_tmx)}")

    print(f"\n📁 Output location: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
