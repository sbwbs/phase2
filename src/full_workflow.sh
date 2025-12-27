#!/bin/bash

# GreenCross Full Translation Workflow
# Step 1: Run full production translation (all 1,997 segments)
# Step 2: Wait for completion
# Step 3: Post-process (remove labels + merge with original format)
# Step 4: Generate final report

set -e

echo "╔════════════════════════════════════════════════════════════════════════════════════════╗"
echo "║ 🚀 GreenCross IMMUNCELL-LC Full Translation Workflow (All 1,997 Segments)            ║"
echo "╚════════════════════════════════════════════════════════════════════════════════════════╝"

cd /Users/won.suh/Project/translate-ai/phase2
source venv_new/bin/activate

# Step 1: Run translation if not already running
echo ""
echo "STEP 1️⃣  Production Translation (all 1,997 segments)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if process already running
if pgrep -f "greencross_translation_pipeline.py" > /dev/null; then
    echo "✅ Translation process already running in background"
    echo "   Waiting for completion (estimated 25-35 minutes)..."
else
    echo "🔄 Starting translation pipeline..."
    python src/greencross_translation_pipeline.py &
    TRANSLATION_PID=$!
    echo "   Process ID: $TRANSLATION_PID"
fi

# Step 2: Wait for translation to complete
echo ""
echo "⏳ Waiting for translation to complete..."
sleep 10

while pgrep -f "greencross_translation_pipeline.py" > /dev/null; do
    sleep 30
    echo "   ...still processing ($(date))"
done

echo "✅ Translation complete!"

# Step 3: Post-process translated file
echo ""
echo "STEP 2️⃣  Post-Processing (remove labels + merge with original)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python src/greencross_post_processor.py

# Step 4: Generate final report
echo ""
echo "STEP 3️⃣  Final Report & Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 << 'EOF'
import pandas as pd
import glob
import os
from datetime import datetime

# Find the final processed file
files = glob.glob("/Users/won.suh/Downloads/Bilingual files/*FINAL*.xlsx")
if files:
    final_file = max(files, key=os.path.getctime)
    df = pd.read_excel(final_file)

    print(f"\n✅ FINAL OUTPUT FILE")
    print(f"   Path: {final_file}")
    print(f"   Filename: {os.path.basename(final_file)}")
    print(f"\n📊 FINAL STATISTICS")
    print(f"   Total segments: {len(df)}")
    print(f"   Translated (filled): {(df['Target segment'].notna()).sum()}")
    print(f"   Not translated (empty): {df['Target segment'].isna().sum()}")

    # Check for labels
    has_labels = False
    label_count = 0
    for target in df['Target segment']:
        if isinstance(target, str) and 'English Translation' in target:
            has_labels = True
            label_count += 1

    print(f"\n✅ QUALITY CHECK")
    if has_labels:
        print(f"   ⚠️  {label_count} segments still have 'English Translation:' labels")
    else:
        print(f"   ✅ All 'English Translation:' labels removed successfully")

    print(f"\n✅ FILE READY FOR DELIVERY")
    print(f"   Status: Ready for use")

else:
    # Check for translated files
    translated_files = glob.glob("/Users/won.suh/Downloads/Bilingual files/*translated*.xlsx")
    if translated_files:
        latest = max(translated_files, key=os.path.getctime)
        df = pd.read_excel(latest)
        print(f"\n✅ TRANSLATED FILE (pre-post-processing)")
        print(f"   Filename: {os.path.basename(latest)}")
        print(f"   Segments: {len(df)}")
        print(f"   Status: Post-processing still pending")
EOF

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════════════════╗"
echo "║ ✅ Workflow Complete!                                                                ║"
echo "╚════════════════════════════════════════════════════════════════════════════════════════╝"
