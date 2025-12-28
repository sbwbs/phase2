#!/usr/bin/env python3
"""
Enhanced Batch Production Phase 2 Translation Pipeline
Combines style guide intelligence with batch processing for optimal performance
Performance target: ~0.4-0.5s per segment (5x faster than individual processing)
"""

import os
import sys
import pandas as pd
import logging
import time
import json
import openai
import openpyxl
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/Users/won.suh/Project/translate-ai/.env")

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

# Import our working glossary loader
from glossary_loader import GlossaryLoader

# Import ValkeyManager for persistent term storage
from memory.valkey_manager import ValkeyManager, SessionMetadata

# Import the style guide manager
from style_guide_config import StyleGuideManager, StyleGuideVariant

@dataclass
class BatchEnhancedResult:
    """Result for batch processing with style guide enhancement and detailed cost analysis"""
    segment_id: int
    source_text: str
    reference_en: str
    translated_text: str
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

class EnhancedBatchPipeline:
    """Enhanced batch pipeline combining style guides with batch processing"""
    
    def __init__(self, 
                 model_name: str = "Owl", 
                 use_valkey: bool = True,
                 batch_size: int = 5,
                 style_guide_variant: str = "standard"):
        
        self.model_name = model_name
        self.batch_size = batch_size
        self.session_id = f"enhanced_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.use_valkey = use_valkey
        
        # Setup logging
        self.setup_logging()
        
        # Initialize OpenAI client for GPT-5 OWL
        self.client = openai.OpenAI()
        
        # Initialize style guide manager
        self.style_guide_manager = StyleGuideManager()
        self.style_guide_variant = StyleGuideVariant(style_guide_variant)
        self.style_guide_manager.set_variant(self.style_guide_variant)
        self.logger.info(f"🎨 Style Guide set to: {self.style_guide_variant.value}")
        
        # Load REAL Phase 2 glossary (2906 terms)
        self.logger.info("📚 Loading REAL Phase 2 glossary data...")
        try:
            self.glossary_loader = GlossaryLoader()
            self.glossary_terms, self.glossary_stats = self.glossary_loader.load_all_glossaries()
            
            self.logger.info(f"✅ REAL Phase 2 glossary loaded successfully:")
            self.logger.info(f"   📋 Total terms: {self.glossary_stats['total_terms']}")
            self.logger.info(f"   🏥 Coding Form terms: {self.glossary_stats['coding_form_terms']}")
            self.logger.info(f"   🧪 Clinical Trials terms: {self.glossary_stats['clinical_trials_terms']}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load glossary: {e}")
            self.glossary_terms = {}
            self.glossary_stats = {'total_terms': 0}
        
        # Initialize memory system - ensure locked_terms is always initialized
        self.locked_terms = {}
        self.previous_translations = []
        
        try:
            if self.use_valkey:
                self.memory = ValkeyManager()
                self.session_metadata = SessionMetadata(
                    session_id=self.session_id,
                    model_name=self.model_name,
                    created_at=datetime.now(),
                    total_segments=0
                )
                self.memory.start_session(self.session_metadata)
                self.logger.info("🔄 Valkey memory system initialized")
                # For Valkey, we still keep local variables for fallback
            else:
                self.memory = None
                self.logger.info("💾 Using in-memory storage")
        except Exception as e:
            self.logger.warning(f"⚠️ Memory system initialization failed: {e}, using in-memory fallback")
            self.memory = None
        
        storage_type = "Valkey (persistent)" if self.use_valkey else "In-memory"
        self.logger.info(f"🚀 Enhanced Batch Pipeline initialized with {storage_type} storage")
        self.logger.info(f"📦 Batch size: {self.batch_size} segments per API call")
    
    def setup_logging(self):
        """Setup enhanced logging for the pipeline"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'enhanced_batch_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def search_real_glossary(self, korean_text: str) -> List[Dict]:
        """Search for Korean terms in the REAL Phase 2 glossary (2906 terms)"""
        if not self.glossary_terms:
            return []
        
        found_terms = []
        korean_text_lower = korean_text.lower()
        
        # Direct term matching from list of term dictionaries
        for term in self.glossary_terms:
            korean_term = term['korean'].lower()
            
            # Exact match
            if korean_term in korean_text_lower:
                found_terms.append({
                    'korean': term['korean'],
                    'english': term['english'],
                    'source': term['source'],
                    'score': term.get('score', 0.9),
                    'match_type': 'exact'
                })
        
        # Sort by length (longer terms first for better matching)
        found_terms.sort(key=lambda x: len(x['korean']), reverse=True)
        
        return found_terms
    
    def build_enhanced_batch_context(self, korean_texts: List[str]) -> Tuple[str, int]:
        """Build enhanced context optimized for batch processing"""
        context_components = []
        token_count = 0
        
        # Component 1: Collect all glossary terms for the batch
        all_glossary_terms = {}
        for korean_text in korean_texts:
            terms = self.search_real_glossary(korean_text)
            for term in terms:
                all_glossary_terms[term['korean']] = term
        
        # Add terminology section
        if all_glossary_terms:
            terminology_section = "## Key Medical Terminology\n"
            for term in list(all_glossary_terms.values())[:20]:  # Limit to top 20 terms
                terminology_section += f"- {term['korean']}: {term['english']} ({term['source']})\n"
            context_components.append(terminology_section)
            token_count += len(terminology_section) // 4
        
        # Component 2: Session Memory (locked terms from previous translations)
        locked_terms_items = self.get_locked_terms_items(10)  # Top 10 for batch
        if locked_terms_items:
            locked_section = "\n## Locked Terms (Maintain Consistency)\n"
            for ko, en in locked_terms_items:
                locked_section += f"- {ko}: {en}\n"
            context_components.append(locked_section)
            token_count += len(locked_section) // 4
        
        # Component 3: Previous Context (last 3 translations for batch context)
        if hasattr(self, 'previous_translations') and self.previous_translations:
            context_section = "\n## Previous Translation Context\n"
            for prev in self.previous_translations[-3:]:
                context_section += f"Previous: {prev['korean'][:50]}... → {prev['english'][:50]}...\n"
            context_components.append(context_section)
            token_count += len(context_section) // 4
        
        # Component 4: Style Guide
        style_guide = self.style_guide_manager.get_style_guide(self.style_guide_variant)
        if style_guide:
            context_components.append(style_guide)
            style_guide_tokens = len(style_guide) // 4
            token_count += style_guide_tokens
        
        # Component 5: Enhanced Batch Translation Instructions with Context-Aware Glossary Usage
        instructions = f"""\n## Batch Translation Instructions

