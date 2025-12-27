#!/usr/bin/env python3
"""
Protocol QA Rule Extractor - Processor 1
Loads reference documents from /Users/won.suh/Downloads/pair/
Extracts EN-KO translation rules using GPT-5.2
Output: JSON file with extracted rules for use in QA validator
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict

import openai
from docx import Document
from tenacity import retry, wait_exponential, stop_after_attempt

sys.path.insert(0, os.path.dirname(__file__))


class ProtocolQARuleExtractor:
    """Extract EN-KO translation rules from reference documents"""

    def __init__(self):
        """Initialize rule extractor"""
        self.setup_logging()
        self.client = openai.OpenAI()
        self.extracted_rules = {}

    def setup_logging(self):
        """Initialize logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_reference_documents(self) -> str:
        """
        Load reference documents from /Users/won.suh/Downloads/pair/
        Extract text content from both EN and KO versions

        Returns:
            Combined text from both documents for rule extraction
        """
        self.logger.info("📂 Loading reference documents...")

        en_doc_path = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_EN.docx"
        ko_doc_path = "/Users/won.suh/Downloads/pair/83-0060-02_Protocol 1.2-18Jul2025_Korean_final.docx"

        if not os.path.exists(en_doc_path):
            raise FileNotFoundError(f"EN doc not found: {en_doc_path}")
        if not os.path.exists(ko_doc_path):
            raise FileNotFoundError(f"KO doc not found: {ko_doc_path}")

        # Load English document
        en_doc = Document(en_doc_path)
        en_text = "\n".join([p.text for p in en_doc.paragraphs if p.text.strip()])
        self.logger.info(f"  ✓ English doc: {len(en_text)} chars")

        # Load Korean document
        ko_doc = Document(ko_doc_path)
        ko_text = "\n".join([p.text for p in ko_doc.paragraphs if p.text.strip()])
        self.logger.info(f"  ✓ Korean doc: {len(ko_text)} chars")

        # Return combined for analysis
        return f"ENGLISH:\n{en_text}\n\nKOREAN:\n{ko_text}"

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

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    def extract_rules_from_docs(self, doc_text: str) -> Dict:
        """
        Use GPT-5.2 to extract EN-KO translation rules from reference documents

        Args:
            doc_text: Combined EN and KO document text

        Returns:
            Dict with extracted rules
        """
        prompt = f"""You are a clinical protocol translation expert. I'm providing you with professional EN-KO translation examples from a clinical study protocol.

REFERENCE DOCUMENTS:
{doc_text[:5000]}  # Limit to first 5000 chars to stay in budget

TASK: Analyze these professional translations and extract the KEY TRANSLATION RULES that should be applied when translating English clinical protocols to Korean.

Extract rules in these categories:

1. **TERMINOLOGY RULES**: How are key medical/clinical terms translated?
   - Examples of term translations observed
   - Patterns for handling technical terms
   - Abbreviation handling (Korean(English, ABBREV) format?)

2. **TONE & FORMALITY**: What register/style is used?
   - Formal endings (합니다, 됩니다, etc.)
   - Passive vs active voice preference
   - Sentence structure patterns

3. **STRUCTURAL PATTERNS**: How are EN sentences transformed to KO?
   - Complex sentences: split or combined?
   - Word order patterns (SVO vs SOV)
   - Clause linking patterns

4. **REGULATORY COMPLIANCE**: Any specific clinical/regulatory patterns?
   - ICH GCP terminology
   - Clinical trial specific terms
   - Bilingual presentation rules

OUTPUT ONLY VALID JSON (no markdown, no explanations):
{{
  "rules": [
    {{
      "category": "terminology",
      "rule": "Title Page is always translated as '제목페이지' not '표지'",
      "priority": "critical",
      "examples": ["Title Page → 제목페이지"]
    }},
    {{
      "category": "tone",
      "rule": "Use formal 합니다 endings in main clauses",
      "priority": "high",
      "examples": ["is conducted → 수행됩니다"]
    }}
  ]
}}

IMPORTANT:
- Extract 15-25 rules maximum
- Focus on CRITICAL patterns (appear in multiple places)
- Be specific with actual Korean terms/endings observed
- Priority: critical > high > medium > low
- Return ONLY valid JSON"""

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
                self.logger.info(f"✅ Extracted {len(result.get('rules', []))} rules from reference docs")
                return result
            else:
                self.logger.warning("⚠️  Could not find JSON in response")
                return {"rules": []}

        except Exception as e:
            self.logger.error(f"❌ Error extracting rules: {e}")
            return {"rules": []}

    def save_rules(self, rules: Dict, output_path: str) -> str:
        """
        Save extracted rules to JSON file

        Args:
            rules: Dict with extracted rules
            output_path: Path to save JSON

        Returns:
            Path to saved file
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        output_data = {
            "extraction_date": datetime.now().isoformat(),
            "source": "Reference documents: /Users/won.suh/Downloads/pair/",
            "total_rules": len(rules.get("rules", [])),
            "rules": rules.get("rules", [])
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"💾 Saved rules to: {output_path}")
        return output_path

    def run(self) -> str:
        """
        Execute rule extraction workflow

        Returns:
            Path to extracted rules JSON file
        """
        self.logger.info("=" * 100)
        self.logger.info("🚀 PROTOCOL QA RULE EXTRACTOR - Processor 1")
        self.logger.info("=" * 100)

        try:
            # Step 1: Load reference documents
            self.logger.info("\n📋 STEP 1: Load Reference Documents")
            self.logger.info("-" * 100)
            doc_text = self.load_reference_documents()

            # Step 2: Extract rules
            self.logger.info("\n📖 STEP 2: Extract EN-KO Rules from Reference Docs")
            self.logger.info("-" * 100)
            rules = self.extract_rules_from_docs(doc_text)

            # Step 3: Save rules
            self.logger.info("\n💾 STEP 3: Save Rules to JSON")
            self.logger.info("-" * 100)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"/Users/won.suh/Project/translate-ai/phase2/data/protocol_qa_rules_{timestamp}.json"
            self.save_rules(rules, output_file)

            self.logger.info("")
            self.logger.info("=" * 100)
            self.logger.info("✅ RULE EXTRACTION COMPLETE")
            self.logger.info("=" * 100)
            self.logger.info(f"\n📁 Rules saved to: {output_file}")
            self.logger.info(f"📊 Total rules extracted: {len(rules.get('rules', []))}\n")

            return output_file

        except Exception as e:
            self.logger.error(f"❌ Rule extraction failed: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """Main execution"""
    extractor = ProtocolQARuleExtractor()
    rules_file = extractor.run()
    print(f"\n✅ Rules extracted: {rules_file}")


if __name__ == '__main__':
    main()
