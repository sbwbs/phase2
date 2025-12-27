#!/usr/bin/env python3
"""
Protocol QA Validator - Processor 2
Uses rules extracted by Processor 1
Validates each segment (source EN + target KO) against the rules
Provides Pass/Fail + suggested fix
Output: Excel report with validation results
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional

import openai
import pandas as pd
from tenacity import retry, wait_exponential, stop_after_attempt

sys.path.insert(0, os.path.dirname(__file__))


class ProtocolQAValidator:
    """Validate translations using extracted rules"""

    def __init__(self, rules_json_path: str):
        """
        Initialize validator with extracted rules

        Args:
            rules_json_path: Path to protocol_qa_rules_*.json from Processor 1
        """
        self.setup_logging()
        self.rules_json_path = rules_json_path
        self.client = openai.OpenAI()
        self.rules = []
        self.load_rules()

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_rules(self):
        """Load extracted rules from JSON"""
        if not os.path.exists(self.rules_json_path):
            self.logger.error(f"❌ Rules file not found: {self.rules_json_path}")
            return

        self.logger.info(f"📖 Loading rules from: {self.rules_json_path}")

        try:
            with open(self.rules_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.rules = data.get("rules", [])
            self.logger.info(f"  ✓ Loaded {len(self.rules)} validation rules")

            # Show summary
            by_category = {}
            for rule in self.rules:
                cat = rule.get("category", "unknown")
                by_category[cat] = by_category.get(cat, 0) + 1
            for cat, count in sorted(by_category.items()):
                self.logger.info(f"    - {cat}: {count} rules")

        except Exception as e:
            self.logger.error(f"❌ Error loading rules: {e}")

    def _extract_text_from_response(self, response) -> str:
        """Extract text from GPT-5 Responses API response object"""
        try:
            if hasattr(response, "output_text") and response.output_text:
                text = str(response.output_text).strip()
                if text:
                    return text

            if hasattr(response, "output") and isinstance(response.output, list):
                for item in response.output:
                    if hasattr(item, "content") and isinstance(item.content, list):
                        for content_item in item.content:
                            if hasattr(content_item, "text") and content_item.text:
                                text = str(content_item.text).strip()
                                if text:
                                    return text
                    if hasattr(item, "text") and item.text:
                        text = str(item.text).strip()
                        if text:
                            return text

            output = getattr(response, "output", None)
            if isinstance(output, str) and output:
                return output.strip()

        except Exception as e:
            self.logger.debug(f"Error in extraction: {e}")
            pass

        try:
            if hasattr(response, "text"):
                text_obj = response.text
                if hasattr(text_obj, "content"):
                    return str(text_obj.content).strip()
                elif isinstance(text_obj, str):
                    return text_obj.strip()
        except Exception:
            pass

        try:
            return str(response).strip()
        except Exception:
            return "[Response Extraction Failed]"

    def _format_rules_for_prompt(self) -> str:
        """Format rules for inclusion in validation prompt"""
        rules_text = "# TRANSLATION RULES (extracted from reference documents)\n\n"

        for i, rule in enumerate(self.rules[:20], 1):  # Use top 20 rules max
            category = rule.get("category", "unknown")
            priority = rule.get("priority", "medium")
            rule_desc = rule.get("rule", "")
            examples = rule.get("examples", [])

            rules_text += f"{i}. [{priority.upper()}] {category.upper()}\n"
            rules_text += f"   Rule: {rule_desc}\n"
            if examples:
                rules_text += f"   Examples: {', '.join(examples[:2])}\n"
            rules_text += "\n"

        return rules_text

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(2))
    def validate_segment(self, segment_id: str, source_en: str, target_ko: str) -> Dict:
        """
        Validate a single segment against the rules

        Args:
            segment_id: Unique segment identifier
            source_en: English source text
            target_ko: Korean target text

        Returns:
            Dict with validation result
        """
        rules_prompt = self._format_rules_for_prompt()

        prompt = f"""{rules_prompt}

# TRANSLATION TO VALIDATE
Segment ID: {segment_id}
Source (EN): {source_en}
Target (KO): {target_ko}

# VALIDATION TASK
Check this translation against the rules above.

1. Does it follow the rules?
2. Any violations?
3. If violations: suggest a corrected version

OUTPUT ONLY THIS JSON (no markdown):
{{
  "segment_id": "{segment_id}",
  "status": "PASS",
  "violations": [],
  "suggested_correction": null,
  "reason": "Translation follows all identified rules"
}}

