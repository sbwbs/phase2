#!/usr/bin/env python3
"""
Quick Excel file inspector to understand the data structure
"""

import pandas as pd
import sys

def inspect_excel_file(file_path):
    """Inspect Excel file structure"""
    try:
        print(f"📊 Inspecting: {file_path}")
        print("=" * 80)
        
        # Read Excel file
        xl_file = pd.ExcelFile(file_path)
        
        print(f"📋 Sheets found: {xl_file.sheet_names}")
        print()
        
        for sheet_name in xl_file.sheet_names:
            print(f"📄 Sheet: {sheet_name}")
            print("-" * 40)
            
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            print(f"Rows: {len(df)}")
            print(f"Columns: {list(df.columns)}")
            print()
            
            # Show first few rows
            print("First 3 rows:")
            print(df.head(3).to_string())
            print()
            print("=" * 80)
            print()
            
    except Exception as e:
        print(f"Error inspecting file: {e}")

if __name__ == "__main__":
    file_path = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/1_테스트용_Generated_Preview_KO-EN.xlsx"
    inspect_excel_file(file_path)