**GLOSSARY USAGE HIERARCHY:**
1. **CONTEXT FIRST**: Always prioritize document context and domain consistency over rigid glossary adherence
2. **DOMAIN MATCHING**: Use glossary terms only when they match the document's specific domain
   - For "clinical study protocol" documents: "임상시험" → "clinical study" (protocols use "study")
   - For "clinical trial reports/publications" documents: "임상시험" → "clinical trial" (reports use "trial")
   - Judge context appropriateness before applying glossary terms
3. **SESSION CONSISTENCY**: Use locked terms from session memory for terms NOT covered by appropriate glossary matches
4. **GLOSSARY AS REFERENCE**: Treat glossary as reference guide, not absolute authority - LLM should judge contextual appropriateness

**TRANSLATION PRIORITIES:**
- **PRIORITY 1**: Document context and domain-specific terminology consistency
- **PRIORITY 2**: Appropriate glossary terms that match document context
- **PRIORITY 3**: Session memory terms for consistency within document
- **PRIORITY 4**: ICH GCP regulatory compliance and professional medical language

**CRITICAL RULE**: For protocol documents, "임상시험" should be "clinical study" not "clinical trial". For trial reports/publications, use "clinical trial". The LLM must evaluate document type and context appropriateness of all glossary suggestions.

