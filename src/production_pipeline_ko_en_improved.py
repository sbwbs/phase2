#!/usr/bin/env python3
"""
IMPROVED KO-EN Production Translation Pipeline
Based on comprehensive feedback analysis addressing hallucination and verbosity issues.
Key improvements: Hallucination detection, concise output, strict literal translation
"""

import os
import sys
import pandas as pd
import logging
import time
import json
import openai
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/Users/won.suh/Project/translate-ai/.env")

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

# Import ValkeyManager for persistent term storage
from memory.valkey_manager import ValkeyManager, SessionMetadata

# Import QA framework
from translation_qa import TranslationQAChecker, StrictGlossaryEnforcer, HallucinationDetector

# Import working glossary loader
from glossary_loader import GlossaryLoader

# Import segment filter for cost optimization
from utils.segment_filter import SegmentFilter

# Import tag handler for CAT tool integration
from utils.tag_handler import TagHandler

# Import style guide system for enhanced prompts
from style_guide_config import StyleGuideManager, StyleGuideVariant

# Import Qdrant for Tier 2 semantic search (optional)
QDRANT_AVAILABLE = False
QDRANT_IMPORT_ERROR = None
try:
    from memory.qdrant_manager import QdrantManager
    from loaders.qdrant_data_loader import QdrantDataLoader, GLOSSARY_COLLECTION, TM_COLLECTION_KO_EN
    QDRANT_AVAILABLE = True
except ImportError as e:
    QDRANT_IMPORT_ERROR = str(e)
    # Log the actual error so it's not silent
    import logging
    logging.getLogger(__name__).warning(f"⚠️ Qdrant imports failed: {e}. Semantic search will be disabled.")

@dataclass
class KOENTranslationResult:
    """Result for KO-EN translation with hallucination detection and QA validation"""
    segment_id: int
    source_text_ko: str
    reference_en: str
    translated_text_en: str
    quality_score: float
    glossary_terms_found: int
    glossary_terms_used: List[Dict]
    processing_time: float
    total_tokens: int
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    cost_per_quality_point: float
    status: str
    error_message: Optional[str] = None
    qa_issues: List[str] = None
    hallucination_detected: bool = False
    hallucination_details: Optional[str] = None
    verbosity_score: float = 0.0  # Higher = more verbose
    has_tags: bool = False  # Whether source contains tags
    tag_validation_passed: bool = True  # Tag preservation validation
    tag_validation_issues: List[str] = None  # Tag-specific issues

