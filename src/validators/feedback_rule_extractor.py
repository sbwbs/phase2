#!/usr/bin/env python3
"""
Feedback Rule Extractor
Uses GPT-5 OWL to extract validation rules from customer feedback files
"""

import json
import logging
import os
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import pandas as pd
from pathlib import Path
import re

logger = logging.getLogger(__name__)

@dataclass
class ValidationRule:
    rule_id: str
    category: str
    description: str
    pattern: Optional[str]
    severity: str
    examples: List[tuple]
    checker_function: str
    source: str

class FeedbackRuleExtractor:
    """
    Extracts validation rules from customer feedback files using LLM
    Supports Excel (.xlsx) feedback files
    """

    def __init__(self, model_name: str = "gpt-5"):
        """
        Initialize rule extractor with LLM model

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

    def extract_rules_from_excel(self, excel_path: str) -> List[ValidationRule]:
        """
        Read Excel feedback file and extract validation rules using LLM

        Args:
            excel_path: Path to Excel feedback file

        Returns:
            List of ValidationRule objects extracted from feedback
        """
        self.logger.info(f"Extracting rules from Excel: {excel_path}")

        try:
            # Read Excel file
            df = pd.read_excel(excel_path)

            if df.empty:
                self.logger.warning(f"Excel file empty: {excel_path}")
                return []

            # Convert to readable text format
            feedback_text = self._convert_excel_to_text(df, excel_path)

            # Extract rules using LLM
            rules = self._extract_rules_with_llm(feedback_text, excel_path)

            return rules

        except Exception as e:
            self.logger.error(f"Error extracting rules from Excel: {e}")
            return []

    def extract_rules_from_docx(self, docx_path: str) -> List[ValidationRule]:
        """
        Read Word document feedback and extract validation rules using LLM

        Args:
            docx_path: Path to Word document feedback file

        Returns:
            List of ValidationRule objects extracted from feedback
        """
        self.logger.info(f"Extracting rules from DOCX: {docx_path}")

        try:
            # Try importing python-docx
            try:
                from docx import Document
            except ImportError:
                self.logger.error("python-docx required. Install with: pip install python-docx")
                return []

            # Read Word document
            doc = Document(docx_path)
            feedback_text = "\n".join([para.text for para in doc.paragraphs])

            if not feedback_text.strip():
                self.logger.warning(f"No text found in Word document: {docx_path}")
                return []

            # Extract rules using LLM
            rules = self._extract_rules_with_llm(feedback_text, docx_path)

            return rules

        except Exception as e:
            self.logger.error(f"Error extracting rules from DOCX: {e}")
            return []

    def consolidate_rules(self, all_rules: List[ValidationRule]) -> Dict[str, ValidationRule]:
        """
        Merge rules from multiple feedback files
        Remove duplicates, prioritize by frequency

        Args:
            all_rules: List of all rules from all feedback files

        Returns:
            Dictionary of consolidated rules (rule_id -> ValidationRule)
        """
        self.logger.info(f"Consolidating {len(all_rules)} rules from multiple sources")

        consolidated = {}

        for rule in all_rules:
            if rule.rule_id in consolidated:
                # Rule already exists - merge examples
                existing_rule = consolidated[rule.rule_id]
                existing_rule.examples.extend(rule.examples)
                existing_rule.examples = list(set(existing_rule.examples))  # Deduplicate
            else:
                consolidated[rule.rule_id] = rule

        self.logger.info(f"Consolidated to {len(consolidated)} unique rules")
        return consolidated

    # Helper Methods

    def _convert_excel_to_text(self, df: pd.DataFrame, filename: str) -> str:
        """Convert Excel DataFrame to readable text format for LLM"""
        text_parts = [f"Feedback file: {Path(filename).name}\n"]

        # Add column headers
        text_parts.append("Columns: " + ", ".join(df.columns.tolist()) + "\n")

        # Add data rows
        text_parts.append("\nFeedback content:\n")
        for idx, row in df.iterrows():
            text_parts.append(f"Row {idx + 1}:")
            for col, value in row.items():
                if pd.notna(value):
                    text_parts.append(f"  {col}: {value}")
            text_parts.append("")

        return "\n".join(text_parts)

    def _extract_rules_with_llm(self, feedback_text: str, source_file: str) -> List[ValidationRule]:
        """
        Use GPT-5 OWL to analyze feedback and extract validation rules

        Args:
            feedback_text: Feedback content as text
            source_file: Source filename for rule tracking

        Returns:
            List of extracted ValidationRule objects
        """
        self.logger.info(f"Using {self.model_name} to extract rules from feedback")

        # Create LLM prompt
        prompt = self._create_extraction_prompt(feedback_text, source_file)

        try:
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-5",  # GPT-5 OWL
                messages=[
                    {
                        "role": "system",
                        "content": "You are a clinical translation quality assurance expert. Extract validation rules from customer feedback on translations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_completion_tokens=2000,
                response_format={"type": "json_object"}
            )

            # Parse response
            response_text = response.choices[0].message.content

            # Extract JSON from response
            rules_data = json.loads(response_text)

            # Convert to ValidationRule objects
            rules = self._parse_llm_response(rules_data, source_file)

            self.logger.info(f"Extracted {len(rules)} rules from {Path(source_file).name}")
            return rules

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse LLM response as JSON: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error calling LLM: {e}")
            return []

    def _create_extraction_prompt(self, feedback_text: str, source_file: str) -> str:
        """Create LLM prompt for rule extraction"""
        return f"""Analyze the following customer feedback on clinical protocol translations and extract validation rules.

