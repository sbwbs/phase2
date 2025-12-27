"""
Qdrant configuration management.
Pattern adapted from: /Users/won.suh/Project/rag-hybrid-qdrant/config.py

Provides centralized configuration for Qdrant vector database integration
with validation and environment variable loading.

Supports project-scoped collections for multi-project isolation.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Optional, List
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


def sanitize_collection_name(name: str) -> str:
    """
    Sanitize a string for use as a Qdrant collection name.

    - Converts to lowercase
    - Replaces spaces/special chars with underscores
    - Removes consecutive underscores
    - Strips leading/trailing underscores
    """
    name = name.lower()
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')
    return name or "default"


@dataclass
class QdrantConfig:
    """
    Configuration for Qdrant vector database integration.

    Usage:
        # From environment variables (with project)
        config = QdrantConfig.from_env(project_id="greencross")

        # Manual configuration
        config = QdrantConfig(
            project_id="greencross",
            qdrant_url="https://xxx.cloud.qdrant.io:6333",
            qdrant_api_key="xxx",
            openai_api_key="xxx",
            enable_hybrid=True
        )

        # Get project-scoped collection names
        config.get_glossary_collection()  # "greencross_glossary"
        config.get_tm_collection("ko_en") # "greencross_tm_ko_en"

        # Initialize manager
        from memory.qdrant_manager import QdrantManager
        manager = QdrantManager(
            qdrant_url=config.qdrant_url,
            qdrant_api_key=config.qdrant_api_key,
            openai_api_key=config.openai_api_key,
            enable_hybrid=config.enable_hybrid
        )
    """

    # Project identification
    project_id: str = ""  # e.g., "greencross", "protocol_abc"

    # Required credentials
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    openai_api_key: str = ""

    # Base collection names (will be prefixed with project_id)
    _glossary_base: str = "glossary"
    _tm_base: str = "tm"

    # Embedding configuration
    embedding_model: str = "text-embedding-3-small"
    vector_size: int = 512

    # Sparse embedding configuration
    # Options: "splade" (client-side, default), "bm25" (server-side, requires Qdrant inference)
    sparse_model: str = "splade"
    splade_model_name: str = "prithvida/Splade_PP_en_v1"

    # Feature flags
    enable_hybrid: bool = True
    use_qdrant: bool = False  # Master switch for Qdrant integration

    # Search configuration
    glossary_search_limit: int = 15
    tm_search_limit: int = 5
    glossary_score_threshold: float = 0.75
    tm_score_threshold: float = 0.70

    # Batch configuration
    embedding_batch_size: int = 100

    def get_glossary_collection(self) -> str:
        """
        Get project-scoped glossary collection name.

        Returns:
            "glossary" if no project_id
            "{project_id}_glossary" if project_id is set
        """
        if self.project_id:
            return f"{sanitize_collection_name(self.project_id)}_{self._glossary_base}"
        return self._glossary_base

    def get_tm_collection(self, direction: str = "ko_en") -> str:
        """
        Get project-scoped TM collection name for a translation direction.

        Args:
            direction: "ko_en" or "en_ko"

        Returns:
            "tm_ko_en" if no project_id
            "{project_id}_tm_ko_en" if project_id is set
        """
        direction = direction.lower().replace("-", "_")
        if direction not in ("ko_en", "en_ko"):
            raise ValueError(f"Invalid direction: {direction}. Must be 'ko_en' or 'en_ko'")

        collection_name = f"{self._tm_base}_{direction}"
        if self.project_id:
            return f"{sanitize_collection_name(self.project_id)}_{collection_name}"
        return collection_name

    def get_all_collections(self) -> dict:
        """
        Get all project-scoped collection names.

        Returns:
            Dict with keys: glossary, tm_ko_en, tm_en_ko
        """
        return {
            "glossary": self.get_glossary_collection(),
            "tm_ko_en": self.get_tm_collection("ko_en"),
            "tm_en_ko": self.get_tm_collection("en_ko"),
        }

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.use_qdrant:
            self.validate()

    def validate(self) -> bool:
        """
        Validate that all required configuration is present.

        Raises:
            ValueError: If required configuration is missing
        """
        required = {
            "qdrant_url": self.qdrant_url,
            "qdrant_api_key": self.qdrant_api_key,
            "openai_api_key": self.openai_api_key
        }

        missing = [name for name, value in required.items() if not value]

        if missing:
            raise ValueError(f"Missing required Qdrant configuration: {', '.join(missing)}")

        logger.info("Qdrant configuration validated successfully")
        return True

    @classmethod
    def from_env(
        cls,
        project_id: str = "",
        env_file: Optional[str] = None
    ) -> "QdrantConfig":
        """
        Load configuration from environment variables.

        Args:
            project_id: Project identifier for scoped collections (e.g., "greencross")
            env_file: Optional path to .env file

        Environment variables:
            QDRANT_URL: Qdrant Cloud URL
            QDRANT_API_KEY: Qdrant API key
            OPENAI_API_KEY: OpenAI API key for embeddings
            USE_QDRANT: Enable Qdrant integration (true/false)
            ENABLE_HYBRID_SEARCH: Enable hybrid search (true/false)
            QDRANT_PROJECT_ID: Default project ID (overridden by project_id param)

        Returns:
            QdrantConfig instance with project-scoped collection names
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        def str_to_bool(val: str) -> bool:
            return val.lower() in ('true', '1', 'yes', 'on')

        # Use provided project_id or fall back to env var
        effective_project_id = project_id or os.getenv("QDRANT_PROJECT_ID", "")

        config = cls(
            project_id=effective_project_id,
            qdrant_url=os.getenv("QDRANT_URL", ""),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),

            # Feature flags
            use_qdrant=str_to_bool(os.getenv("USE_QDRANT", "false")),
            enable_hybrid=str_to_bool(os.getenv("ENABLE_HYBRID_SEARCH", "true")),

            # Search thresholds
            glossary_score_threshold=float(os.getenv("GLOSSARY_SCORE_THRESHOLD", "0.75")),
            tm_score_threshold=float(os.getenv("TM_SCORE_THRESHOLD", "0.70")),
        )

        mode = "enabled" if config.use_qdrant else "disabled"
        hybrid = "hybrid" if config.enable_hybrid else "dense-only"
        project_info = f", project: {config.project_id}" if config.project_id else ""
        logger.info(f"Qdrant config loaded from env: {mode}, search mode: {hybrid}{project_info}")

        return config

    def to_dict(self) -> dict:
        """Convert config to dictionary (safe for logging - masks secrets)."""
        return {
            "project_id": self.project_id or "(global)",
            "qdrant_url": self.qdrant_url[:20] + "..." if self.qdrant_url else None,
            "qdrant_api_key": "***" if self.qdrant_api_key else None,
            "openai_api_key": "***" if self.openai_api_key else None,
            "glossary_collection": self.get_glossary_collection(),
            "tm_collection_ko_en": self.get_tm_collection("ko_en"),
            "tm_collection_en_ko": self.get_tm_collection("en_ko"),
            "embedding_model": self.embedding_model,
            "vector_size": self.vector_size,
            "enable_hybrid": self.enable_hybrid,
            "use_qdrant": self.use_qdrant,
            "glossary_search_limit": self.glossary_search_limit,
            "tm_search_limit": self.tm_search_limit,
        }

    def __repr__(self) -> str:
        project_info = f", project_id='{self.project_id}'" if self.project_id else ""
        return f"QdrantConfig(use_qdrant={self.use_qdrant}, enable_hybrid={self.enable_hybrid}{project_info})"
