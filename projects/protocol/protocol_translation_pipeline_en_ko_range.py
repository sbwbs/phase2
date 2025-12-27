#!/usr/bin/env python3
"""
Protocol Translation Pipeline EN-KO - Range-Based Parallel Processing
Translates segments in a specified range for parallel multi-process execution
Similar to GreenCross parallel processing architecture
"""

import os
import sys
import pandas as pd
import logging
import time
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from loaders.tmx_memory_loader_en_ko import TMXMemoryLoaderENKO
from loaders.protocol_glossary_loader_en_ko import ProtocolGlossaryLoaderENKO
from production_pipeline_en_ko_improved import ImprovedENKOPipeline


class ProtocolTranslationPipelineRange:
    """Pipeline for translating Protocol EN-KO segments in a specified range for parallel processing"""

    def __init__(self, start_idx: int = 0, end_idx: int = 910, use_enhanced_prompts: bool = True):
        self.start_idx = start_idx
        self.end_idx = end_idx
        self.use_enhanced_prompts = use_enhanced_prompts
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"🚀 Initializing Protocol EN-KO Translation Pipeline (Range-based: {start_idx}-{end_idx})")
        self.logger.info(f"  Enhanced prompts: {use_enhanced_prompts}")

    def setup_logging(self):
        """Setup logging"""
        log_dir = "/Users/won.suh/Project/translate-ai/phase2/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = f"{log_dir}/protocol_en_ko_range_{self.start_idx}_{self.end_idx}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ],
            force=True
        )

    def load_input_file(self) -> Tuple[pd.DataFrame, str]:
        """Load input Excel file"""
        # Look for the most recent input file
        search_path = "/Users/won.suh/Downloads/"
        pattern = "83-0060-0002_Protocol*docx.review*.xlsx"

        files = sorted(Path(search_path).glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise FileNotFoundError(f"No input file found matching {pattern}")

        input_file = str(files[0])
        self.logger.info(f"📂 Loading input from: {input_file}")

        df = pd.read_excel(input_file)
        return df, input_file

    def filter_not_translated(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter only Not Translated segments"""
        # Filter for segments with "Not Translated (0%)" status or empty target
        not_translated = df[
            (df['Segment status'].astype(str).str.contains('Not Translated', case=False, na=False)) |
            (df['Target segment'].isna()) |
            (df['Target segment'].astype(str).str.strip() == '')
        ].copy()

        self.logger.info(f"✅ Filtered {len(not_translated)} Not Translated segments from {len(df)} total")
        return not_translated

    def process(self) -> Tuple[List[Dict], Dict]:
        """Process segment range"""
        try:
            # Step 1: Load data
            df, input_file = self.load_input_file()
            not_translated_df = self.filter_not_translated(df)

            self.logger.info(f"\n====================================================================================================")
            self.logger.info(f"📋 Protocol EN-KO Translation Pipeline - Range Processing ({self.start_idx}-{self.end_idx})")
            self.logger.info(f"====================================================================================================\n")

            # Step 2: Initialize pipeline
            self.logger.info("🔧 STEP 1: Initializing translation pipeline with TM/Glossary...")
            pipeline = ImprovedENKOPipeline(
                use_enhanced_prompts=self.use_enhanced_prompts,
                model_name="Owl"
            )
            self.logger.info("✅ Pipeline initialized")

            # Step 3: Extract range
            start_time = time.time()
            range_start = min(self.start_idx, len(not_translated_df))
            range_end = min(self.end_idx, len(not_translated_df))
            range_df = not_translated_df.iloc[range_start:range_end].reset_index(drop=True)

            self.logger.info(f"\n🔄 STEP 2: Processing range {self.start_idx}-{self.end_idx}...")
            self.logger.info(f"  Segments in this range: {len(range_df)}")

            # Step 4: Translate segments
            translations = []
            stats = {
                'successful': 0,
                'failed': 0,
                'glossary_matches': 0,
                'qa_issues': 0,
                'total_time': 0
            }

            for local_idx, (_, row) in enumerate(range_df.iterrows(), start=1):
                global_idx = self.start_idx + local_idx - 1
                try:
                    segment_id = row['Segment ID']
                    source_en = str(row['Source segment']).strip()

                    if not source_en or len(source_en) < 2:
                        self.logger.debug(f"  [{global_idx}] Skipping empty segment")
                        continue

                    # Translate
                    result = self._translate_segment(pipeline, source_en, segment_id)

                    target_text = result['translation']
                    translations.append({
                        'Segment ID': segment_id,
                        'Source segment': source_en,
                        'Target segment': target_text,
                        'Glossary matches': result.get('glossary_matches', 0),
                        'QA issues': result.get('qa_issues', 0)
                    })

                    stats['successful'] += 1
                    stats['glossary_matches'] += result.get('glossary_matches', 0)
                    stats['qa_issues'] += result.get('qa_issues', 0)

                    # Progress logging every 10 segments
                    if (local_idx % 10) == 0:
                        elapsed = time.time() - start_time
                        rate = local_idx / elapsed
                        remaining = (len(range_df) - local_idx) / rate
                        self.logger.info(f"  ✓ Processed {local_idx}/{len(range_df)} segments (ETA: {remaining:.0f}s)")

                except Exception as e:
                    self.logger.warning(f"  ⚠️  [{global_idx}] Error: {str(e)[:100]}")
                    stats['failed'] += 1

            stats['total_time'] = time.time() - start_time
            self.logger.info(f"\n✅ Range processing complete: {stats['successful']} successful, {stats['failed']} failed")
            self.logger.info(f"  Total time: {stats['total_time']:.1f}s")

            return translations, stats

        except Exception as e:
            self.logger.error(f"❌ Pipeline failed: {e}")
            raise

    def _translate_segment(self, pipeline, source_en, segment_id) -> Dict:
        """Translate single segment with comprehensive error tracking"""
        try:
            start_time = time.time()

            # Build context
            try:
                context, token_count, mandatory_violations = pipeline.build_en_ko_strict_context(source_en)
            except Exception as ctx_error:
                self.logger.error(f"[{segment_id}] Context building failed: {str(ctx_error)[:100]}")
                return {'translation': f'[CONTEXT_ERROR]', 'glossary_matches': 0, 'qa_issues': 1}

            # Create prompt - CRITICAL: wrap single string in list
            try:
                prompt = pipeline.create_strict_en_ko_prompt([source_en], context)
            except Exception as prompt_error:
                self.logger.error(f"[{segment_id}] Prompt creation failed: {str(prompt_error)[:100]}")
                return {'translation': f'[PROMPT_ERROR]', 'glossary_matches': 0, 'qa_issues': 1}

            # Call API
            try:
                translation, input_tokens, output_tokens, metadata = pipeline.translate_batch_with_gpt5_owl_strict(prompt)

                if "error" in metadata:
                    self.logger.error(f"[{segment_id}] API returned error: {metadata['error']}")
                    return {'translation': f'[API_ERROR]', 'glossary_matches': 0, 'qa_issues': 1}
            except Exception as api_error:
                self.logger.error(f"[{segment_id}] API call failed: {str(api_error)[:100]}")
                return {'translation': f'[API_ERROR]', 'glossary_matches': 0, 'qa_issues': 1}

            # Handle batch response
            try:
                if isinstance(translation, list):
                    if len(translation) > 0:
                        translation = translation[0]
                    else:
                        self.logger.error(f"[{segment_id}] Translation list is empty!")
                        return {'translation': '[EMPTY_RESPONSE]', 'glossary_matches': 0, 'qa_issues': 1}

                if not translation or len(str(translation).strip()) == 0:
                    self.logger.error(f"[{segment_id}] Translation is empty!")
                    return {'translation': '[EMPTY_TRANSLATION]', 'glossary_matches': 0, 'qa_issues': 1}

            except Exception as extract_error:
                self.logger.error(f"[{segment_id}] Response extraction failed: {str(extract_error)[:100]}")
                return {'translation': f'[EXTRACT_ERROR]', 'glossary_matches': 0, 'qa_issues': 1}

            # Validate translation
            try:
                qa_issues = pipeline.validate_translation_strict(source_en, translation, {})
            except Exception as qa_error:
                self.logger.debug(f"[{segment_id}] QA validation warning: {str(qa_error)[:100]}")
                qa_issues = []

            processing_time = time.time() - start_time
            final_translation = str(translation).strip()

            return {
                'translation': final_translation,
                'glossary_matches': 0,
                'qa_issues': len(qa_issues),
                'processing_time': processing_time
            }

        except Exception as e:
            self.logger.error(f"[{segment_id}] Translation failed: {str(e)[:100]}")
            return {'translation': '[FAILED]', 'glossary_matches': 0, 'qa_issues': 1}

    def save_results(self, translations: List[Dict], output_file: Optional[str] = None) -> str:
        """Save translations to Excel"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"/Users/won.suh/Downloads/Protocol_EN_KO_range_{self.start_idx}_{self.end_idx}_{timestamp}.xlsx"

        results_df = pd.DataFrame(translations)
        results_df.to_excel(output_file, index=False, engine='openpyxl')

        self.logger.info(f"✅ Results saved to: {output_file}")
        return output_file


def main():
    parser = argparse.ArgumentParser(description='Protocol EN-KO Translation Pipeline - Range Based Parallel Processing')
    parser.add_argument('start', type=int, help='Start index (0-based)')
    parser.add_argument('end', type=int, help='End index (exclusive)')
    parser.add_argument('--baseline', action='store_true', help='Use baseline prompts (no examples)')

    args = parser.parse_args()

    try:
        pipeline = ProtocolTranslationPipelineRange(
            start_idx=args.start,
            end_idx=args.end,
            use_enhanced_prompts=not args.baseline
        )

        translations, stats = pipeline.process()
        output_file = pipeline.save_results(translations)

        print(f"\n{'='*100}")
        print(f"✅ RANGE COMPLETE ({args.start}-{args.end})")
        print(f"  Successful: {stats['successful']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Time: {stats['total_time']:.1f}s")
        print(f"  Output: {output_file}")
        print(f"{'='*100}\n")

    except Exception as e:
        print(f"\n❌ RANGE FAILED ({args.start}-{args.end}): {e}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
