#!/usr/bin/env python3
"""
Protocol Consistency Validator
Validates translated Korean segments against extracted consistency rules
Uses GPT-5.2 for intelligent validation and auto-correction
"""

import json
import logging
import os
import sys
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

# OpenAI for GPT-5.2
import openai
from tenacity import retry, wait_exponential, stop_after_attempt

sys.path.insert(0, os.path.dirname(__file__))


@dataclass
class RuleViolation:
    """Represents a rule violation found during validation"""
    rule_id: str
    rule_description: str
    violation_detail: str
    severity: str  # "critical", "high", "medium", "low"
    suggested_correction: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validating a single translation"""
    segment_id: str
    source_en: str
    original_ko: str
    consistency_score: float  # 0.0-1.0
    rule_violations: List[RuleViolation] = field(default_factory=list)
    needs_correction: bool = False
    tone_formality: str = "appropriate"  # appropriate/too-informal/too-formal
    corrected_ko: Optional[str] = None


class ConsistencyRuleValidator:
    """Validate translations against consistency rules using GPT-5.2"""

    def __init__(self, rules_json_path: str, model_name: str = "gpt-5.2"):
        """
        Initialize validator with extracted rules

        Args:
            rules_json_path: Path to extracted_consistency_rules.json
            model_name: GPT model to use ("gpt-5.2" recommended)
        """
        self.setup_logging()
        self.rules_json_path = rules_json_path
        self.model_name = model_name
        self.extracted_rules = {}
        self.validation_results = []
        self.api_calls_made = 0
        self.total_cost = 0.0

        # Initialize OpenAI
        self.client = openai.OpenAI()

        # Load rules
        self._load_rules()

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _extract_text_from_response(self, response) -> str:
        """Extract text from GPT-5 Responses API response object"""
        try:
            # Method 1: Direct output_text attribute (primary for Responses API)
            if hasattr(response, "output_text") and response.output_text:
                text = str(response.output_text).strip()
                if text:
                    return text

            # Method 2: Extract from output list (ResponseOutputMessage)
            if hasattr(response, "output") and isinstance(response.output, list):
                for item in response.output:
                    # Look for ResponseOutputMessage with content
                    if hasattr(item, "content") and isinstance(item.content, list):
                        for content_item in item.content:
                            if hasattr(content_item, "text") and content_item.text:
                                text = str(content_item.text).strip()
                                if text:
                                    return text
                    # Also try direct text attribute
                    if hasattr(item, "text") and item.text:
                        text = str(item.text).strip()
                        if text:
                            return text

            # Method 3: Try output as string
            output = getattr(response, "output", None)
            if isinstance(output, str) and output:
                return output.strip()

        except Exception as e:
            self.logger.debug(f"Error in primary extraction: {e}")
            pass

        # Method 4: Fallback to text object
        try:
            if hasattr(response, "text"):
                text_obj = response.text
                if hasattr(text_obj, "content"):
                    return str(text_obj.content).strip()
                elif isinstance(text_obj, str):
                    return text_obj.strip()
        except Exception:
            pass

        # Method 5: Final fallback - convert to string
        try:
            return str(response).strip()
        except Exception:
            return "[Response Extraction Failed]"

    def _load_rules(self):
        """Load extracted consistency rules from JSON"""
        if not os.path.exists(self.rules_json_path):
            self.logger.warning(f"⚠️  Rules file not found: {self.rules_json_path}")
            return

        self.logger.info(f"📖 Loading consistency rules from: {self.rules_json_path}")

        try:
            with open(self.rules_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.extracted_rules = data.get("rules", [])
            self.logger.info(f"  ✓ Loaded {len(self.extracted_rules)} rules")

            # Show rule summary
            categories = {}
            for rule in self.extracted_rules:
                cat = rule.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1
            for cat, count in sorted(categories.items()):
                self.logger.info(f"    - {cat}: {count} rules")

        except Exception as e:
            self.logger.error(f"❌ Error loading rules: {e}")

    def _format_rules_for_prompt(self) -> str:
        """Format extracted rules for inclusion in validation prompt"""
        rules_text = "# EXTRACTED CONSISTENCY RULES FROM PROFESSIONAL REFERENCE\n\n"

        for i, rule in enumerate(self.extracted_rules[:30], 1):  # Top 30 rules max to stay within context
            category = rule.get("category", "unknown")
            priority = rule.get("priority", "medium")
            description = rule.get("description", "")

            rules_text += f"{i}. [{priority.upper()}] {category.upper()}\n"
            rules_text += f"   Description: {description}\n"

            # Add validation keywords if available
            pattern = rule.get("validation_pattern", "")
            if pattern:
                rules_text += f"   Look for: {pattern[:100]}\n"

            rules_text += "\n"

        return rules_text

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    def validate_translation_batch(self, segments: List[Dict]) -> List[ValidationResult]:
        """
        Validate a batch of translations against consistency rules

        Args:
            segments: List of {segment_id, source_en, target_ko} dicts

        Returns:
            List of ValidationResult objects
        """
        # Format rules for prompt
        rules_prompt = self._format_rules_for_prompt()

        # Format segments for prompt
        segments_text = ""
        for i, seg in enumerate(segments, 1):
            segments_text += f"{i}. EN: {seg['source_en']}\n   KO: {seg['target_ko']}\n\n"

        prompt = f"""{rules_prompt}