Source file: {Path(source_file).name}

Feedback content:
{feedback_text}

Extract validation rules by identifying:
1. Patterns of corrections (e.g., "shall" used in X segments, "should" in Y segments)
2. Numeric/dosage inconsistencies flagged by reviewer
3. Modal verb usage corrections (must/shall/should/may/will per ICH GCP)
4. Terminology enforcement issues
5. Ratio and unit inconsistencies

For each pattern found, provide:
- Rule ID (unique identifier like MODAL_VERB_SHALL, DOSAGE_FORMAT, etc.)
- Category (modal_verbs, numbers, ratios, terminology, units, etc.)
- Description of the rule (clear, actionable)
- Pattern or regex if applicable (else null)
- Severity (critical, high, medium, low)
- Examples array with [incorrect, correct] pairs from feedback
- Checker function name (validate_modal_verbs, validate_dosages, etc.)

Return ONLY valid JSON in this format:
{{
  "rules": [
    {{
      "rule_id": "RULE_NAME",
      "category": "category_name",
      "description": "Clear description of rule",
      "pattern": "regex pattern or null",
      "severity": "critical|high|medium|low",
      "examples": [["incorrect", "correct"], ["incorrect", "correct"]],
      "checker_function": "function_name"
    }}
  ]
}}

Critical rules to identify:
- Mandatory terms that must be translated consistently
- Modal verb hierarchy per ICH GCP guidelines
- Numeric accuracy requirements (exact matching for dosages)
- Unit/ratio formatting requirements
- Prohibited translations or phrasings"""

    def _parse_llm_response(self, response_data: Dict, source_file: str) -> List[ValidationRule]:
        """Convert LLM response JSON to ValidationRule objects"""
        rules = []

        rules_list = response_data.get('rules', [])

        for rule_data in rules_list:
            try:
                rule = ValidationRule(
                    rule_id=rule_data.get('rule_id', 'UNKNOWN'),
                    category=rule_data.get('category', 'general'),
                    description=rule_data.get('description', ''),
                    pattern=rule_data.get('pattern'),
                    severity=rule_data.get('severity', 'medium'),
                    examples=rule_data.get('examples', []),
                    checker_function=rule_data.get('checker_function', 'validate_generic'),
                    source=str(Path(source_file).name)
                )
                rules.append(rule)
            except Exception as e:
                self.logger.warning(f"Failed to parse rule: {e}")
                continue

        return rules


def convert_rule_to_dict(rule: ValidationRule) -> Dict:
    """Convert ValidationRule to dictionary for Excel export"""
    return asdict(rule)


def rules_to_dataframe(rules: Dict[str, ValidationRule]) -> pd.DataFrame:
    """Convert rules dictionary to pandas DataFrame"""
    rules_list = [
        {
            'Rule ID': rule.rule_id,
            'Category': rule.category,
            'Description': rule.description,
            'Pattern': rule.pattern or 'N/A',
            'Severity': rule.severity,
            'Example Count': len(rule.examples),
            'Examples': '; '.join([f"{ex[0]} → {ex[1]}" for ex in rule.examples[:3]]),
            'Source': rule.source
        }
        for rule in rules.values()
    ]

    return pd.DataFrame(rules_list)