Or if violations found:
{{
  "segment_id": "{segment_id}",
  "status": "FAIL",
  "violations": [
    {{
      "rule": "Use formal 합니다 endings",
      "issue": "Found informal ~이다 ending",
      "priority": "high"
    }}
  ],
  "suggested_correction": "corrected Korean text here",
  "reason": "Violation of formal tone rule"
}}"""

        try:
            response = self.client.responses.create(
                model="gpt-5.2",
                input=[{"role": "user", "content": prompt}],
                text={"verbosity": "low"},
                reasoning={"effort": "low"}
            )

            response_text = self._extract_text_from_response(response)

            # Extract JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                return result
            else:
                self.logger.warning(f"⚠️  Could not parse validation response for {segment_id}")
                return {
                    "segment_id": segment_id,
                    "status": "ERROR",
                    "violations": [],
                    "suggested_correction": None,
                    "reason": "Could not parse response"
                }

        except Exception as e:
            self.logger.error(f"❌ Validation error for {segment_id}: {e}")
            return {
                "segment_id": segment_id,
                "status": "ERROR",
                "violations": [],
                "suggested_correction": None,
                "reason": str(e)
            }

    def validate_all_segments(self, merged_excel_path: str, max_segments: Optional[int] = None) -> List[Dict]:
        """
        Validate all segments in the merged translation file

        Args:
            merged_excel_path: Path to merged translations Excel file
            max_segments: Maximum segments to validate (for testing)

        Returns:
            List of validation results
        """
        self.logger.info(f"📊 Loading merged translations: {merged_excel_path}")

        df = pd.read_excel(merged_excel_path)
        self.logger.info(f"  Total segments: {len(df)}")

        # Filter segments with both source and target
        valid_segments = []
        for idx, row in df.iterrows():
            if max_segments and len(valid_segments) >= max_segments:
                break

            if pd.notna(row.get('Source segment')) and pd.notna(row.get('Target segment')):
                valid_segments.append({
                    'segment_id': str(row.get('Segment ID', f'seg_{idx}')),
                    'source_en': str(row['Source segment']),
                    'target_ko': str(row['Target segment'])
                })

        self.logger.info(f"  Valid segments to validate: {len(valid_segments)}")

        # Validate each segment
        validation_results = []
        for i, seg in enumerate(valid_segments, 1):
            if i % 50 == 0 or i == len(valid_segments):
                self.logger.info(f"  Progress: {i}/{len(valid_segments)} segments validated")

            result = self.validate_segment(seg['segment_id'], seg['source_en'], seg['target_ko'])
            result['source_en'] = seg['source_en']
            result['target_ko'] = seg['target_ko']
            validation_results.append(result)

        return validation_results

    def save_report(self, validation_results: List[Dict], output_path: str) -> str:
        """
        Save validation results to Excel report

        Args:
            validation_results: List of validation results
            output_path: Path to save Excel file

        Returns:
            Path to saved file
        """
        self.logger.info(f"💾 Generating report: {output_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Prepare data
        report_data = []
        pass_count = 0
        fail_count = 0
        error_count = 0

        for result in validation_results:
            status = result.get('status', 'UNKNOWN')
            if status == 'PASS':
                pass_count += 1
            elif status == 'FAIL':
                fail_count += 1
            else:
                error_count += 1

            violations_str = "; ".join([
                f"{v.get('rule', 'Unknown')}: {v.get('issue', '')}"
                for v in result.get('violations', [])
            ])

            report_data.append({
                'Segment ID': result.get('segment_id', ''),
                'Source (EN)': result.get('source_en', '')[:150],
                'Target (KO)': result.get('target_ko', '')[:150],
                'Status': status,
                'Violations': violations_str[:200],
                'Reason': result.get('reason', '')[:150],
                'Suggested Fix': result.get('suggested_correction', '')[:150] if result.get('suggested_correction') else ''
            })

        df = pd.DataFrame(report_data)

        # Save to Excel
        df.to_excel(output_path, index=False, engine='openpyxl')

        self.logger.info(f"  ✓ Report saved")
        self.logger.info(f"\n📊 VALIDATION SUMMARY:")
        self.logger.info(f"  ✅ PASS: {pass_count} segments")
        self.logger.info(f"  ❌ FAIL: {fail_count} segments")
        self.logger.info(f"  ⚠️  ERROR: {error_count} segments")
        self.logger.info(f"  Total: {len(validation_results)} segments\n")

        return output_path

    def run(self, merged_excel_path: str, test_mode: bool = False, test_segments: int = 50) -> str:
        """
        Execute QA validation workflow

        Args:
            merged_excel_path: Path to merged translations
            test_mode: If True, validate only subset
            test_segments: Number of segments for test mode

        Returns:
            Path to validation report
        """
        self.logger.info("=" * 100)
        self.logger.info("🚀 PROTOCOL QA VALIDATOR - Processor 2")
        self.logger.info("=" * 100)

        try:
            # Step 1: Validate segments
            self.logger.info("\n📋 STEP 1: Validate Translation Segments")
            self.logger.info("-" * 100)

            max_segs = test_segments if test_mode else None
            results = self.validate_all_segments(merged_excel_path, max_segments=max_segs)

            # Step 2: Save report
            self.logger.info("\n💾 STEP 2: Save Validation Report")
            self.logger.info("-" * 100)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            mode_suffix = "_TEST" if test_mode else ""
            output_file = f"/Users/won.suh/Downloads/Protocol_QA_Validation{mode_suffix}_{timestamp}.xlsx"
            self.save_report(results, output_file)

            self.logger.info("")
            self.logger.info("=" * 100)
            self.logger.info("✅ QA VALIDATION COMPLETE")
            self.logger.info("=" * 100)
            self.logger.info(f"\n📁 Report: {output_file}\n")

            return output_file

        except Exception as e:
            self.logger.error(f"❌ QA validation failed: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """Main execution"""
    # First run rule extractor to get rules file
    from protocol_qa_rule_extractor import ProtocolQARuleExtractor

    extractor = ProtocolQARuleExtractor()
    rules_file = extractor.run()

    # Then run validator
    validator = ProtocolQAValidator(rules_file)
    merged_file = "/Users/won.suh/Downloads/83-0060-0002_Protocol_FINAL_MERGED_20251212_151821.xlsx"
    report_file = validator.run(merged_file, test_mode=True, test_segments=50)

    print(f"\n✅ Validation complete: {report_file}")


if __name__ == '__main__':
    main()
