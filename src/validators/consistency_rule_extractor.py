#!/usr/bin/env python3
"""
Consistency Rule Extractor
Extracts tone, terminology, and structural consistency rules from reference EN-KO translation pairs
Uses GPT-5.2 for pattern recognition and rule generation
"""

import json
import logging
import os
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field
import pandas as pd
from datetime import datetime

# OpenAI for GPT-5.2
import openai
from tenacity import retry, wait_exponential, stop_after_attempt


@dataclass
class ConsistencyRule:
    """Represents a single consistency rule extracted from reference pairs"""
    rule_id: str
    category: str  # "tone", "terminology", "structure", "clinical"
    description: str
    priority: str  # "critical", "high", "medium", "low"
    example_pairs: List[Dict[str, str]] = field(default_factory=list)  # [{en: ..., ko: ...}, ...]
    validation_pattern: Optional[str] = None  # regex or keyword pattern for validation
    checker_function: Optional[str] = None  # Python code snippet for complex checks


class ConsistencyRuleExtractor:
    """Extract consistency rules from EN-KO reference pairs using GPT-5.2"""

    def __init__(self, model_name: str = "gpt-5.2", batch_size: int = 50):
        """
        Initialize rule extractor

        Args:
            model_name: GPT model to use ("gpt-5.2" recommended)
            batch_size: Number of pairs to process per API call
        """
        self.setup_logging()
        self.model_name = model_name
        self.batch_size = batch_size
        self.extracted_rules: List[ConsistencyRule] = []
        self.api_calls_made = 0
        self.total_cost = 0.0

        # Initialize OpenAI (use responses API for GPT-5 models)
        self.client = openai.OpenAI()

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

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(5))
    def call_gpt52_extraction(self, pair_batch: List[Dict[str, str]]) -> Dict:
        """
        Call GPT-5.2 to extract consistency rules from reference pairs

        Args:
            pair_batch: List of {en: ..., ko: ...} translation pairs

        Returns:
            Dict with extracted rules in JSON format
        """
        # Format pairs for prompt
        pairs_text = "\n".join([
            f"{i+1}. EN: {pair['en']}\n   KO: {pair['ko']}"
            for i, pair in enumerate(pair_batch)
        ])

        prompt = f"""Given these {len(pair_batch)} professional English-to-Korean clinical protocol translation pairs, analyze and extract consistency rules.

TRANSLATION PAIRS:
{pairs_text}

TASK: Identify and extract the following types of consistency patterns:

1. **TONE & REGISTER PATTERNS**: How is formality maintained?
   - Examples: 합니다 endings, passive voice usage, objective tone

2. **TERMINOLOGY CONSISTENCY**: How are medical/clinical terms translated?
   - Examples: Recurring term translations, abbreviation handling, Korean(English, ABBREV) format

3. **STRUCTURAL PATTERNS**: How are EN→KO transformations handled?
   - Examples: Word order changes, sentence splits, clause linking patterns, particle usage

4. **CLINICAL PROTOCOL SPECIFIC**: Any ICH GCP or regulatory compliance patterns?

OUTPUT AS JSON with this structure (provide ONLY valid JSON, no markdown):
{{
  "rules": [
    {{
      "rule_id": "TONE-001",
      "category": "tone",
      "priority": "critical",
      "description": "Use formal 합니다 endings for main clauses in regulatory content",
      "examples": [
        {{"en": "...", "ko": "...", "pattern": "explanation of the pattern"}},
        {{"en": "...", "ko": "...", "pattern": "explanation of the pattern"}}
      ],
      "validation_keywords": ["합니다", "됩니다"]
    }}
  ]
}}

IMPORTANT:
- Extract 5-10 distinct rules per batch
- Focus on patterns that appear in multiple pairs
- Priority: Extract CRITICAL patterns (appear in 50%+ of pairs)
- Be specific: Include actual Korean patterns, endings, terminology
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

            # Try to extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
            else:
                self.logger.warning("⚠️  Could not find JSON in response")
                result = {"rules": []}

            # Track API usage
            self.api_calls_made += 1
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Cost calculation (GPT-5.2 pricing: $0.50/1M input, $2.00/1M output)
            call_cost = (input_tokens * 0.50 + output_tokens * 2.00) / 1_000_000
            self.total_cost += call_cost

            self.logger.info(f"  API Call {self.api_calls_made}: {input_tokens} input, {output_tokens} output tokens (${call_cost:.4f})")

            return result

        except json.JSONDecodeError as e:
            self.logger.error(f"  ❌ JSON decode error: {e}")
            return {"rules": []}

    def extract_rules_from_pairs(self, reference_pairs: List[Dict[str, str]]) -> List[ConsistencyRule]:
        """
        Extract consistency rules from reference pairs

        Args:
            reference_pairs: List of {en: ..., ko: ...} professional translation pairs

        Returns:
            List of extracted ConsistencyRule objects
        """
        self.logger.info(f"🔍 Extracting consistency rules from {len(reference_pairs)} reference pairs...")

        all_rules = []
        rule_counter = {}  # Track rule count per category

        # Process in batches
        for batch_idx in range(0, len(reference_pairs), self.batch_size):
            batch = reference_pairs[batch_idx:batch_idx + self.batch_size]
            batch_num = (batch_idx // self.batch_size) + 1

            self.logger.info(f"\n📦 Processing batch {batch_num} ({len(batch)} pairs)...")

            # Call GPT-5.2
            result = self.call_gpt52_extraction(batch)

            # Parse results
            if "rules" in result:
                for rule_data in result["rules"]:
                    # Create ConsistencyRule object
                    rule_id = rule_data.get("rule_id", f"RULE-{len(all_rules)+1}")
                    category = rule_data.get("category", "general")
                    priority = rule_data.get("priority", "medium")

                    rule = ConsistencyRule(
                        rule_id=rule_id,
                        category=category,
                        priority=priority,
                        description=rule_data.get("description", ""),
                        example_pairs=rule_data.get("examples", []),
                        validation_pattern="|".join(rule_data.get("validation_keywords", []))
                    )

                    all_rules.append(rule)

                    # Count by category
                    if category not in rule_counter:
                        rule_counter[category] = 0
                    rule_counter[category] += 1

                    self.logger.info(f"  ✓ Extracted: {rule_id} ({category}, priority={priority})")

        # Deduplicate and consolidate
        self.logger.info(f"\n🔄 Consolidating {len(all_rules)} rules...")

        consolidated_rules = self._deduplicate_rules(all_rules)

        self.logger.info(f"  Consolidated to {len(consolidated_rules)} unique rules")
        self.logger.info("\n  Rule summary by category:")
        for category, count in sorted(rule_counter.items()):
            self.logger.info(f"    - {category}: {count} rules")

        self.extracted_rules = consolidated_rules
        return consolidated_rules

    def _deduplicate_rules(self, rules: List[ConsistencyRule]) -> List[ConsistencyRule]:
        """
        Remove duplicate/similar rules, keep highest priority versions

        Args:
            rules: List of ConsistencyRule objects

        Returns:
            Deduplicated list
        """
        # Group by description similarity (simple approach)
        seen_descriptions = {}
        deduplicated = []

        for rule in rules:
            # Normalize description for comparison
            desc_key = rule.description[:50].lower()

            if desc_key not in seen_descriptions:
                seen_descriptions[desc_key] = rule
                deduplicated.append(rule)
            else:
                # Keep higher priority version
                existing = seen_descriptions[desc_key]
                priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

                if priority_order[rule.priority] < priority_order[existing.priority]:
                    # New rule has higher priority, replace
                    deduplicated.remove(existing)
                    deduplicated.append(rule)
                    seen_descriptions[desc_key] = rule

        return deduplicated

    def save_rules_json(self, output_path: str):
        """
        Save extracted rules to JSON file

        Args:
            output_path: Path to output JSON file
        """
        self.logger.info(f"💾 Saving rules to JSON: {output_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Convert to serializable format
        rules_dict = {
            "metadata": {
                "extraction_date": datetime.now().isoformat(),
                "total_rules": len(self.extracted_rules),
                "api_calls": self.api_calls_made,
                "total_cost": f"${self.total_cost:.4f}",
                "model": self.model_name
            },
            "rules": [
                {
                    **asdict(rule),
                    "category": rule.category,
                    "priority": rule.priority,
                    "description": rule.description
                }
                for rule in self.extracted_rules
            ]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(rules_dict, f, indent=2, ensure_ascii=False)

        self.logger.info(f"  ✓ Saved {len(self.extracted_rules)} rules")

        return output_path

    def save_rules_excel(self, output_path: str):
        """
        Save extracted rules to Excel for human review

        Args:
            output_path: Path to output Excel file
        """
        self.logger.info(f"💾 Saving rules to Excel: {output_path}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Create DataFrame
        rows = []
        for rule in self.extracted_rules:
            rows.append({
                'Rule ID': rule.rule_id,
                'Category': rule.category,
                'Priority': rule.priority,
                'Description': rule.description,
                'Example 1 (EN)': rule.example_pairs[0]['en'] if rule.example_pairs else '',
                'Example 1 (KO)': rule.example_pairs[0]['ko'] if rule.example_pairs else '',
                'Example 2 (EN)': rule.example_pairs[1]['en'] if len(rule.example_pairs) > 1 else '',
                'Example 2 (KO)': rule.example_pairs[1]['ko'] if len(rule.example_pairs) > 1 else '',
                'Validation Pattern': rule.validation_pattern or '',
            })

        df = pd.DataFrame(rows)
        df.to_excel(output_path, index=False, engine='openpyxl')

        self.logger.info(f"  ✓ Saved {len(self.extracted_rules)} rules to Excel")

        return output_path


def main():
    """Main execution - test rule extraction"""
    # This will be called from run_protocol_consistency_qa.py
    # For standalone testing:
    print("Consistency Rule Extractor module loaded successfully")


if __name__ == '__main__':
    main()
