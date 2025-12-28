#!/usr/bin/env python3
"""
GSK Arexvy (아렉스비주) Translation Pipeline

Korean → English translation for Post-Marketing Surveillance Protocol.

Project: gsk_arexvy
Domain: PMS (Post-Marketing Surveillance) Protocol
Source: Bilingual_아렉스비주 사용성적조사 계획서_v1.0_clean.xlsx
TM: GSK Korea_KO-ENUS.tmx (2,638 TUs)
Direction: Korean → English

Run:
    python projects/gsk_arexvy/gsk_arexvy_pipeline.py --test 3   # Quick test
    python projects/gsk_arexvy/gsk_arexvy_pipeline.py            # Full run
    python projects/gsk_arexvy/gsk_arexvy_pipeline.py --untranslated  # Only untranslated
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Setup paths
PROJECT_DIR = Path(__file__).parent
PHASE2_DIR = PROJECT_DIR.parent.parent
SRC_DIR = PHASE2_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv
load_dotenv(PHASE2_DIR / ".env")

import pandas as pd

# ============================================
# PROJECT CONFIGURATION
# ============================================

PROJECT_ID = "gsk_arexvy"
PROJECT_NAME = "GSK Arexvy PMS Protocol"
DIRECTION = "ko_en"

# Input file (bilingual Excel - Korean source, English target)
INPUT_FILE = PROJECT_DIR / "data/source/Bilingual_아렉스비주 사용성적조사 계획서_v1.0_clean.xlsx"

# TMX file (2,638 translation units)
TMX_FILE = PROJECT_DIR / "data/tm/GSK Korea_KO-ENUS.tmx"

# Glossary files (symlinks to existing glossaries)
GLOSSARY_FILES = [
    (PHASE2_DIR / "data/GreenCross_2025_terms.xlsx", 1),      # Priority 1
    (PHASE2_DIR / "data/combined_en_ko_glossary.xlsx", 2),    # Priority 2
]

# Output directory
OUTPUT_DIR = PROJECT_DIR / "output"

# Model configuration
MODEL_NAME = "Owl"  # GPT-5 OWL
BATCH_SIZE = 50     # Segments per API call

# Memory configuration
USE_VALKEY = True   # Tier 1 - Session cache
USE_QDRANT = os.getenv("USE_QDRANT", "false").lower() == "true"  # Tier 2 - Semantic search

# Style guide (from 번역 지침.txt)
# "규제기관 제출용 공식 문서. 학술적, 공식적 톤. 불필요한 의역 피하고 명확하고 간결하게. 제품명, 수치 변형 금지."
STYLE_GUIDE = "REGULATORY_COMPLIANCE"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_glossary():
    """Load glossary terms from all glossary files."""
    from loaders.greencross_glossary_loader import GreenCrossGlossaryLoader

    loader = GreenCrossGlossaryLoader()
    all_terms = []

    for glossary_path, priority in GLOSSARY_FILES:
        if glossary_path.exists():
            try:
                # Try loading with GreenCross loader (sheet 'Glossary of Terms')
                try:
                    terms = loader.load_glossary(str(glossary_path))
                except Exception:
                    # Fallback: load as simple Excel with Korean/English columns
                    terms = load_simple_glossary(str(glossary_path), priority)

                # Update priority for all loaded terms
                for term in terms:
                    term['priority'] = priority

                all_terms.extend(terms)
                logger.info(f"✓ Loaded glossary: {len(terms)} terms (Priority {priority}) from {glossary_path.name}")
            except Exception as e:
                logger.warning(f"⚠ Error loading {glossary_path}: {e}")
        else:
            logger.warning(f"⚠ Glossary not found: {glossary_path}")

    logger.info(f"Total glossary terms: {len(all_terms)}")
    return all_terms


def load_simple_glossary(file_path: str, priority: int = 2):
    """Load a simple glossary with Korean/English columns."""
    df = pd.read_excel(file_path)

    # Find Korean and English columns
    korean_col = None
    english_col = None
    for col in df.columns:
        col_lower = str(col).lower()
        if 'korean' in col_lower or 'ko' == col_lower or '한국어' in col_lower:
            korean_col = col
        elif 'english' in col_lower or 'en' == col_lower or '영어' in col_lower:
            english_col = col

    if not korean_col or not english_col:
        # Use first two columns as fallback
        korean_col = df.columns[0]
        english_col = df.columns[1]

    terms = []
    for _, row in df.iterrows():
        korean = str(row[korean_col]).strip() if pd.notna(row[korean_col]) else None
        english = str(row[english_col]).strip() if pd.notna(row[english_col]) else None

        if korean and english and korean != 'nan' and english != 'nan':
            terms.append({
                'korean': korean,
                'english': english,
                'source': Path(file_path).stem,
                'priority': priority
            })

    return terms


def load_tm():
    """Load translation memory from TMX file."""
    from loaders.tmx_memory_loader import TMXMemoryLoader

    if TMX_FILE.exists():
        try:
            tm_loader = TMXMemoryLoader(str(TMX_FILE))
            logger.info(f"✓ Loaded TMX: {len(tm_loader.translation_units)} translation units")
            return tm_loader
        except Exception as e:
            logger.warning(f"⚠ Error loading TMX: {e}")
            return None
    else:
        logger.warning(f"⚠ TMX file not found: {TMX_FILE}")
        return None


def load_source_data(untranslated_only: bool = False):
    """Load source data from bilingual Excel."""
    df = pd.read_excel(INPUT_FILE)
    logger.info(f"✓ Loaded source: {len(df)} segments from {INPUT_FILE.name}")

    if untranslated_only:
        # Filter to only untranslated segments
        mask = df['Target segment'].isna() | (df['Target segment'].astype(str).str.strip() == '')
        df = df[mask].copy()
        logger.info(f"  Filtered to {len(df)} untranslated segments")

    return df


def setup_qdrant_collections(glossary_terms, tm_loader):
    """
    Create Qdrant collections and load data using QdrantManager + QdrantDataLoader.
    Uses hybrid search (dense + SPLADE) for better retrieval.
    Returns the configured QdrantManager for reuse in the pipeline.
    """
    from memory.qdrant_manager import QdrantManager
    from memory.qdrant_config import QdrantConfig
    from loaders.qdrant_data_loader import QdrantDataLoader

    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not qdrant_url or not qdrant_api_key:
        logger.warning("⚠ Qdrant credentials not configured, skipping collection setup")
        return None

    try:
        # Create project-scoped configuration
        config = QdrantConfig(
            project_id=PROJECT_ID,
            qdrant_url=qdrant_url,
            qdrant_api_key=qdrant_api_key,
            openai_api_key=openai_api_key,
            embedding_model="text-embedding-3-small",
            vector_size=512,
            enable_hybrid=True,
            sparse_model="splade",
            use_qdrant=True
        )

        # Initialize QdrantManager with hybrid search (SPLADE)
        manager = QdrantManager.from_config(config)

        if not manager.health_check():
            logger.error("✗ Qdrant health check failed")
            return None

        # Initialize data loader with project-scoped config
        # Collections will be: gsk_arexvy_glossary, gsk_arexvy_tm_ko_en
        loader = QdrantDataLoader(manager, config=config, batch_size=50)

        logger.info(f"📁 Using project-scoped collections: {config.get_all_collections()}")

        # Load glossary (skips if already populated)
        if glossary_terms:
            glossary_count = loader.load_glossary(glossary_terms)
            if glossary_count > 0:
                logger.info(f"✓ Loaded {glossary_count} glossary terms to Qdrant (hybrid)")
            else:
                stats = loader.get_collection_stats()
                glossary_col = config.get_glossary_collection()
                logger.info(f"✓ Qdrant glossary already populated: {stats.get(glossary_col, 0)} terms")

        # Load TM (skips if already populated)
        if tm_loader and tm_loader.translation_units:
            # TMX loader already provides 'source' and 'target' keys
            # Just ensure 'id' is set for each pair
            tm_pairs = [
                {'source': tu.get('source', ''), 'target': tu.get('target', ''), 'id': tu.get('id', str(i))}
                for i, tu in enumerate(tm_loader.translation_units)
                if tu.get('source') and tu.get('target')
            ]
            logger.info(f"  Prepared {len(tm_pairs)} TM pairs for Qdrant")
            tm_count = loader.load_tm_ko_en(tm_pairs)
            if tm_count > 0:
                logger.info(f"✓ Loaded {tm_count} TM pairs to Qdrant (hybrid)")
            else:
                stats = loader.get_collection_stats()
                tm_col = config.get_tm_collection("ko_en")
                logger.info(f"✓ Qdrant TM already populated: {stats.get(tm_col, 0)} pairs")

        # Show final stats
        stats = loader.get_collection_stats()
        logger.info(f"📊 Qdrant collections: {stats}")

        # Return manager and config for reuse
        return manager, config

    except Exception as e:
        logger.error(f"✗ Error setting up Qdrant: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_pipeline(glossary_terms, tm_loader):
    """Create the translation pipeline."""
    from production_pipeline_ko_en_improved import ImprovedKOENPipeline

    # Find GreenCross glossary path if it exists
    greencross_path = None
    for glossary_path, priority in GLOSSARY_FILES:
        if glossary_path.exists() and priority == 1:
            greencross_path = str(glossary_path)
            break

    pipeline_kwargs = {
        "model_name": MODEL_NAME,
        "batch_size": BATCH_SIZE,
        "use_valkey": USE_VALKEY,
        "greencross_glossary_path": greencross_path,
        "tmx_memory_path": str(TMX_FILE) if TMX_FILE.exists() else None,
    }

    qdrant_manager = None
    qdrant_config = None

    # Add Qdrant if enabled
    if USE_QDRANT:
        # Setup Qdrant collections and load data - returns configured manager
        result = setup_qdrant_collections(glossary_terms, tm_loader)
        if result:
            qdrant_manager, qdrant_config = result
            pipeline_kwargs.update({
                "use_qdrant": True,
                "qdrant_url": os.getenv("QDRANT_URL"),
                "qdrant_api_key": os.getenv("QDRANT_API_KEY"),
            })
            logger.info("✓ Qdrant hybrid semantic search enabled (project-scoped)")
        else:
            logger.warning("⚠ Qdrant setup failed, falling back to keyword search")

    pipeline = ImprovedKOENPipeline(**pipeline_kwargs)

    # Inject the pre-configured Qdrant manager with project-scoped collections
    if qdrant_manager and qdrant_config:
        pipeline.qdrant_manager = qdrant_manager
        pipeline.qdrant_config = qdrant_config
        # Update collection names to use project-scoped versions
        pipeline.glossary_collection = qdrant_config.get_glossary_collection()
        pipeline.tm_collection = qdrant_config.get_tm_collection("ko_en")
        logger.info(f"✓ Injected project-scoped Qdrant manager (collections: {qdrant_config.get_all_collections()})")

    # Override combined_glossary with our loaded terms
    if glossary_terms:
        pipeline.combined_glossary = glossary_terms
        # Invalidate cache to ensure fresh results with new glossary
        if pipeline.use_valkey and hasattr(pipeline, 'memory') and pipeline.memory:
            try:
                pipeline.memory.invalidate_cache("glossary_*")
                logger.info(f"✓ Using custom glossary: {len(glossary_terms)} terms (cache invalidated)")
            except Exception as e:
                logger.warning(f"⚠ Cache invalidation failed: {e}")
                logger.info(f"✓ Using custom glossary: {len(glossary_terms)} terms")
        else:
            logger.info(f"✓ Using custom glossary: {len(glossary_terms)} terms")

    # Override TM loader with our loaded data
    if tm_loader:
        pipeline.tm_loader = tm_loader
        logger.info(f"✓ Using custom TM: {len(tm_loader.translation_units)} units")

    return pipeline


def translate_segments(pipeline, df, start_row: int = 0, end_row: int = None):
    """Translate segments using BATCH processing for speed."""
    if end_row is None:
        end_row = len(df)

    results = []
    total = end_row - start_row

    # Prepare all segment data
    all_segments = []
    segment_rows = []  # Keep track of original rows for metadata

    for idx in range(start_row, end_row):
        row = df.iloc[idx]
        segment_id = str(row.get('Segment ID', idx))
        source_text = str(row['Source segment'])

        if pd.isna(row['Source segment']) or not source_text.strip():
            logger.debug(f"Skipping empty segment {segment_id}")
            continue

        segment_data = {
            'source_ko': source_text,
            'segment_id': segment_id,
            'reference_en': str(row.get('Target segment', '')) if pd.notna(row.get('Target segment')) else ''
        }
        all_segments.append(segment_data)
        segment_rows.append(row)

    logger.info(f"Processing {len(all_segments)} segments in batches of {BATCH_SIZE}...")

    # Process in batches
    for batch_start in range(0, len(all_segments), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(all_segments))
        batch_data = all_segments[batch_start:batch_end]
        batch_rows = segment_rows[batch_start:batch_end]

        try:
            # Use batch processing for speed (50 segments per API call)
            batch_results = pipeline.process_ko_en_batch_strict(batch_data)

            for i, result in enumerate(batch_results):
                row = batch_rows[i]

                result_dict = {
                    'segment_id': result.segment_id,
                    'source_text': result.source_text_ko,
                    'translation': result.translated_text_en,
                    'reference': result.reference_en,
                    'quality_score': result.quality_score,
                    'glossary_count': result.glossary_terms_found,
                    'tm_count': 0,
                    'processing_time': result.processing_time,
                    'total_cost': result.total_cost,
                    'status': result.status,
                    'qa_issues': result.qa_issues,
                    'original_status': row.get('Segment status', ''),
                    'original_target': str(row.get('Target segment', '')) if pd.notna(row.get('Target segment')) else ''
                }
                results.append(result_dict)

            # Progress
            progress = batch_end
            logger.info(f"[{progress}/{len(all_segments)}] ✓ Batch complete (segments {batch_start+1}-{batch_end})")

        except Exception as e:
            logger.error(f"Error in batch {batch_start}-{batch_end}: {e}")
            import traceback
            traceback.print_exc()

            # Fallback: add error entries for this batch
            for i, seg in enumerate(batch_data):
                results.append({
                    'segment_id': seg['segment_id'],
                    'source_text': seg['source_ko'],
                    'translation': '',
                    'error': str(e)
                })

    return results


def save_results(results, suffix: str = ""):
    """Save translation results to Excel."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"{PROJECT_ID}_translated{suffix}_{timestamp}.xlsx"

    # Create DataFrame
    df_results = pd.DataFrame(results)

    # Reorder columns for clarity
    columns_order = [
        'segment_id', 'source_text', 'translation',
        'original_target', 'original_status',
        'glossary_count', 'tm_count', 'quality_score'
    ]
    existing_cols = [c for c in columns_order if c in df_results.columns]
    other_cols = [c for c in df_results.columns if c not in existing_cols]
    df_results = df_results[existing_cols + other_cols]

    # Save
    df_results.to_excel(output_file, index=False)
    logger.info(f"✓ Saved results: {output_file}")

    return output_file


