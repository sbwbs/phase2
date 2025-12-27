#!/usr/bin/env python3
"""
LLM Semantic Validator
Uses GPT-5 OWL to validate translation meaning preservation and customer feedback compliance
"""

import json
import logging
import os
from typing import List, Dict, Optional
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    passed: bool
    message: str
    confidence: float
    issues: List[Dict]
    details: Dict

class LLMSemanticValidator:
    """Uses GPT-5 OWL for semantic translation validation"""

    def __init__(self, model_name: str = "gpt-5"):
        """
        Initialize semantic validator with GPT-5 OWL

        Args:
            model_name: LLM model to use ('gpt-5' for OWL)
        """
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)

        # Import OpenAI client
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        except ImportError:
            self.logger.error("OpenAI library required. Install with: pip install openai")
            raise

    def validate_translation(
        self,
        source: str,
        target: str,
        direction: str = "ko-en"
    ) -> ValidationResult:
        """
        Comprehensive translation validation using hardcoded prompts with GPT-5 OWL

        Checks:
        1. Numbers and dosages match exactly (100 mg, 5 mL, etc.)
        2. Ratios preserved (mg/kg, mg/m², mL/min)
        3. Modal verbs follow ICH GCP hierarchy (must > shall > should > may > will)
        4. Meaning preserved (no additions or omissions)
        5. Critical details accurate

        Args:
            source: Source text
            target: Target translation
            direction: Translation direction (ko-en or en-ko)

        Returns:
            ValidationResult with pass/fail and confidence score
        """
        self.logger.info(f"Validating translation ({direction})")

        prompt = self._create_validation_prompt(source, target, direction)

        try:
            response = self.client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a clinical translation QA expert. Validate if translations preserve source meaning."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_completion_tokens=1000,
                response_format={"type": "json_object"}
            )

            response_text = response.choices[0].message.content
            result_data = json.loads(response_text)

            return self._parse_meaning_result(result_data, source, target)

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse LLM response: {e}")
            return ValidationResult(
                passed=False,
                message=f"LLM response parsing error",
                confidence=0.0,
                issues=[{"type": "parsing_error", "detail": str(e)}],
                details={}
            )
        except Exception as e:
            self.logger.error(f"Error validating meaning: {e}")
            return ValidationResult(
                passed=False,
                message=f"Validation error: {str(e)}",
                confidence=0.0,
                issues=[{"type": "validation_error", "detail": str(e)}],
                details={}
            )

    def validate_critical_details(
        self,
        source: str,
        target: str,
        critical_terms: List[str]
    ) -> List[Dict]:
        """
        Check if critical details (numbers, dosages, terms) are preserved

        Args:
            source: Source text
            target: Target translation
            critical_terms: List of critical terms to verify

        Returns:
            List of issues found with critical details
        """
        self.logger.info(f"Validating {len(critical_terms)} critical details")

        issues = []

        # Check numeric preservation
        source_numbers = re.findall(r'\d+(?:\.\d+)?', source)
        target_numbers = re.findall(r'\d+(?:\.\d+)?', target)

        if source_numbers and set(source_numbers) != set(target_numbers):
            issues.append({
                "type": "numeric_mismatch",
                "source_numbers": source_numbers,
                "target_numbers": target_numbers,
                "severity": "critical"
            })

        # Check critical term presence
        for term in critical_terms:
            if term.lower() not in target.lower():
                issues.append({
                    "type": "missing_critical_term",
                    "term": term,
                    "severity": "high"
                })

        return issues

    def cross_validate_with_feedback(
        self,
        source: str,
        target: str,
        feedback_rules: List[Dict]
    ) -> ValidationResult:
        """
        Apply extracted customer feedback rules using LLM judgment

        Args:
            source: Source text
            target: Target translation
            feedback_rules: List of extracted validation rules from feedback

        Returns:
            ValidationResult indicating compliance with customer feedback rules
        """
        self.logger.info(f"Cross-validating with {len(feedback_rules)} customer feedback rules")

        # Format rules for prompt
        rules_text = self._format_rules_for_prompt(feedback_rules)

        prompt = self._create_feedback_validation_prompt(source, target, rules_text)

        try:
            response = self.client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a clinical translation QA expert. Validate translations against customer feedback rules."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            response_text = response.choices[0].message.content
            result_data = json.loads(response_text)

            return self._parse_feedback_result(result_data, source, target)

        except Exception as e:
            self.logger.error(f"Error validating feedback compliance: {e}")
            return ValidationResult(
                passed=False,
                message=f"Feedback validation error: {str(e)}",
                confidence=0.0,
                issues=[{"type": "validation_error", "detail": str(e)}],
                details={}
            )

    def validate_all(
        self,
        source: str,
        target: str,
        feedback_rules: List[Dict] = None,
        critical_terms: List[str] = None,
        direction: str = "ko-en"
    ) -> ValidationResult:
        """
        Run comprehensive LLM semantic validation

        Args:
            source: Source text
            target: Target translation
            feedback_rules: Customer feedback rules to validate against
            critical_terms: Critical terms that must be preserved
            direction: Translation direction

        Returns:
            Comprehensive ValidationResult
        """
        self.logger.info("Running comprehensive semantic validation")

        feedback_rules = feedback_rules or []
        critical_terms = critical_terms or []

        # Check meaning preservation
        meaning_result = self.validate_meaning_preservation(source, target, direction)

        # Check critical details
        critical_issues = self.validate_critical_details(source, target, critical_terms)

        # Check feedback compliance
        feedback_result = (
            self.cross_validate_with_feedback(source, target, feedback_rules)
            if feedback_rules
            else ValidationResult(
                passed=True,
                message="No feedback rules to validate",
                confidence=1.0,
                issues=[],
                details={}
            )
        )

        # Aggregate results
        all_issues = meaning_result.issues + critical_issues + feedback_result.issues
        passed = meaning_result.passed and feedback_result.passed and len(critical_issues) == 0

        avg_confidence = (meaning_result.confidence + feedback_result.confidence) / 2

        return ValidationResult(
            passed=passed,
            message=self._aggregate_message(meaning_result, feedback_result, critical_issues),
            confidence=avg_confidence,
            issues=all_issues,
            details={
                "meaning_preserved": meaning_result.passed,
                "critical_details_ok": len(critical_issues) == 0,
                "feedback_compliant": feedback_result.passed,
                "confidence": avg_confidence
            }
        )

    # Helper Methods

    def _create_validation_prompt(self, source: str, target: str, direction: str) -> str:
        """
        Create comprehensive hardcoded validation prompt for GPT-5 OWL

        This prompt validates:
        - Numbers/dosages (100 mg, 5 mL, etc.)
        - Ratios (mg/kg, mg/m², mL/min)
        - Modal verbs per ICH GCP (must > shall > should > may > will)
        - Meaning preservation (no additions/omissions)
        - Critical details accuracy
        """
        lang_map = {"ko-en": ("Korean", "English"), "en-ko": ("English", "Korean")}
        source_lang, target_lang = lang_map.get(direction, ("Source", "Target"))

        return f"""You are a clinical translation QA expert. Validate this translation comprehensively.

Source ({source_lang}):
{source}

Target ({target_lang}):
{target}

VALIDATION CHECKLIST:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NUMERIC ACCURACY (CRITICAL)
   ✓ All numbers match exactly (100 mg, 5 mL, patient counts)
   ✓ Dosages preserved (100mg NOT "approximately 100mg")
   ✓ Ratios correct (mg/kg, mg/m², mL/min)
   ✓ Percentages exact (95%, 0.05, p<0.001)

2. MODAL VERB COMPLIANCE (HIGH - ICH GCP)
   ✓ MUST (highest) - Legal/regulatory requirements
   ✓ SHALL (mandatory) - Protocol procedures (~해야 한다)
   ✓ SHOULD (strong) - Recommendations (권장)
   ✓ MAY (optional) - Permission (~할 수 있다)
   ✓ WILL (future) - Factual statements
   ✗ NO downgrades (must→should, shall→may)

3. MEANING PRESERVATION (HIGH)
   ✓ Exact meaning maintained
   ✓ No additions (extra information not in source)
   ✓ No omissions (missing critical details)
   ✓ Appropriate tone/register for clinical docs

4. CRITICAL DETAILS (HIGH)
   ✓ Terminology correct (교수→Professor ONLY, not MD/PhD)
   ✓ Units consistent (mg/kg not mg per kg)
   ✓ Names formatted correctly (Last, First)
   ✓ Abbreviations consistent

5. TECHNICAL REQUIREMENTS
   ✓ No hallucinations (additions of context)
   ✓ No verbosity (translation not 1.5x longer than source)
   ✓ Symbols converted to words if applicable

RESPONSE FORMAT - STRICT JSON:
{{
  "overall_pass": true/false,
  "numeric_accuracy": {{
    "passed": true/false,
    "issues": ["issue1", "issue2"]
  }},
  "modal_verbs": {{
    "passed": true/false,
    "issues": ["issue1", "issue2"]
  }},
  "meaning_preservation": {{
    "passed": true/false,
    "issues": ["issue1", "issue2"]
  }},
  "critical_details": {{
    "passed": true/false,
    "issues": ["issue1", "issue2"]
  }},
  "confidence": 0.85,
  "explanation": "brief summary of validation result"
}}

INSTRUCTIONS:
1. Check EACH criterion carefully
2. Flag ANY discrepancy, no matter how small
3. Be STRICT on numbers - exact matching required
4. Be STRICT on modal verbs - ICH GCP hierarchy enforced
5. Be STRICT on meaning - no additions or omissions
6. Return confidence 0.0-1.0 based on severity of issues"""

    def _create_feedback_validation_prompt(self, source: str, target: str, rules_text: str) -> str:
        """Create prompt for feedback compliance validation"""
        return f"""Validate this translation against customer feedback rules and regulatory guidelines.

Source:
{source}

Target:
{target}

Customer Feedback Rules:
{rules_text}

Regulatory Guidelines:
- Modal verbs per ICH GCP (must > shall > should > may > will)
- Numeric accuracy (exact matching for dosages, percentages)
- Terminology consistency (use approved glossary terms)
- Unit/ratio formatting (mg/kg, mg/m², mL/min exact format)

Validation tasks:
1. Check if translation follows all extracted customer rules
2. Verify modal verb usage aligns with ICH GCP hierarchy
3. Confirm numeric values match exactly
4. Validate terminology against approved glossary
5. Check ratio and unit formatting

Respond with JSON containing:
{{
  "rules_compliance": true/false,
  "violations": [
    {{"rule_id": "RULE_NAME", "issue": "description", "severity": "critical|high|medium|low"}}
  ],
  "modal_verbs_correct": true/false,
  "numeric_accuracy": true/false,
  "terminology_correct": true/false,
  "confidence": 0.0-1.0,
  "recommendation": "PASS|CONDITIONAL|FAIL"
}}"""

    def _format_rules_for_prompt(self, feedback_rules: List[Dict]) -> str:
        """Format feedback rules for LLM prompt"""
        if not feedback_rules:
            return "No customer feedback rules provided."

        rules_text = []
        for rule in feedback_rules:
            rule_id = rule.get('rule_id', 'UNKNOWN')
            description = rule.get('description', '')
            category = rule.get('category', '')
            examples = rule.get('examples', [])

            rule_str = f"- {rule_id} ({category}): {description}"
            if examples:
                example_str = "; ".join([f'"{ex[0]}" → "{ex[1]}"' for ex in examples[:2]])
                rule_str += f" [Examples: {example_str}]"
            rules_text.append(rule_str)

        return "\n".join(rules_text)

    def _parse_meaning_result(self, result_data: Dict, source: str, target: str) -> ValidationResult:
        """Parse meaning validation response"""
        passed = result_data.get('meaning_preserved', False)
        confidence = result_data.get('confidence', 0.0)
        critical_issues = result_data.get('critical_issues', [])

        issues = [
            {
                "type": "meaning_not_preserved",
                "issue": issue,
                "severity": result_data.get('severity', 'high')
            }
            for issue in critical_issues
        ]

        return ValidationResult(
            passed=passed,
            message=result_data.get('explanation', 'Validation complete'),
            confidence=confidence,
            issues=issues,
            details={
                "critical_issues": critical_issues,
                "severity": result_data.get('severity', 'unknown')
            }
        )

    def _parse_feedback_result(self, result_data: Dict, source: str, target: str) -> ValidationResult:
        """Parse feedback compliance validation response"""
        passed = result_data.get('rules_compliance', False)
        confidence = result_data.get('confidence', 0.0)
        violations = result_data.get('violations', [])

        return ValidationResult(
            passed=passed,
            message=f"Feedback compliance: {result_data.get('recommendation', 'UNKNOWN')}",
            confidence=confidence,
            issues=violations,
            details={
                "modal_verbs_correct": result_data.get('modal_verbs_correct', False),
                "numeric_accuracy": result_data.get('numeric_accuracy', False),
                "terminology_correct": result_data.get('terminology_correct', False),
                "recommendation": result_data.get('recommendation', 'UNKNOWN')
            }
        )

    def _aggregate_message(self, meaning_result: ValidationResult, feedback_result: ValidationResult, critical_issues: List) -> str:
        """Aggregate validation results into summary message"""
        status = []

        if meaning_result.passed:
            status.append("✅ Meaning preserved")
        else:
            status.append("❌ Meaning issues detected")

        if len(critical_issues) == 0:
            status.append("✅ Critical details preserved")
        else:
            status.append(f"❌ {len(critical_issues)} critical issues found")

        if feedback_result.passed:
            status.append("✅ Feedback compliant")
        else:
            status.append("❌ Feedback violations detected")

        return " | ".join(status)
