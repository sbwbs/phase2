#!/usr/bin/env python3
"""
Protocol QA Validator - Range-Based (for Parallel Processing)
Validates translation segments in a specific range
Designed to be run in parallel (4 separate processes)

Usage:
  python3 protocol_qa_validator_range.py <rules_json_path> <start_row> <end_row>

Example (4 parallel processes):
  Process 1: python3 protocol_qa_validator_range.py rules.json 0 550
  Process 2: python3 protocol_qa_validator_range.py rules.json 550 1089
  Process 3: python3 protocol_qa_validator_range.py rules.json 1089 1635
  Process 4: python3 protocol_qa_validator_range.py rules.json 1635 2178
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


class ProtocolQAValidatorRange:
    """Validate translations for a specific range of segments"""

    def __init__(self, rules_json_path: str, start_row: int, end_row: int):
        """
        Initialize validator for range

        Args:
            rules_json_path: Path to protocol_qa_rules_*.json
            start_row: Starting row index
            end_row: Ending row index
        """
        self.setup_logging()
        self.rules_json_path = rules_json_path
        self.start_row = start_row
        self.end_row = end_row
        self.client = openai.OpenAI()
        self.rules = []
        self.process_id = f"P{start_row}-{end_row}"
        self.load_rules()

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def load_rules(self):
        """Load extracted rules from JSON"""
        if not os.path.exists(self.rules_json_path):
            self.logger.error(f"❌ Rules file not found: {self.rules_json_path}")
            return

        self.logger.info(f"[{self.process_id}] 📖 Loading rules from: {self.rules_json_path}")

        try:
            with open(self.rules_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.rules = data.get("rules", [])
            self.logger.info(f"[{self.process_id}] ✓ Loaded {len(self.rules)} validation rules")

        except Exception as e:
            self.logger.error(f"[{self.process_id}] ❌ Error loading rules: {e}")

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

        for i, rule in enumerate(self.rules[:20], 1):
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

    def validate_range(self, merged_excel_path: str) -> List[Dict]:
        """
        Validate segments in the specified range

        Args:
            merged_excel_path: Path to merged translations Excel file

        Returns:
            List of validation results for this range
        """
        self.logger.info(f"[{self.process_id}] 📊 Loading merged translations: {merged_excel_path}")

        df = pd.read_excel(merged_excel_path)
        self.logger.info(f"[{self.process_id}] Total segments in file: {len(df)}")

        # Get range
        range_df = df.iloc[self.start_row:self.end_row]
        self.logger.info(f"[{self.process_id}] Processing range: {self.start_row}-{self.end_row} ({len(range_df)} segments)")

        # Filter segments with both source and target
        valid_segments = []
        for idx, row in range_df.iterrows():
            if pd.notna(row.get('Source segment')) and pd.notna(row.get('Target segment')):
                valid_segments.append({
                    'segment_id': str(row.get('Segment ID', f'seg_{idx}')),
                    'source_en': str(row['Source segment']),
                    'target_ko': str(row['Target segment']),
                    'row_index': idx
                })

        self.logger.info(f"[{self.process_id}] Valid segments to validate: {len(valid_segments)}")

        # Validate each segment
        validation_results = []
        for i, seg in enumerate(valid_segments, 1):
            result = self.validate_segment(seg['segment_id'], seg['source_en'], seg['target_ko'])
            result['source_en'] = seg['source_en']
            result['target_ko'] = seg['target_ko']
            validation_results.append(result)

            # Progress update every 50 segments
            if i % 50 == 0 or i == len(valid_segments):
                self.logger.info(f"[{self.process_id}] Progress: {i}/{len(valid_segments)} segments validated")

        return validation_results

    def save_range_results(self, validation_results: List[Dict], output_dir: str) -> str:
        """
        Save validation results for this range

        Args:
            validation_results: List of validation results
            output_dir: Directory to save results

        Returns:
            Path to saved file
        """
        os.makedirs(output_dir, exist_ok=True)

        # Count results
        pass_count = sum(1 for r in validation_results if r.get('status') == 'PASS')
        fail_count = sum(1 for r in validation_results if r.get('status') == 'FAIL')
        error_count = sum(1 for r in validation_results if r.get('status') == 'ERROR')

        # Prepare data
        report_data = []
        for result in validation_results:
            violations_str = "; ".join([
                f"{v.get('rule', 'Unknown')}: {v.get('issue', '')}"
                for v in result.get('violations', [])
            ])

            report_data.append({
                'Segment ID': result.get('segment_id', ''),
                'Source (EN)': result.get('source_en', '')[:150],
                'Target (KO)': result.get('target_ko', '')[:150],
                'Status': result.get('status', 'UNKNOWN'),
                'Violations': violations_str[:200],
                'Reason': result.get('reason', '')[:150],
                'Suggested Fix': result.get('suggested_correction', '')[:150] if result.get('suggested_correction') else ''
            })

        df = pd.DataFrame(report_data)

        # Save to CSV (faster than Excel for large files)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"{output_dir}/protocol_qa_range_{self.start_row}_{self.end_row}_{timestamp}.csv"
        df.to_csv(output_file, index=False, encoding='utf-8')

        self.logger.info(f"[{self.process_id}] ✅ Results saved: {output_file}")
        self.logger.info(f"[{self.process_id}] PASS: {pass_count} | FAIL: {fail_count} | ERROR: {error_count}")

        return output_file

    def run(self, merged_excel_path: str, output_dir: str) -> str:
        """
        Execute validation for this range

        Args:
            merged_excel_path: Path to merged translations
            output_dir: Directory to save results

        Returns:
            Path to results file
        """
        self.logger.info(f"\n[{self.process_id}] 🚀 PROCESS START: Range {self.start_row}-{self.end_row}")
        self.logger.info("=" * 100)

        try:
            # Validate range
            results = self.validate_range(merged_excel_path)

            # Save results
            output_file = self.save_range_results(results, output_dir)

            self.logger.info(f"[{self.process_id}] ✅ PROCESS COMPLETE")
            self.logger.info("=" * 100 + "\n")

            return output_file

        except Exception as e:
            self.logger.error(f"[{self.process_id}] ❌ Process failed: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """Main entry point for range-based validation"""
    import argparse

    parser = argparse.ArgumentParser(description="Protocol QA Validator - Range-Based Processing")
    parser.add_argument("rules_json_path", help="Path to protocol_qa_rules_*.json")
    parser.add_argument("start_row", type=int, help="Start row index")
    parser.add_argument("end_row", type=int, help="End row index")
    parser.add_argument("--output-dir", default="/tmp/protocol_qa_ranges", help="Output directory for results")
    parser.add_argument("--merged-file", default="/Users/won.suh/Downloads/83-0060-0002_Protocol_FINAL_MERGED_20251212_151821.xlsx", help="Merged translations file")

    args = parser.parse_args()

    validator = ProtocolQAValidatorRange(args.rules_json_path, args.start_row, args.end_row)
    validator.run(args.merged_file, args.output_dir)


if __name__ == '__main__':
    main()
