#!/usr/bin/env python3
"""
GreenCross IMMUNCELL-LC Investigator's Brochure Translation Pipeline
Korean → English with TM/Glossary Integration and Valkey Memory

Comprehensive translation system with:
- GreenCross glossary (789 terms, Priority 1)
- Translation Memory (75,369 TUs with fuzzy matching)
- Valkey auto-locking for term consistency
- REGULATORY_COMPLIANCE_ENHANCED prompts (customer feedback rules + golden examples)
"""

import os
import sys
import logging
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import time

# Add to path
sys.path.insert(0, os.path.dirname(__file__))

from production_pipeline_ko_en_improved import ImprovedKOENPipeline
from greencross_io_handler import GreenCrossExcelHandler


class GreenCrossTranslationPipeline:
    """Main execution script for GreenCross Cell IMMUNCELL-LC translation"""

    def __init__(self, test_limit: Optional[int] = None):
        """
        Initialize pipeline

        Args:
            test_limit: Limit number of segments for testing (None = all)
        """
        self.test_limit = test_limit
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

    def setup_logging(self):
        """Setup logging"""
        log_dir = "/Users/won.suh/Project/translate-ai/phase2/logs"
        os.makedirs(log_dir, exist_ok=True)

        log_file = f"{log_dir}/greencross_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def run(self):
        """Execute full translation pipeline"""
        self.logger.info("=" * 100)
        self.logger.info("🚀 GreenCross IMMUNCELL-LC Translation Pipeline")
        self.logger.info("=" * 100)

        # Configuration
        INPUT_FILE = "/Users/won.suh/Downloads/Bilingual files/[GC Cell] IMMUNCELL-LC_IB_v5.0 국문.docx.review.xlsx"
        GLOSSARY_FILE = "/Users/won.suh/Downloads/linguistic_asset/Glossary_GreenCross_KOKR-ENUS_2025-10-30.xlsx"
        TM_FILE = "/Users/won.suh/Downloads/linguistic_asset/GreenCross_KOKR-ENUS.tmx"

        try:
            # Step 1: Load segments for translation
            self.logger.info("\n📂 STEP 1: Loading segments for translation...")
            segments_df = self._load_segments(INPUT_FILE)

            if segments_df is None or len(segments_df) == 0:
                self.logger.error("❌ No segments loaded. Exiting.")
                return

            # Step 2: Initialize pipeline with GreenCross resources
            self.logger.info("\n🔧 STEP 2: Initializing translation pipeline...")
            pipeline = self._initialize_pipeline(GLOSSARY_FILE, TM_FILE)

            # Step 3: Process translations
            self.logger.info("\n🔄 STEP 3: Processing translations...")
            translations, processing_stats = self._process_translations(pipeline, segments_df)

            # Step 4: Save results
            self.logger.info("\n💾 STEP 4: Saving translated segments...")
            output_file = self._save_results(INPUT_FILE, translations)

            # Step 5: Generate reports
            self.logger.info("\n📊 STEP 5: Generating reports...")
            self._generate_reports(pipeline, translations, processing_stats)

            self.logger.info("\n✅ Translation pipeline completed successfully!")
            self.logger.info("=" * 100)

        except Exception as e:
            self.logger.error(f"❌ Fatal error in pipeline: {e}", exc_info=True)
            return

    def _load_segments(self, input_file: str) -> Optional[pd.DataFrame]:
        """Load segments from Excel file"""
        try:
            io_handler = GreenCrossExcelHandler()
            segments_df = io_handler.load_segments_for_translation(input_file, limit=self.test_limit)

            self.logger.info(f"✅ Loaded {len(segments_df)} segments for translation")

            # Log statistics
            stats = io_handler.get_segment_statistics(segments_df)
            self.logger.info(f"  Average source length: {stats['average_source_length']:.0f} chars")
            self.logger.info(f"  Max source length: {stats['max_source_length']} chars")
            self.logger.info(f"  Min source length: {stats['min_source_length']} chars")

            return segments_df

        except Exception as e:
            self.logger.error(f"❌ Error loading segments: {e}", exc_info=True)
            return None

    def _initialize_pipeline(self, glossary_file: str, tm_file: str) -> ImprovedKOENPipeline:
        """Initialize translation pipeline with GreenCross resources"""
        pipeline = ImprovedKOENPipeline(
            model_name="Owl",  # GPT-5 OWL
            use_valkey=True,  # Enable Valkey for term consistency
            batch_size=50,  # Batch size for processing
            use_enhanced_prompts=True,  # REGULATORY_COMPLIANCE_ENHANCED (customer feedback + examples)
            greencross_glossary_path=glossary_file,  # GreenCross glossary
            tmx_memory_path=tm_file,  # Translation Memory
            project_id="greencross"  # Use project-scoped Qdrant collections
        )

        # Initialize Valkey session
        pipeline.session_metadata.doc_id = f"greencross_immuncell_ib_v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if pipeline.use_valkey:
            pipeline.memory.initialize_session(pipeline.session_metadata)
            self.logger.info(f"✅ Valkey session initialized: {pipeline.session_metadata.doc_id}")

        return pipeline

    def _process_translations(self, pipeline: ImprovedKOENPipeline,
                            segments_df: pd.DataFrame) -> tuple:
        """Process translations for all segments"""
        translations = []
        self.original_df = segments_df.copy()  # Store original for later merging
        processing_stats = {
            'total_segments': len(segments_df),
            'successful': 0,
            'failed': 0,
            'total_time': 0,
            'total_tokens': 0,
            'glossary_matches_total': 0,
            'tm_matches_total': 0,
            'qa_issues_total': 0
        }

        start_time = time.time()

        for idx, row in segments_df.iterrows():
            try:
                segment_id = row['Segment ID']
                source_korean = row['Source segment']

                # Call the translate method (this needs to exist in pipeline)
                # For now, we'll create a placeholder
                result = self._translate_segment(pipeline, source_korean, segment_id)

                translations.append({
                    'Segment ID': segment_id,
                    'Target segment': result['translation'],
                    'glossary_terms_used': result.get('glossary_terms_count', 0),
                    'tm_matches_found': result.get('tm_matches_count', 0),
                    'qa_issues': result.get('qa_issues_count', 0)
                })

                # Update statistics
                processing_stats['successful'] += 1
                processing_stats['glossary_matches_total'] += result.get('glossary_terms_count', 0)
                processing_stats['tm_matches_total'] += result.get('tm_matches_count', 0)
                processing_stats['qa_issues_total'] += result.get('qa_issues_count', 0)

                # Progress logging
                if (idx + 1) % 10 == 0:
                    self.logger.info(f"  ✓ Processed {idx + 1}/{len(segments_df)} segments...")

            except Exception as e:
                self.logger.error(f"  ❌ Error processing segment {idx}: {e}")
                processing_stats['failed'] += 1
                translations.append({
                    'Segment ID': row['Segment ID'],
                    'Target segment': f"[ERROR: {str(e)[:50]}]",
                    'glossary_terms_used': 0,
                    'tm_matches_found': 0,
                    'qa_issues': 1
                })

        processing_stats['total_time'] = time.time() - start_time

        self.logger.info(f"✅ Completed {processing_stats['successful']}/{len(segments_df)} translations")
        self.logger.info(f"  Processing time: {processing_stats['total_time']:.1f}s")

        return translations, processing_stats

    def _translate_segment(self, pipeline: ImprovedKOENPipeline, korean_text: str,
                          segment_id: str) -> Dict:
        """
        Translate a single segment

        This is a simplified version - in production, would use pipeline's translate_single_segment
        """
        try:
            # Build context with glossary and TM
            segment_id_str = str(segment_id)
            context, token_count, mandatory_violations = pipeline.build_ko_en_strict_context(korean_text)

            # Create prompt
            prompt = pipeline.create_strict_ko_en_prompt(korean_text, context)

            # Translate using GPT-5 OWL
            translation, input_tokens, output_tokens, metadata = pipeline.translate_with_gpt5_owl_strict(prompt)

            # Validate translation
            qa_issues, hallucination_detected, hallucination_details = pipeline.validate_translation_strict(
                korean_text, translation, mandatory_violations
            )

            # Search for glossary and TM matches for reporting
            found_terms, _ = pipeline.search_glossary_ko_en_strict(korean_text, segment_id_str)
            glossary_terms_count = len(found_terms)

            tm_matches_count = 0
            if pipeline.tm_loader:
                tm_matches = pipeline.tm_loader.find_similar_segments(korean_text, top_k=3, threshold=0.75)
                tm_matches_count = len(tm_matches)

            return {
                'translation': translation.strip(),
                'glossary_terms_count': glossary_terms_count,
                'tm_matches_count': tm_matches_count,
                'qa_issues_count': len(qa_issues),
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            }

        except Exception as e:
            self.logger.error(f"Translation error for segment {segment_id}: {e}")
            raise

    def _save_results(self, input_file: str, translations: List[Dict]) -> str:
        """Save translated segments to Excel"""
        try:
            io_handler = GreenCrossExcelHandler()

            output_dir = os.path.dirname(input_file)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(
                output_dir,
                f"[GC Cell] IMMUNCELL-LC_IB_v5.0_translated_{timestamp}.xlsx"
            )

            translations_df = pd.DataFrame(translations)
            io_handler.save_translated_segments(translations_df, output_file, original_df=self.original_df)

            self.logger.info(f"✅ Saved {len(translations_df)} segments to: {output_file}")

            return output_file

        except Exception as e:
            self.logger.error(f"❌ Error saving results: {e}", exc_info=True)
            raise

    def _generate_reports(self, pipeline: ImprovedKOENPipeline, translations: List[Dict],
                         stats: Dict):
        """Generate comprehensive reports"""
        try:
            self.logger.info(f"\n📋 Translation Summary:")
            self.logger.info(f"  Total segments: {stats['total_segments']}")
            self.logger.info(f"  Successfully translated: {stats['successful']}")
            self.logger.info(f"  Failed: {stats['failed']}")
            self.logger.info(f"  Total glossary term matches: {stats['glossary_matches_total']}")
            self.logger.info(f"  Total TM matches found: {stats['tm_matches_total']}")
            self.logger.info(f"  Total QA issues detected: {stats['qa_issues_total']}")

            self.logger.info(f"\n⚡ Performance Metrics:")
            self.logger.info(f"  Total processing time: {stats['total_time']:.1f}s")
            self.logger.info(f"  Average time per segment: {stats['total_time'] / stats['total_segments']:.2f}s")

            # Valkey session summary
            if pipeline.use_valkey and pipeline.memory:
                try:
                    valkey_summary = pipeline.memory.get_session_summary(pipeline.session_metadata.doc_id)
                    self.logger.info(f"\n🔒 Valkey Session Summary:")
                    self.logger.info(f"  Session ID: {valkey_summary['session_id']}")
                    self.logger.info(f"  Status: {valkey_summary['status']}")
                    self.logger.info(f"  Total term mappings: {valkey_summary['total_term_mappings']}")
                    self.logger.info(f"  Locked terms count: {valkey_summary['locked_terms_count']}")
                    self.logger.info(f"  Unlocked terms count: {valkey_summary['unlocked_terms_count']}")

                    if valkey_summary['locked_terms']:
                        self.logger.info(f"\n  Sample locked terms (first 5):")
                        for term in valkey_summary['locked_terms'][:5]:
                            self.logger.info(f"    - {term['source']} → {term['target']}")

                except Exception as e:
                    self.logger.warning(f"Could not retrieve Valkey summary: {e}")

        except Exception as e:
            self.logger.error(f"Error generating reports: {e}")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="GreenCross Translation Pipeline")
    parser.add_argument(
        "--test",
        type=int,
        default=None,
        help="Test mode: limit to N segments (default: None = all)"
    )

    args = parser.parse_args()

    pipeline = GreenCrossTranslationPipeline(test_limit=args.test)
    pipeline.run()


if __name__ == "__main__":
    main()
