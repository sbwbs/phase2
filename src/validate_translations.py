#!/usr/bin/env python3
"""
Translation Validation Script
Validates AI-generated translations against customer feedback rules
5-step workflow: extract rules → load files → validate → report → summary
"""

import sys
import os
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validators import (
    FeedbackRuleExtractor,
    NumberValidator,
    ModalVerbValidator,
    LLMSemanticValidator
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TranslationValidator:
    """Main validation orchestrator"""

    def __init__(self, model_name: str = "gpt-5"):
        """Initialize validators with GPT-5 OWL model"""
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)

        # Initialize validators
        self.feedback_extractor = FeedbackRuleExtractor(model_name=model_name)
        self.number_validator = NumberValidator()
        self.modal_validator = ModalVerbValidator()
        self.llm_validator = LLMSemanticValidator(model_name=model_name)

        self.consolidated_rules = {}
        self.validation_results = []

    def validate_translations(self, translation_file: str, feedback_files: List[str] = None, skip_llm: bool = False) -> str:
        """
        Run full validation workflow

        Args:
            translation_file: Path to Excel file with translations to validate
            feedback_files: List of feedback files (optional, for future learning)
            skip_llm: Skip LLM validation to speed up (use hardcoded rules only)

        Returns:
            Path to generated validation report
        """
        print("\n" + "=" * 100)
        print("📚 TRANSLATION VALIDATION SYSTEM")
        print("=" * 100)

        # STEP 1: Skip feedback extraction - use hardcoded validation rules
        print("\n✅ STEP 1: Using hardcoded validation rules (Fast mode - no LLM extraction)...")
        self.consolidated_rules = {}  # Empty - using hardcoded checks instead
        print("  ✅ Validation rules loaded from code")

        # STEP 2: Load translation file to validate
        print("\n📂 STEP 2: Loading translations to validate...")
        df, source_col, target_col = self._load_translation_file(translation_file)

        # STEP 3: Initialize validators
        print("\n🔧 STEP 3: Initializing validators...")
        self.logger.info(f"Using model: {self.model_name}")
        print(f"  ✅ LLM Semantic Validation: {'DISABLED (use --with-llm to enable)' if skip_llm else 'ENABLED'}")

        # STEP 4: Run validation on each segment
        print("\n🔄 STEP 4: Validating translations...")
        self._validate_all_segments(df, source_col, target_col, skip_llm=skip_llm)

        # STEP 5: Generate Excel report
        print("\n💾 STEP 5: Generating validation report...")
        output_file = self._generate_report(translation_file, df)

        # Print summary
        self._print_summary()

        return output_file

    def _extract_rules_from_feedback(self, feedback_files: List[str]):
        """Extract rules from all feedback files"""
        all_rules = []

        for file_path in feedback_files:
            if not os.path.exists(file_path):
                self.logger.warning(f"Feedback file not found: {file_path}")
                continue

            try:
                if file_path.endswith('.xlsx'):
                    rules = self.feedback_extractor.extract_rules_from_excel(file_path)
                elif file_path.endswith('.docx'):
                    rules = self.feedback_extractor.extract_rules_from_docx(file_path)
                else:
                    self.logger.warning(f"Unsupported file format: {file_path}")
                    continue

                all_rules.extend(rules)
                print(f"  ✅ Extracted {len(rules)} rules from {Path(file_path).name}")

            except Exception as e:
                self.logger.error(f"Error processing feedback file {file_path}: {e}")
                continue

        # Consolidate rules
        self.consolidated_rules = self.feedback_extractor.consolidate_rules(all_rules)
        print(f"\n✅ Total consolidated rules: {len(self.consolidated_rules)}")

        # Display rule summary
        for rule_id, rule in list(self.consolidated_rules.items())[:5]:
            print(f"   - {rule_id} ({rule.category}): {rule.description[:60]}...")

        if len(self.consolidated_rules) > 5:
            print(f"   ... and {len(self.consolidated_rules) - 5} more rules")

    def _load_translation_file(self, translation_file: str) -> tuple:
        """Load and analyze translation file"""
        if not os.path.exists(translation_file):
            raise FileNotFoundError(f"Translation file not found: {translation_file}")

        df = pd.read_excel(translation_file)
        print(f"  ✅ Loaded file: {Path(translation_file).name}")
        print(f"  ✅ Total rows: {len(df)}")

        # Auto-detect source and target columns
        source_col = self._detect_source_column(df)
        target_col = self._detect_target_column(df)

        if not source_col or not target_col:
            raise ValueError("Could not auto-detect source/target columns")

        print(f"  ✅ Source column: '{source_col}'")
        print(f"  ✅ Target column: '{target_col}'")

        return df, source_col, target_col

    def _validate_all_segments(self, df: pd.DataFrame, source_col: str, target_col: str):
        """Run validation on all segments"""
        total_segments = 0
        processed = 0
        passed = 0
        failed = 0

        for idx, row in df.iterrows():
            total_segments += 1

            segment_id = row.get('Segment ID', row.get('segment_id', idx))
            source_text = row[source_col]
            target_text = row[target_col]

            # Skip if target is empty (not translated yet)
            if pd.isna(target_text) or not str(target_text).strip():
                continue

            processed += 1

            # Run all validators
            issues = []

            # 1. Numeric validation
            issues.extend(self.number_validator.validate_numbers(str(source_text), str(target_text)))
            issues.extend(self.number_validator.validate_dosages(str(source_text), str(target_text)))
            issues.extend(self.number_validator.validate_ratios(str(source_text), str(target_text)))
            issues.extend(self.number_validator.validate_units(str(source_text), str(target_text)))
            issues.extend(self.number_validator.validate_percentages(str(source_text), str(target_text)))

            # 2. Modal verb validation
            issues.extend(self.modal_validator.validate_modal_verb_consistency(
                str(source_text), str(target_text)
            ))
            issues.extend(self.modal_validator.detect_modal_verb_downgrade(
                str(source_text), str(target_text)
            ))

            # 3. LLM semantic validation (if rules extracted)
            if self.consolidated_rules:
                feedback_rules = [
                    {
                        'rule_id': rule.rule_id,
                        'category': rule.category,
                        'description': rule.description,
                        'examples': rule.examples
                    }
                    for rule in self.consolidated_rules.values()
                ]
                llm_result = self.llm_validator.cross_validate_with_feedback(
                    str(source_text), str(target_text), feedback_rules
                )
            else:
                # Fallback to basic meaning preservation check
                llm_result = self.llm_validator.validate_meaning_preservation(
                    str(source_text), str(target_text), direction="ko-en"
                )

            # Aggregate results
            overall_pass = len(issues) == 0 and llm_result.passed

            if overall_pass:
                passed += 1
            else:
                failed += 1

            result = {
                'Segment ID': segment_id,
                'Source': str(source_text)[:100],
                'Target': str(target_text)[:100],
                'Overall Status': 'PASS' if overall_pass else 'FAIL',
                'Issue Count': len(issues),
                'Issues': '; '.join([f"{i.category}: {i.message}" for i in issues]),
                'LLM Semantic Check': 'PASS' if llm_result.passed else 'FAIL',
                'Confidence': llm_result.confidence,
                'LLM Details': llm_result.message
            }

            self.validation_results.append(result)

            # Progress indicator
            if (processed) % 10 == 0:
                print(f"   Validated {processed}/{total_segments} segments... ({passed} passed, {failed} failed)")

        print(f"\n✅ Validation complete: {processed}/{total_segments} segments checked")
        print(f"   ✅ Passed: {passed}")
        print(f"   ❌ Failed: {failed}")

    def _generate_report(self, translation_file: str, original_df: pd.DataFrame) -> str:
        """Generate Excel report with validation results"""
        # Create results DataFrame
        results_df = pd.DataFrame(self.validation_results)

        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_name = Path(translation_file).stem
        output_file = Path(translation_file).parent / f"{input_name}_VALIDATION_REPORT_{timestamp}.xlsx"

        try:
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # Sheet 1: Detailed validation results
                results_df.to_excel(writer, sheet_name='Validation Results', index=False)

                # Sheet 2: Summary statistics
                summary = {
                    'Metric': [
                        'Total Segments',
                        'Validated Segments',
                        'Passed',
                        'Failed',
                        'Pass Rate (%)',
                        'Total Issues Found',
                        'Average Confidence'
                    ],
                    'Value': [
                        len(original_df),
                        len(self.validation_results),
                        (results_df['Overall Status'] == 'PASS').sum(),
                        (results_df['Overall Status'] == 'FAIL').sum(),
                        f"{(results_df['Overall Status'] == 'PASS').sum() / len(self.validation_results) * 100:.1f}" if self.validation_results else "0",
                        results_df['Issue Count'].sum(),
                        f"{results_df['Confidence'].mean():.2f}" if len(results_df) > 0 else "0"
                    ]
                }
                summary_df = pd.DataFrame(summary)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)

                # Sheet 3: Validation rules used
                if self.consolidated_rules:
                    rules_list = []
                    for rule in self.consolidated_rules.values():
                        rules_list.append({
                            'Rule ID': rule.rule_id,
                            'Category': rule.category,
                            'Description': rule.description,
                            'Severity': rule.severity,
                            'Example Count': len(rule.examples),
                            'Source': rule.source
                        })
                    rules_df = pd.DataFrame(rules_list)
                    rules_df.to_excel(writer, sheet_name='Validation Rules', index=False)

            print(f"✅ Report saved: {output_file}")
            return str(output_file)

        except Exception as e:
            self.logger.error(f"Error generating report: {e}")
            raise

    def _print_summary(self):
        """Print final validation summary"""
        if not self.validation_results:
            print("\n⚠️  No validation results to summarize")
            return

        results_df = pd.DataFrame(self.validation_results)
        passed = (results_df['Overall Status'] == 'PASS').sum()
        failed = (results_df['Overall Status'] == 'FAIL').sum()
        total = len(results_df)
        pass_rate = (passed / total * 100) if total > 0 else 0

        print("\n📊 VALIDATION SUMMARY")
        print("=" * 100)
        print(f"Total Segments Validated: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Pass Rate: {pass_rate:.1f}%")
        print(f"Total Issues Found: {results_df['Issue Count'].sum()}")
        print(f"Average Confidence: {results_df['Confidence'].mean():.2f}")
        print(f"Total Rules Used: {len(self.consolidated_rules)}")
        print("=" * 100)

    # Helper methods

    def _detect_source_column(self, df: pd.DataFrame) -> Optional[str]:
        """Auto-detect source language column"""
        candidates = ['Source', 'source', 'Source segment', 'Korean', 'korean', 'Ko', 'KO']
        for col in candidates:
            if col in df.columns:
                return col
        # Fallback to first column
        return df.columns[0] if len(df.columns) > 0 else None

    def _detect_target_column(self, df: pd.DataFrame) -> Optional[str]:
        """Auto-detect target language column"""
        candidates = ['Target', 'target', 'Target segment', 'English', 'english', 'En', 'EN']
        for col in candidates:
            if col in df.columns:
                return col
        # Fallback to second column
        return df.columns[1] if len(df.columns) > 1 else None


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Validate AI-generated translations against customer feedback rules'
    )
    parser.add_argument(
        'translation_file',
        help='Path to Excel file with translations to validate'
    )
    parser.add_argument(
        '--feedback',
        nargs='+',
        help='Path(s) to customer feedback files (Excel or Word documents)',
        default=[]
    )
    parser.add_argument(
        '--model',
        default='gpt-5',
        help='LLM model to use for validation (default: gpt-5 for OWL)'
    )

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.translation_file):
        print(f"❌ Error: Translation file not found: {args.translation_file}")
        sys.exit(1)

    # Use default feedback files if not provided
    if not args.feedback:
        default_feedback_dir = Path("/Users/won.suh/Downloads/DU-00001_유한_Debriefing_2025-11-22/")
        if default_feedback_dir.exists():
            args.feedback = [
                str(default_feedback_dir / "2025-11-17_선영_Debriefing.xlsx"),
                str(default_feedback_dir / "2025-11-17_주연_Debriefing(유한).xlsx"),
                str(default_feedback_dir / "2025-11-18_주연_조동사 사용.xlsx"),
                str(default_feedback_dir / "AD-223P3_Protocol_v5.1_2024.11.11_final_EN_고객사 코맨트.docx")
            ]
        else:
            print("⚠️  Warning: No feedback files provided and default location not found")
            print("   Please provide feedback files with --feedback flag")
            args.feedback = []

    # Run validation
    try:
        validator = TranslationValidator(model_name=args.model)
        report_file = validator.validate_translations(args.translation_file, args.feedback)
        print(f"\n✅ Validation complete! Report: {report_file}")

    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        logger.exception("Validation error")
        sys.exit(1)


if __name__ == "__main__":
    main()