Maintain consistency across all {len(korean_texts)} segments in this batch while respecting document context over glossary rigidity."""
        
        context_components.append(instructions)
        token_count += len(instructions) // 4
        
        return "\n".join(context_components), token_count
    
    def create_enhanced_batch_prompt(self, korean_texts: List[str], context: str) -> str:
        """Create enhanced batch prompt with style guide and context"""
        
        # Build numbered segments for batch processing
        segments_section = "\n## Korean Segments to Translate:\n"
        for i, korean_text in enumerate(korean_texts, 1):
            segments_section += f"{i}. {korean_text}\n"
        
        prompt = f"""{context}

{segments_section}

## Response Format:
Please provide exactly {len(korean_texts)} English translations in this format:

1. [English translation of segment 1]
2. [English translation of segment 2]
{f"3. [English translation of segment 3]" if len(korean_texts) > 2 else ""}
{f"4. [English translation of segment 4]" if len(korean_texts) > 3 else ""}
{f"5. [English translation of segment 5]" if len(korean_texts) > 4 else ""}

IMPORTANT: 
- Provide ONLY the numbered translations
- Do not include explanations or additional text
- Maintain consistent terminology across all translations
- Follow the style guide and prioritize glossary terms"""
        
        return prompt
    
    def translate_batch_with_gpt5_owl(self, prompt: str) -> Tuple[List[str], int, float, Dict]:
        """Translate batch using GPT-5 OWL Responses API"""
        try:
            start_time = time.time()
            
            response = self.client.responses.create(
                model="gpt-5",
                input=[{"role": "user", "content": prompt}],
                text={"verbosity": "medium"},
                reasoning={"effort": "minimal"}
            )
            
            # Extract translation text from response
            translation_text = self._extract_text_from_openai_responses(response)
            
            # Parse individual translations from batch response
            translations = self._parse_batch_response(translation_text)
            
            # Calculate approximate tokens and cost
            prompt_tokens = len(prompt) // 4
            completion_tokens = len(translation_text) // 4
            total_tokens = prompt_tokens + completion_tokens
            
            # GPT-5 pricing (official 2025 rates)
            # Input: $1.25 per 1M tokens, Output: $10.00 per 1M tokens
            input_cost = prompt_tokens * 0.00000125  # $1.25 per 1M tokens
            output_cost = completion_tokens * 0.00001  # $10.00 per 1M tokens
            cost = input_cost + output_cost
            
            processing_time = time.time() - start_time
            
            metadata = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'input_cost': input_cost,
                'output_cost': output_cost,
                'total_cost': cost,
                'processing_time': processing_time,
                'model': 'gpt-5'
            }
            
            return translations, total_tokens, cost, metadata
            
        except Exception as e:
            self.logger.error(f"❌ GPT-5 OWL translation failed: {e}")
            return [], 0, 0.0, {'error': str(e)}
    
    def _extract_text_from_openai_responses(self, response) -> str:
        """Extract text from OpenAI Responses API response"""
        try:
            if hasattr(response, 'output_text') and response.output_text:
                return str(response.output_text).strip()
            elif hasattr(response, 'output') and response.output:
                return str(response.output).strip()
            elif hasattr(response, 'text') and hasattr(response.text, 'content'):
                return str(response.text.content).strip()
            else:
                return str(response.text).strip()
        except Exception as e:
            self.logger.error(f"❌ Failed to extract text from response: {e}")
            return str(response).strip()
    
    def _parse_batch_response(self, response_text: str) -> List[str]:
        """Parse batch response into individual translations"""
        translations = []
        lines = response_text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            # Look for numbered responses: "1. ", "2. ", etc.
            if line and any(line.startswith(f"{i}. ") for i in range(1, 10)):
                # Extract translation after the number
                translation = line.split('. ', 1)[1] if '. ' in line else line
                translations.append(translation.strip())
        
        return translations
    
    def assess_batch_quality(self, korean_texts: List[str], translations: List[str], 
                           reference_texts: List[str]) -> List[float]:
        """Assess quality for each translation in the batch"""
        quality_scores = []
        
        for i, (korean, translation, reference) in enumerate(zip(korean_texts, translations, reference_texts)):
            # Simple quality assessment based on:
            # 1. Translation completeness
            # 2. Terminology usage
            # 3. Length appropriateness
            
            score = 0.5  # Base score
            
            # Check if translation is not empty
            if translation and len(translation.strip()) > 0:
                score += 0.2
            
            # Check length ratio (should be reasonable)
            if translation and korean:
                length_ratio = len(translation) / len(korean)
                if 0.5 <= length_ratio <= 3.0:  # Reasonable range
                    score += 0.1
            
            # Check for glossary term usage
            glossary_terms = self.search_real_glossary(korean)
            if glossary_terms:
                terms_used = sum(1 for term in glossary_terms if term['english'].lower() in translation.lower())
                if terms_used > 0:
                    score += min(0.2, terms_used * 0.05)
            
            # Bonus for clinical terminology patterns
            clinical_patterns = ['study', 'clinical', 'trial', 'patient', 'treatment', 'adverse', 'efficacy']
            pattern_matches = sum(1 for pattern in clinical_patterns if pattern in translation.lower())
            if pattern_matches > 0:
                score += min(0.1, pattern_matches * 0.02)
            
            quality_scores.append(min(1.0, score))
        
        return quality_scores
    
    def process_batch(self, batch_data: List[Dict], batch_num: int, total_batches: int) -> List[BatchEnhancedResult]:
        """Process a batch of segments with enhanced style guide"""
        batch_start_time = time.time()
        
        # Extract data from batch
        korean_texts = [item['korean'] for item in batch_data]
        reference_texts = [item.get('reference', '') for item in batch_data]
        segment_ids = [item['segment_id'] for item in batch_data]
        
        self.logger.info(f"🚀 Processing batch {batch_num}/{total_batches} with {len(korean_texts)} segments: {segment_ids}")
        
        try:
            # Step 1: Build enhanced context for the batch
            context, context_tokens = self.build_enhanced_batch_context(korean_texts)
            
            # Step 2: Create batch prompt
            prompt = self.create_enhanced_batch_prompt(korean_texts, context)
            
            # Step 3: Translate batch
            translations, api_tokens, cost, metadata = self.translate_batch_with_gpt5_owl(prompt)
            
            # Step 4: Handle response parsing
            if len(translations) != len(korean_texts):
                self.logger.warning(f"⚠️ Expected {len(korean_texts)} translations, got {len(translations)}")
                # Pad or truncate as needed
                while len(translations) < len(korean_texts):
                    translations.append("")
                translations = translations[:len(korean_texts)]
            
            # Step 5: Assess quality for each translation
            quality_scores = self.assess_batch_quality(korean_texts, translations, reference_texts)
            
            # Step 6: Create results
            results = []
            batch_processing_time = time.time() - batch_start_time
            
            for i, (segment_id, korean, reference, translation, quality) in enumerate(
                zip(segment_ids, korean_texts, reference_texts, translations, quality_scores)):
                
                # Search glossary terms for this specific segment
                glossary_terms = self.search_real_glossary(korean)
                
                # Calculate per-segment cost breakdown
                avg_input_tokens = metadata.get('prompt_tokens', 0) // len(korean_texts)
                avg_output_tokens = metadata.get('completion_tokens', 0) // len(korean_texts)
                avg_total_tokens = api_tokens // len(korean_texts)
                avg_input_cost = metadata.get('input_cost', 0) / len(korean_texts)
                avg_output_cost = metadata.get('output_cost', 0) / len(korean_texts)
                avg_total_cost = cost / len(korean_texts)
                
                # Calculate cost efficiency (cost per quality point)
                cost_per_quality = avg_total_cost / quality if quality > 0 else 0
                
                result = BatchEnhancedResult(
                    segment_id=segment_id,
                    source_text=korean,
                    reference_en=reference,
                    translated_text=translation,
                    style_guide_variant=self.style_guide_variant,
                    quality_score=quality,
                    glossary_terms_found=len(glossary_terms),
                    glossary_terms_used=glossary_terms,
                    processing_time=batch_processing_time / len(korean_texts),  # Average per segment
                    total_tokens=avg_total_tokens,
                    input_tokens=avg_input_tokens,
                    output_tokens=avg_output_tokens,
                    style_guide_tokens=context_tokens // len(korean_texts),  # Average per segment
                    input_cost=avg_input_cost,
                    output_cost=avg_output_cost,
                    total_cost=avg_total_cost,
                    cost_per_quality_point=cost_per_quality,
                    status="completed"
                )
                results.append(result)
            
            # Step 7: Update session memory with successful translations
            for korean, translation, glossary_terms in zip(korean_texts, translations, [self.search_real_glossary(k) for k in korean_texts]):
                if translation:  # Only update if translation succeeded
                    self.update_session_memory(korean, translation, glossary_terms)
            
            batch_time = time.time() - batch_start_time
            avg_time_per_segment = batch_time / len(korean_texts)
            avg_quality = sum(quality_scores) / len(quality_scores)
            avg_tokens = api_tokens // len(korean_texts)
            
            self.logger.info(f"✅ Batch {batch_num} completed in {batch_time:.2f}s (avg: {avg_time_per_segment:.2f}s per segment)")
            self.logger.info(f"📊 Batch Progress: {batch_num}/{total_batches} | Segments: {segment_ids[-1]}/{1400} | Quality: {avg_quality:.2f} | Tokens: {avg_tokens} | Cost: ${cost:.4f}")
            
            return results
            
        except Exception as e:
            # Handle batch failure
            self.logger.error(f"❌ Batch {batch_num} failed: {e}")
            
            error_results = []
            for i, (segment_id, korean, reference) in enumerate(zip(segment_ids, korean_texts, reference_texts)):
                result = BatchEnhancedResult(
                    segment_id=segment_id,
                    source_text=korean,
                    reference_en=reference,
                    translated_text="",
                    style_guide_variant=self.style_guide_variant,
                    quality_score=0.0,
                    glossary_terms_found=0,
                    glossary_terms_used=[],
                    processing_time=0.0,
                    total_tokens=0,
                    input_tokens=0,
                    output_tokens=0,
                    style_guide_tokens=0,
                    input_cost=0.0,
                    output_cost=0.0,
                    total_cost=0.0,
                    cost_per_quality_point=0.0,
                    status="error",
                    error_message=str(e)
                )
                error_results.append(result)
            
            return error_results
    
    def update_session_memory(self, korean_text: str, english_text: str, glossary_terms: List[Dict]):
        """Update session memory with translated terms"""
        try:
            if self.memory:
                # Use Valkey storage
                for term in glossary_terms:
                    self.memory.lock_term(term['korean'], term['english'])
                
                # Store previous translation
                self.memory.store_previous_translation(korean_text, english_text)
            else:
                # Use in-memory storage
                for term in glossary_terms:
                    self.locked_terms[term['korean']] = term['english']
                
                # Store previous translation
                if not hasattr(self, 'previous_translations'):
                    self.previous_translations = []
                
                self.previous_translations.append({
                    'korean': korean_text,
                    'english': english_text,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Keep only last 10 translations
                if len(self.previous_translations) > 10:
                    self.previous_translations = self.previous_translations[-10:]
                    
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to update session memory: {e}")
    
    def get_locked_terms(self) -> Dict[str, str]:
        """Get locked terms from session memory"""
        try:
            if self.memory:
                return self.memory.get_locked_terms()
            else:
                return self.locked_terms
        except Exception as e:
            self.logger.warning(f"Failed to get locked terms: {e}")
            return self.locked_terms if hasattr(self, 'locked_terms') else {}
    
    def get_locked_terms_items(self, limit: int = 10):
        """Get locked terms as items with limit"""
        locked_terms = self.get_locked_terms()
        if isinstance(locked_terms, dict):
            return list(locked_terms.items())[:limit]
        else:
            return []
    
    def run_enhanced_batch_pipeline(self, input_file: str, output_file: str = None) -> Dict:
        """Run the enhanced batch pipeline on input data"""
        
        print(f"\n🚀 Starting Enhanced Batch Mode - Production Pipeline with Style Guides")
        print(f"=" * 80)
        print(f"✅ Style guide variant set to: {self.style_guide_variant.value}")
        print(f"🎨 Using Style Guide: {self.style_guide_variant.value}")
        
        style_guide = self.style_guide_manager.get_style_guide(self.style_guide_variant)
        style_guide_tokens = len(style_guide) // 4 if style_guide else 0
        quality_config = self.style_guide_manager.variants[self.style_guide_variant]
        
        print(f"📊 Style Guide Tokens: ~{style_guide_tokens} tokens")
        print(f"🎯 Expected Quality Improvement: {quality_config.quality_score}")
        print()
        
        # Load test data
        print(f"📊 Loading test data from: {input_file}")
        try:
            df = pd.read_excel(input_file)
            print(f"✅ Loaded {len(df)} segments")
            print(f"📋 Columns: {list(df.columns)}")
            print()
        except Exception as e:
            self.logger.error(f"❌ Failed to load data: {e}")
            return {}
        
        # Prepare data for batch processing
        batch_data = []
        for idx, row in df.iterrows():
            korean_text = row.get('Source text', row.get('source_text', ''))
            reference_text = row.get('Target text', row.get('reference_en', ''))
            
            if korean_text:
                batch_data.append({
                    'segment_id': idx + 1,
                    'korean': korean_text,
                    'reference': reference_text
                })
        
        total_segments = len(batch_data)
        total_batches = (total_segments + self.batch_size - 1) // self.batch_size
        
        print(f"🚀 Starting Enhanced Batch Production Pipeline")
        print(f"📚 Using REAL glossary: {self.glossary_stats['total_terms']} terms")
        print(f"📦 Batch size: {self.batch_size} segments per API call")
        print(f"📦 Processing {total_batches} batches of up to {self.batch_size} segments each")
        
        # Process batches
        all_results = []
        start_time = time.time()
        
        for batch_num in range(1, total_batches + 1):
            batch_start_idx = (batch_num - 1) * self.batch_size
            batch_end_idx = min(batch_start_idx + self.batch_size, total_segments)
            current_batch = batch_data[batch_start_idx:batch_end_idx]
            
            batch_results = self.process_batch(current_batch, batch_num, total_batches)
            all_results.extend(batch_results)
            
            # Progress report every 10 batches
            if batch_num % 10 == 0:
                elapsed_time = time.time() - start_time
                segments_completed = len(all_results)
                progress_pct = (segments_completed / total_segments) * 100
                completed_results = [r for r in all_results if r.status == "completed"]
                avg_quality = sum(r.quality_score for r in completed_results) / len(completed_results) if completed_results else 0
                avg_tokens = sum(r.total_tokens for r in completed_results) / len(completed_results) if completed_results else 0
                avg_cost = sum(r.total_cost for r in completed_results) / len(completed_results) if completed_results else 0
                total_cost = sum(r.total_cost for r in completed_results)
                avg_cost_per_quality = sum(r.cost_per_quality_point for r in completed_results) / len(completed_results) if completed_results else 0
                processing_speed = segments_completed / elapsed_time if elapsed_time > 0 else 0
                
                print(f"\n📈 Progress Report:")
                print(f"   Segments completed: {segments_completed}/{total_segments} ({progress_pct:.1f}%)")
                print(f"   Overall avg quality: {avg_quality:.3f}")
                print(f"   Overall avg tokens: {avg_tokens:.0f}")
                print(f"   Overall avg cost per segment: ${avg_cost:.6f}")
                print(f"   Total cost so far: ${total_cost:.4f}")
                print(f"   Cost efficiency: ${avg_cost_per_quality:.6f} per quality point")
                print(f"   Processing speed: {processing_speed:.2f} segments/sec")
                print(f"   Elapsed time: {elapsed_time:.1f}s")
                print()
        
        # Generate final results
        total_time = time.time() - start_time
        completed_results = [r for r in all_results if r.status == "completed"]
        
        # Calculate comprehensive cost metrics
        total_cost = sum(r.total_cost for r in completed_results)
        avg_cost_per_segment = total_cost / len(completed_results) if completed_results else 0
        avg_input_cost = sum(r.input_cost for r in completed_results) / len(completed_results) if completed_results else 0
        avg_output_cost = sum(r.output_cost for r in completed_results) / len(completed_results) if completed_results else 0
        avg_cost_per_quality = sum(r.cost_per_quality_point for r in completed_results) / len(completed_results) if completed_results else 0
        
        final_metrics = {
            'total_segments': total_segments,
            'completed_segments': len(completed_results),
            'completion_rate': len(completed_results) / total_segments,
            'total_processing_time': total_time,
            'average_time_per_segment': total_time / total_segments,
            'average_quality_score': sum(r.quality_score for r in completed_results) / len(completed_results) if completed_results else 0,
            'average_tokens_per_segment': sum(r.total_tokens for r in completed_results) / len(completed_results) if completed_results else 0,
            'average_input_tokens': sum(r.input_tokens for r in completed_results) / len(completed_results) if completed_results else 0,
            'average_output_tokens': sum(r.output_tokens for r in completed_results) / len(completed_results) if completed_results else 0,
            'total_cost': total_cost,
            'average_cost_per_segment': avg_cost_per_segment,
            'average_input_cost': avg_input_cost,
            'average_output_cost': avg_output_cost,
            'cost_per_quality_point': avg_cost_per_quality,
            'cost_per_page_25_segments': avg_cost_per_segment * 25,
            'cost_per_50_page_document': avg_cost_per_segment * 1250,
            'total_api_calls': total_batches,
            'segments_per_api_call': self.batch_size,
            'style_guide_variant': self.style_guide_variant.value,
            'style_guide_tokens': style_guide_tokens
        }
        
        print(f"\n🎉 Enhanced Batch Pipeline Completed!")
        print(f"📊 Final Metrics:")
        print(f"   Total time: {total_time:.1f}s")
        print(f"   Average per segment: {final_metrics['average_time_per_segment']:.2f}s")
        print(f"   Completion rate: {final_metrics['completion_rate']:.1%}")
        print(f"   Average quality: {final_metrics['average_quality_score']:.3f}")
        print(f"   Average tokens: {final_metrics['average_tokens_per_segment']:.0f}")
        print(f"   API efficiency: {final_metrics['segments_per_api_call']} segments/call")
        print()
        print(f"💰 Cost Analysis (GPT-5 Official Pricing):")
        print(f"   Total cost: ${final_metrics['total_cost']:.4f}")
        print(f"   Cost per segment: ${final_metrics['average_cost_per_segment']:.6f}")
        print(f"   Cost per page (25 segments): ${final_metrics['cost_per_page_25_segments']:.4f}")
        print(f"   Cost per 50-page document: ${final_metrics['cost_per_50_page_document']:.2f}")
        print(f"   Cost efficiency: ${final_metrics['cost_per_quality_point']:.6f} per quality point")
        print(f"   Input/Output split: ${final_metrics['average_input_cost']:.6f} / ${final_metrics['average_output_cost']:.6f}")
        
        # Save results to Excel
        if not output_file:
            output_file = f"enhanced_batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        self.save_results_to_excel(all_results, final_metrics, output_file)
        
        return {
            'results': all_results,
            'metrics': final_metrics,
            'output_file': output_file
        }
    
    def save_results_to_excel(self, results: List[BatchEnhancedResult], metrics: Dict, output_file: str):
        """Save results to Excel with multiple sheets"""
        
        # Create main results dataframe
        results_data = []
        glossary_data = []
        
        for result in results:
            results_data.append({
                'Segment ID': result.segment_id,
                'Source Text': result.source_text,
                'Reference EN': result.reference_en,
                'Translated Text': result.translated_text,
                'Style Guide Variant': result.style_guide_variant.value,
                'Quality Score': result.quality_score,
                'Total Tokens': result.total_tokens,
                'Input Tokens': result.input_tokens,
                'Output Tokens': result.output_tokens,
                'Style Guide Tokens': result.style_guide_tokens,
                'Input Cost ($)': result.input_cost,
                'Output Cost ($)': result.output_cost,
                'Total Cost ($)': result.total_cost,
                'Cost per Quality Point': result.cost_per_quality_point,
                'Processing Time (s)': result.processing_time,
                'Glossary Terms Found': result.glossary_terms_found,
                'Status': result.status,
                'Error Message': result.error_message or ''
            })
            
            # Add glossary terms details
            for term in result.glossary_terms_used:
                glossary_data.append({
                    'Segment ID': result.segment_id,
                    'Korean Term': term['korean'],
                    'English Term': term['english'],
                    'Source': term['source']
                })
        
        # Create summary data
        summary_data = [{
            'Metric': key.replace('_', ' ').title(),
            'Value': value
        } for key, value in metrics.items()]
        
        # Create cost analysis data
        cost_analysis_data = []
        
        # Add cost breakdown by quality ranges
        quality_ranges = [(0.0, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
        for min_q, max_q in quality_ranges:
            range_results = [r for r in results if min_q <= r.quality_score < max_q and r.status == "completed"]
            if range_results:
                avg_cost = sum(r.total_cost for r in range_results) / len(range_results)
                avg_quality = sum(r.quality_score for r in range_results) / len(range_results)
                avg_tokens = sum(r.total_tokens for r in range_results) / len(range_results)
                cost_analysis_data.append({
                    'Quality Range': f"{min_q:.1f} - {max_q:.1f}",
                    'Segment Count': len(range_results),
                    'Avg Quality': f"{avg_quality:.3f}",
                    'Avg Cost ($)': f"{avg_cost:.6f}",
                    'Avg Tokens': f"{avg_tokens:.0f}",
                    'Cost per Quality Point': f"{avg_cost/avg_quality:.6f}" if avg_quality > 0 else "0"
                })
        
        # Save to Excel with multiple sheets
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            pd.DataFrame(results_data).to_excel(writer, sheet_name='Enhanced_Batch_Results', index=False)
            pd.DataFrame(glossary_data).to_excel(writer, sheet_name='Glossary_Terms_Used', index=False)
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Pipeline_Metrics', index=False)
            pd.DataFrame(cost_analysis_data).to_excel(writer, sheet_name='Cost_Quality_Analysis', index=False)
        
        self.logger.info(f"💾 Results saved to: {output_file}")
        print(f"💾 Results saved to: {output_file}")

def main():
    """Main function to run the enhanced batch pipeline"""
    
    # Configuration
    input_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/1_테스트용_Generated_Preview_KO-EN.xlsx"
    
    # Initialize enhanced batch pipeline
    pipeline = EnhancedBatchPipeline(
        model_name="Owl",
        use_valkey=False,  # Use in-memory for demo
        batch_size=5,      # Optimal batch size
        style_guide_variant="standard"  # Use standard style guide
    )
    
    # Run the pipeline
    results = pipeline.run_enhanced_batch_pipeline(input_file)
    
    if results:
        print(f"\n✅ Pipeline completed successfully!")
        print(f"📁 Results file: {results['output_file']}")
        print(f"📊 Processed {results['metrics']['total_segments']} segments")
        print(f"⚡ Speed: {results['metrics']['average_time_per_segment']:.2f}s per segment")
        print(f"🎯 Quality: {results['metrics']['average_quality_score']:.3f}")

if __name__ == "__main__":
    main()