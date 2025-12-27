#!/usr/bin/env python3
"""
IMPROVED EN-KO Production Translation Pipeline
Based on comprehensive feedback analysis from regulatory reviewers.
Key improvements: Literal translation focus, strict terminology, hallucination prevention
"""

import os
import sys
import pandas as pd
import logging
import time
import json
import openai
import openpyxl
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

# Add utils directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
from segment_filter import SegmentFilter
from tag_handler import TagHandler

# Load environment variables
load_dotenv("/Users/won.suh/Project/translate-ai/.env")

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

# Import ValkeyManager for persistent term storage
from memory.valkey_manager import ValkeyManager, SessionMetadata

# Import the style guide manager
from style_guide_config import StyleGuideManager, StyleGuideVariant

# Import QA framework
from translation_qa import TranslationQAChecker, StrictGlossaryEnforcer

@dataclass
class ENKOTranslationResult:
    """Result for EN-KO translation with comprehensive metrics and QA validation"""
    segment_id: int
    source_text_en: str
    reference_ko: str
    translated_text_ko: str
    style_guide_variant: StyleGuideVariant
    quality_score: float
    glossary_terms_found: int
    glossary_terms_used: List[Dict]
    processing_time: float
    total_tokens: int
    input_tokens: int
    output_tokens: int
    style_guide_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    cost_per_quality_point: float
    status: str
    error_message: Optional[str] = None
    qa_issues: List[str] = None
    terminology_violations: List[str] = None
    has_tags: bool = False  # Whether source contains tags
    tag_validation_passed: bool = True  # Tag preservation validation
    tag_validation_issues: List[str] = None  # Tag-specific issues

