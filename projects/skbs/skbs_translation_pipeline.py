#!/usr/bin/env python3
"""
SKBS Clinical Consent Form Translation Pipeline
Korean → English translation for SK Bioscience NBP608_004 varicella vaccine trial

Supports two form types:
- Adult Consent Form (ICF_FORMAL) - 673 segments
- Children's Assent Form (ICF_CHILD_FRIENDLY) - 89 segments, ages 7-12

Usage:
    python skbs_translation_pipeline.py --form adult [--test N]
    python skbs_translation_pipeline.py --form child [--test N]
"""

import os
import sys
import argparse
import logging
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import time

# Add to path
sys.path.insert(0, os.path.dirname(__file__))

from production_pipeline_ko_en_improved import ImprovedKOENPipeline
from loaders.skbs_excel_loader import SKBSExcelHandler
from loaders.tmx_memory_loader import TMXMemoryLoader
from style_guide_config import StyleGuideVariant, StyleGuideManager


class SKBSTranslationPipeline:
    """SKBS Clinical Consent Form Translation Pipeline"""

    # File paths
    ADULT_FILE = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Bilingual/별첨 1-1) NBP608_004_시험대상자설명서 및 서면 동의서_V1.0.xlsx"
    CHILD_FILE = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Bilingual/별첨 1-3) NBP608_004_소아용 연구참여 승낙서_V1.0.xlsx"
    TM_FILE = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/TM&TB/SK Bioscience_TM_KOKR-ENUS.tmx"
    OUTPUT_DIR = "/Users/won.suh/Downloads/SKBS_KO-EN (1)/Output"

    def __init__(self, form_type: str = "adult", test_limit: Optional[int] = None):
        """
        Initialize pipeline

        Args:
            form_type: "adult" or "child"
            test_limit: Limit number of segments for testing (None = all)
        """
        self.form_type = form_type.lower()
        self.test_limit = test_limit
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        # Select input file and style variant based on form type
        if self.form_type == "adult":
            self.input_file = self.ADULT_FILE
            self.style_variant = StyleGuideVariant.ICF_FORMAL
            self.form_description = "Adult/Guardian Consent Form"
        elif self.form_type == "child":
            self.input_file = self.CHILD_FILE
            self.style_variant = StyleGuideVariant.ICF_CHILD_FRIENDLY
            self.form_description = "Children's Assent Form (ages 7-12)"
        else:
            raise ValueError(f"Invalid form_type: {form_type}. Must be 'adult' or 'child'")

        # Validate files exist
        if not os.path.exists(self.input_file):
            raise FileNotFoundError(f"Input file not found: {self.input_file}")
        if not os.path.exists(self.TM_FILE):
            raise FileNotFoundError(f"TM file not found: {self.TM_FILE}")

    def setup_logging(self):
        """Setup logging"""
        log_dir = "/Users/won.suh/Project/translate-ai/phase2/logs"
        os.makedirs(log_dir, exist_ok=True)

        log_file = f"{log_dir}/skbs_pipeline_{self.form_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
        self.logger.info(f"🚀 SKBS Translation Pipeline - {self.form_description}")
        self.logger.info(f"   Form Type: {self.form_type}")
        self.logger.info(f"   Style Variant: {self.style_variant.value}")
        self.logger.info(f"   Test Limit: {self.test_limit if self.test_limit else 'ALL segments'}")
        self.logger.info("=" * 100)

        try:
            # Step 1: Load segments for translation
            self.logger.info("\n📂 STEP 1: Loading segments for translation...")
            segments_df = self._load_segments()

            if segments_df is None or len(segments_df) == 0:
                self.logger.error("❌ No segments loaded. Exiting.")
                return

            # Step 2: Initialize pipeline with SKBS TM
            self.logger.info("\n🔧 STEP 2: Initializing translation pipeline...")
            pipeline = self._initialize_pipeline()

            # Step 3: Process translations
            self.logger.info("\n🔄 STEP 3: Processing translations...")
            translations, processing_stats = self._process_translations(pipeline, segments_df)

            # Step 4: Save results
            self.logger.info("\n💾 STEP 4: Saving translated segments...")
            output_file = self._save_results(translations)

            # Step 5: Generate reports
            self.logger.info("\n📊 STEP 5: Generating reports...")
            self._generate_reports(pipeline, translations, processing_stats)

            self.logger.info("\n✅ Translation pipeline completed successfully!")
            self.logger.info(f"📄 Output file: {output_file}")
            self.logger.info("=" * 100)

            return output_file

        except Exception as e:
            self.logger.error(f"❌ Fatal error in pipeline: {e}", exc_info=True)
            raise

    def _load_segments(self) -> Optional[pd.DataFrame]:
        """Load segments from Excel file"""
        try:
            self.io_handler = SKBSExcelHandler()
            segments_df = self.io_handler.load_segments_for_translation(
                self.input_file,
                limit=self.test_limit
            )

            self.logger.info(f"✅ Loaded {len(segments_df)} segments for translation")

            # Log statistics
            stats = self.io_handler.get_segment_statistics(segments_df)
            self.logger.info(f"  Average source length: {stats['average_source_length']:.0f} chars")
            self.logger.info(f"  Max source length: {stats['max_source_length']} chars")
            self.logger.info(f"  Min source length: {stats['min_source_length']} chars")
            if 'segments_with_tags' in stats:
                self.logger.info(f"  Segments with CAT tags: {stats['segments_with_tags']}")

            return segments_df

        except Exception as e:
            self.logger.error(f"❌ Error loading segments: {e}", exc_info=True)
            return None

    def _initialize_pipeline(self) -> ImprovedKOENPipeline:
        """Initialize translation pipeline with SKBS TM"""
        # Get style guide content
        style_manager = StyleGuideManager()
        style_guide_content = style_manager.get_style_guide(self.style_variant)

        self.logger.info(f"📝 Style guide: {self.style_variant.value}")
        self.logger.info(f"   Token estimate: ~{len(style_guide_content) // 4} tokens")

        # Initialize pipeline
        pipeline = ImprovedKOENPipeline(
            model_name="Owl",  # GPT-5 OWL
            use_valkey=True,  # Enable Valkey for term consistency
            batch_size=50,  # Batch size for processing
            use_enhanced_prompts=True,  # Use style guide
            tmx_memory_path=self.TM_FILE,  # SKBS Translation Memory (18,562 units)
            project_id="skbs"  # Use project-scoped Qdrant collections
        )

        # Store style guide for use in prompts
        pipeline.style_guide_content = style_guide_content
        pipeline.style_variant = self.style_variant

        # Initialize Valkey session
        session_id = f"skbs_{self.form_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        pipeline.session_metadata.doc_id = session_id
        if pipeline.use_valkey:
            pipeline.memory.initialize_session(pipeline.session_metadata)
            self.logger.info(f"✅ Valkey session initialized: {session_id}")

        # Log TM loading
        if pipeline.tm_loader:
            self.logger.info(f"✅ TM loaded: {len(pipeline.tm_loader.translation_units)} translation units")
        else:
            self.logger.warning("⚠️ TM not loaded - using fallback")

        return pipeline

    def _process_translations(self, pipeline: ImprovedKOENPipeline,
                            segments_df: pd.DataFrame) -> tuple:
        """Process translations for all segments"""
        translations = []
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

                # Translate the segment
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
                processing_stats['total_tokens'] += result.get('input_tokens', 0) + result.get('output_tokens', 0)

                # Progress logging
                if (idx + 1) % 10 == 0 or (idx + 1) == len(segments_df):
                    elapsed = time.time() - start_time
                    rate = (idx + 1) / elapsed if elapsed > 0 else 0
                    eta = (len(segments_df) - idx - 1) / rate if rate > 0 else 0
                    self.logger.info(
                        f"  ✓ Processed {idx + 1}/{len(segments_df)} segments "
                        f"({(idx + 1) / len(segments_df) * 100:.1f}%) "
                        f"- ETA: {eta:.0f}s"
                    )

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
        Translate a single segment using the pipeline
        """
        try:
            segment_id_str = str(segment_id)

            # Build context with glossary and TM
            context, token_count, mandatory_violations = pipeline.build_ko_en_strict_context(korean_text)

            # Inject style guide into context
            if hasattr(pipeline, 'style_guide_content') and pipeline.style_guide_content:
                context = pipeline.style_guide_content + "\n\n" + context

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

            # Post-process to clean up artifacts
            clean_translation = pipeline.post_process_translation_strict(translation, korean_text)

            return {
                'translation': clean_translation.strip(),
                'glossary_terms_count': glossary_terms_count,
                'tm_matches_count': tm_matches_count,
                'qa_issues_count': len(qa_issues),
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
            }

        except Exception as e:
            self.logger.error(f"Translation error for segment {segment_id}: {e}")
            raise

    def _save_results(self, translations: List[Dict]) -> str:
        """Save translated segments to Excel"""
        try:
            # Ensure output directory exists
            os.makedirs(self.OUTPUT_DIR, exist_ok=True)

            # Generate output filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            form_name = "adult_consent" if self.form_type == "adult" else "child_assent"
            output_file = os.path.join(
                self.OUTPUT_DIR,
                f"SKBS_{form_name}_translated_{timestamp}.xlsx"
            )

            # Convert to DataFrame and save
            translations_df = pd.DataFrame(translations)
            self.io_handler.save_translated_segments(translations_df, output_file)

            self.logger.info(f"✅ Saved {len(translations_df)} segments to: {output_file}")

            return output_file

        except Exception as e:
            self.logger.error(f"❌ Error saving results: {e}", exc_info=True)
            raise

    def _generate_reports(self, pipeline: ImprovedKOENPipeline, translations: List[Dict],
                         stats: Dict):
        """Generate comprehensive reports"""
        try:
            self.logger.info(f"\n📋 Translation Summary ({self.form_description}):")
            self.logger.info(f"  Total segments: {stats['total_segments']}")
            self.logger.info(f"  Successfully translated: {stats['successful']}")
            self.logger.info(f"  Failed: {stats['failed']}")
            self.logger.info(f"  Total glossary term matches: {stats['glossary_matches_total']}")
            self.logger.info(f"  Total TM matches found: {stats['tm_matches_total']}")
            self.logger.info(f"  Total QA issues detected: {stats['qa_issues_total']}")
            self.logger.info(f"  Total tokens used: {stats['total_tokens']}")

            self.logger.info(f"\n⚡ Performance Metrics:")
            self.logger.info(f"  Total processing time: {stats['total_time']:.1f}s")
            if stats['total_segments'] > 0:
                self.logger.info(f"  Average time per segment: {stats['total_time'] / stats['total_segments']:.2f}s")

            # Estimate cost (GPT-5 OWL pricing approximation)
            input_cost = stats['total_tokens'] * 0.000002  # Example rate
            self.logger.info(f"\n💰 Estimated Cost: ~${input_cost:.4f}")

            # Valkey session summary
            if pipeline.use_valkey and pipeline.memory:
                try:
                    valkey_summary = pipeline.memory.get_session_summary(pipeline.session_metadata.doc_id)
                    self.logger.info(f"\n🔒 Valkey Session Summary:")
                    self.logger.info(f"  Session ID: {valkey_summary.get('session_id', 'N/A')}")
                    self.logger.info(f"  Total term mappings: {valkey_summary.get('total_term_mappings', 0)}")
                except Exception as e:
                    self.logger.debug(f"Could not get Valkey summary: {e}")

        except Exception as e:
            self.logger.error(f"❌ Error generating reports: {e}")


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description="SKBS Clinical Consent Form Translation Pipeline (KO→EN)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python skbs_translation_pipeline.py --form adult          # Translate all adult consent segments
  python skbs_translation_pipeline.py --form child          # Translate all children's assent segments
  python skbs_translation_pipeline.py --form adult --test 5 # Test with 5 adult segments
  python skbs_translation_pipeline.py --form child --test 3 # Test with 3 children's segments
        """
    )

    parser.add_argument(
        "--form", "-f",
        type=str,
        required=True,
        choices=["adult", "child"],
        help="Form type: 'adult' (consent form) or 'child' (assent form for ages 7-12)"
    )

    parser.add_argument(
        "--test", "-t",
        type=int,
        default=None,
        help="Limit number of segments for testing (default: all segments)"
    )

    args = parser.parse_args()

    # Run pipeline
    pipeline = SKBSTranslationPipeline(
        form_type=args.form,
        test_limit=args.test
    )

    output_file = pipeline.run()

    if output_file:
        print(f"\n✅ Translation complete! Output: {output_file}")
    else:
        print("\n❌ Translation failed. Check logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
