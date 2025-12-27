#!/usr/bin/env python3
"""
Protocol Translation Pipeline EN-KO - Only Not Translated Segments
Translates only segments marked as "Not Translated (0%)" with empty target
"""

import os
import sys
import pandas as pd
import logging
import time
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from loaders.tmx_memory_loader_en_ko import TMXMemoryLoaderENKO
from loaders.protocol_glossary_loader_en_ko import ProtocolGlossaryLoaderENKO
from production_pipeline_en_ko_improved import ImprovedENKOPipeline


class ProtocolTranslationPipelineNotTranslated:
    """Pipeline for translating only Not Translated segments"""

    def __init__(self, test_limit: Optional[int] = None, use_enhanced_prompts: bool = True):
        self.test_limit = test_limit
        self.use_enhanced_prompts = use_enhanced_prompts
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        self.logger.info("🚀 Initializing Protocol EN-KO Translation Pipeline (Not Translated Only)...")
        self.logger.info(f"  Test mode: {'ON (' + str(test_limit) + ' segments)' if test_limit else 'OFF'}")
        self.logger.info(f"  Enhanced prompts: {use_enhanced_prompts}")

    def setup_logging(self):
        """Setup logging"""
        log_dir = "/Users/won.suh/Project/translate-ai/phase2/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = f"{log_dir}/protocol_en_ko_not_translated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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
        self.logger.info("📋 Protocol EN-KO Translation Pipeline - Not Translated Segments Only")
        self.logger.info("=" * 100)

        try:
            # Step 1: Load segments
            self.logger.info("\n📂 STEP 1: Loading Not Translated segments from Excel...")
            segments_df, all_df = self._load_not_translated_segments()

            if segments_df is None or len(segments_df) == 0:
                self.logger.error("❌ No Not Translated segments found. Exiting.")
                return

            # Step 2: Initialize pipeline
            self.logger.info("\n🔧 STEP 2: Initializing translation pipeline with TM/Glossary...")
            pipeline = self._initialize_pipeline()

            # Step 3: Process translations
            self.logger.info("\n🔄 STEP 3: Processing translations...")
            translations, stats = self._process_translations(pipeline, segments_df)

            # Step 4: Merge back to original
            self.logger.info("\n💾 STEP 4: Merging translations back to original file...")
            output_file = self._merge_and_save(all_df, translations)

            # Step 5: Generate reports
            self.logger.info("\n📊 STEP 5: Generating reports...")
            self._generate_reports(stats, output_file)

            self.logger.info("\n✅ Translation pipeline completed successfully!")
            self.logger.info("=" * 100)

        except Exception as e:
            self.logger.error(f"❌ Pipeline error: {e}", exc_info=True)

    def _load_not_translated_segments(self):
        """Load only Not Translated segments (where Target == Source or empty)"""
        try:
            input_file = "/Users/won.suh/Downloads/83-0060-0002_Protocol v.2.0_28Nov2025.docx.review (1).xlsx"

            all_df = pd.read_excel(input_file)
            self.logger.info(f"✅ Loaded all segments from: {input_file}")
            self.logger.info(f"   Total rows: {len(all_df)}")

            # Filter for Not Translated segments where source has content
            # (target is either empty, same as source, or just whitespace)
            mask = (
                (all_df['Segment status'] == 'Not Translated (0%)') &
                (all_df['Source segment'].astype(str).str.strip() != '')
            )
            not_translated_df = all_df[mask].copy().reset_index(drop=True)

            self.logger.info(f"   Not Translated segments: {len(not_translated_df)}")

            # Apply test limit if specified
            if self.test_limit and len(not_translated_df) > self.test_limit:
                not_translated_df = not_translated_df.iloc[:self.test_limit].copy()
                self.logger.info(f"   Test mode: Limited to {self.test_limit} segments")

            return not_translated_df, all_df

        except Exception as e:
            self.logger.error(f"❌ Error loading segments: {e}")
            return None, None

    def _initialize_pipeline(self):
        """Initialize pipeline with resources"""
        try:
            # Load TMX
            self.logger.info("  Loading Translation Memory...")
            tmx_files = [
                "/Users/won.suh/Downloads/linguistic asset/AVK_83-0060-002_Protocol v1.2_EN-KO.tmx",
                "/Users/won.suh/Downloads/linguistic asset/Avance Clinical CRO_ENUS-KOKR.tmx"
            ]

            tmx_loader = None
            if all(os.path.exists(f) for f in tmx_files):
                try:
                    tmx_loader = TMXMemoryLoaderENKO(tmx_files)
                    self.logger.info(f"  ✅ TMX loader ready: {len(tmx_loader.translation_units)} pairs")
                except Exception as e:
                    self.logger.warning(f"  ⚠️  TMX loading skipped: {str(e)[:100]}")

            # Load glossary
            self.logger.info("  Loading glossary...")
            glossary_loader = None
            protocol_glossary_file = "/Users/won.suh/Downloads/linguistic asset/Avance Clinical CRO_ZE46-0134-0002_EN-KO_Glossary_2025-06-10.xlsx"
            if os.path.exists(protocol_glossary_file):
                try:
                    glossary_loader = ProtocolGlossaryLoaderENKO()
                    glossary_loader.load_protocol_glossary(protocol_glossary_file)
                    glossary_loader.load_combined_glossary()
                    glossary_loader.merge_glossaries()
                    self.logger.info(f"  ✅ Glossary loader ready")
                except Exception as e:
                    self.logger.warning(f"  ⚠️  Glossary loading skipped: {str(e)[:100]}")

            # Initialize pipeline
            pipeline = ImprovedENKOPipeline(
                model_name="Owl",
                use_valkey=True,
                batch_size=50,
                style_guide_variant="clinical_protocol_data_driven" if self.use_enhanced_prompts else "clinical_protocol_strict",
                use_enhanced_prompts=self.use_enhanced_prompts,
                tmx_loader=tmx_loader,
                glossary_loader=glossary_loader
            )

            self.logger.info(f"✅ Pipeline initialized")
            self.logger.info(f"  Style guide: clinical_protocol_data_driven" if self.use_enhanced_prompts else "clinical_protocol_strict")

            return pipeline

        except Exception as e:
            self.logger.error(f"❌ Error initializing pipeline: {e}")
            raise

    def _process_translations(self, pipeline, segments_df):
        """Process translations for Not Translated segments"""
        translations = []
        stats = {
            'total_segments': len(segments_df),
            'successful': 0,
            'failed': 0,
            'total_time': 0,
            'glossary_matches_total': 0,
            'qa_issues_total': 0,
        }

        start_time = time.time()

        for batch_idx in range(0, len(segments_df), 50):
            batch = segments_df.iloc[batch_idx:batch_idx+50]
            batch_num = (batch_idx // 50) + 1
            
            self.logger.info(f"\n🔄 Processing batch {batch_num} ({len(batch)} segments, rows {batch_idx+1}-{min(batch_idx+50, len(segments_df))})...")

            for row_idx, (_, row) in enumerate(batch.iterrows(), start=batch_idx + 1):
                try:
                    segment_id = row['Segment ID']
                    source_en = str(row['Source segment']).strip()

                    if not source_en or len(source_en) < 2:
                        continue

                    # Translate
                    result = self._translate_segment(pipeline, source_en, segment_id)

                    # Log what's being appended
                    target_text = result['translation']
                    self.logger.info(f"  [{segment_id}] APPENDING to list: {repr(target_text)[:100]}")

                    translations.append({
                        'Segment ID': segment_id,
                        'Source segment': source_en,
                        'Target segment': target_text,
                        'glossary_matches': result.get('glossary_matches', 0),
                        'qa_issues': result.get('qa_issues', 0),
                        'processing_time': result.get('processing_time', 0),
                    })

                    self.logger.info(f"  [{segment_id}] APPENDED: {repr(translations[-1]['Target segment'])[:100]}")

                    stats['successful'] += 1
                    stats['glossary_matches_total'] += result.get('glossary_matches', 0)
                    stats['qa_issues_total'] += result.get('qa_issues', 0)

                    if (row_idx % 10) == 0:
                        self.logger.debug(f"  ✓ Processed {row_idx} segments")

                except Exception as e:
                    self.logger.warning(f"  ⚠️  Error: {str(e)[:100]}")
                    stats['failed'] += 1

        stats['total_time'] = time.time() - start_time
        self.logger.info(f"\n✅ Batch processing complete: {stats['successful']} successful, {stats['failed']} failed")
        self.logger.info(f"  Total time: {stats['total_time']:.1f}s")

        return translations, stats

    def _translate_segment(self, pipeline, source_en, segment_id):
        """Translate single segment with comprehensive error tracking"""
        try:
            start_time = time.time()

            # Step 1: Build context
            try:
                context, token_count, mandatory_violations = pipeline.build_en_ko_strict_context(source_en)
                self.logger.debug(f"[{segment_id}] Context built: {token_count} tokens")
            except Exception as ctx_error:
                self.logger.error(f"[{segment_id}] Context building failed: {str(ctx_error)[:100]}")
                return {'translation': f'[CONTEXT_ERROR: {str(ctx_error)[:30]}]', 'glossary_matches': 0, 'qa_issues': 1, 'processing_time': 0}

            # Step 2: Create prompt
            try:
                # CRITICAL FIX: create_strict_en_ko_prompt expects List[str], wrap single string in list
                prompt = pipeline.create_strict_en_ko_prompt([source_en], context)
                self.logger.debug(f"[{segment_id}] Prompt created: {len(prompt)} chars")
            except Exception as prompt_error:
                self.logger.error(f"[{segment_id}] Prompt creation failed: {str(prompt_error)[:100]}")
                return {'translation': f'[PROMPT_ERROR: {str(prompt_error)[:30]}]', 'glossary_matches': 0, 'qa_issues': 1, 'processing_time': 0}

            # Step 3: Call API for translation
            try:
                translation, input_tokens, output_tokens, metadata = pipeline.translate_batch_with_gpt5_owl_strict(prompt)
                self.logger.debug(f"[{segment_id}] API call successful: {input_tokens} in, {output_tokens} out")

                # Check for API errors in metadata
                if "error" in metadata:
                    self.logger.error(f"[{segment_id}] API returned error: {metadata['error']}")
                    return {'translation': f'[API_ERROR: {metadata["error"][:30]}]', 'glossary_matches': 0, 'qa_issues': 1, 'processing_time': 0}

            except Exception as api_error:
                self.logger.error(f"[{segment_id}] API call failed: {str(api_error)[:100]}")
                return {'translation': f'[API_ERROR: {str(api_error)[:30]}]', 'glossary_matches': 0, 'qa_issues': 1, 'processing_time': 0}

            # Step 4: Handle batch response
            try:
                self.logger.info(f"[{segment_id}] Translation BEFORE extraction: {repr(translation)[:100]}")
                self.logger.info(f"[{segment_id}] Translation type: {type(translation)}")

                if isinstance(translation, list):
                    if len(translation) > 0:
                        translation = translation[0]
                        self.logger.info(f"[{segment_id}] AFTER extraction from list: {repr(translation)[:100]}")
                        self.logger.info(f"[{segment_id}] Length: {len(str(translation))} chars")
                    else:
                        self.logger.error(f"[{segment_id}] Translation list is empty!")
                        return {'translation': '[EMPTY_RESPONSE]', 'glossary_matches': 0, 'qa_issues': 1, 'processing_time': 0}

                if not translation or len(str(translation).strip()) == 0:
                    self.logger.error(f"[{segment_id}] Translation is empty!")
                    return {'translation': '[EMPTY_TRANSLATION]', 'glossary_matches': 0, 'qa_issues': 1, 'processing_time': 0}

            except Exception as extract_error:
                self.logger.error(f"[{segment_id}] Response extraction failed: {str(extract_error)[:100]}")
                return {'translation': f'[EXTRACT_ERROR: {str(extract_error)[:30]}]', 'glossary_matches': 0, 'qa_issues': 1, 'processing_time': 0}

            # Step 5: Validate translation
            try:
                qa_issues = pipeline.validate_translation_strict(source_en, translation, mandatory_violations)
                self.logger.debug(f"[{segment_id}] QA validation: {len(qa_issues)} issues")
            except Exception as qa_error:
                self.logger.warning(f"[{segment_id}] QA validation failed: {str(qa_error)[:100]}")
                qa_issues = []  # Continue despite QA failure

            # Step 6: Search glossary
            try:
                found_terms = pipeline.search_glossary_en_ko_strict(source_en)
                glossary_terms_count = len(found_terms)
                self.logger.debug(f"[{segment_id}] Glossary: {glossary_terms_count} terms found")
            except Exception as glossary_error:
                self.logger.warning(f"[{segment_id}] Glossary search failed: {str(glossary_error)[:100]}")
                glossary_terms_count = 0

            # Prepare return dictionary with logging
            final_translation = str(translation).strip()
            self.logger.info(f"[{segment_id}] FINAL translation (after strip): {repr(final_translation)[:100]}")
            self.logger.info(f"[{segment_id}] FINAL length: {len(final_translation)} chars")

            result = {
                'translation': final_translation,
                'glossary_matches': glossary_terms_count,
                'qa_issues': len(qa_issues),
                'processing_time': time.time() - start_time,
            }

            self.logger.info(f"[{segment_id}] RETURNING dict: {repr(result['translation'])[:100]}")
            return result

        except Exception as e:
            self.logger.error(f"[{segment_id}] Unexpected error: {str(e)[:100]}")
            return {
                'translation': f'[UNEXPECTED_ERROR: {str(e)[:30]}]',
                'glossary_matches': 0,
                'qa_issues': 1,
                'processing_time': time.time() - start_time,
            }

    def _merge_and_save(self, all_df, translations):
        """Merge translations back to original dataframe and save"""
        try:
            # Create translation lookup
            translation_dict = {
                t['Segment ID']: t['Target segment'] for t in translations
            }

            # Update original dataframe
            for idx, row in all_df.iterrows():
                segment_id = row['Segment ID']
                if segment_id in translation_dict:
                    all_df.at[idx, 'Target segment'] = translation_dict[segment_id]

            # Save to new file
            output_dir = "/Users/won.suh/Downloads"
            output_file = f"{output_dir}/83-0060-0002_Protocol_translated_notranslated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

            all_df.to_excel(output_file, index=False)
            self.logger.info(f"✅ Merged file saved to: {output_file}")

            return output_file

        except Exception as e:
            self.logger.error(f"❌ Error merging: {e}")
            raise

    def _generate_reports(self, stats, output_file):
        """Generate translation reports"""
        self.logger.info("📊 Translation Statistics:")
        self.logger.info(f"  Total segments: {stats['total_segments']}")
        self.logger.info(f"  Successful: {stats['successful']}")
        self.logger.info(f"  Failed: {stats['failed']}")
        self.logger.info(f"  Total time: {stats['total_time']:.1f}s ({stats['total_time']/60:.1f} min)")
        self.logger.info(f"  Glossary matches: {stats['glossary_matches_total']}")
        self.logger.info(f"  QA issues: {stats['qa_issues_total']}")
        self.logger.info(f"\n📁 Output file: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Protocol EN-KO Translation Pipeline (Not Translated Only)")
    parser.add_argument('--test', type=int, help='Limit segments for testing', default=None)
    parser.add_argument('--baseline', action='store_true', help='Use baseline prompts')
    args = parser.parse_args()

    pipeline = ProtocolTranslationPipelineNotTranslated(
        test_limit=args.test,
        use_enhanced_prompts=not args.baseline
    )
    pipeline.run()


if __name__ == "__main__":
    main()
