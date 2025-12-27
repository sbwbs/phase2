#!/usr/bin/env python3
"""
Merge parallel translation results back into original template
Combines 4 range-based output files into single consolidated result
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

class ParallelResultsMerger:
    """Merge parallel translation results into template"""

    def __init__(self):
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

    def setup_logging(self):
        """Setup logging"""
        log_dir = "/Users/won.suh/Project/translate-ai/phase2/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = f"{log_dir}/merge_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def load_template(self) -> pd.DataFrame:
        """Load original template"""
        template_path = "/Users/won.suh/Downloads/83-0060-0002_Protocol v.2.0_28Nov2025.docx.review (1).xlsx"

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")

        self.logger.info(f"📂 Loading template: {template_path}")
        df = pd.read_excel(template_path)
        self.logger.info(f"   Loaded {len(df)} rows from template")
        return df

    def load_parallel_results(self) -> pd.DataFrame:
        """Load and combine all 4 parallel result files"""
        downloads_dir = "/Users/won.suh/Downloads/"
        pattern = "Protocol_EN_KO_range_*.xlsx"

        files = sorted(Path(downloads_dir).glob(pattern), key=lambda p: p.stat().st_mtime)

        if len(files) < 4:
            raise FileNotFoundError(f"Expected 4 result files, found {len(files)}")

        self.logger.info(f"📂 Loading {len(files)} parallel result files:")

        all_results = []
        total_rows = 0

        for i, file_path in enumerate(files, 1):
            df = pd.read_excel(file_path)
            self.logger.info(f"   {i}. {file_path.name}: {len(df)} rows")
            all_results.append(df)
            total_rows += len(df)

        # Combine all results
        combined = pd.concat(all_results, ignore_index=True)
        self.logger.info(f"✅ Combined {total_rows} rows from all files")

        return combined

    def merge_into_template(self, template_df: pd.DataFrame, results_df: pd.DataFrame) -> pd.DataFrame:
        """Merge translation results back into template"""
        self.logger.info("\n🔄 MERGING RESULTS INTO TEMPLATE...")

        # Create a working copy of template
        merged_df = template_df.copy()

        # Create a mapping of Segment ID -> Target segment from results
        results_map = {}
        for _, row in results_df.iterrows():
            segment_id = row['Segment ID']
            target = row['Target segment']
            results_map[segment_id] = target

        self.logger.info(f"   Created mapping with {len(results_map)} translations")

        # Update template with translations
        updated_count = 0
        skipped_count = 0

        for idx, row in merged_df.iterrows():
            segment_id = row['Segment ID']

            if segment_id in results_map:
                merged_df.at[idx, 'Target segment'] = results_map[segment_id]
                updated_count += 1
            else:
                skipped_count += 1

        self.logger.info(f"   Updated: {updated_count} segments")
        self.logger.info(f"   Skipped: {skipped_count} segments (not in results)")

        return merged_df

    def save_merged_result(self, merged_df: pd.DataFrame) -> str:
        """Save merged result to Excel"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"/Users/won.suh/Downloads/83-0060-0002_Protocol_FINAL_MERGED_{timestamp}.xlsx"

        self.logger.info(f"\n💾 SAVING MERGED RESULT...")
        merged_df.to_excel(output_file, index=False, engine='openpyxl')

        file_size = os.path.getsize(output_file) / 1024 / 1024  # MB
        self.logger.info(f"   ✅ Saved to: {output_file}")
        self.logger.info(f"   File size: {file_size:.2f} MB")
        self.logger.info(f"   Total rows: {len(merged_df)}")

        return output_file

    def verify_results(self, merged_df: pd.DataFrame):
        """Verify translation coverage"""
        self.logger.info(f"\n📊 VERIFICATION REPORT...")

        total_segments = len(merged_df)
        translated = merged_df['Target segment'].notna().sum()
        translated = sum(1 for x in merged_df['Target segment'] if pd.notna(x) and str(x).strip() != '')
        empty = total_segments - translated

        self.logger.info(f"   Total segments: {total_segments}")
        self.logger.info(f"   Translated: {translated} ({translated/total_segments*100:.1f}%)")
        self.logger.info(f"   Empty: {empty} ({empty/total_segments*100:.1f}%)")

        return translated, empty

    def run(self):
        """Execute merge operation"""
        try:
            self.logger.info("=" * 100)
            self.logger.info("🚀 MERGING PARALLEL TRANSLATION RESULTS INTO TEMPLATE")
            self.logger.info("=" * 100)
            self.logger.info("")

            # Step 1: Load template
            template_df = self.load_template()

            # Step 2: Load and combine results
            results_df = self.load_parallel_results()

            # Step 3: Merge
            merged_df = self.merge_into_template(template_df, results_df)

            # Step 4: Verify
            translated, empty = self.verify_results(merged_df)

            # Step 5: Save
            output_file = self.save_merged_result(merged_df)

            self.logger.info("")
            self.logger.info("=" * 100)
            self.logger.info("✅ MERGE COMPLETE!")
            self.logger.info("=" * 100)
            self.logger.info(f"\n📁 Output: {output_file}\n")

            return output_file

        except Exception as e:
            self.logger.error(f"❌ Merge failed: {e}")
            raise


def main():
    merger = ParallelResultsMerger()
    output_file = merger.run()
    print(f"\n✅ Final merged file: {output_file}")


if __name__ == '__main__':
    main()
