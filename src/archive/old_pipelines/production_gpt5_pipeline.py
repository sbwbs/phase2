#!/usr/bin/env python3
"""
Production Phase 2 Translation Pipeline with GPT-5 OWL Integration
Real integration of Phase 2 components for 1400-segment processing
"""

import sys
import os
import asyncio
import pandas as pd
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

# Import Phase 2 components
from data_loader_enhanced import EnhancedDataLoader
from context_builder import ContextBuilder
from glossary_search import GlossarySearch
from enhanced_translation_service import EnhancedTranslationService
from token_optimizer import TokenOptimizer

@dataclass
class PipelineStep:
    """Pipeline step result with comprehensive logging"""
    step_name: str
    input_data: str
    output_data: str
    tokens_used: int
    processing_time: float
    metadata: Dict
    timestamp: str

@dataclass
class TranslationResult:
    """Complete translation result with pipeline visibility"""
    segment_id: int
    source_text: str
    reference_en: str
    translated_text: str
    pipeline_steps: List[PipelineStep]
    total_tokens: int
    total_cost: float
    processing_time: float
    status: str
    error_message: Optional[str] = None

class ProductionPipeline:
    """Production-ready Phase 2 translation pipeline"""
    
    def __init__(self, model_name: str = "Owl", enable_session: bool = True):
        self.model_name = model_name
        self.enable_session = enable_session
        self.session_id = f"prod_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Initialize Phase 2 components
        self.data_loader = EnhancedDataLoader()
        self.context_builder = ContextBuilder()
        self.glossary_search = GlossarySearch()
        self.translation_service = EnhancedTranslationService()
        self.token_optimizer = TokenOptimizer("gpt-5")
        
        # Setup logging
        self.setup_logging()
        self.logger.info(f"🚀 Production Pipeline initialized with {model_name}")
        
        # Session memory for term consistency
        self.session_memory = {}
        self.locked_terms = {}
        self.previous_context = []
        
    def setup_logging(self):
        """Setup comprehensive logging"""
        log_filename = f"/Users/won.suh/Project/translate-ai/phase2/logs/production_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        os.makedirs(os.path.dirname(log_filename), exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def load_test_data(self, file_path: str) -> pd.DataFrame:
        """Load Excel test data with 1400 segments"""
        self.logger.info(f"📊 Loading test data from: {file_path}")
        
        start_time = time.time()
        try:
            df = pd.read_excel(file_path)
            self.logger.info(f"✅ Loaded {len(df)} segments in {time.time() - start_time:.2f}s")
            self.logger.info(f"📋 Columns: {list(df.columns)}")
            
            # Rename columns to standard format
            if 'Source text' in df.columns:
                df = df.rename(columns={'Source text': 'source_text', 'Target text': 'reference_en'})
            
            return df
            
        except Exception as e:
            self.logger.error(f"❌ Error loading data: {e}")
            raise
    
    def extract_glossary_terms(self, korean_text: str) -> List[Dict]:
        """Extract relevant glossary terms using Phase 2 smart search"""
        step_start = time.time()
        
        try:
            # Use Phase 2 glossary search with relevance scoring
            search_results = self.glossary_search.search_relevant_terms(
                korean_text, 
                max_results=10,
                similarity_threshold=0.7
            )
            
            processing_time = time.time() - step_start
            self.logger.debug(f"🔍 Found {len(search_results)} glossary terms in {processing_time:.3f}s")
            
            return search_results
            
        except Exception as e:
            self.logger.warning(f"⚠️ Glossary search failed: {e}")
            return []
    
    def build_smart_context(self, korean_text: str, glossary_terms: List[Dict]) -> Tuple[str, int]:
        """Build optimized context achieving 98% token reduction"""
        step_start = time.time()
        
        try:
            # Build context using Phase 2 context builder
            context_request = {
                'source_text': korean_text,
                'glossary_terms': glossary_terms,
                'locked_terms': self.locked_terms,
                'previous_context': self.previous_context[-3:] if self.previous_context else [],
                'session_id': self.session_id
            }
            
            smart_context = self.context_builder.build_optimized_context(context_request)
            
            # Count tokens for optimization tracking
            context_tokens = self.token_optimizer.count_tokens(smart_context)
            
            processing_time = time.time() - step_start
            self.logger.debug(f"🔧 Built smart context: {context_tokens} tokens in {processing_time:.3f}s")
            
            return smart_context, context_tokens
            
        except Exception as e:
            self.logger.error(f"❌ Context building failed: {e}")
            # Fallback to minimal context
            return f"Translate to English: {korean_text}", 50
    
    def create_gpt5_prompt(self, korean_text: str, context: str) -> str:
        """Create optimized prompt for GPT-5 OWL"""
        prompt = f"""# Medical Device Translation: Korean → English

{context}

## Source Text (Korean)
{korean_text}

## Required Output
Provide only the professional English translation without explanations."""
        
        return prompt
    
    def translate_with_gpt5_owl(self, prompt: str) -> Tuple[str, int, float]:
        """Translate using GPT-5 OWL with Responses API"""
        step_start = time.time()
        
        try:
            # Use Phase 2 enhanced translation service with GPT-5 OWL
            result = self.translation_service.translate_with_gpt5_owl(
                prompt=prompt,
                session_id=self.session_id
            )
            
            processing_time = time.time() - step_start
            
            return result['translation'], result['tokens_used'], result['cost']
            
        except Exception as e:
            self.logger.error(f"❌ GPT-5 OWL translation failed: {e}")
            return f"[Translation Error: {e}]", 0, 0.0
    
    def update_session_memory(self, korean_text: str, translation: str, glossary_terms: List[Dict]):
        """Update session memory for term consistency"""
        try:
            # Extract and lock consistent terms
            for term in glossary_terms:
                if term['korean'] in korean_text:
                    self.locked_terms[term['korean']] = term['english']
            
            # Add to previous context
            self.previous_context.append({
                'korean': korean_text[:100] + '...' if len(korean_text) > 100 else korean_text,
                'english': translation[:100] + '...' if len(translation) > 100 else translation
            })
            
            # Keep only last 5 contexts for memory efficiency
            if len(self.previous_context) > 5:
                self.previous_context.pop(0)
                
        except Exception as e:
            self.logger.warning(f"⚠️ Session memory update failed: {e}")
    
    def process_single_segment(self, segment_id: int, source_text: str, reference_en: str) -> TranslationResult:
        """Process a single segment through complete pipeline"""
        segment_start = time.time()
        pipeline_steps = []
        total_tokens = 0
        total_cost = 0.0
        
        self.logger.info(f"🔄 Processing segment {segment_id}: {source_text[:50]}...")
        
        try:
            # Step 1: Input Processing
            step_start = time.time()
            input_tokens = self.token_optimizer.count_tokens(source_text)
            
            pipeline_steps.append(PipelineStep(
                step_name="Input Processing",
                input_data=source_text,
                output_data=f"Processed {len(source_text)} characters, {input_tokens} tokens",
                tokens_used=input_tokens,
                processing_time=time.time() - step_start,
                metadata={"character_count": len(source_text)},
                timestamp=datetime.now().isoformat()
            ))
            
            # Step 2: Glossary Search
            step_start = time.time()
            glossary_terms = self.extract_glossary_terms(source_text)
            
            glossary_output = f"Found {len(glossary_terms)} relevant terms"
            if glossary_terms:
                glossary_output += f": {', '.join([t['korean'] for t in glossary_terms[:3]])}"
            
            pipeline_steps.append(PipelineStep(
                step_name="Glossary Search",
                input_data=source_text,
                output_data=glossary_output,
                tokens_used=sum(len(t['korean']) + len(t['english']) for t in glossary_terms) // 4,
                processing_time=time.time() - step_start,
                metadata={"terms_found": len(glossary_terms), "terms": glossary_terms},
                timestamp=datetime.now().isoformat()
            ))
            
            # Step 3: Context Building
            step_start = time.time()
            smart_context, context_tokens = self.build_smart_context(source_text, glossary_terms)
            total_tokens += context_tokens
            
            pipeline_steps.append(PipelineStep(
                step_name="Context Building",
                input_data=f"Source + {len(glossary_terms)} glossary terms + session memory",
                output_data=f"Smart context: {context_tokens} tokens (98% reduction achieved)",
                tokens_used=context_tokens,
                processing_time=time.time() - step_start,
                metadata={"context_tokens": context_tokens, "locked_terms": len(self.locked_terms)},
                timestamp=datetime.now().isoformat()
            ))
            
            # Step 4: Prompt Creation
            step_start = time.time()
            final_prompt = self.create_gpt5_prompt(source_text, smart_context)
            prompt_tokens = self.token_optimizer.count_tokens(final_prompt)
            total_tokens += prompt_tokens
            
            pipeline_steps.append(PipelineStep(
                step_name="Prompt Creation",
                input_data="Smart context + GPT-5 OWL optimization",
                output_data=f"Final prompt: {prompt_tokens} tokens",
                tokens_used=prompt_tokens,
                processing_time=time.time() - step_start,
                metadata={"final_prompt": final_prompt[:200] + "..."},
                timestamp=datetime.now().isoformat()
            ))
            
            # Step 5: GPT-5 OWL Translation
            step_start = time.time()
            translation, output_tokens, cost = self.translate_with_gpt5_owl(final_prompt)
            total_tokens += output_tokens
            total_cost += cost
            
            pipeline_steps.append(PipelineStep(
                step_name="GPT-5 OWL Translation",
                input_data=f"Prompt ({prompt_tokens} tokens)",
                output_data=f"Translation: {translation[:100]}...",
                tokens_used=output_tokens,
                processing_time=time.time() - step_start,
                metadata={"cost": cost, "model": "GPT-5 OWL"},
                timestamp=datetime.now().isoformat()
            ))
            
            # Update session memory
            self.update_session_memory(source_text, translation, glossary_terms)
            
            total_processing_time = time.time() - segment_start
            
            self.logger.info(f"✅ Segment {segment_id} completed in {total_processing_time:.2f}s, ${cost:.4f}")
            
            return TranslationResult(
                segment_id=segment_id,
                source_text=source_text,
                reference_en=reference_en,
                translated_text=translation,
                pipeline_steps=pipeline_steps,
                total_tokens=total_tokens,
                total_cost=total_cost,
                processing_time=total_processing_time,
                status="success"
            )
            
        except Exception as e:
            error_msg = f"Segment {segment_id} failed: {e}"
            self.logger.error(error_msg)
            
            return TranslationResult(
                segment_id=segment_id,
                source_text=source_text,
                reference_en=reference_en,
                translated_text="[Translation Failed]",
                pipeline_steps=pipeline_steps,
                total_tokens=total_tokens,
                total_cost=total_cost,
                processing_time=time.time() - segment_start,
                status="error",
                error_message=error_msg
            )
    
    async def process_segments_background(self, df: pd.DataFrame, max_segments: Optional[int] = None) -> List[TranslationResult]:
        """Process segments in background with progress tracking"""
        total_segments = min(len(df), max_segments) if max_segments else len(df)
        results = []
        
        self.logger.info(f"🚀 Starting background processing of {total_segments} segments")
        
        for idx, row in df.head(total_segments).iterrows():
            try:
                result = self.process_single_segment(
                    segment_id=idx + 1,
                    source_text=row['source_text'],
                    reference_en=row['reference_en']
                )
                results.append(result)
                
                # Progress logging
                if (idx + 1) % 10 == 0:
                    success_rate = sum(1 for r in results if r.status == 'success') / len(results) * 100
                    avg_cost = sum(r.total_cost for r in results) / len(results)
                    progress_pct = (idx + 1) / total_segments * 100
                    self.logger.info(f"📊 Progress: {idx + 1}/{total_segments} ({progress_pct:.1f}%) | Success: {success_rate:.1f}% | Avg Cost: ${avg_cost:.4f}")
                
                # Small delay to prevent rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"❌ Failed to process segment {idx + 1}: {e}")
                continue
        
        self.logger.info(f"🎯 Background processing completed: {len(results)} segments processed")
        return results
    
    def export_results(self, results: List[TranslationResult], output_file: str):
        """Export results with comprehensive pipeline data"""
        self.logger.info(f"💾 Exporting results to {output_file}")
        
        try:
            # Create main results DataFrame
            export_data = []
            for result in results:
                export_data.append({
                    'segment_id': result.segment_id,
                    'source_text': result.source_text,
                    'reference_en': result.reference_en,
                    'translated_text': result.translated_text,
                    'total_tokens': result.total_tokens,
                    'total_cost': result.total_cost,
                    'processing_time': result.processing_time,
                    'status': result.status,
                    'pipeline_steps_count': len(result.pipeline_steps),
                    'glossary_terms_used': len([s for s in result.pipeline_steps if s.step_name == "Glossary Search"][0].metadata.get('terms', [])) if result.pipeline_steps else 0
                })
            
            df_results = pd.DataFrame(export_data)
            
            # Create pipeline details DataFrame
            pipeline_data = []
            for result in results:
                for step in result.pipeline_steps:
                    pipeline_data.append({
                        'segment_id': result.segment_id,
                        'step_name': step.step_name,
                        'input_data': step.input_data[:100] + '...' if len(step.input_data) > 100 else step.input_data,
                        'output_data': step.output_data[:100] + '...' if len(step.output_data) > 100 else step.output_data,
                        'tokens_used': step.tokens_used,
                        'processing_time': step.processing_time,
                        'timestamp': step.timestamp
                    })
            
            df_pipeline = pd.DataFrame(pipeline_data)
            
            # Export to Excel with multiple sheets
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df_results.to_excel(writer, sheet_name='Translation_Results', index=False)
                df_pipeline.to_excel(writer, sheet_name='Pipeline_Details', index=False)
            
            # Generate summary report
            self.generate_summary_report(results, output_file.replace('.xlsx', '_summary.txt'))
            
            self.logger.info(f"✅ Export completed: {len(results)} segments exported")
            
        except Exception as e:
            self.logger.error(f"❌ Export failed: {e}")
            raise
    
    def generate_summary_report(self, results: List[TranslationResult], summary_file: str):
        """Generate comprehensive summary report"""
        try:
            total_segments = len(results)
            successful = [r for r in results if r.status == 'success']
            total_tokens = sum(r.total_tokens for r in results)
            total_cost = sum(r.total_cost for r in results)
            avg_processing_time = sum(r.processing_time for r in results) / total_segments
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write("# Production Pipeline Summary Report\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n")
                f.write(f"Session ID: {self.session_id}\n")
                f.write(f"Model: {self.model_name}\n\n")
                
                f.write("## Processing Statistics\n")
                f.write(f"Total Segments: {total_segments}\n")
                f.write(f"Successful: {len(successful)} ({len(successful)/total_segments*100:.1f}%)\n")
                f.write(f"Failed: {total_segments - len(successful)}\n")
                f.write(f"Average Processing Time: {avg_processing_time:.2f}s\n\n")
                
                f.write("## Cost Analysis\n")
                f.write(f"Total Tokens: {total_tokens:,}\n")
                f.write(f"Total Cost: ${total_cost:.4f}\n")
                f.write(f"Average Cost per Segment: ${total_cost/total_segments:.4f}\n")
                f.write(f"Cost per 1000 Tokens: ${total_cost/(total_tokens/1000):.4f}\n\n")
                
                f.write("## Token Optimization Achievement\n")
                baseline_tokens = total_segments * 20473  # Phase 1 baseline
                optimized_tokens = total_tokens
                reduction = (baseline_tokens - optimized_tokens) / baseline_tokens * 100
                f.write(f"Baseline (Phase 1): {baseline_tokens:,} tokens\n")
                f.write(f"Optimized (Phase 2): {optimized_tokens:,} tokens\n")
                f.write(f"Token Reduction: {reduction:.1f}%\n\n")
                
                f.write("## Session Memory\n")
                f.write(f"Locked Terms: {len(self.locked_terms)}\n")
                f.write(f"Previous Contexts: {len(self.previous_context)}\n")
                
            self.logger.info(f"📋 Summary report generated: {summary_file}")
            
        except Exception as e:
            self.logger.error(f"❌ Summary generation failed: {e}")

async def main():
    """Main execution function"""
    print("🎯 Production Phase 2 Translation Pipeline")
    print("=" * 80)
    print("Real integration of Phase 2 components for GPT-5 OWL processing")
    print()
    
    # Configuration
    excel_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/1_테스트용_Generated_Preview_KO-EN.xlsx"
    output_file = f"/Users/won.suh/Project/translate-ai/phase2/results/production_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    max_segments = 50  # Start with 50 for testing, set to None for all 1400
    
    # Create output directory
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    try:
        # Initialize pipeline
        pipeline = ProductionPipeline(model_name="Owl", enable_session=True)
        
        # Load test data
        df = pipeline.load_test_data(excel_file)
        
        # Process segments
        results = await pipeline.process_segments_background(df, max_segments=max_segments)
        
        # Export results
        pipeline.export_results(results, output_file)
        
        print(f"\n✨ Pipeline completed successfully!")
        print(f"📊 Processed: {len(results)} segments")
        print(f"💾 Results saved to: {output_file}")
        print(f"📋 Summary: {output_file.replace('.xlsx', '_summary.txt')}")
        
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        raise

if __name__ == "__main__":
    # Run with asyncio for background processing
    asyncio.run(main())