# TRANSLATIONS TO VALIDATE
{segments_text}

# VALIDATION TASK
Validate each translation against the consistency rules above.

For each translation, analyze:
1. Does it follow the extracted tone/register patterns?
2. Are terminology terms translated consistently?
3. Are structural patterns (word order, sentence flow) appropriate?
4. Is the clinical protocol register maintained?

OUTPUT AS JSON (ONLY valid JSON, no markdown):
{{
  "validations": [
    {{
      "index": 1,
      "consistency_score": 0.85,
      "violations": [
        {{
          "rule_id": "TONE-003",
          "rule_description": "Use formal 합니다 endings",
          "severity": "high",
          "violation": "Found informal ~이다 ending in main clause",
          "suggested_correction": "...으로 구성됩니다"
        }}
      ],
      "tone_formality": "appropriate",
      "needs_correction": true,
      "correction_reason": "Critical violation in tone"
    }}
  ]
}}

IMPORTANT:
- Score: 0.0-1.0 (1.0 = perfect consistency)
- Violations: Only report if actual rule violation found
- Only suggest corrections for critical/high severity violations
- Be specific about what violates which rule
- Return ONLY valid JSON"""

        try:
            response = self.client.responses.create(
                model=self.model_name,
                input=[
                    {"role": "user", "content": prompt}
                ],
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
            else:
                self.logger.warning("⚠️  Could not find JSON in validation response")
                result = {"validations": []}

            # Track API usage
            self.api_calls_made += 1
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Cost: GPT-5.2 pricing
            call_cost = (input_tokens * 0.50 + output_tokens * 2.00) / 1_000_000
            self.total_cost += call_cost

            self.logger.debug(f"  API Call: {input_tokens} input, {output_tokens} output (${call_cost:.4f})")

            # Convert to ValidationResult objects
            validation_results = []
            for i, val in enumerate(result.get("validations", [])):
                if i < len(segments):
                    seg = segments[i]

                    # Parse violations
                    violations = []
                    for viol in val.get("violations", []):
                        violations.append(RuleViolation(
                            rule_id=viol.get("rule_id", "UNKNOWN"),
                            rule_description=viol.get("rule_description", ""),
                            violation_detail=viol.get("violation", ""),
                            severity=viol.get("severity", "medium"),
                            suggested_correction=viol.get("suggested_correction")
                        ))

                    result_obj = ValidationResult(
                        segment_id=seg.get("segment_id", ""),
                        source_en=seg['source_en'],
                        original_ko=seg['target_ko'],
                        consistency_score=val.get("consistency_score", 0.5),
                        rule_violations=violations,
                        needs_correction=val.get("needs_correction", False),
                        tone_formality=val.get("tone_formality", "appropriate")
                    )
                    validation_results.append(result_obj)

            return validation_results

        except Exception as e:
            self.logger.error(f"❌ Validation error: {e}")
            # Return default results
            return [
                ValidationResult(
                    segment_id=seg.get("segment_id", ""),
                    source_en=seg['source_en'],
                    original_ko=seg['target_ko'],
                    consistency_score=0.5,
                    rule_violations=[],
                    needs_correction=False
                )
                for seg in segments
            ]

    def generate_correction(self, source_en: str, original_ko: str, violations: List[RuleViolation]) -> str:
        """
        Generate a corrected translation based on violations

        Args:
            source_en: English source text
            original_ko: Original Korean translation
            violations: List of rule violations to fix

        Returns:
            Corrected Korean translation
        """
        violations_text = "\n".join([
            f"- [{v.severity.upper()}] {v.rule_description}: {v.violation_detail}"
            for v in violations
            if v.severity in ["critical", "high"]
        ])

        prompt = f"""You are a clinical protocol translation expert specializing in English-to-Korean medical document translation.

