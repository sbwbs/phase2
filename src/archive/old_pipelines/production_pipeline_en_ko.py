#!/usr/bin/env python3
"""
EN-KO Production Translation Pipeline
Enhanced batch processing for English to Korean clinical protocol translation
Based on production_pipeline_batch_enhanced.py, modified for EN→KO direction
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

# Import ValkeyManager for persistent term storage
from memory.valkey_manager import ValkeyManager, SessionMetadata

# Import the style guide manager
from style_guide_config import StyleGuideManager, StyleGuideVariant

@dataclass
class ENKOTranslationResult:
    """Result for EN-KO translation with comprehensive metrics"""
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

class ENKOPipeline:
    """EN-KO translation pipeline with batch processing and style guides"""
    
    def __init__(self, 
                 model_name: str = "Owl", 
                 use_valkey: bool = False,
                 batch_size: int = 5,
                 style_guide_variant: str = "standard"):
        
        self.model_name = model_name
        self.batch_size = batch_size
        self.session_id = f"en_ko_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
        
        # Load EN-KO glossary
        self.logger.info("📚 Loading EN-KO glossary data...")
        self.glossary_terms = {}
        self.glossary_stats = {'total_terms': 0}
        self.load_en_ko_glossary()
        
        # Initialize memory system
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
            else:
                self.memory = None
                self.logger.info("💾 Using in-memory storage")
        except Exception as e:
            self.logger.warning(f"⚠️ Memory system initialization failed: {e}, using in-memory fallback")
            self.memory = None
        
        storage_type = "Valkey (persistent)" if self.use_valkey else "In-memory"
        self.logger.info(f"🚀 EN-KO Pipeline initialized with {storage_type} storage")
        self.logger.info(f"📦 Batch size: {self.batch_size} segments per API call")
    
    def setup_logging(self):
        """Setup logging for the pipeline"""
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'{log_dir}/en_ko_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_en_ko_glossary(self):
        """Load combined EN-KO glossary from preprocessed file"""
        self.glossary_terms = {}
        
        # Load the preprocessed combined glossary
        combined_file = "/Users/won.suh/Project/translate-ai/phase2/data/combined_en_ko_glossary.xlsx"
        
        try:
            self.logger.info("📚 Loading combined EN-KO glossary...")
            df_combined = pd.read_excel(combined_file)
            
            # Convert to dictionary format for quick lookup
            for _, row in df_combined.iterrows():
                english = str(row.get('English', '')).strip()
                korean = str(row.get('Korean', '')).strip()
                source = str(row.get('Source', 'Unknown')).strip()
                priority = row.get('Priority', 2)
                
                if english and korean:
                    self.glossary_terms[english.lower()] = {
                        'english': english,
                        'korean': korean,
                        'source': source,
                        'priority': priority
                    }
            
            # Final statistics by source
            sources_stats = {}
            for term_data in self.glossary_terms.values():
                source = term_data['source']
                sources_stats[source] = sources_stats.get(source, 0) + 1
            
            self.glossary_stats = {
                'total_terms': len(self.glossary_terms),
                'sources': sources_stats,
                'source_file': combined_file
            }
            
            self.logger.info(f"✅ Combined glossary loaded successfully:")
            self.logger.info(f"   🔗 Total unique terms: {len(self.glossary_terms)}")
            self.logger.info(f"   📁 Source file: {combined_file}")
            
            for source, count in sources_stats.items():
                self.logger.info(f"   📚 {source}: {count} terms")
            
            # Show sample terms from each source
            self.logger.info(f"📝 Sample terms by source:")
            for source_name in sources_stats.keys():
                sample_terms = [(k, v) for k, v in list(self.glossary_terms.items())[:100] 
                              if v['source'] == source_name][:3]
                if sample_terms:
                    self.logger.info(f"   {source_name}:")
                    for _, term_data in sample_terms:
                        self.logger.info(f"     • {term_data['english']} → {term_data['korean']}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load combined glossary: {e}")
            self.logger.info("💡 Try running: python src/create_combined_glossary.py")
            self.glossary_stats = {'total_terms': 0, 'sources': {}}
    
    def search_glossary_en_ko(self, english_text: str) -> List[Dict]:
        """Search for English terms in the EN-KO glossary with improved partial matching"""
        if not self.glossary_terms:
            return []
        
        found_terms = []
        english_text_lower = english_text.lower()
        
        # Search for glossary terms in the English text
        for eng_term, term_data in self.glossary_terms.items():
            match_type = None
            score = 0.0
            
            # 1. Exact phrase match (highest priority)
            if eng_term in english_text_lower:
                match_type = 'exact'
                score = 1.0
            
            # 2. Partial word match (for multi-word terms)
            elif len(eng_term.split()) > 1:
                term_words = eng_term.split()
                # Check if significant words from the term are in the text
                matched_words = []
                for word in term_words:
                    if len(word) > 3 and word in english_text_lower:  # Only significant words
                        matched_words.append(word)
                
                # If we match at least 2 significant words or 1 very specific word
                if len(matched_words) >= 2 or (len(matched_words) >= 1 and len(matched_words[0]) > 6):
                    match_type = 'partial'
                    score = len(matched_words) / len(term_words)  # Proportion of words matched
            
            # 3. Single important word match (for specific medical terms)
            elif len(eng_term) > 6 and eng_term in english_text_lower:
                match_type = 'word'
                score = 0.8
            
            if match_type:
                found_terms.append({
                    'english': term_data['english'],
                    'korean': term_data['korean'],
                    'source': term_data['source'],
                    'match_type': match_type,
                    'score': score
                })
        
        # Sort by score (higher scores first), then by length
        found_terms.sort(key=lambda x: (x['score'], len(x['english'])), reverse=True)
        
        # Limit to top 10 most relevant terms to avoid context overload
        return found_terms[:10]
    
    def build_en_ko_batch_context(self, english_texts: List[str]) -> Tuple[str, int]:
        """Build context for EN→KO batch translation"""
        context_components = []
        token_count = 0
        
        # Component 1: Collect all glossary terms for the batch
        all_glossary_terms = {}
        for english_text in english_texts:
            terms = self.search_glossary_en_ko(english_text)
            for term in terms:
                all_glossary_terms[term['english']] = term
        
        # Add terminology section
        if all_glossary_terms:
            terminology_section = "## 의학 전문 용어 (Medical Terminology)\n"
            for term in list(all_glossary_terms.values())[:20]:  # Limit to top 20 terms
                terminology_section += f"- {term['english']}: {term['korean']}\n"
            context_components.append(terminology_section)
            token_count += len(terminology_section) // 4
        
        # Component 2: Session Memory (locked terms from previous translations)
        if self.locked_terms:
            locked_section = "\n## 일관성 유지 용어 (Maintain Consistency)\n"
            for en, ko in list(self.locked_terms.items())[:10]:
                locked_section += f"- {en}: {ko}\n"
            context_components.append(locked_section)
            token_count += len(locked_section) // 4
        
        # Component 3: Previous Context
        if self.previous_translations:
            context_section = "\n## 이전 번역 문맥 (Previous Context)\n"
            for prev in self.previous_translations[-3:]:
                context_section += f"이전: {prev['english'][:50]}... → {prev['korean'][:50]}...\n"
            context_components.append(context_section)
            token_count += len(context_section) // 4
        
        # Component 4: EN→KO Translation Guidelines
        guidelines = """