class ImprovedKOENPipeline:
    """
    Improved KO-EN translation pipeline with hallucination detection and concise output
    """

    def __init__(self,
                 model_name: str = "Owl",
                 use_valkey: bool = False,
                 batch_size: int = 50,
                 use_enhanced_prompts: bool = False,
                 greencross_glossary_path: Optional[str] = None,
                 tmx_memory_path: Optional[str] = None,
                 use_qdrant: bool = False,
                 qdrant_url: Optional[str] = None,
                 qdrant_api_key: Optional[str] = None,
                 strict_qdrant: bool = False):
        """
        Initialize the KO-EN translation pipeline.

        Args:
            strict_qdrant: If True, raise error if Qdrant is requested but unavailable.
                          If False (default), silently fall back to keyword search.
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.session_id = f"improved_ko_en_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.use_valkey = use_valkey
        self.use_enhanced_prompts = use_enhanced_prompts
        self.strict_qdrant = strict_qdrant
        self.qdrant_manager = None

        # Validate Qdrant availability if requested
        if use_qdrant and not QDRANT_AVAILABLE:
            error_msg = f"Qdrant requested but imports failed: {QDRANT_IMPORT_ERROR}"
            if strict_qdrant:
                raise RuntimeError(error_msg)
            else:
                import logging
                logging.getLogger(__name__).warning(f"⚠️ {error_msg}. Falling back to keyword search.")

        self.use_qdrant = use_qdrant and QDRANT_AVAILABLE

        # Setup logging
        self.setup_logging()

        # Initialize OpenAI client for GPT-5 OWL
        self.client = openai.OpenAI()

        # Initialize QA framework
        self.qa_checker = TranslationQAChecker()
        self.glossary_enforcer = StrictGlossaryEnforcer()
        self.hallucination_detector = HallucinationDetector()

        # Initialize segment filter for cost optimization
        self.segment_filter = SegmentFilter()

        # Initialize tag handler for CAT tool integration
        self.tag_handler = TagHandler()

        # Initialize style guide system
        self.style_guide_manager = StyleGuideManager()

        # Select style guide variant based on enhanced prompts setting
        if self.use_enhanced_prompts:
            self.style_guide_variant = StyleGuideVariant.REGULATORY_COMPLIANCE_ENHANCED
            self.logger.info("📚 Using ENHANCED prompts with golden examples (~900 tokens)")
        else:
            self.style_guide_variant = StyleGuideVariant.REGULATORY_COMPLIANCE
            self.logger.info("📚 Using BASELINE prompts (~400 tokens)")
        
        # Load KO-EN glossary with strict enforcement
        self.logger.info("📚 Loading KO-EN glossary with hallucination prevention...")
        self.glossary_loader = GlossaryLoader()
        self.combined_glossary = self._load_simple_combined_glossary()
        self.mandatory_terms = self._extract_mandatory_ko_en_terms()

        # Load GreenCross glossary if provided (Priority 1)
        self.greencross_glossary = []
        if greencross_glossary_path:
            self.greencross_glossary = self._load_greencross_glossary(greencross_glossary_path)
            # Merge glossaries: GreenCross takes precedence
            self.combined_glossary = self._merge_glossaries(self.greencross_glossary, self.combined_glossary)

        # Load TMX memory if provided
        self.tm_loader = None
        if tmx_memory_path:
            self.tm_loader = self._load_tmx_memory(tmx_memory_path)

        # Initialize Qdrant for semantic search (Tier 2)
        if self.use_qdrant and qdrant_url and qdrant_api_key:
            try:
                self.qdrant_manager = QdrantManager(
                    qdrant_url=qdrant_url,
                    qdrant_api_key=qdrant_api_key,
                    openai_api_key=os.getenv('OPENAI_API_KEY')
                )
                if self.qdrant_manager.health_check():
                    self._load_data_to_qdrant()
                    # Validate search actually works
                    if self._validate_qdrant_search():
                        self.logger.info("✅ Qdrant semantic search enabled (Tier 2)")
                    else:
                        error_msg = "Qdrant search validation failed"
                        if self.strict_qdrant:
                            raise RuntimeError(error_msg)
                        self.logger.warning(f"⚠️ {error_msg}, using keyword search")
                        self.use_qdrant = False
                        self.qdrant_manager = None
                else:
                    error_msg = "Qdrant health check failed"
                    if self.strict_qdrant:
                        raise RuntimeError(error_msg)
                    self.logger.warning(f"⚠️ {error_msg}, using keyword search")
                    self.use_qdrant = False
                    self.qdrant_manager = None
            except RuntimeError:
                raise  # Re-raise RuntimeError from strict mode
            except Exception as e:
                error_msg = f"Qdrant initialization failed: {e}"
                if self.strict_qdrant:
                    raise RuntimeError(error_msg)
                self.logger.warning(f"⚠️ {error_msg}, using keyword search")
                self.use_qdrant = False
                self.qdrant_manager = None
        elif self.use_qdrant:
            error_msg = "Qdrant credentials not provided"
            if self.strict_qdrant:
                raise RuntimeError(error_msg)
            self.logger.warning(f"⚠️ {error_msg}, using keyword search")
            self.use_qdrant = False

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
                    source_language="ko",
                    target_language="en",
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
        """Setup comprehensive logging with hallucination tracking"""
        log_dir = "/Users/won.suh/Project/translate-ai/logs"
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = f"{log_dir}/improved_ko_en_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"📋 Improved KO-EN Pipeline initialized with hallucination detection")

    def _load_data_to_qdrant(self) -> None:
        """Load glossary and TM to Qdrant if not already populated."""
        if not self.qdrant_manager:
            return

        loader = QdrantDataLoader(self.qdrant_manager)

        # Load glossary (uses self.combined_glossary already loaded)
        glossary_count = loader.load_glossary(self.combined_glossary)
        if glossary_count > 0:
            self.logger.info(f"📚 Loaded {glossary_count} glossary terms to Qdrant")

        # Load TM (uses self.tm_loader if available)
        if self.tm_loader and hasattr(self.tm_loader, 'translation_units'):
            tm_count = loader.load_tm_ko_en(self.tm_loader.translation_units)
            if tm_count > 0:
                self.logger.info(f"📚 Loaded {tm_count} TM pairs to Qdrant")

        # Log collection stats
        stats = loader.get_collection_stats()
        self.logger.info(f"📊 Qdrant collections: Glossary={stats.get(GLOSSARY_COLLECTION, 0)}, TM={stats.get(TM_COLLECTION_KO_EN, 0)}")

    def _validate_qdrant_search(self) -> bool:
        """
        Validate that Qdrant search actually works before relying on it.
        Performs a test search to catch configuration issues early.

        Returns:
            True if search works, False otherwise
        """
        if not self.qdrant_manager:
            return False

        try:
            # Test search on glossary collection with a simple Korean term
            test_query = "임상시험"  # "clinical trial" - common medical term
            results = self.qdrant_manager.search(GLOSSARY_COLLECTION, test_query, limit=1)

            # Check if we got results (even 0 results is OK, we're testing the search mechanism)
            self.logger.info(f"✅ Qdrant search validation passed (glossary returned {len(results)} results)")

            # Also test TM collection if it exists
            try:
                tm_results = self.qdrant_manager.search(TM_COLLECTION_KO_EN, test_query, limit=1)
                self.logger.info(f"✅ Qdrant TM search validation passed (returned {len(tm_results)} results)")
            except Exception as e:
                self.logger.warning(f"⚠️ Qdrant TM search validation failed: {e} (TM may not be loaded)")

            return True
        except Exception as e:
            self.logger.error(f"❌ Qdrant search validation failed: {e}")
            return False

    def diagnose_qdrant_setup(self) -> dict:
        """
        Run diagnostics on Qdrant configuration.
        Useful for debugging issues with semantic search.

        Returns:
            Dict with diagnostic information
        """
        diagnostics = {
            'qdrant_available': QDRANT_AVAILABLE,
            'qdrant_import_error': QDRANT_IMPORT_ERROR,
            'manager_initialized': self.qdrant_manager is not None,
            'use_qdrant_flag': self.use_qdrant,
            'strict_mode': self.strict_qdrant,
            'collections': {},
            'search_test': {}
        }

        if self.qdrant_manager:
            # Check collections
            for coll_name in [GLOSSARY_COLLECTION, TM_COLLECTION_KO_EN]:
                try:
                    count = self.qdrant_manager.get_collection_count(coll_name)
                    is_hybrid = self.qdrant_manager.is_collection_hybrid(coll_name)
                    diagnostics['collections'][coll_name] = {
                        'exists': True,
                        'count': count,
                        'is_hybrid': is_hybrid
                    }
                except Exception as e:
                    diagnostics['collections'][coll_name] = {
                        'exists': False,
                        'error': str(e)
                    }

            # Test search on each collection
            test_query = "테스트"
            for coll_name in [GLOSSARY_COLLECTION, TM_COLLECTION_KO_EN]:
                try:
                    results = self.qdrant_manager.search(coll_name, test_query, limit=1)
                    diagnostics['search_test'][coll_name] = {
                        'success': True,
                        'results_count': len(results)
                    }
                except Exception as e:
                    diagnostics['search_test'][coll_name] = {
                        'success': False,
                        'error': str(e)
                    }

        return diagnostics

    def _load_simple_combined_glossary(self) -> List[Dict]:
        """Load the actual combined glossary file"""
        combined_glossary = []
        
        try:
            # Load the actual combined glossary
            combined_file = "/Users/won.suh/Project/translate-ai/phase2/data/combined_en_ko_glossary.xlsx"
            df_combined = pd.read_excel(combined_file, sheet_name='Sheet1')
            
            for _, row in df_combined.iterrows():
                if pd.notna(row['Korean']) and pd.notna(row['English']):
                    combined_glossary.append({
                        'korean': str(row['Korean']).strip(),
                        'english': str(row['English']).strip(),
                        'source': str(row.get('Source', 'Combined')),
                        'priority': row.get('Priority', 2)
                    })
            
            self.logger.info(f"Loaded {len(combined_glossary)} terms from combined glossary")
            
        except Exception as e:
            self.logger.warning(f"Could not load combined glossary: {e}")
            
            # Fallback: Add mandatory terms as glossary entries
            for ko, en in self._extract_mandatory_ko_en_terms().items():
                combined_glossary.append({
                    'korean': ko,
                    'english': en,
                    'source': 'Mandatory Terms',
                    'priority': 1
                })
            
            self.logger.info(f"Using {len(combined_glossary)} mandatory terms as fallback")
        
        return combined_glossary

    def _extract_mandatory_ko_en_terms(self) -> Dict[str, str]:
        """Extract mandatory terms for consistent KO-EN translation (Updated with customer feedback)"""
        mandatory_terms = {
            # Clinical terms
            "임상시험": "clinical study",
            "임상시험계획서": "clinical study protocol",
            "이상반응": "adverse event",
            "중대한 이상반응": "serious adverse event",
            "임상시험용 의약품": "investigational product",
            "시험대상자": "Subjects",  # UPDATED: "Subjects" not "study subject" per customer feedback
            "대상자": "Subjects",  # ADDED: Consistent subject terminology
            "동의서": "informed consent",
            "의뢰자": "sponsor",
            "의뢰자 대표자": "sponsor representative",

            # Customer feedback corrections (CRITICAL)
            "비율": "rate",  # ADDED: "rate" not "ratio" for achievement/response metrics
            "신장": "height",  # ADDED: Body measurement context, NOT "renal function"
            "대체 날짜": "Imputed date",  # ADDED: Statistics context, NOT "Alternate date"

            # Academic titles (CRITICAL - prevent hallucination)
            "교수": "Professor",
            "부교수": "Associate Professor",
            "조교수": "Assistant Professor",
            "연구교수": "Research Professor",

            # Medical departments
            "내과": "Department of Internal Medicine",
            "외과": "Department of Surgery",
            "소화기내과": "Division of Gastroenterology",
            "심장내과": "Division of Cardiology",

            # Phase designations
            "제1상": "Phase 1",
            "제2상": "Phase 2",
            "제3상": "Phase 3"
        }

        return mandatory_terms

    def _load_greencross_glossary(self, file_path: str) -> List[Dict]:
        """Load GreenCross glossary (Priority 1) using specialized loader"""
        try:
            from loaders.greencross_glossary_loader import GreenCrossGlossaryLoader
            loader = GreenCrossGlossaryLoader()
            glossary = loader.load_glossary(file_path)
            self.logger.info(f"✅ Loaded {len(glossary)} GreenCross terms (Priority 1)")
            return glossary
        except Exception as e:
            self.logger.error(f"❌ Error loading GreenCross glossary: {e}")
            return []

    def _merge_glossaries(self, gc_glossary: List[Dict], existing_glossary: List[Dict]) -> List[Dict]:
        """Merge GreenCross glossary with existing, GreenCross takes precedence"""
        try:
            from loaders.greencross_glossary_loader import GreenCrossGlossaryLoader
            loader = GreenCrossGlossaryLoader()
            merged = loader.merge_with_existing_glossary(gc_glossary, existing_glossary)
            return merged
        except Exception as e:
            self.logger.error(f"Error merging glossaries: {e}, using GreenCross only")
            return gc_glossary

    def _load_tmx_memory(self, file_path: str):
        """Load TMX translation memory with fuzzy matching"""
        try:
            from loaders.tmx_memory_loader import TMXMemoryLoader
            loader = TMXMemoryLoader(file_path)
            stats = loader.get_statistics()
            self.logger.info(f"✅ Loaded TMX with {stats['total_units']} translation units")
            return loader
        except Exception as e:
            self.logger.error(f"❌ Error loading TMX memory: {e}")
            return None

    def search_glossary_ko_en_strict(self, korean_text: str, segment_id: str = None) -> Tuple[List[Dict], List[str]]:
        """Search glossary with hallucination prevention. Uses Qdrant semantic search if enabled."""
        found_terms = []
        mandatory_violations = []
        found_korean_terms = set()  # Track terms to avoid duplicates

        # ALWAYS: Check for mandatory terms first (keyword match - critical terms)
        for ko_term, en_term in self.mandatory_terms.items():
            if ko_term in korean_text:
                found_terms.append({
                    'korean': ko_term,
                    'english': en_term,
                    'source': 'Mandatory Standard',
                    'mandatory': True,
                    'priority': 1
                })
                found_korean_terms.add(ko_term)
                mandatory_violations.append(f"MANDATORY: '{ko_term}' → '{en_term}'")

        # Search for additional terms - use Qdrant semantic search if enabled
        if self.use_qdrant and self.qdrant_manager:
            # Semantic search via Qdrant
            try:
                qdrant_results = self.qdrant_manager.search(
                    GLOSSARY_COLLECTION,
                    korean_text,
                    limit=15
                )
                for r in qdrant_results:
                    if r['score'] >= 0.75:  # Semantic threshold
                        korean_term = r['payload'].get('korean', '')
                        if korean_term and korean_term not in found_korean_terms:
                            found_terms.append({
                                'korean': korean_term,
                                'english': r['payload'].get('english', ''),
                                'source': f"Qdrant ({r['payload'].get('source', 'unknown')})",
                                'mandatory': r['payload'].get('mandatory', False),
                                'priority': r['payload'].get('priority', 2),
                                'semantic_score': r['score']
                            })
                            found_korean_terms.add(korean_term)
            except Exception as e:
                self.logger.warning(f"⚠️ Qdrant search failed: {e}, falling back to keyword search")
                # Fall through to keyword search below

        # Fallback or supplement: keyword search in combined glossary
        if not self.use_qdrant or not self.qdrant_manager:
            for term_entry in self.combined_glossary:
                korean_term = term_entry.get('korean', '')
                if korean_term and korean_term in korean_text:
                    if korean_term not in found_korean_terms:
                        found_terms.append({
                            'korean': korean_term,
                            'english': term_entry.get('english', ''),
                            'source': term_entry.get('source', 'Combined Glossary'),
                            'mandatory': False,
                            'priority': 2
                        })
                        found_korean_terms.add(korean_term)
        
        # Sort by mandatory first, then priority
        found_terms.sort(key=lambda x: (x['mandatory'], x['priority']), reverse=True)

        # Auto-lock glossary matches in Valkey (if enabled)
        if self.use_valkey and self.memory and segment_id:
            for term in found_terms:
                if term.get('mandatory', False) or term.get('priority', 2) == 1:
                    try:
                        self.memory.add_term_mapping(
                            doc_id=self.session_id,
                            source_term=term['korean'],
                            target_term=term['english'],
                            segment_id=segment_id,
                            confidence=0.95
                        )
                        self.memory.lock_term(
                            doc_id=self.session_id,
                            source_term=term['korean']
                        )
                        self.logger.debug(f"🔒 Locked term: {term['korean']} → {term['english']}")
                    except Exception as e:
                        self.logger.debug(f"⚠️ Could not lock term in Valkey: {e}")

        return found_terms[:15], mandatory_violations

    def build_ko_en_strict_context(self, korean_text: str) -> Tuple[str, int, List[str]]:
        """Build strict context for KO→EN literal translation with hallucination prevention"""
        context_components = []
        token_count = 0

        # Search for terms in this text
        found_terms, mandatory_violations = self.search_glossary_ko_en_strict(korean_text)

        # Component 1: Mandatory Terms Section
        mandatory_terms = [t for t in found_terms if t['mandatory']]
        if mandatory_terms:
            mandatory_section = "## 🚨 MANDATORY TRANSLATION TERMS\n"
            mandatory_section += "These terms MUST be translated exactly as specified:\n"
            for term in mandatory_terms:
                mandatory_section += f"- {term['korean']} → {term['english']} (REQUIRED)\n"
            context_components.append(mandatory_section)
            token_count += len(mandatory_section) // 4

        # Component 2: Additional Terms (if space allows)
        additional_terms = [t for t in found_terms if not t['mandatory']][:10]
        if additional_terms and token_count < 200:
            additional_section = "\n## Additional Medical Terms:\n"
            for term in additional_terms:
                additional_section += f"- {term['korean']}: {term['english']}\n"
            context_components.append(additional_section)
            token_count += len(additional_section) // 4

        # Component 2B: TM Context (Translation Memory matches)
        # Use Qdrant semantic search if enabled, else fuzzy matching
        similar_segments = []
        if self.use_qdrant and self.qdrant_manager:
            try:
                tm_results = self.qdrant_manager.search(
                    TM_COLLECTION_KO_EN,
                    korean_text,
                    limit=5
                )
                similar_segments = [
                    {
                        'source': r['payload'].get('source', ''),
                        'target': r['payload'].get('target', ''),
                        'similarity': r['score']
                    }
                    for r in tm_results if r['score'] >= 0.70  # Semantic threshold
                ][:3]  # Top 3
            except Exception as e:
                self.logger.debug(f"Qdrant TM search failed: {e}, using fuzzy matching")
                # Fall through to fuzzy matching

        # Fallback to fuzzy matching if no Qdrant results or Qdrant disabled
        if not similar_segments and self.tm_loader:
            similar_segments = self.tm_loader.find_similar_segments(
                korean_text,
                top_k=3,
                threshold=0.75
            )

        if similar_segments and token_count < 500:
            search_method = "Semantic" if self.use_qdrant else "Fuzzy"
            tm_context = f"\n## Similar Previous Translations ({search_method} Match):\n"
            for i, match in enumerate(similar_segments, 1):
                similarity_pct = int(match['similarity'] * 100)
                tm_context += f"{i}. [{similarity_pct}% match] KO: {match['source'][:80]}\n"
                tm_context += f"   EN: {match['target'][:80]}\n\n"
            context_components.append(tm_context)
            token_count += len(tm_context) // 4

        # Component 3: Session Memory
        if self.locked_terms:
            locked_section = "\n## Document Consistency Terms:\n"
            for ko, en in list(self.locked_terms.items())[:5]:
                locked_section += f"- {ko}: {en}\n"
            context_components.append(locked_section)
            token_count += len(locked_section) // 4

        # Component 4: Style Guide (baseline or enhanced with examples)
        style_guide_content = self.style_guide_manager.get_style_guide(self.style_guide_variant)
        context_components.append(style_guide_content)
        token_count += len(style_guide_content) // 4

        return "\n".join(context_components), token_count, mandatory_violations

    def create_strict_ko_en_prompt(self, korean_text: str, context: str) -> str:
        """Create strict prompt for literal KO→EN translation with anti-hallucination measures and tag preservation"""

        # Check if text contains tags
        has_tags = self.tag_handler.has_tags(korean_text)
        tag_section = ""

        if has_tags:
            # Add tag preservation instructions
            tag_section = self.tag_handler.create_tag_preservation_prompt_section()

        prompt = f"""{context}
{tag_section}
## Source Text (Korean)
{korean_text}

