#!/usr/bin/env python3
"""
Protocol Consistency QA - Main Orchestration Script
Coordinates:
1. Reference document loading and alignment
2. Consistency rule extraction from reference pairs
3. Translation validation against extracted rules
4. Auto-correction of critical/high violations
5. Final QA report generation
"""

import sys
import os
import logging
import argparse
import pandas as pd
from datetime import datetime
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from loaders.reference_doc_loader import ReferenceDocLoader
from validators.consistency_rule_extractor import ConsistencyRuleExtractor
from protocol_consistency_validator import ConsistencyRuleValidator


class ProtocolConsistencyQA:
    """Main orchestrator for protocol consistency QA system"""

    def __init__(self, test_mode: bool = False, test_segments: int = 50):
        """
        Initialize QA system

        Args:
            test_mode: If True, run quick test on subset of data
            test_segments: Number of segments for test mode
        """
        self.setup_logging()
        self.test_mode = test_mode
        self.test_segments = test_segments
        self.logger = logging.getLogger(__name__)

    def setup_logging(self):
        """Initialize logging"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)

    def run_quick_test(self) -> bool:
        """
        Run quick test with subset of data

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("=" * 100)
        self.logger.info("🧪 RUNNING QUICK TEST (50 segments)")
        self.logger.info("=" * 100)

        try:
            # Step 1: Extract reference document pairs
            self.logger.info("\n📋 PHASE 1: EXTRACT REFERENCE PAIRS")
            self.logger.info("-" * 100)

            en_doc = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_EN.docx"
            ko_doc = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_Korean_final.docx"

            loader = ReferenceDocLoader(en_doc, ko_doc)
            loader.load_documents()
            loader.extract_paragraphs()
            loader.align_paragraphs()

            # Save aligned pairs
            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
            pairs_file = f"/Users/won.suh/Project/translate-ai/phase2/data/reference_pairs_test_{timestamp}.xlsx"
            loader.save_aligned_pairs(pairs_file)

            # For test, use first 100 reference pairs
            ref_df = pd.read_excel(pairs_file)
            ref_pairs = [
                {'en': row['en_text'], 'ko': row['ko_text']}
                for _, row in ref_df.head(100).iterrows()
            ]

            self.logger.info(f"✅ Extracted {len(ref_pairs)} reference pairs")

            # Step 2: Extract consistency rules from first 100 reference pairs
            self.logger.info("\n📖 PHASE 2: EXTRACT CONSISTENCY RULES")
            self.logger.info("-" * 100)

            rule_extractor = ConsistencyRuleExtractor(model_name="gpt-5.2", batch_size=50)
            extracted_rules = rule_extractor.extract_rules_from_pairs(ref_pairs)

            rules_json_file = f"/Users/won.suh/Project/translate-ai/phase2/data/consistency_rules_test_{timestamp}.json"
            rule_extractor.save_rules_json(rules_json_file)

            self.logger.info(f"✅ Extracted {len(extracted_rules)} consistency rules")

            # Step 3: Load merged translations for validation
            self.logger.info("\n📊 PHASE 3: VALIDATE TRANSLATIONS (TEST: 50 segments)")
            self.logger.info("-" * 100)

            merged_file = "/Users/won.suh/Downloads/83-0060-0002_Protocol_FINAL_MERGED_20251212_151821.xlsx"
            merged_df = pd.read_excel(merged_file)

            self.logger.info(f"Loaded {len(merged_df)} segments from merged file")

            # Validate only segments 100-150 (avoid headers)
            test_df = merged_df.iloc[100:100 + self.test_segments].copy()

            validator = ConsistencyRuleValidator(rules_json_file, model_name="gpt-5.2")
            validation_results = validator.validate_translations(test_df, batch_size=10)

            self.logger.info(f"✅ Validated {len(validation_results)} translations")

            # Step 4: Auto-correct critical/high violations
            self.logger.info("\n✏️  PHASE 4: GENERATE CORRECTIONS (Sample)")
            self.logger.info("-" * 100)

            corrected_count = 0
            for result in validation_results[:5]:  # Correct only first 5 for test
                critical_high = [v for v in result.rule_violations if v.severity in ["critical", "high"]]
                if critical_high and result.consistency_score < 0.75:
                    corrected = validator.generate_correction(
                        result.source_en,
                        result.original_ko,
                        critical_high
                    )
                    result.corrected_ko = corrected
                    corrected_count += 1
                    self.logger.info(f"  ✓ Corrected segment {result.segment_id}")

            self.logger.info(f"✅ Generated {corrected_count} corrections")

            # Step 5: Save test results
            self.logger.info("\n💾 PHASE 5: SAVE TEST RESULTS")
            self.logger.info("-" * 100)

            output_file = f"/Users/won.suh/Downloads/Protocol_QA_TEST_{timestamp}.xlsx"
            validator.save_validation_results(output_file)

            self.logger.info("")
            self.logger.info("=" * 100)
            self.logger.info("✅ QUICK TEST COMPLETE!")
            self.logger.info("=" * 100)
            self.logger.info(f"\n📁 Test output: {output_file}")
            self.logger.info(f"📖 Rules extracted: {len(extracted_rules)}")
            self.logger.info(f"✅ Segments validated: {len(validation_results)}")
            self.logger.info(f"✏️  Corrections generated: {corrected_count}")
            self.logger.info(f"\n💡 Review the test results and approve full run with all 2,178 segments\n")

            return True

        except Exception as e:
            self.logger.error(f"❌ Quick test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_full_production(self) -> bool:
        """
        Run full production with all 2,178 segments

        Returns:
            True if successful, False otherwise
        """
        self.logger.info("=" * 100)
        self.logger.info("🚀 RUNNING FULL PRODUCTION (ALL 2,178 SEGMENTS)")
        self.logger.info("=" * 100)

        try:
            # Step 1: Extract all reference document pairs
            self.logger.info("\n📋 PHASE 1: EXTRACT ALL REFERENCE PAIRS")
            self.logger.info("-" * 100)

            en_doc = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_EN.docx"
            ko_doc = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_Korean_final.docx"

            loader = ReferenceDocLoader(en_doc, ko_doc)
            loader.load_documents()
            loader.extract_paragraphs()
            loader.align_paragraphs()

            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
            pairs_file = f"/Users/won.suh/Project/translate-ai/phase2/data/reference_pairs_production_{timestamp}.xlsx"
            loader.save_aligned_pairs(pairs_file)

            # Load ALL reference pairs
            ref_df = pd.read_excel(pairs_file)
            ref_pairs = [
                {'en': row['en_text'], 'ko': row['ko_text']}
                for _, row in ref_df.iterrows()
            ]

            self.logger.info(f"✅ Extracted {len(ref_pairs)} reference pairs")

            # Step 2: Extract comprehensive consistency rules
            self.logger.info("\n📖 PHASE 2: EXTRACT COMPREHENSIVE CONSISTENCY RULES")
            self.logger.info("-" * 100)

            rule_extractor = ConsistencyRuleExtractor(model_name="gpt-5.2", batch_size=50)
            extracted_rules = rule_extractor.extract_rules_from_pairs(ref_pairs)

            rules_json_file = f"/Users/won.suh/Project/translate-ai/phase2/data/consistency_rules_production_{timestamp}.json"
            rule_extractor.save_rules_json(rules_json_file)

            rules_excel_file = f"/Users/won.suh/Project/translate-ai/phase2/data/consistency_rules_production_{timestamp}.xlsx"
            rule_extractor.save_rules_excel(rules_excel_file)

            self.logger.info(f"✅ Extracted {len(extracted_rules)} consistency rules")

            # Step 3: Validate ALL translations
            self.logger.info("\n📊 PHASE 3: VALIDATE ALL 2,178 TRANSLATIONS")
            self.logger.info("-" * 100)

            merged_file = "/Users/won.suh/Downloads/83-0060-0002_Protocol_FINAL_MERGED_20251212_151821.xlsx"
            merged_df = pd.read_excel(merged_file)

            validator = ConsistencyRuleValidator(rules_json_file, model_name="gpt-5.2")
            validation_results = validator.validate_translations(merged_df, batch_size=50)

            self.logger.info(f"✅ Validated {len(validation_results)} translations")

            # Step 4: Auto-correct critical/high violations
            self.logger.info("\n✏️  PHASE 4: AUTO-CORRECT CRITICAL/HIGH VIOLATIONS")
            self.logger.info("-" * 100)

            corrected_count = 0
            for i, result in enumerate(validation_results):
                critical_high = [v for v in result.rule_violations if v.severity in ["critical", "high"]]
                if critical_high and result.consistency_score < 0.75:
                    corrected = validator.generate_correction(
                        result.source_en,
                        result.original_ko,
                        critical_high
                    )
                    result.corrected_ko = corrected
                    corrected_count += 1

                    # Progress update every 100 segments
                    if (i + 1) % 100 == 0:
                        self.logger.info(f"  Progress: {i+1}/{len(validation_results)} segments processed")

            self.logger.info(f"✅ Generated {corrected_count} corrections")

            # Step 5: Save final results
            self.logger.info("\n💾 PHASE 5: SAVE FINAL QA REPORT")
            self.logger.info("-" * 100)

            output_file = f"/Users/won.suh/Downloads/83-0060-0002_Protocol_QA_VALIDATED_{timestamp}.xlsx"
            validator.save_validation_results(output_file)

            self.logger.info("")
            self.logger.info("=" * 100)
            self.logger.info("✅ FULL PRODUCTION COMPLETE!")
            self.logger.info("=" * 100)
            self.logger.info(f"\n📁 Final output: {output_file}")
            self.logger.info(f"📖 Rules extracted: {len(extracted_rules)}")
            self.logger.info(f"✅ Segments validated: {len(validation_results)}")
            self.logger.info(f"✏️  Corrections generated: {corrected_count}")
            self.logger.info(f"💰 Total cost: ${validator.total_cost:.2f}\n")

            return True

        except Exception as e:
            self.logger.error(f"❌ Production run failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self):
        """Main execution"""
        if self.test_mode:
            success = self.run_quick_test()
            if success:
                self.logger.info("\n💡 Quick test completed successfully!")
                self.logger.info("   Review the test output and run with --production flag for full run")
        else:
            self.run_full_production()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Protocol Consistency QA System")
    parser.add_argument(
        "--mode",
        choices=["test", "production"],
        default="test",
        help="Run mode: test (50 segments) or production (all 2,178 segments)"
    )
    parser.add_argument(
        "--test-segments",
        type=int,
        default=50,
        help="Number of segments for test mode (default: 50)"
    )

    args = parser.parse_args()

    qa_system = ProtocolConsistencyQA(
        test_mode=(args.mode == "test"),
        test_segments=args.test_segments
    )
    qa_system.run()


if __name__ == '__main__':
    main()