class ImprovedENKOPipeline:
    """
    Improved EN-KO translation pipeline with strict literal translation and QA validation
    """

    def __init__(self,
                 model_name: str = "Owl",
                 use_valkey: bool = False,
                 batch_size: int = 50,
                 style_guide_variant: str = "clinical_protocol_strict",
                 use_enhanced_prompts: bool = False,
                 tmx_loader: Optional['TMXMemoryLoaderENKO'] = None,
                 glossary_loader: Optional['ProtocolGlossaryLoaderENKO'] = None):

        self.model_name = model_name
        self.batch_size = batch_size
        self.session_id = f"improved_en_ko_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.use_valkey = use_valkey
        self.use_enhanced_prompts = use_enhanced_prompts

        # Initialize segment filter for cost optimization
        self.segment_filter = SegmentFilter()

        # Initialize tag handler for CAT tool integration
        self.tag_handler = TagHandler()

        # Setup logging
        self.setup_logging()

        # Initialize OpenAI client for GPT-5 OWL
        self.client = openai.OpenAI()

        # Initialize QA framework
        self.qa_checker = TranslationQAChecker()
        self.glossary_enforcer = StrictGlossaryEnforcer()

        # Initialize style guide system
        self.style_guide_manager = StyleGuideManager()

        # Initialize TM and Glossary loaders (optional)
        self.tmx_loader = tmx_loader
        self.glossary_loader = glossary_loader

        # Select style guide variant based on enhanced prompts setting
        # Override style_guide_variant parameter if use_enhanced_prompts is True
        if self.use_enhanced_prompts:
            self.style_guide_variant = StyleGuideVariant.CLINICAL_PROTOCOL_STRICT_ENHANCED
            self.logger.info("📚 Using ENHANCED prompts with golden examples (~900 tokens)")
        else:
            # Use provided variant or default to clinical_protocol_strict
            self.style_guide_variant = StyleGuideVariant(style_guide_variant)
            self.logger.info(f"📚 Using BASELINE prompts: {self.style_guide_variant.value}")
        
        # Load EN-KO glossary with strict enforcement
        self.logger.info("📚 Loading EN-KO glossary with strict enforcement...")
        self.glossary_terms = {}
        self.mandatory_terms = {}
        self.glossary_stats = {'total_terms': 0, 'mandatory_terms': 0}
        self.load_en_ko_glossary_strict()
        
        # Initialize memory system
        self.locked_terms = {}
        self.previous_translations = []
        
        try:
            if self.use_valkey:
                self.memory = ValkeyManager()
                self.session_metadata = SessionMetadata(
                    doc_id=self.session_id,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    source_language="en",
                    target_language="ko", 
                    total_segments=0,
                    processed_segments=0,
                    term_count=0,
                    status="active"
                )
                self.memory.initialize_session(self.session_metadata)
                self.logger.info(f"✅ Valkey session initialized: {self.session_id}")
            else:
                self.logger.info("💾 Using in-memory storage (Valkey disabled)")
        except Exception as e:
            self.logger.warning(f"⚠️ Valkey initialization failed: {e}, using in-memory storage")
            self.use_valkey = False

    def setup_logging(self) -> None:
        """Setup comprehensive logging for QA tracking"""
        log_dir = "/Users/won.suh/Project/translate-ai/logs"
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = f"{log_dir}/improved_en_ko_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"📋 Improved EN-KO Pipeline initialized with QA validation")

    def load_en_ko_glossary_strict(self) -> None:
        """Load EN-KO combined glossary with mandatory term enforcement (419 terms)"""
        try:
            # Define mandatory regulatory terms (must be translated consistently)
            self.mandatory_terms = {
                "title page": "제목페이지",
                "sponsor representative": "의뢰자 대표자", 
                "clinical study protocol": "임상시험계획서",
                "informed consent": "동의서",
                "adverse event": "이상반응",
                "serious adverse event": "중대한 이상반응",
                "investigational product": "임상시험용 의약품",
                "phase 1": "제1상",
                "phase 2": "제2상", 
                "phase 3": "제3상",
                "multicenter": "다기관",
                "open-label": "공개 라벨",
                "dose escalation": "용량 증량",
                "maximum tolerated dose": "최대 내약 용량"
            }
            
            # Load Combined EN-KO Glossary (419 terms)
            combined_file = "/Users/won.suh/Project/translate-ai/phase2/data/combined_en_ko_glossary.xlsx"
            df_combined = pd.read_excel(combined_file, sheet_name='Sheet1')
            
            self.logger.info(f"🔄 Loading combined glossary with {len(df_combined)} terms...")
            
            # Load all combined glossary terms
            for _, row in df_combined.iterrows():
                if pd.notna(row['English']) and pd.notna(row['Korean']):
                    english_term = str(row['English']).strip().lower()
                    korean_term = str(row['Korean']).strip()
                    source = str(row.get('Source', 'Combined'))
                    priority = row.get('Priority', 2)
                    
                    self.glossary_terms[english_term] = {
                        'english': str(row['English']).strip(),  # Keep original case
                        'korean': korean_term,
                        'source': source,
                        'priority': priority,
                        'mandatory': english_term in self.mandatory_terms
                    }
            
            # Ensure all mandatory terms are included with highest priority
            for eng, kor in self.mandatory_terms.items():
                if eng not in self.glossary_terms:
                    self.glossary_terms[eng] = {
                        'english': eng,
                        'korean': kor,
                        'source': 'Regulatory Standard',
                        'priority': 1,
                        'mandatory': True
                    }
                else:
                    # Upgrade existing term to mandatory
                    self.glossary_terms[eng]['mandatory'] = True
                    self.glossary_terms[eng]['priority'] = 1
            
            # Calculate statistics
            self.glossary_stats['total_terms'] = len(self.glossary_terms)
            self.glossary_stats['mandatory_terms'] = len(self.mandatory_terms)
            self.glossary_stats['avance_terms'] = len([t for t in self.glossary_terms.values() if t['source'] == 'Avance Clinical'])
            self.glossary_stats['clinical_trials_terms'] = len([t for t in self.glossary_terms.values() if t['source'] == 'Clinical Trials'])
            self.glossary_stats['coding_form_terms'] = len([t for t in self.glossary_terms.values() if 'Coding Form' in t['source']])
            
            self.logger.info(f"📚 Loaded {self.glossary_stats['total_terms']} terms from combined glossary:")
            self.logger.info(f"   - Mandatory terms: {self.glossary_stats['mandatory_terms']}")
            self.logger.info(f"   - Avance Clinical: {self.glossary_stats['avance_terms']}")
            self.logger.info(f"   - Clinical Trials: {self.glossary_stats['clinical_trials_terms']}")
            self.logger.info(f"   - Coding Form: {self.glossary_stats['coding_form_terms']}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load combined EN-KO glossary: {e}")
            self.logger.info("🔄 Falling back to Avance Clinical glossary...")
            
            # Fallback to Avance Clinical only
            try:
                avance_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/영한/2_용어집_Avance Clinical Glossary.xlsx"
                df_avance = pd.read_excel(avance_file, sheet_name='Sheet1')
                
                for _, row in df_avance.iterrows():
                    if pd.notna(row['English']) and pd.notna(row['Korean']):
                        english_term = str(row['English']).strip().lower()
                        korean_term = str(row['Korean']).strip()
                        
                        self.glossary_terms[english_term] = {
                            'english': str(row['English']).strip(),
                            'korean': korean_term,
                            'source': 'Avance Clinical',
                            'priority': 1,
                            'mandatory': english_term in self.mandatory_terms
                        }
                
                # Add mandatory terms
                for eng, kor in self.mandatory_terms.items():
                    if eng not in self.glossary_terms:
                        self.glossary_terms[eng] = {
                            'english': eng,
                            'korean': kor,
                            'source': 'Regulatory Standard',
                            'priority': 1,
                            'mandatory': True
                        }
                
                self.glossary_stats['total_terms'] = len(self.glossary_terms)
                self.glossary_stats['mandatory_terms'] = len(self.mandatory_terms)
                
                self.logger.info(f"📚 Fallback: Loaded {self.glossary_stats['total_terms']} terms "
                               f"({self.glossary_stats['mandatory_terms']} mandatory)")
                
            except Exception as fallback_error:
                self.logger.error(f"❌ Fallback also failed: {fallback_error}")
                # Use minimal mandatory terms only
                self.glossary_terms = {eng.lower(): {'english': eng, 'korean': kor, 'mandatory': True} 
                                     for eng, kor in self.mandatory_terms.items()}
                self.glossary_stats['total_terms'] = len(self.mandatory_terms)
                self.glossary_stats['mandatory_terms'] = len(self.mandatory_terms)

    def search_glossary_en_ko_strict(self, english_text: str) -> List[Dict]:
        """Search glossary with mandatory term enforcement"""
        english_text_lower = english_text.lower()
        found_terms = []
        mandatory_violations = []
        
        for term_key, term_data in self.glossary_terms.items():
            eng_term = term_data['english']
            match_type = None
            score = 0.0
            
            # Exact phrase match (highest priority)
            if eng_term in english_text_lower:
                match_type = 'exact'
                score = 1.0
                
                # Check if mandatory term
                if term_data.get('mandatory', False):
                    mandatory_violations.append({
                        'term': eng_term,
                        'required_translation': term_data['korean'],
                        'severity': 'critical'
                    })
            
            # Partial word match for multi-word terms
            elif len(eng_term.split()) > 1:
                term_words = eng_term.split()
                matched_words = []
                for word in term_words:
                    if len(word) > 3 and word in english_text_lower:
                        matched_words.append(word)
                
                if len(matched_words) >= 2 or (len(matched_words) >= 1 and len(matched_words[0]) > 6):
                    match_type = 'partial'
                    score = len(matched_words) / len(term_words)
            
            if match_type:
                found_terms.append({
                    'english': term_data['english'],
                    'korean': term_data['korean'],
                    'source': term_data['source'],
                    'match_type': match_type,
                    'score': score,
                    'mandatory': term_data.get('mandatory', False),
                    'priority': term_data.get('priority', 2)
                })
        
        # Sort by mandatory first, then score, then length
        found_terms.sort(key=lambda x: (x['mandatory'], x['score'], len(x['english'])), reverse=True)

        return found_terms[:10], mandatory_violations

    def search_tm_for_en_text(self, english_text: str, top_k: int = 3) -> List[Dict]:
        """
        Search Translation Memory for similar English segments
        Returns top K matches with Korean translations

        Args:
            english_text: English text to search for
            top_k: Number of top TM matches to return

        Returns:
            List of TM matches with similarity scores
        """
        if not self.tmx_loader:
            return []

        try:
            matches = self.tmx_loader.find_similar_segments(english_text, top_k=top_k, threshold=0.75)

            if matches:
                self.logger.debug(f"Found {len(matches)} TM matches for segment: {english_text[:50]}...")
                for i, match in enumerate(matches, 1):
                    sim_pct = int(match['similarity'] * 100)
                    self.logger.debug(f"  {i}. [{sim_pct}%] TM: {match['target'][:60]}...")

            return matches
        except Exception as e:
            self.logger.warning(f"⚠️ TM search failed: {e}")
            return []

    def build_en_ko_strict_context(self, english_texts: List[str]) -> Tuple[str, int, List[str]]:
        """Build strict context for EN→KO literal translation with TM integration"""
        context_components = []
        token_count = 0
        all_mandatory_violations = []

        # Component 1: Collect mandatory terms for the batch
        mandatory_terms_for_batch = {}
        all_glossary_terms = {}

        for english_text in english_texts:
            terms, violations = self.search_glossary_en_ko_strict(english_text)
            all_mandatory_violations.extend(violations)

            for term in terms:
                if term['mandatory']:
                    mandatory_terms_for_batch[term['english']] = term
                else:
                    all_glossary_terms[term['english']] = term

        # Add mandatory terminology section
        if mandatory_terms_for_batch:
            mandatory_section = "## 🚨 필수 규제 용어 (MANDATORY REGULATORY TERMS)\n"
            mandatory_section += "다음 용어들은 반드시 지정된 한국어로 번역해야 합니다:\n"
            for term in mandatory_terms_for_batch.values():
                mandatory_section += f"- {term['english']} → {term['korean']} (필수)\n"
            context_components.append(mandatory_section)
            token_count += len(mandatory_section) // 4

        # Add additional terminology if space allows
        if all_glossary_terms and token_count < 200:
            terminology_section = "\n## 추가 의학 용어 (Additional Medical Terms)\n"
            for term in list(all_glossary_terms.values())[:10]:  # Limit additional terms
                terminology_section += f"- {term['english']}: {term['korean']}\n"
            context_components.append(terminology_section)
            token_count += len(terminology_section) // 4

        # Component 2: Translation Memory (TM) matches (NEW)
        if self.tmx_loader and token_count < 300:
            tm_section = "\n## 🔍 참고할 유사 번역 (Similar Translation Memory Matches)\n"
            tm_section += "다음은 번역 메모리에서 찾은 유사한 번역들입니다. 참고만 하세요:\n"
            tm_matches_found = 0

            for english_text in english_texts[:5]:  # Check first 5 segments for TM matches
                tm_matches = self.search_tm_for_en_text(english_text, top_k=2)
                for match in tm_matches:
                    if tm_matches_found < 5:  # Limit TM matches in context
                        sim_pct = int(match['similarity'] * 100)
                        tm_section += f"- [{sim_pct}%] EN: {match['source'][:60]}... → KO: {match['target'][:60]}...\n"
                        tm_matches_found += 1

            if tm_matches_found > 0:
                context_components.append(tm_section)
                token_count += len(tm_section) // 4

        # Component 3: Session Memory (locked terms)
        if self.locked_terms:
            locked_section = "\n## 문서 내 일관성 용어 (Document Consistency Terms)\n"
            for en, ko in list(self.locked_terms.items())[:5]:
                locked_section += f"- {en}: {ko}\n"
            context_components.append(locked_section)
            token_count += len(locked_section) // 4

        # Component 4: Style Guide (baseline or enhanced with examples)
        style_guide_content = self.style_guide_manager.get_style_guide(self.style_guide_variant)
        context_components.append(style_guide_content)
        token_count += len(style_guide_content) // 4

        return "\n".join(context_components), token_count, all_mandatory_violations

    def create_strict_en_ko_prompt(self, english_texts: List[str], context: str) -> str:
        """Create strict prompt for literal EN→KO translation with tag preservation"""

        # Check if any text contains tags
        has_tags = any(self.tag_handler.has_tags(text) for text in english_texts)
        tag_section = ""

        if has_tags:
            # Add tag preservation instructions
            tag_section = self.tag_handler.create_tag_preservation_prompt_section()

        # Build numbered segments
        segments_section = "\n## 번역할 영어 텍스트 (English Text to Translate):\n"
        for i, english_text in enumerate(english_texts, 1):
            segments_section += f"{i}. {english_text}\n"

        prompt = f"""{context}
{tag_section}
{segments_section}

## 🔒 응답 형식 (STRICT Response Format):
다음 형식으로 정확히 {len(english_texts)}개의 한국어 번역을 제공하십시오.
원문을 직역하되, 위의 필수 규제 용어를 반드시 사용하십시오.

1. [첫 번째 문장의 정확한 한국어 직역]
2. [두 번째 문장의 정확한 한국어 직역]
{f"3. [세 번째 문장의 정확한 한국어 직역]" if len(english_texts) > 2 else ""}
{f"4. [네 번째 문장의 정확한 한국어 직역]" if len(english_texts) > 3 else ""}
{f"5. [다섯 번째 문장의 정확한 한국어 직역]" if len(english_texts) > 4 else ""}

🚨 중요한 규칙:
- 번호가 매겨진 번역만 제공 (설명 금지)
- 원문에 없는 정보 추가 절대 금지
- 필수 규제 용어 정확히 사용
- 모든 번역에서 용어 일관성 유지
- 직역을 원칙으로 하되 자연스러운 한국어 사용
{'- 모든 태그(<123>, </123>, <123/>, [METADATA])를 정확히 보존 (위 예시 참조)' if has_tags else ''}"""

        return prompt

    def translate_batch_with_gpt5_owl_strict(self, prompt: str) -> Tuple[List[str], int, float, Dict]:
        """Translate batch using GPT-5 OWL with strict literal translation settings"""
        try:
            start_time = time.time()
            
            # Adjusted parameters for literal translation
            try:
                response = self.client.responses.create(
                    model="gpt-5.2",
                    input=[{"role": "user", "content": prompt}],
                    text={"verbosity": "low"},
                    reasoning={"effort": "low"}   # Use 'low' instead of 'minimal' (gpt-5.2 doesn't support minimal)
                )
            except Exception as api_error:
                self.logger.error(f"API Error (gpt-5.2): {str(api_error)[:200]}")
                # Fallback to gpt-5 if gpt-5.2 fails
                try:
                    self.logger.info("Falling back to gpt-5 model")
                    response = self.client.responses.create(
                        model="gpt-5",
                        input=[{"role": "user", "content": prompt}],
                        text={"verbosity": "low"},
                        reasoning={"effort": "low"}
                    )
                except Exception as fallback_error:
                    self.logger.error(f"Fallback API Error (gpt-5): {str(fallback_error)[:200]}")
                    return [], 0, 0.0, {"error": f"API failure: {str(fallback_error)[:100]}"}

            processing_time = time.time() - start_time

            # Extract response with error handling
            try:
                translation_text = self._extract_text_from_openai_responses(response)
                if not translation_text or translation_text == "[GPT-5 OWL Response Extraction Failed]":
                    self.logger.warning(f"Failed to extract text from response")
                    self.logger.debug(f"Response object: {response}")
                    return [], 0, 0.0, {"error": "Response extraction failed"}
            except Exception as extract_error:
                self.logger.error(f"Extraction error: {str(extract_error)[:200]}")
                return [], 0, 0.0, {"error": f"Extraction failure: {str(extract_error)[:100]}"}

            # Parse batch response with error handling
            try:
                translations = self._parse_batch_response_strict(translation_text)
                if not translations:
                    self.logger.warning(f"No translations parsed from response text: {translation_text[:100]}")
                    return [], 0, 0.0, {"error": "Parsing returned empty translations"}
            except Exception as parse_error:
                self.logger.error(f"Parsing error: {str(parse_error)[:200]}")
                return [], 0, 0.0, {"error": f"Parsing failure: {str(parse_error)[:100]}"}
            
            # Calculate metrics
            input_tokens = len(prompt) // 4
            output_tokens = len(translation_text) // 4
            cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1000
            
            metadata = {
                "model_used": "GPT-5 OWL",
                "api_used": "Responses API",
                "reasoning_effort": "medium",
                "text_verbosity": "minimal",
                "literal_translation_mode": True
            }
            
            return translations, output_tokens, cost, metadata
            
        except Exception as e:
            self.logger.error(f"❌ GPT-5 OWL strict translation failed: {e}")
            return [], 0, 0.0, {"error": str(e)}

    def _parse_batch_response_strict(self, response_text: str) -> List[str]:
        """Parse batch response with strict validation (handles both single and batch responses)"""
        # Ensure we're working with a string
        if not isinstance(response_text, str):
            response_text = str(response_text)

        lines = response_text.strip().split('\n')
        translations = []

        # Try to parse numbered responses (1. 2. 3. etc.)
        has_numbered = False
        for line in lines:
            line = line.strip()
            if not line:  # Skip empty lines
                continue
            # Match numbered responses (1. 2. 3. etc.)
            match = re.match(r'^\d+\.\s*(.+)$', line)
            if match:
                has_numbered = True
                translation = match.group(1).strip()
                # Remove any explanatory text in parentheses or brackets
                translation = re.sub(r'\([^)]*설명[^)]*\)', '', translation)
                translation = re.sub(r'\[[^]]*설명[^]]*\]', '', translation)
                translations.append(translation)

        # If no numbered items found, treat the entire response as a single translation
        if not has_numbered and lines:
            full_text = ' '.join([line.strip() for line in lines if line.strip()])
            if full_text and len(full_text.strip()) > 0:
                translations.append(full_text)

        # Ensure we return a list of strings, not a list of characters
        if not translations and response_text:
            # Ultimate fallback: return the entire response as a single translation
            translations = [response_text.strip()]

        return translations

    def _extract_text_from_openai_responses(self, response) -> str:
        """Extract text from GPT-5 OWL Responses API response object"""
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
            return "[GPT-5 OWL Response Extraction Failed]"

    def validate_translation_strict(self, source_text: str, translation: str, 
                                  mandatory_violations: List[str]) -> List[str]:
        """Validate translation with strict QA checks"""
        issues = []
        
        # Check mandatory term usage
        for violation in mandatory_violations:
            term = violation['term']
            required = violation['required_translation']
            if term in source_text.lower() and required not in translation:
                issues.append(f"MANDATORY TERM VIOLATION: '{term}' must be translated as '{required}'")
        
        # Check for added information
        if self._detect_information_addition(source_text, translation):
            issues.append("INFORMATION ADDITION: Translation contains information not in source")
        
        # Check for subjective language
        subjective_patterns = ['적정함', '우수함', '양호함', '바람직함']
        for pattern in subjective_patterns:
            if pattern in translation:
                issues.append(f"SUBJECTIVE LANGUAGE: Contains '{pattern}' - use objective language only")
        
        return issues

    def _detect_information_addition(self, source: str, translation: str) -> bool:
        """Detect if translation adds information not in source"""
        # Simple heuristic: if translation is significantly longer, might be adding info
        source_words = len(source.split())
        translation_chars = len(translation)
        
        # Korean typically 1.5-2x longer than English, but >3x suggests addition
        if translation_chars > source_words * 15:  # ~3x expansion ratio
            return True
        
        return False

    def process_en_ko_batch_strict(self, batch_data: List[Dict]) -> List[ENKOTranslationResult]:
        """Process batch with strict QA validation and intelligent segment filtering"""
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        results = []
        
        # Pre-filter segments for auto-copy vs LLM processing
        llm_texts = []  # Only texts that need LLM
        segment_processing_plan = []  # Track what to do with each segment
        
        for i, item in enumerate(batch_data):
            source_text = item['source_en']
            should_copy, reason = self.segment_filter.should_auto_copy(source_text)
            
            if should_copy:
                # Auto-copy segment (no LLM needed)
                segment_processing_plan.append({
                    'type': 'auto_copy',
                    'reason': reason,
                    'source_text': source_text
                })
            else:
                # LLM processing needed
                segment_processing_plan.append({
                    'type': 'llm',
                    'llm_index': len(llm_texts)  # Track position in LLM batch
                })
                llm_texts.append(source_text)
        
        # Process LLM batch only if there are texts that need translation
        translations = []
        llm_cost = 0
        if llm_texts:
            # Build strict context for LLM texts only (includes style guide)
            context, context_tokens, mandatory_violations = self.build_en_ko_strict_context(llm_texts)

            # Create strict prompt for LLM texts
            prompt = self.create_strict_en_ko_prompt(llm_texts, context)

            # Style guide tokens are included in context_tokens
            # (context now includes style guide content from build_en_ko_strict_context)
            style_guide_tokens = context_tokens  # For backwards compatibility with metrics

            # Translate LLM batch
            translations, output_tokens, llm_cost, metadata = self.translate_batch_with_gpt5_owl_strict(prompt)
        else:
            # No LLM processing needed
            context_tokens = 0
            mandatory_violations = []
        
        # Now process all segments according to the plan
        for i, item in enumerate(batch_data):
            plan = segment_processing_plan[i]
            source_text = item['source_en']

            # Check if segment has tags
            has_tags = self.tag_handler.has_tags(source_text)
            tag_validation_passed = True
            tag_validation_issues = []

            if plan['type'] == 'auto_copy':
                # Auto-copy segment (instant, no cost)
                translation = plan['source_text']  # Direct copy
                processing_time = 0.0
                segment_cost = 0.0
                qa_issues = []  # Auto-copy has no QA issues
                status = "auto_copied"
                metadata_dict = {"auto_copy_reason": plan['reason']}
            else:
                # LLM processed segment
                llm_idx = plan['llm_index']
                translation = translations[llm_idx] if llm_idx < len(translations) else "[TRANSLATION FAILED]"

            # Tag validation (if segment has tags)
            if has_tags:
                tag_validation = self.tag_handler.validate_tags(source_text, translation)
                tag_validation_passed = tag_validation.is_valid
                tag_validation_issues = tag_validation.issues

                if not tag_validation_passed:
                    self.logger.warning(
                        f"⚠️ Tag validation failed for segment {item.get('segment_id', i)}: {tag_validation_issues}"
                    )

            # Run strict QA validation
            qa_issues = self.validate_translation_strict(
                source_text,
                translation,
                mandatory_violations
            )

            # Check terminology violations
            term_violations = self.glossary_enforcer.validate_translation(
                source_text, translation, "en-ko"
            )

            # Calculate quality score (penalize for issues)
            base_quality = 0.90  # Start high for literal translation
            quality_penalty = len(qa_issues) * 0.1 + len(term_violations) * 0.15
            if not tag_validation_passed:
                quality_penalty += 0.5  # Critical penalty for tag preservation failure
            quality_score = max(0.0, base_quality - quality_penalty)
            
            # Determine status based on all validation results
            if plan['type'] == 'auto_copy':
                status = "auto_copied"
            elif not tag_validation_passed:
                status = "tag_validation_failed"
            elif qa_issues or term_violations:
                status = "qa_issues"
            else:
                status = "success"

            result = ENKOTranslationResult(
                segment_id=item.get('segment_id', i),
                source_text_en=item['source_en'],
                reference_ko=item.get('reference_ko', ''),
                translated_text_ko=translation,
                style_guide_variant=self.style_guide_variant,
                quality_score=quality_score,
                glossary_terms_found=len(mandatory_violations),
                glossary_terms_used=[],
                processing_time=metadata.get('processing_time', 0.0) if llm_texts else 0.0,
                total_tokens=output_tokens + context_tokens if llm_texts else 0,
                input_tokens=len(prompt) // 4 if llm_texts else 0,
                output_tokens=output_tokens if llm_texts else 0,
                style_guide_tokens=style_guide_tokens if llm_texts else 0,
                input_cost=llm_cost * 0.3 / len(batch_data) if llm_texts else 0.0,
                output_cost=llm_cost * 0.7 / len(batch_data) if llm_texts else 0.0,
                total_cost=llm_cost / len(batch_data) if llm_texts else 0.0,
                cost_per_quality_point=(llm_cost / len(batch_data)) / quality_score if quality_score > 0 and llm_texts else float('inf'),
                status=status,
                error_message=None,
                qa_issues=qa_issues,
                terminology_violations=term_violations,
                has_tags=has_tags,
                tag_validation_passed=tag_validation_passed,
                tag_validation_issues=tag_validation_issues
            )
            
            results.append(result)
            
            # Log QA issues
            if qa_issues or term_violations:
                self.logger.warning(f"⚠️ Segment {result.segment_id} QA Issues: {qa_issues + term_violations}")
        
        return results

# Usage example
if __name__ == "__main__":
    # Initialize improved pipeline
    pipeline = ImprovedENKOPipeline(
        model_name="Owl",
        batch_size=5,
        style_guide_variant="clinical_protocol_strict"
    )
    
    # Test with sample data
    test_data = [
        {
            'segment_id': 1,
            'source_en': 'Title Page of Clinical Study Protocol',
            'reference_ko': ''
        },
        {
            'segment_id': 2, 
            'source_en': 'The Sponsor Representative will oversee the clinical study.',
            'reference_ko': ''
        }
    ]
    
    # Process batch
    results = pipeline.process_en_ko_batch_strict(test_data)
    
    # Display results
    for result in results:
        print(f"Segment {result.segment_id}:")
        print(f"Source: {result.source_text_en}")
        print(f"Translation: {result.translated_text_ko}")
        print(f"Quality: {result.quality_score:.2f}")
        if result.qa_issues:
            print(f"QA Issues: {result.qa_issues}")
        if result.terminology_violations:
            print(f"Term Violations: {result.terminology_violations}")
        print("-" * 50)