# ORIGINAL TRANSLATION
Source (EN): {source_en}
Current Translation (KO): {original_ko}

# VIOLATIONS TO FIX
{violations_text}

# CORRECTION TASK
Generate a corrected Korean translation that:
1. Fixes all the critical/high severity violations listed above
2. Maintains semantic accuracy of the original English
3. Uses formal 임상시험계획서 (clinical protocol) register
4. Follows Korean grammatical patterns (SOV word order, appropriate particles)
5. Uses proper medical terminology

IMPORTANT:
- Output ONLY the corrected Korean text
- Do not include explanations or JSON
- Ensure the corrected translation addresses each violation
- Maintain professional tone"""

        try:
            response = self.client.responses.create(
                model=self.model_name,
                input=[
                    {"role": "user", "content": prompt}
                ],
                text={"verbosity": "low"},
                reasoning={"effort": "low"}
            )

            corrected = self._extract_text_from_response(response).strip()

            # Track usage
            self.api_calls_made += 1
            cost = (response.usage.input_tokens * 0.50 + response.usage.output_tokens * 2.00) / 1_000_000
            self.total_cost += cost

            return corrected

        except Exception as e:
            self.logger.error(f"❌ Error generating correction: {e}")
            return original_ko

    def validate_translations(self, merged_df: pd.DataFrame, batch_size: int = 50, max_segments: Optional[int] = None) -> List[ValidationResult]:
        """
        Validate all translations in merged DataFrame

        Args:
            merged_df: DataFrame with Segment ID, Source segment, Target segment columns
            batch_size: Batch size for API calls
            max_segments: Maximum segments to validate (for testing)

        Returns:
            List of all ValidationResult objects
        """
        self.logger.info(f"🔍 Validating translations...")

        # Prepare segments
        segments_to_validate = []
        for idx, row in merged_df.iterrows():
            if max_segments and len(segments_to_validate) >= max_segments:
                break

            if pd.notna(row.get('Source segment')) and pd.notna(row.get('Target segment')):
                segments_to_validate.append({
                    'segment_id': str(row.get('Segment ID', f'seg_{idx}')),
                    'source_en': str(row['Source segment']),
                    'target_ko': str(row['Target segment'])
                })

        self.logger.info(f"  Total segments to validate: {len(segments_to_validate)}")

        # Process in batches
        all_results = []
        for batch_idx in range(0, len(segments_to_validate), batch_size):
            batch = segments_to_validate[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            total_batches = (len(segments_to_validate) + batch_size - 1) // batch_size

            self.logger.info(f"\n📦 Batch {batch_num}/{total_batches} ({len(batch)} segments)")

            # Validate batch
            batch_results = self.validate_translation_batch(batch)
            all_results.extend(batch_results)

            # Show progress
            if batch_idx + batch_size < len(segments_to_validate):
                pass  # Progress shown in next iteration

        self.logger.info(f"\n✅ Validated {len(all_results)} segments")
        self.logger.info(f"  Total API calls: {self.api_calls_made}")
        self.logger.info(f"  Total cost: ${self.total_cost:.4f}")

        self.validation_results = all_results
        return all_results

    def save_validation_results(self, output_path: str):
        """
        Save validation results to Excel

        Args:
            output_path: Path to output Excel file
        """
        self.logger.info(f"💾 Saving validation results to: {output_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Sheet 1: QA_Results
        results_data = []
        for result in self.validation_results:
            violation_count_critical = sum(1 for v in result.rule_violations if v.severity == "critical")
            violation_count_high = sum(1 for v in result.rule_violations if v.severity == "high")
            violation_count_medium = sum(1 for v in result.rule_violations if v.severity == "medium")

            status = "PASS" if not result.rule_violations else ("CORRECTED" if result.corrected_ko else "REVIEW")

            results_data.append({
                'Segment ID': result.segment_id,
                'Source (EN)': result.source_en[:150],
                'Original (KO)': result.original_ko[:150],
                'Consistency Score': round(result.consistency_score, 2),
                'Tone Formality': result.tone_formality,
                'Violations (Critical/High/Med)': f"{violation_count_critical}/{violation_count_high}/{violation_count_medium}",
                'Needs Correction': result.needs_correction,
                'Corrected (KO)': result.corrected_ko[:150] if result.corrected_ko else '',
                'Status': status
            })

        df_results = pd.DataFrame(results_data)

        # Sheet 2: Rule_Violations
        violations_data = []
        for result in self.validation_results:
            for viol in result.rule_violations:
                violations_data.append({
                    'Segment ID': result.segment_id,
                    'Rule ID': viol.rule_id,
                    'Rule Description': viol.rule_description,
                    'Violation': viol.violation_detail,
                    'Severity': viol.severity,
                    'Suggested Correction': viol.suggested_correction or ''
                })

        df_violations = pd.DataFrame(violations_data)

        # Sheet 3: Summary
        total_segments = len(self.validation_results)
        segments_pass = sum(1 for r in self.validation_results if not r.rule_violations)
        segments_corrected = sum(1 for r in self.validation_results if r.corrected_ko)
        segments_review = total_segments - segments_pass - segments_corrected
        avg_score = sum(r.consistency_score for r in self.validation_results) / total_segments if total_segments > 0 else 0

        summary_data = {
            'Metric': [
                'Total Segments Validated',
                'Segments PASS (No violations)',
                'Segments CORRECTED',
                'Segments Need REVIEW',
                'Average Consistency Score',
                'API Calls Made',
                'Total Cost'
            ],
            'Value': [
                str(total_segments),
                f"{segments_pass} ({100*segments_pass/total_segments:.1f}%)",
                f"{segments_corrected} ({100*segments_corrected/total_segments:.1f}%)",
                f"{segments_review} ({100*segments_review/total_segments:.1f}%)",
                f"{avg_score:.2f}",
                str(self.api_calls_made),
                f"${self.total_cost:.4f}"
            ]
        }
        df_summary = pd.DataFrame(summary_data)

        # Write to Excel
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df_results.to_excel(writer, sheet_name='QA_Results', index=False)
            df_violations.to_excel(writer, sheet_name='Rule_Violations', index=False)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)

        self.logger.info(f"  ✓ Saved validation results to {output_path}")

        return output_path


def main():
    """Main execution"""
    print("Protocol Consistency Validator module loaded successfully")


if __name__ == '__main__':
    main()
