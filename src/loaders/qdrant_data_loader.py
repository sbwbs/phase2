"""
Load TM and Glossary data into Qdrant collections.
Reuses existing loader outputs - no changes to data loading logic.

Collections (project-scoped):
- {project_id}_glossary: Glossary entries for semantic term matching
- {project_id}_tm_ko_en: KO->EN TM pairs for semantic TM search
- {project_id}_tm_en_ko: EN->KO TM pairs for semantic TM search

Supports:
- Dense-only loading (backward compatible)
- Hybrid loading (dense + BM25 sparse) for improved exact term matching
- Project-scoped collections for multi-project isolation
- Server-side BM25 sparse embedding (no fastembed needed)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List, Dict, Optional, TYPE_CHECKING
import logging
from datetime import datetime

if TYPE_CHECKING:
    from memory.qdrant_config import QdrantConfig

logger = logging.getLogger(__name__)

# Default collection names (used when no config provided)
DEFAULT_GLOSSARY_COLLECTION = "glossary"
DEFAULT_TM_COLLECTION_KO_EN = "tm_ko_en"
DEFAULT_TM_COLLECTION_EN_KO = "tm_en_ko"

# Export aliases for backward compatibility
GLOSSARY_COLLECTION = DEFAULT_GLOSSARY_COLLECTION
TM_COLLECTION_KO_EN = DEFAULT_TM_COLLECTION_KO_EN
TM_COLLECTION_EN_KO = DEFAULT_TM_COLLECTION_EN_KO


class QdrantDataLoader:
    """
    Load TM and Glossary data into Qdrant collections.

    Supports project-scoped collections for multi-project isolation.

    Usage:
        from memory.qdrant_manager import QdrantManager
        from memory.qdrant_config import QdrantConfig

        # Option 1: With project-scoped config (recommended)
        config = QdrantConfig.from_env(project_id="greencross")
        manager = QdrantManager.from_config(config)
        loader = QdrantDataLoader(manager, config=config)

        # Collections will be: greencross_glossary, greencross_tm_ko_en, etc.
        loader.load_glossary(combined_glossary)
        loader.load_tm_ko_en(tm_pairs)

        # Option 2: Without config (uses default collection names)
        manager = QdrantManager(qdrant_url, qdrant_api_key, openai_api_key)
        loader = QdrantDataLoader(manager)

        # Collections will be: glossary, tm_ko_en, tm_en_ko
        loader.load_glossary(combined_glossary)
    """

    def __init__(
        self,
        qdrant_manager,
        config: Optional["QdrantConfig"] = None,
        batch_size: int = 100
    ):
        """
        Initialize data loader.

        Args:
            qdrant_manager: QdrantManager instance
            config: Optional QdrantConfig for project-scoped collection names
            batch_size: Number of items to embed per batch (default 100)
        """
        self.qdrant = qdrant_manager
        self.config = config
        self.batch_size = batch_size

    def _get_glossary_collection(self) -> str:
        """Get glossary collection name from config or use default."""
        if self.config:
            return self.config.get_glossary_collection()
        return DEFAULT_GLOSSARY_COLLECTION

    def _get_tm_collection(self, direction: str = "ko_en") -> str:
        """Get TM collection name from config or use default."""
        if self.config:
            return self.config.get_tm_collection(direction)
        return DEFAULT_TM_COLLECTION_KO_EN if direction == "ko_en" else DEFAULT_TM_COLLECTION_EN_KO

    def load_glossary(
        self,
        glossary: List[Dict],
        force_reload: bool = False,
        collection_name: Optional[str] = None
    ) -> int:
        """
        Load glossary terms into Qdrant.

        Args:
            glossary: List of glossary dicts from GlossaryLoader
                      Expected keys: korean, english, source, priority
            force_reload: If True, delete and reload collection
            collection_name: Override collection name (uses config if not provided)

        Returns:
            Number of terms loaded (0 if skipped)
        """
        collection_name = collection_name or self._get_glossary_collection()
        # Create collection if needed
        self.qdrant.create_collection_if_not_exists(collection_name)

        # Check if already populated
        current_count = self.qdrant.get_collection_count(collection_name)
        if not force_reload and current_count > 0:
            logger.info(f"Glossary collection '{collection_name}' already has {current_count} terms, skipping load")
            return 0

        # Force reload - delete first
        if force_reload and current_count > 0:
            logger.info(f"Force reload: deleting existing {current_count} terms")
            self.qdrant.delete_collection(collection_name)
            self.qdrant.create_collection_if_not_exists(collection_name)

        logger.info(f"Loading {len(glossary)} glossary terms to Qdrant...")
        start_time = datetime.now()

        # Prepare texts for batch embedding
        korean_texts = []
        valid_terms = []
        for term in glossary:
            korean = term.get('korean', '').strip()
            if korean:
                korean_texts.append(korean)
                valid_terms.append(term)

        if not korean_texts:
            logger.warning("No valid glossary terms to load")
            return 0

        use_hybrid = getattr(self.qdrant, 'enable_hybrid', False)

        # Batch embed all texts (dense embeddings)
        logger.info(f"Generating dense embeddings for {len(korean_texts)} terms...")
        embeddings = self.qdrant.get_embeddings_batch(korean_texts, batch_size=self.batch_size)

        # Prepare points for upsert
        # For hybrid, text is passed and Qdrant generates BM25 server-side
        points = []
        for i, (term, embedding) in enumerate(zip(valid_terms, embeddings)):
            korean_text = term.get('korean', '')
            point = {
                'id': i,
                'vector': embedding,
                'text': korean_text,  # For server-side BM25 sparse embedding
                'payload': {
                    'korean': korean_text,
                    'english': term.get('english', ''),
                    'source': term.get('source', 'unknown'),
                    'priority': term.get('priority', 2),
                    'mandatory': term.get('mandatory', False),
                    'alternatives': term.get('alternatives', [])
                }
            }
            points.append(point)

            # Upsert in batches
            if len(points) >= self.batch_size:
                self.qdrant.upsert_batch(collection_name, points, hybrid=use_hybrid)
                logger.info(f"Loaded {i + 1}/{len(valid_terms)} glossary terms")
                points = []

        # Final batch
        if points:
            self.qdrant.upsert_batch(collection_name, points, hybrid=use_hybrid)

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Glossary loading complete: {len(valid_terms)} terms in {elapsed:.1f}s")

        return len(valid_terms)

    def load_tm_ko_en(
        self,
        tm_pairs: List[Dict],
        force_reload: bool = False,
        collection_name: Optional[str] = None
    ) -> int:
        """
        Load KO->EN translation memory into Qdrant.

        Args:
            tm_pairs: List of TM dicts from TMXMemoryLoader
                      Expected keys: source (Korean), target (English), id
            force_reload: If True, delete and reload collection
            collection_name: Override collection name (uses config if not provided)

        Returns:
            Number of pairs loaded (0 if skipped)
        """
        collection_name = collection_name or self._get_tm_collection("ko_en")
        return self._load_tm(
            tm_pairs=tm_pairs,
            source_key='source',
            target_key='target',
            force_reload=force_reload,
            collection_name=collection_name,
            direction="KO->EN"
        )

    def load_tm_en_ko(
        self,
        tm_pairs: List[Dict],
        force_reload: bool = False,
        collection_name: Optional[str] = None
    ) -> int:
        """
        Load EN->KO translation memory into Qdrant.

        Args:
            tm_pairs: List of TM dicts
                      Expected keys: source (English), target (Korean), id
            force_reload: If True, delete and reload collection
            collection_name: Override collection name (uses config if not provided)

        Returns:
            Number of pairs loaded (0 if skipped)
        """
        collection_name = collection_name or self._get_tm_collection("en_ko")
        return self._load_tm(
            tm_pairs=tm_pairs,
            source_key='source',
            target_key='target',
            force_reload=force_reload,
            collection_name=collection_name,
            direction="EN->KO"
        )

    def _load_tm(
        self,
        tm_pairs: List[Dict],
        source_key: str,
        target_key: str,
        force_reload: bool,
        collection_name: str,
        direction: str
    ) -> int:
        """
        Internal method to load TM pairs.

        Args:
            tm_pairs: List of TM dicts
            source_key: Key for source text in dict
            target_key: Key for target text in dict
            force_reload: Delete and reload if True
            collection_name: Target collection
            direction: "KO->EN" or "EN->KO" for logging

        Returns:
            Number of pairs loaded
        """
        # Create collection if needed
        self.qdrant.create_collection_if_not_exists(collection_name)

        # Check if already populated
        current_count = self.qdrant.get_collection_count(collection_name)
        if not force_reload and current_count > 0:
            logger.info(f"TM collection '{collection_name}' already has {current_count} pairs, skipping load")
            return 0

        # Force reload - delete first
        if force_reload and current_count > 0:
            logger.info(f"Force reload: deleting existing {current_count} TM pairs")
            self.qdrant.delete_collection(collection_name)
            self.qdrant.create_collection_if_not_exists(collection_name)

        logger.info(f"Loading {len(tm_pairs)} {direction} TM pairs to Qdrant...")
        start_time = datetime.now()

        # Prepare texts for batch embedding
        source_texts = []
        valid_pairs = []
        for pair in tm_pairs:
            source = pair.get(source_key, '').strip()
            target = pair.get(target_key, '').strip()
            if source and target:
                source_texts.append(source)
                valid_pairs.append(pair)

        if not source_texts:
            logger.warning(f"No valid {direction} TM pairs to load")
            return 0

        use_hybrid = getattr(self.qdrant, 'enable_hybrid', False)

        # Batch embed all source texts (dense embeddings)
        logger.info(f"Generating dense embeddings for {len(source_texts)} TM source texts...")
        embeddings = self.qdrant.get_embeddings_batch(source_texts, batch_size=self.batch_size)

        # Prepare points for upsert
        # For hybrid, text is passed and Qdrant generates BM25 server-side
        points = []
        for i, (pair, embedding) in enumerate(zip(valid_pairs, embeddings)):
            source_text = pair.get(source_key, '')
            point = {
                'id': i,
                'vector': embedding,
                'text': source_text,  # For server-side BM25 sparse embedding
                'payload': {
                    'source': source_text,
                    'target': pair.get(target_key, ''),
                    'tu_id': pair.get('id', str(i)),
                    'direction': direction
                }
            }
            points.append(point)

            # Upsert in batches
            if len(points) >= self.batch_size:
                self.qdrant.upsert_batch(collection_name, points, hybrid=use_hybrid)
                logger.info(f"Loaded {i + 1}/{len(valid_pairs)} TM pairs")
                points = []

        # Final batch
        if points:
            self.qdrant.upsert_batch(collection_name, points, hybrid=use_hybrid)

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"TM loading complete: {len(valid_pairs)} {direction} pairs in {elapsed:.1f}s")

        return len(valid_pairs)

    def load_tm(
        self,
        tm_pairs: List[Dict],
        force_reload: bool = False,
        collection_name: Optional[str] = None
    ) -> int:
        """
        Alias for load_tm_ko_en for backward compatibility.
        """
        return self.load_tm_ko_en(tm_pairs, force_reload, collection_name)

    def is_collection_populated(self, collection_name: str, min_count: int = 1) -> bool:
        """
        Check if collection has at least min_count entries.

        Args:
            collection_name: Collection to check
            min_count: Minimum required count

        Returns:
            True if populated, False otherwise
        """
        count = self.qdrant.get_collection_count(collection_name)
        return count >= min_count

    def get_collection_stats(self) -> Dict[str, int]:
        """
        Get stats for all translation collections.

        Uses project-scoped collection names if config is provided.

        Returns:
            Dict with collection name -> count
        """
        glossary_col = self._get_glossary_collection()
        tm_ko_en_col = self._get_tm_collection("ko_en")
        tm_en_ko_col = self._get_tm_collection("en_ko")

        return {
            glossary_col: self.qdrant.get_collection_count(glossary_col),
            tm_ko_en_col: self.qdrant.get_collection_count(tm_ko_en_col),
            tm_en_ko_col: self.qdrant.get_collection_count(tm_en_ko_col)
        }