## 영한 번역 지침 (EN→KO Translation Guidelines)

### 전문 의학 한국어 사용 원칙:
1. **공식 의학 용어 사용**: 대한의학협회 의학용어집 기준 준수
2. **임상시험 용어 표준화**:
   - "clinical study" → "임상시험"
   - "clinical trial" → "임상시험"
   - "investigational product" → "임상시험용 의약품"
   - "adverse event" → "이상반응"
   - "serious adverse event" → "중대한 이상반응"
   - "protocol" → "임상시험계획서"

3. **문체 및 어조**:
   - 전문적이고 격식있는 한국어 사용 (합쇼체)
   - 피동형보다 능동형 선호
   - 명확하고 간결한 표현

4. **숫자 및 단위 처리**:
   - 아라비아 숫자 유지
   - 단위는 국제표준 또는 한국 표준 사용
   - 약물 용량은 원문 그대로 유지

5. **규제 준수**:
   - 식약처 임상시험 관련 용어 가이드라인 준수
   - ICH-GCP 한국어 번역 표준 따름
"""
        context_components.append(guidelines)
        token_count += len(guidelines) // 4
        
        return "\n".join(context_components), token_count
    
    def create_en_ko_batch_prompt(self, english_texts: List[str], context: str) -> str:
        """Create batch prompt for EN→KO translation"""
        
        # Build numbered segments for batch processing
        segments_section = "\n## 번역할 영어 텍스트 (English Segments to Translate):\n"
        for i, english_text in enumerate(english_texts, 1):
            segments_section += f"{i}. {english_text}\n"
        
        prompt = f"""{context}

{segments_section}

## 응답 형식 (Response Format):
다음 형식으로 정확히 {len(english_texts)}개의 한국어 번역을 제공하십시오:

1. [1번 문장의 한국어 번역]
2. [2번 문장의 한국어 번역]
{f"3. [3번 문장의 한국어 번역]" if len(english_texts) > 2 else ""}
{f"4. [4번 문장의 한국어 번역]" if len(english_texts) > 3 else ""}
{f"5. [5번 문장의 한국어 번역]" if len(english_texts) > 4 else ""}

중요 사항:
- 번호가 매겨진 번역만 제공
- 추가 설명이나 텍스트 포함 금지
- 모든 번역에서 일관된 용어 사용
- 의학 전문 용어집 및 지침 준수
- 격식있는 한국어 문체 사용 (합쇼체)"""
        
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
            
            # Calculate tokens and cost
            prompt_tokens = len(prompt) // 4
            completion_tokens = len(translation_text) // 4
            total_tokens = prompt_tokens + completion_tokens
            
            # GPT-5 pricing
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
            # Look for numbered responses
            if line and any(line.startswith(f"{i}. ") for i in range(1, 10)):
                translation = line.split('. ', 1)[1] if '. ' in line else line
                translations.append(translation.strip())
        
        return translations
    
    def assess_en_ko_quality(self, english_texts: List[str], translations: List[str], 
                             reference_texts: List[str]) -> List[float]:
        """Assess quality for EN→KO translations"""
        quality_scores = []
        
        for english, translation, reference in zip(english_texts, translations, reference_texts):
            score = 0.5  # Base score
            
            # Check if translation is not empty
            if translation and len(translation.strip()) > 0:
                score += 0.2
            
            # Check length ratio (Korean is typically shorter)
            if translation and english:
                length_ratio = len(translation) / len(english)
                if 0.3 <= length_ratio <= 1.5:  # Korean is more compact
                    score += 0.1
            
            # Check for glossary term usage
            glossary_terms = self.search_glossary_en_ko(english)
            if glossary_terms:
                terms_used = sum(1 for term in glossary_terms if term['korean'] in translation)
                if terms_used > 0:
                    score += min(0.2, terms_used * 0.05)
            
            # Check for Korean medical terminology patterns
            korean_medical_patterns = ['임상시험', '이상반응', '시험대상자', '의약품', '계획서', '효능', '안전성']
            pattern_matches = sum(1 for pattern in korean_medical_patterns if pattern in translation)
            if pattern_matches > 0:
                score += min(0.1, pattern_matches * 0.02)
            
            quality_scores.append(min(1.0, score))
        
        return quality_scores
    
    def process_batch(self, batch_data: List[Dict], batch_num: int, total_batches: int) -> List[ENKOTranslationResult]:
        """Process a batch of EN→KO translations"""
        batch_start_time = time.time()
        
        # Extract data from batch
        english_texts = [item['english'] for item in batch_data]
        reference_texts = [item.get('reference', '') for item in batch_data]
        segment_ids = [item['segment_id'] for item in batch_data]
        
        self.logger.info(f"🚀 Processing batch {batch_num}/{total_batches} with {len(english_texts)} segments")
        
        try:
            # Step 1: Build context for the batch
            context, context_tokens = self.build_en_ko_batch_context(english_texts)
            
            # Step 2: Create batch prompt
            prompt = self.create_en_ko_batch_prompt(english_texts, context)
            
            # Step 3: Translate batch
            translations, api_tokens, cost, metadata = self.translate_batch_with_gpt5_owl(prompt)
            
            # Step 4: Handle response parsing
            if len(translations) != len(english_texts):
                self.logger.warning(f"⚠️ Expected {len(english_texts)} translations, got {len(translations)}")
                while len(translations) < len(english_texts):
                    translations.append("")
                translations = translations[:len(english_texts)]
            
            # Step 5: Assess quality
            quality_scores = self.assess_en_ko_quality(english_texts, translations, reference_texts)
            
            # Step 6: Create results
            results = []
            batch_processing_time = time.time() - batch_start_time
            
            for i, (segment_id, english, reference, translation, quality) in enumerate(
                zip(segment_ids, english_texts, reference_texts, translations, quality_scores)):
                
                # Search glossary terms
                glossary_terms = self.search_glossary_en_ko(english)
                
                # Calculate per-segment costs
                avg_input_tokens = metadata.get('prompt_tokens', 0) // len(english_texts)
                avg_output_tokens = metadata.get('completion_tokens', 0) // len(english_texts)
                avg_total_tokens = api_tokens // len(english_texts) if api_tokens > 0 else 0
                avg_input_cost = metadata.get('input_cost', 0) / len(english_texts)
                avg_output_cost = metadata.get('output_cost', 0) / len(english_texts)
                avg_total_cost = cost / len(english_texts) if cost > 0 else 0
                
                # Calculate cost efficiency
                cost_per_quality = avg_total_cost / quality if quality > 0 else 0
                
                result = ENKOTranslationResult(
                    segment_id=segment_id,
                    source_text_en=english,
                    reference_ko=reference,
                    translated_text_ko=translation,
                    style_guide_variant=self.style_guide_variant,
                    quality_score=quality,
                    glossary_terms_found=len(glossary_terms),
                    glossary_terms_used=glossary_terms,
                    processing_time=batch_processing_time / len(english_texts),
                    total_tokens=avg_total_tokens,
                    input_tokens=avg_input_tokens,
                    output_tokens=avg_output_tokens,
                    style_guide_tokens=context_tokens // len(english_texts),
                    input_cost=avg_input_cost,
                    output_cost=avg_output_cost,
                    total_cost=avg_total_cost,
                    cost_per_quality_point=cost_per_quality,
                    status="completed"
                )
                results.append(result)
            
            # Step 7: Update session memory
            for english, translation in zip(english_texts, translations):
                if translation:
                    self.update_session_memory(english, translation, glossary_terms)
            
            self.logger.info(f"✅ Batch {batch_num} completed in {batch_processing_time:.2f}s")
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Batch {batch_num} failed: {e}")
            
            # Return error results
            error_results = []
            for segment_id, english, reference in zip(segment_ids, english_texts, reference_texts):
                result = ENKOTranslationResult(
                    segment_id=segment_id,
                    source_text_en=english,
                    reference_ko=reference,
                    translated_text_ko="",
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
    
    def update_session_memory(self, english_text: str, korean_text: str, glossary_terms: List[Dict]):
        """Update session memory with translated terms"""
        try:
            # Store locked terms
            for term in glossary_terms:
                self.locked_terms[term['english']] = term['korean']
            
            # Store previous translation
            self.previous_translations.append({
                'english': english_text,
                'korean': korean_text,
                'timestamp': datetime.now().isoformat()
            })
            
            # Keep only last 10 translations
            if len(self.previous_translations) > 10:
                self.previous_translations = self.previous_translations[-10:]
                
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to update session memory: {e}")
    
    def run_en_ko_pipeline(self, input_file: str = None, output_file: str = None) -> Dict:
        """Run the EN→KO translation pipeline"""
        
        # Default to EN-KO test file if not specified
        if not input_file:
            input_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/영한/1_테스트용_Generated_Preview_EN-KO.xlsx"
        
        print(f"\n🚀 Starting EN→KO Translation Pipeline")
        print(f"=" * 80)
        print(f"📁 Input file: {input_file}")
        print(f"🎨 Style guide: {self.style_guide_variant.value}")
        print(f"📦 Batch size: {self.batch_size} segments per API call")
        print()
        
        # Load test data
        print(f"📊 Loading EN-KO test data...")
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
            english_text = str(row.get('Source text', '')).strip()
            reference_text = str(row.get('Target text', '')).strip()
            
            if english_text:
                batch_data.append({
                    'segment_id': idx + 1,
                    'english': english_text,
                    'reference': reference_text
                })
        
        # Process all segments (full document)
        # batch_data = batch_data[:100]  # Remove limit for full processing
        
        total_segments = len(batch_data)
        total_batches = (total_segments + self.batch_size - 1) // self.batch_size
        
        print(f"🚀 Starting EN→KO batch processing")
        print(f"📚 Using glossary: {self.glossary_stats['total_terms']} terms from {self.glossary_stats.get('source', 'Unknown')}")
        print(f"📦 Processing {total_batches} batches of up to {self.batch_size} segments each")
        print()
        
        # Process batches
        all_results = []
        start_time = time.time()
        
        for batch_num in range(1, total_batches + 1):
            batch_start_idx = (batch_num - 1) * self.batch_size
            batch_end_idx = min(batch_start_idx + self.batch_size, total_segments)
            current_batch = batch_data[batch_start_idx:batch_end_idx]
            
            batch_results = self.process_batch(current_batch, batch_num, total_batches)
            all_results.extend(batch_results)
            
            # Progress report every 5 batches
            if batch_num % 5 == 0 or batch_num == total_batches:
                elapsed_time = time.time() - start_time
                segments_completed = len(all_results)
                progress_pct = (segments_completed / total_segments) * 100
                
                print(f"📈 Progress: {segments_completed}/{total_segments} ({progress_pct:.1f}%)")
                print(f"⏱️ Elapsed time: {elapsed_time:.1f}s")
                print()
        
        # Generate final results
        total_time = time.time() - start_time
        completed_results = [r for r in all_results if r.status == "completed"]
        
        # Calculate metrics
        total_cost = sum(r.total_cost for r in completed_results)
        avg_cost_per_segment = total_cost / len(completed_results) if completed_results else 0
        
        final_metrics = {
            'total_segments': total_segments,
            'completed_segments': len(completed_results),
            'completion_rate': len(completed_results) / total_segments if total_segments > 0 else 0,
            'total_processing_time': total_time,
            'average_time_per_segment': total_time / total_segments if total_segments > 0 else 0,
            'average_quality_score': sum(r.quality_score for r in completed_results) / len(completed_results) if completed_results else 0,
            'average_tokens_per_segment': sum(r.total_tokens for r in completed_results) / len(completed_results) if completed_results else 0,
            'total_cost': total_cost,
            'average_cost_per_segment': avg_cost_per_segment,
            'total_api_calls': total_batches,
            'segments_per_api_call': self.batch_size,
            'translation_direction': 'EN→KO',
            'glossary_terms': self.glossary_stats['total_terms']
        }
        
        print(f"\n🎉 EN→KO Translation Pipeline Completed!")
        print(f"📊 Final Metrics:")
        print(f"   Total time: {total_time:.1f}s")
        print(f"   Average per segment: {final_metrics['average_time_per_segment']:.2f}s")
        print(f"   Completion rate: {final_metrics['completion_rate']:.1%}")
        print(f"   Average quality: {final_metrics['average_quality_score']:.3f}")
        print(f"   Average tokens: {final_metrics['average_tokens_per_segment']:.0f}")
        print()
        print(f"💰 Cost Analysis:")
        print(f"   Total cost: ${final_metrics['total_cost']:.4f}")
        print(f"   Cost per segment: ${final_metrics['average_cost_per_segment']:.6f}")
        
        # Save results to Excel
        if not output_file:
            output_file = f"en_ko_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        self.save_results_to_excel(all_results, final_metrics, output_file)
        
        return {
            'results': all_results,
            'metrics': final_metrics,
            'output_file': output_file
        }
    
    def save_results_to_excel(self, results: List[ENKOTranslationResult], metrics: Dict, output_file: str):
        """Save EN→KO results to Excel"""
        
        # Create main results dataframe
        results_data = []
        glossary_data = []
        
        for result in results:
            results_data.append({
                'Segment ID': result.segment_id,
                'Source (EN)': result.source_text_en,
                'Reference (KO)': result.reference_ko,
                'Translation (KO)': result.translated_text_ko,
                'Quality Score': result.quality_score,
                'Total Tokens': result.total_tokens,
                'Total Cost ($)': result.total_cost,
                'Processing Time (s)': result.processing_time,
                'Glossary Terms Found': result.glossary_terms_found,
                'Status': result.status
            })
            
            # Add glossary terms details
            for term in result.glossary_terms_used:
                glossary_data.append({
                    'Segment ID': result.segment_id,
                    'English Term': term['english'],
                    'Korean Term': term['korean'],
                    'Source': term['source']
                })
        
        # Create summary data
        summary_data = [{
            'Metric': key.replace('_', ' ').title(),
            'Value': value
        } for key, value in metrics.items()]
        
        # Save to Excel with multiple sheets
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            pd.DataFrame(results_data).to_excel(writer, sheet_name='EN_KO_Results', index=False)
            pd.DataFrame(glossary_data).to_excel(writer, sheet_name='Glossary_Terms', index=False)
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
        
        self.logger.info(f"💾 Results saved to: {output_file}")
        print(f"💾 Results saved to: {output_file}")

def main():
    """Main function to run EN→KO pipeline"""
    
    # Initialize EN-KO pipeline
    pipeline = ENKOPipeline(
        model_name="Owl",
        use_valkey=True,   # Enable Valkey persistent storage
        batch_size=5,      # Optimal batch size
        style_guide_variant="clinical_protocol"  # Use new EN-KO clinical protocol style guide
    )
    
    # Run the pipeline
    results = pipeline.run_en_ko_pipeline()
    
    if results:
        print(f"\n✅ EN→KO Pipeline completed successfully!")
        print(f"📁 Results file: {results['output_file']}")
        print(f"📊 Processed {results['metrics']['total_segments']} segments")
        print(f"⚡ Speed: {results['metrics']['average_time_per_segment']:.2f}s per segment")
        print(f"🎯 Quality: {results['metrics']['average_quality_score']:.3f}")

if __name__ == "__main__":
    main()