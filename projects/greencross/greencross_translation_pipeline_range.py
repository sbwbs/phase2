#!/usr/bin/env python3
"""
GreenCross Translation Pipeline - Range-Based Version
Translates a specific range of segments (used for parallel processing)

Usage:
    python greencross_translation_pipeline_range.py start_idx end_idx

Example:
    python greencross_translation_pipeline_range.py 0 500      # Segments 0-499
    python greencross_translation_pipeline_range.py 500 1000   # Segments 500-999
"""

import os
import sys
import logging
import pandas as pd
from datetime import datetime
from typing import Optional
import time

sys.path.insert(0, os.path.dirname(__file__))

from production_pipeline_ko_en_improved import ImprovedKOENPipeline
from greencross_io_handler import GreenCrossExcelHandler


class GreenCrossRangeTranslationPipeline:
    """Translation pipeline for a specific range of segments"""

    def __init__(self, start_idx: int, end_idx: int, test_limit: Optional[int] = None):
        self.start_idx = start_idx
        self.end_idx = end_idx
        self.test_limit = test_limit
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

    def setup_logging(self):
        """Setup logging with DEBUG level for detailed tracking"""
        log_dir = "/Users/won.suh/Project/translate-ai/phase2/logs"
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f"{log_dir}/greencross_range_{self.start_idx}_{self.end_idx}_{timestamp}.log"

        # Create logger
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)  # Capture DEBUG and above

        # File handler with DEBUG level
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

        # Console handler with INFO level only (less verbose on screen)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        ))

        # Remove existing handlers to avoid duplication
        logger.handlers = []
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # Also log to unified dashboard file
        dashboard_file = f"{log_dir}/UNIFIED_DASHBOARD_{timestamp}.log"
        dashboard_handler = logging.FileHandler(dashboard_file)
        dashboard_handler.setLevel(logging.INFO)
        dashboard_formatter = logging.Formatter(
            f'[RANGE {self.start_idx}-{self.end_idx}] %(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        dashboard_handler.setFormatter(dashboard_formatter)
        logger.addHandler(dashboard_handler)

        self.log_file = log_file
        self.logger = logger

    def run(self):
        """Execute translation pipeline for range"""
        self.logger.info("=" * 100)
        self.logger.info(f"🚀 GreenCross IMMUNCELL-LC Translation Pipeline (Segments {self.start_idx}-{self.end_idx})")
        self.logger.info("=" * 100)

        INPUT_FILE = "/Users/won.suh/Downloads/Bilingual files/[GC Cell] IMMUNCELL-LC_IB_v5.0 국문.docx.review.xlsx"
        GLOSSARY_FILE = "/Users/won.suh/Downloads/linguistic_asset/Glossary_GreenCross_KOKR-ENUS_2025-10-30.xlsx"
        TM_FILE = "/Users/won.suh/Downloads/linguistic_asset/GreenCross_KOKR-ENUS.tmx"

        try:
            # Step 1: Load all segments (we'll filter by range)
            self.logger.info(f"\n📂 STEP 1: Loading segments {self.start_idx}-{self.end_idx}...")
            segments_df = self._load_segments_range(INPUT_FILE)

            if segments_df is None or len(segments_df) == 0:
                self.logger.error("❌ No segments loaded. Exiting.")
                return

            # Step 2: Initialize pipeline
            self.logger.info(f"\n🔧 STEP 2: Initializing translation pipeline...")
            pipeline = self._initialize_pipeline(GLOSSARY_FILE, TM_FILE)

            # Step 3: Process translations for range
            self.logger.info(f"\n🔄 STEP 3: Processing translations...")
            translations, processing_stats = self._process_translations(pipeline, segments_df)

            # Step 4: Save results
            self.logger.info(f"\n💾 STEP 4: Saving translated segments...")
            output_file = self._save_results(INPUT_FILE, translations, segments_df)

            # Step 5: Generate reports
            self.logger.info(f"\n📊 STEP 5: Generating reports...")
            self._generate_reports(pipeline, translations, processing_stats)

            self.logger.info(f"\n✅ Range translation completed successfully!")
            self.logger.info("=" * 100)

        except Exception as e:
            self.logger.error(f"❌ Fatal error in pipeline: {e}", exc_info=True)
            sys.exit(1)

    def _load_segments_range(self, input_file: str) -> Optional[pd.DataFrame]:
        """Load segments for specific range"""
        try:
            io_handler = GreenCrossExcelHandler()
            segments_df = io_handler.load_segments_for_translation(input_file, limit=None)

            # Filter by range
            segments_df = segments_df[self.start_idx:self.end_idx].reset_index(drop=True)

            self.logger.info(f"✅ Loaded {len(segments_df)} segments from range {self.start_idx}-{self.end_idx}")

            return segments_df

        except Exception as e:
            self.logger.error(f"❌ Error loading segments: {e}", exc_info=True)
            return None

    def _initialize_pipeline(self, glossary_file: str, tm_file: str) -> ImprovedKOENPipeline:
        """Initialize pipeline"""
        pipeline = ImprovedKOENPipeline(
            model_name="Owl",
            use_valkey=True,
            batch_size=50,
            use_enhanced_prompts=True,
            greencross_glossary_path=glossary_file,
            tmx_memory_path=tm_file
        )

        pipeline.session_metadata.doc_id = f"greencross_range_{self.start_idx}_{self.end_idx}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if pipeline.use_valkey:
            pipeline.memory.initialize_session(pipeline.session_metadata)
            self.logger.info(f"✅ Valkey session initialized: {pipeline.session_metadata.doc_id}")

        return pipeline

    def _process_translations(self, pipeline: ImprovedKOENPipeline, segments_df: pd.DataFrame) -> tuple:
        """Process translations with detailed logging"""
        translations = []
        self.original_df = segments_df.copy()
        processing_stats = {
            'total_segments': len(segments_df),
            'successful': 0,
            'failed': 0,
            'total_time': 0,
            'glossary_matches_total': 0,
            'tm_matches_total': 0,
            'qa_issues_total': 0,
            'api_calls': 0,
            'total_tokens_used': 0
        }

        start_time = time.time()
        self.logger.info(f"🔄 Starting translation of {len(segments_df)} segments...")

        for idx, row in segments_df.iterrows():
            try:
                segment_id = row['Segment ID']
                source_korean = row['Source segment']

                # Log segment start
                self.logger.debug(f"📍 Segment {segment_id}: Processing korean text ({len(source_korean)} chars)")
                self.logger.debug(f"   Korean: {source_korean[:100]}")

                result = self._translate_segment(pipeline, source_korean, segment_id)

                # Log detailed results
                glossary_count = result.get('glossary_terms_count', 0)
                tm_count = result.get('tm_matches_count', 0)
                qa_count = result.get('qa_issues_count', 0)
                tokens = result.get('tokens_used', 0)

                self.logger.debug(f"   ✅ Translation: {result['translation'][:100]}")
                if glossary_count > 0:
                    self.logger.debug(f"   📚 Glossary matches: {glossary_count}")
                if tm_count > 0:
                    self.logger.debug(f"   📖 TM matches: {tm_count}")
                if qa_count > 0:
                    self.logger.debug(f"   ⚠️  QA issues: {qa_count}")
                if tokens > 0:
                    self.logger.debug(f"   🔌 Tokens: {tokens}")

                translations.append({
                    'Segment ID': segment_id,
                    'Target segment': result['translation'],
                    'glossary_terms_used': glossary_count,
                    'tm_matches_found': tm_count,
                    'qa_issues': qa_count
                })

                processing_stats['successful'] += 1
                processing_stats['glossary_matches_total'] += glossary_count
                processing_stats['tm_matches_total'] += tm_count
                processing_stats['qa_issues_total'] += qa_count
                processing_stats['api_calls'] += 1
                processing_stats['total_tokens_used'] += tokens

                # Progress logging every 10 segments
                if (idx + 1) % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = elapsed / (idx + 1)
                    remaining = rate * (len(segments_df) - (idx + 1))
                    self.logger.info(f"  ✓ Progress: {idx + 1}/{len(segments_df)} segments ({(idx+1)*100//len(segments_df)}%)")
                    self.logger.info(f"    Elapsed: {elapsed:.1f}s | Rate: {rate:.1f}s/seg | ETA: {remaining/60:.1f}min")
                    self.logger.info(f"    Glossary matches: {processing_stats['glossary_matches_total']} | TM matches: {processing_stats['tm_matches_total']} | QA issues: {processing_stats['qa_issues_total']}")

            except Exception as e:
                self.logger.error(f"  ❌ Error processing segment {row['Segment ID']}: {str(e)}", exc_info=True)
                processing_stats['failed'] += 1
                translations.append({
                    'Segment ID': row['Segment ID'],
                    'Target segment': f"[ERROR]",
                    'glossary_terms_used': 0,
                    'tm_matches_found': 0,
                    'qa_issues': 1
                })

        processing_stats['total_time'] = time.time() - start_time

        self.logger.info(f"\n✅ Completed {processing_stats['successful']}/{len(segments_df)} translations")
        self.logger.info(f"  Processing time: {processing_stats['total_time']:.1f}s ({processing_stats['total_time']/60:.1f} min)")
        self.logger.info(f"  API calls: {processing_stats['api_calls']}")
        self.logger.info(f"  Total tokens: {processing_stats['total_tokens_used']}")
        self.logger.info(f"  Glossary matches: {processing_stats['glossary_matches_total']}")
        self.logger.info(f"  TM matches: {processing_stats['tm_matches_total']}")
        self.logger.info(f"  QA issues: {processing_stats['qa_issues_total']}")

        return translations, processing_stats

    def _translate_segment(self, pipeline: ImprovedKOENPipeline, korean_text: str, segment_id: str) -> dict:
        """Translate single segment"""
        try:
            segment_id_str = str(segment_id)
            context, token_count, mandatory_violations = pipeline.build_ko_en_strict_context(korean_text)
            prompt = pipeline.create_strict_ko_en_prompt(korean_text, context)
            translation, input_tokens, output_tokens, metadata = pipeline.translate_with_gpt5_owl_strict(prompt)
            qa_issues, hallucination_detected, hallucination_details = pipeline.validate_translation_strict(
                korean_text, translation, mandatory_violations
            )

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
            }

        except Exception as e:
            self.logger.error(f"Translation error for segment {segment_id}: {e}")
            raise

    def _save_results(self, input_file: str, translations: list, segments_df: pd.DataFrame) -> str:
        """Save results"""
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

    def _generate_reports(self, pipeline: ImprovedKOENPipeline, translations: list, stats: dict):
        """Generate reports"""
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

        except Exception as e:
            self.logger.error(f"Error generating reports: {e}")


def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print("Usage: python greencross_translation_pipeline_range.py start_idx end_idx")
        print("Example: python greencross_translation_pipeline_range.py 0 500")
        sys.exit(1)

    try:
        start_idx = int(sys.argv[1])
        end_idx = int(sys.argv[2])
    except ValueError:
        print("Error: start_idx and end_idx must be integers")
        sys.exit(1)

    pipeline = GreenCrossRangeTranslationPipeline(start_idx, end_idx)
    pipeline.run()


if __name__ == "__main__":
    main()