## 🔒 REQUIRED OUTPUT FORMAT:
Provide ONLY the professional English translation following these strict rules:

1. Translate ONLY what is written in the Korean text
2. Do NOT add any degrees, titles, or information not present in Korean
3. Use the mandatory terms specified above exactly as given
4. Be concise and direct - avoid verbose explanations
5. Follow regulatory writing style (not technical writing)
6. Maintain exact information parity with Korean source
{'7. PRESERVE all tags exactly as shown in examples above (CRITICAL)' if has_tags else ''}

CRITICAL: If you add ANY information not in the Korean text, this will be considered a critical translation error.

English Translation:"""

        return prompt

    def translate_with_gpt5_owl_strict(self, prompt: str) -> Tuple[str, int, float, Dict]:
        """Translate using GPT-5 OWL with anti-hallucination settings"""
        try:
            start_time = time.time()
            
            # Strict parameters to prevent hallucination and reduce verbosity
            response = self.client.responses.create(
                model="gpt-5",
                input=[{"role": "user", "content": prompt}],
                text={"verbosity": "low"},    # LOW to reduce verbosity  
                reasoning={"effort": "medium"}     # MEDIUM for better accuracy
            )
            
            processing_time = time.time() - start_time
            
            # Extract response
            translation = self._extract_text_from_openai_responses(response)
            
            # Calculate metrics
            input_tokens = len(prompt) // 4
            output_tokens = len(translation) // 4
            cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1000
            
            metadata = {
                "model_used": "GPT-5 OWL",
                "api_used": "Responses API", 
                "reasoning_effort": "medium",
                "text_verbosity": "minimal",
                "anti_hallucination_mode": True,
                "processing_time": processing_time
            }
            
            return translation, output_tokens, cost, metadata
            
        except Exception as e:
            self.logger.error(f"❌ GPT-5 OWL strict translation failed: {e}")
            # Fallback to GPT-4o with strict instructions
            return self._fallback_to_gpt4o_strict(prompt)

    def _fallback_to_gpt4o_strict(self, prompt: str) -> Tuple[str, int, float, Dict]:
        """Fallback to GPT-4o with strict anti-hallucination instructions"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a strict medical translator. NEVER add information not in the source text. Be concise and literal."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,  # Reduced to encourage conciseness
                temperature=0.1  # Lower temperature for consistency
            )
            
            translation = response.choices[0].message.content.strip()
            output_tokens = response.usage.completion_tokens
            cost = (response.usage.prompt_tokens * 0.15 + output_tokens * 0.60) / 1000
            
            metadata = {
                "model_used": "GPT-4o (fallback)",
                "api_used": "Chat Completions",
                "anti_hallucination_mode": True,
                "temperature": 0.1
            }
            
            return translation, output_tokens, cost, metadata
            
        except Exception as e:
            self.logger.error(f"❌ GPT-4o fallback also failed: {e}")
            return "[TRANSLATION FAILED]", 0, 0.0, {"error": str(e)}

    def _extract_text_from_openai_responses(self, response) -> str:
        """Extract text with improved fallbacks for GPT-5 OWL"""
        try:
            if hasattr(response, "output_text") and response.output_text:
                return str(response.output_text).strip()
            output = getattr(response, "output", None)
            if isinstance(output, str):
                return output.strip()
            if output is not None:
                return str(output).strip()
        except Exception:
            pass
        
        try:
            if hasattr(response, "text"):
                text_obj = response.text
                if hasattr(text_obj, "content"):
                    return str(text_obj.content).strip()
                elif isinstance(text_obj, str):
                    return text_obj.strip()
                else:
                    return str(text_obj).strip()
        except Exception:
            pass
            
        try:
            return str(response).strip()
        except Exception:
            return "[GPT-5 OWL Response Extraction Failed]"

    def post_process_translation_strict(self, translation: str, source_korean: str) -> str:
        """Post-process translation to remove common issues"""
        # Remove prompt label artifacts that LLM may include
        # Use regex to handle variations with different whitespace (space, newline, etc.)
        translation = re.sub(r'^English\s+[Tt]ranslations?:\s*', '', translation, flags=re.IGNORECASE)
        translation = re.sub(r'^[Tt]ranslations?:\s*', '', translation)

        # Also handle inline occurrences
        translation = translation.replace('English Translation: ', '')
        translation = translation.replace('English Translations: ', '')
        translation = translation.replace('English translation: ', '')
        translation = translation.replace('English translations: ', '')

        translation = re.sub(r'^\d+\.\s+', '', translation)  # Remove numbering if present

        # Remove redundant phrases
        translation = re.sub(r'\b(\w+)\s+\1\b', r'\1', translation)  # Remove word duplicates

        # Standardize abbreviation format
        translation = re.sub(r'\b([A-Z]{2,})\s*\(([^)]+)\)', r'\2 (\1)', translation)  # Fix abbrev order

        # Clean up extra spaces
        translation = re.sub(r'\s+', ' ', translation).strip()

        # Remove common verbose phrases
        verbose_patterns = [
            r'as mentioned above,?\s*',
            r'it should be noted that\s*',
            r'it is important to\s*',
            r'please note that\s*'
        ]

        for pattern in verbose_patterns:
            translation = re.sub(pattern, '', translation, flags=re.IGNORECASE)

        return translation

    def validate_translation_strict(self, source_korean: str, translation: str, 
                                  mandatory_violations: List[str]) -> Tuple[List[str], bool, str]:
        """Comprehensive validation including hallucination detection"""
        issues = []
        
        # Check mandatory term usage
        for violation in mandatory_violations:
            parts = violation.split("'")
            if len(parts) >= 4:
                ko_term = parts[1]
                en_term = parts[3]
                if ko_term in source_korean and en_term not in translation.lower():
                    issues.append(f"MANDATORY TERM MISSING: '{ko_term}' should be '{en_term}'")
        
        # Hallucination detection
        hallucination_detected, hallucination_details = self.hallucination_detector.detect_hallucination(
            source_korean, translation, "ko-en"
        )
        
        if hallucination_detected:
            issues.append(f"HALLUCINATION DETECTED: {hallucination_details}")
        
        # Check verbosity (calculate verbosity score)
        source_chars = len(source_korean)
        translation_words = len(translation.split())
        expected_words = source_chars * 0.6  # Rough Korean char to English word ratio
        verbosity_score = translation_words / expected_words if expected_words > 0 else 1.0
        
        if verbosity_score > 1.5:  # More than 50% longer than expected
            issues.append(f"EXCESSIVE VERBOSITY: Translation is {verbosity_score:.1f}x expected length")
        
        # Check for common abbreviation issues
        if self._check_abbreviation_consistency(translation):
            issues.append("ABBREVIATION INCONSISTENCY: Mixed capitalization or usage patterns")
        
        return issues, hallucination_detected, hallucination_details

    def _check_abbreviation_consistency(self, translation: str) -> bool:
        """Check for abbreviation consistency issues"""
        # Find potential abbreviation inconsistencies
        ae_pattern = r'\b(adverse events?|AEs?|Adverse Events?)\b'
        matches = re.findall(ae_pattern, translation, re.IGNORECASE)
        
        if len(set(m.lower() for m in matches)) > 2:  # More than 2 different forms
            return True
            
        # Check for mid-sentence capitalization
        mid_sentence_caps = re.search(r'\b[a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b', translation)
        if mid_sentence_caps:
            return True
            
        return False

    def process_ko_en_batch_strict(self, batch_data: List[Dict]) -> List[KOENTranslationResult]:
        """Process batch with strict QA validation and intelligent segment filtering"""
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        results = []
        
        # Pre-filter segments for auto-copy vs LLM processing
        llm_texts = []  # Only texts that need LLM
        segment_processing_plan = []  # Track what to do with each segment
        
        for i, item in enumerate(batch_data):
            source_text = item['source_ko']
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
        context_tokens = 0
        mandatory_violations = []
        
        if llm_texts:
            # Build strict context for LLM texts only
            context_text = self.build_ko_en_strict_context(llm_texts[0])[0]  # Use first text for context
            context_tokens = len(context_text) // 4
            
            # Create batch prompt for KO-EN translation
            prompt = f"""{context_text}

## Source Texts (Korean)
"""
            for idx, korean_text in enumerate(llm_texts, 1):
                prompt += f"{idx}. {korean_text}\n"
                
            prompt += f"""
## 🔒 REQUIRED OUTPUT FORMAT:
Provide ONLY the professional English translations following these strict rules:

1. Translate ONLY what is written in the Korean text
2. Do NOT add any degrees, titles, or information not present in Korean
3. Use the mandatory terms specified above exactly as given
4. Be concise and direct - avoid verbose explanations
5. Follow regulatory writing style (not technical writing)
6. Maintain exact information parity with Korean source

CRITICAL: If you add ANY information not in the Korean text, this will be considered a critical translation error.

Format your response as:
1. [English translation of text 1]
2. [English translation of text 2]
...and so on.

English Translations:"""
            
            # Translate LLM batch
            translation_text, output_tokens, llm_cost, metadata = self.translate_with_gpt5_owl_strict(prompt)
            
            # Parse batch response
            translations = self._parse_batch_response(translation_text, len(llm_texts))
        
        # Now process all segments according to the plan
        for i, item in enumerate(batch_data):
            start_time = time.time()
            plan = segment_processing_plan[i]
            korean_text = item['source_ko']
            segment_id = item.get('segment_id', i)
            
            if plan['type'] == 'auto_copy':
                # Auto-copy segment (instant, no cost)
                translation = plan['source_text']  # Direct copy
                processing_time = 0.0
                segment_cost = 0.0
                qa_issues = []  # Auto-copy has no QA issues
                status = "auto_copied"
                hallucination_detected = False
                hallucination_details = ""
                quality_score = 1.0  # Perfect for exact copy
                verbosity_score = 1.0
            else:
                # LLM processed segment
                llm_idx = plan['llm_index']
                translation = translations[llm_idx] if llm_idx < len(translations) else "[TRANSLATION FAILED]"
                
                # Post-process to clean up common issues
                translation = self.post_process_translation_strict(translation, korean_text)
                
                # Comprehensive validation
                qa_issues, hallucination_detected, hallucination_details = self.validate_translation_strict(
                    korean_text, translation, mandatory_violations
                )
                
                processing_time = time.time() - start_time
                segment_cost = llm_cost / len(llm_texts) if llm_texts else 0
                
                # Calculate quality score with penalties
                base_quality = 0.90
                quality_penalty = len(qa_issues) * 0.1
                if hallucination_detected:
                    quality_penalty += 0.3  # Heavy penalty for hallucination
                
                quality_score = max(0.0, base_quality - quality_penalty)
                
                # Calculate verbosity score
                source_chars = len(korean_text)
                translation_words = len(translation.split())
                expected_words = source_chars * 0.6
                verbosity_score = translation_words / expected_words if expected_words > 0 else 1.0
                
                status = "success" if not qa_issues else "qa_issues"
            
            result = KOENTranslationResult(
                segment_id=segment_id,
                source_text_ko=korean_text,
                reference_en=item.get('reference_en', ''),
                translated_text_en=translation,
                quality_score=quality_score,
                glossary_terms_found=len(mandatory_violations),
                glossary_terms_used=[],
                processing_time=processing_time,
                total_tokens=(output_tokens + context_tokens) // len(batch_data) if len(batch_data) > 0 else 0,
                input_tokens=(len(prompt) // 4) // len(batch_data) if len(batch_data) > 0 else 0,
                output_tokens=output_tokens // len(batch_data) if len(batch_data) > 0 else 0,
                input_cost=segment_cost * 0.3,
                output_cost=segment_cost * 0.7,
                total_cost=segment_cost,
                cost_per_quality_point=segment_cost / quality_score if quality_score > 0 else float('inf'),
                status=status,
                error_message=None,
                qa_issues=qa_issues,
                hallucination_detected=hallucination_detected,
                hallucination_details=hallucination_details,
                verbosity_score=verbosity_score
            )
            
            results.append(result)
            
            # Log critical issues
            if hallucination_detected:
                self.logger.error(f"🚨 HALLUCINATION in segment {segment_id}: {hallucination_details}")
            if qa_issues:
                self.logger.warning(f"⚠️ QA Issues in segment {segment_id}: {qa_issues}")
        
        return results

    def _parse_batch_response(self, response_text: str, expected_count: int) -> List[str]:
        """Parse batch response from LLM into individual translations"""
        translations = []
        
        # Try to extract numbered translations
        lines = response_text.strip().split('\n')
        current_translation = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for numbered format: "1.", "2.", etc.
            import re
            if re.match(r'^\d+\.', line):
                # Save previous translation if exists
                if current_translation:
                    translations.append(current_translation.strip())
                
                # Start new translation (remove number)
                current_translation = re.sub(r'^\d+\.\s*', '', line)
            else:
                # Continue current translation
                if current_translation:
                    current_translation += " " + line
                else:
                    current_translation = line
        
        # Add final translation
        if current_translation:
            translations.append(current_translation.strip())
        
        # Ensure we have the expected number of translations
        while len(translations) < expected_count:
            translations.append("[TRANSLATION ERROR]")
        
        return translations[:expected_count]

    def process_ko_en_segment_strict(self, segment_data: Dict) -> KOENTranslationResult:
        """Process single segment with comprehensive QA validation and tag preservation"""
        start_time = time.time()

        korean_text = segment_data['source_ko']
        segment_id = segment_data.get('segment_id', 0)

        # Check if segment contains tags
        has_tags = self.tag_handler.has_tags(korean_text)
        tag_validation_passed = True
        tag_validation_issues = []

        # Build context with mandatory term tracking
        context, context_tokens, mandatory_violations = self.build_ko_en_strict_context(korean_text)

        # Create strict prompt (with tag instructions if needed)
        prompt = self.create_strict_ko_en_prompt(korean_text, context)

        # Translate with strict settings
        translation, output_tokens, cost, metadata = self.translate_with_gpt5_owl_strict(prompt)

        # Post-process to clean up common issues
        translation = self.post_process_translation_strict(translation, korean_text)

        # Tag validation (if segment has tags)
        if has_tags:
            tag_validation = self.tag_handler.validate_tags(korean_text, translation)
            tag_validation_passed = tag_validation.is_valid
            tag_validation_issues = tag_validation.issues

            if not tag_validation_passed:
                self.logger.warning(
                    f"⚠️ Tag validation failed for segment {segment_id}: {tag_validation_issues}"
                )

        # Comprehensive validation
        qa_issues, hallucination_detected, hallucination_details = self.validate_translation_strict(
            korean_text, translation, mandatory_violations
        )

        processing_time = time.time() - start_time

        # Calculate quality score with penalties
        base_quality = 0.90
        quality_penalty = len(qa_issues) * 0.1
        if hallucination_detected:
            quality_penalty += 0.3  # Heavy penalty for hallucination
        if not tag_validation_passed:
            quality_penalty += 0.5  # Critical penalty for tag preservation failure

        quality_score = max(0.0, base_quality - quality_penalty)
        
        # Calculate verbosity score
        source_chars = len(korean_text)
        translation_words = len(translation.split())
        expected_words = source_chars * 0.6
        verbosity_score = translation_words / expected_words if expected_words > 0 else 1.0
        
        # Determine status based on all validation results
        if not tag_validation_passed:
            status = "tag_validation_failed"
        elif hallucination_detected:
            status = "hallucination_detected"
        elif qa_issues:
            status = "qa_issues"
        else:
            status = "success"

        result = KOENTranslationResult(
            segment_id=segment_id,
            source_text_ko=korean_text,
            reference_en=segment_data.get('reference_en', ''),
            translated_text_en=translation,
            quality_score=quality_score,
            glossary_terms_found=len(mandatory_violations),
            glossary_terms_used=[],
            processing_time=processing_time,
            total_tokens=output_tokens + context_tokens,
            input_tokens=len(prompt) // 4,
            output_tokens=output_tokens,
            input_cost=cost * 0.3,
            output_cost=cost * 0.7,
            total_cost=cost,
            cost_per_quality_point=cost / quality_score if quality_score > 0 else float('inf'),
            status=status,
            error_message=None,
            qa_issues=qa_issues,
            hallucination_detected=hallucination_detected,
            hallucination_details=hallucination_details,
            verbosity_score=verbosity_score,
            has_tags=has_tags,
            tag_validation_passed=tag_validation_passed,
            tag_validation_issues=tag_validation_issues
        )
        
        # Log critical issues
        if hallucination_detected:
            self.logger.error(f"🚨 HALLUCINATION in segment {segment_id}: {hallucination_details}")
        if qa_issues:
            self.logger.warning(f"⚠️ QA Issues in segment {segment_id}: {qa_issues}")
        
        return result

# Usage example
if __name__ == "__main__":
    # Initialize improved pipeline with BASELINE prompts
    print("=" * 80)
    print("TESTING BASELINE PROMPTS (use_enhanced_prompts=False)")
    print("=" * 80)
    pipeline_baseline = ImprovedKOENPipeline(model_name="Owl", use_enhanced_prompts=False)

    # Test with problematic segment (similar to segment 60)
    test_data = {
        'segment_id': 60,
        'source_ko': '원광대학교병원 소화기내과 최석채 교수',
        'reference_en': ''
    }

    # Process segment with baseline
    result_baseline = pipeline_baseline.process_ko_en_segment_strict(test_data)

    # Display baseline results
    print(f"\nSegment {result_baseline.segment_id} - BASELINE:")
    print(f"Source: {result_baseline.source_text_ko}")
    print(f"Translation: {result_baseline.translated_text_en}")
    print(f"Quality: {result_baseline.quality_score:.2f}")
    print(f"Verbosity Score: {result_baseline.verbosity_score:.2f}")
    if result_baseline.hallucination_detected:
        print(f"🚨 HALLUCINATION: {result_baseline.hallucination_details}")
    if result_baseline.qa_issues:
        print(f"QA Issues: {result_baseline.qa_issues}")

    # Initialize improved pipeline with ENHANCED prompts (golden examples)
    print("\n" + "=" * 80)
    print("TESTING ENHANCED PROMPTS (use_enhanced_prompts=True)")
    print("=" * 80)
    pipeline_enhanced = ImprovedKOENPipeline(model_name="Owl", use_enhanced_prompts=True)

    # Process segment with enhanced prompts
    result_enhanced = pipeline_enhanced.process_ko_en_segment_strict(test_data)

    # Display enhanced results
    print(f"\nSegment {result_enhanced.segment_id} - ENHANCED:")
    print(f"Source: {result_enhanced.source_text_ko}")
    print(f"Translation: {result_enhanced.translated_text_en}")
    print(f"Quality: {result_enhanced.quality_score:.2f}")
    print(f"Verbosity Score: {result_enhanced.verbosity_score:.2f}")
    if result_enhanced.hallucination_detected:
        print(f"🚨 HALLUCINATION: {result_enhanced.hallucination_details}")
    if result_enhanced.qa_issues:
        print(f"QA Issues: {result_enhanced.qa_issues}")

    # Compare results
    print("\n" + "=" * 80)
    print("COMPARISON:")
    print("=" * 80)
    print(f"Quality improvement: {result_enhanced.quality_score - result_baseline.quality_score:+.2f}")
    print(f"Token cost difference: {result_enhanced.total_tokens - result_baseline.total_tokens:+d} tokens")