def main():
    parser = argparse.ArgumentParser(description=f"{PROJECT_NAME} Translation Pipeline")
    parser.add_argument("--test", type=int, metavar="N", help="Test with N segments")
    parser.add_argument("--start", type=int, default=0, help="Start row (0-indexed)")
    parser.add_argument("--end", type=int, help="End row")
    parser.add_argument("--untranslated", action="store_true", help="Only translate untranslated segments")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be translated without actually translating")
    args = parser.parse_args()

    # Header
    print(f"\n{'=' * 60}")
    print(f"{PROJECT_NAME} Translation Pipeline")
    print(f"Direction: {DIRECTION.upper()}")
    print(f"{'=' * 60}\n")

    # Load resources
    logger.info("Loading resources...")
    glossary_terms = load_glossary()
    tm_loader = load_tm()

    # Load source data
    df = load_source_data(untranslated_only=args.untranslated)

    if len(df) == 0:
        logger.warning("No segments to translate!")
        return

    # Determine range
    start_row = args.start
    end_row = args.end or len(df)

    if args.test:
        end_row = min(start_row + args.test, len(df))
        logger.info(f"🧪 TEST MODE: Processing {end_row - start_row} segments")

    # Show summary
    logger.info(f"\nSegments to process: {end_row - start_row} (rows {start_row} to {end_row})")
    logger.info(f"Glossary terms: {len(glossary_terms)}")
    logger.info(f"TM units: {len(tm_loader.translation_units) if tm_loader else 0}")

    if args.dry_run:
        logger.info("\n[DRY RUN] Would translate the following segments:")
        for idx in range(start_row, min(end_row, start_row + 10)):
            row = df.iloc[idx]
            source = str(row['Source segment'])[:50]
            logger.info(f"  {idx}: {source}...")
        if end_row - start_row > 10:
            logger.info(f"  ... and {end_row - start_row - 10} more")
        return

    # Create pipeline and translate
    pipeline = create_pipeline(glossary_terms, tm_loader)

    logger.info("\nStarting translation...")
    start_time = datetime.now()

    results = translate_segments(pipeline, df, start_row, end_row)

    elapsed = (datetime.now() - start_time).total_seconds()

    # Save results
    suffix = "_test" if args.test else ""
    if args.untranslated:
        suffix += "_untranslated"
    output_file = save_results(results, suffix)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"✓ Complete!")
    print(f"  Segments translated: {len(results)}")
    print(f"  Time: {elapsed:.1f}s ({elapsed/len(results):.1f}s per segment)")
    print(f"  Output: {output_file}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
