"""
Qdrant vector database manager for semantic search.
Pattern adapted from: /Users/won.suh/Project/rfp-rag-hybrid/utils/search.py

Tier 2 Memory: Semantic search for TM and Glossary retrieval.

Supports:
- Dense-only search (backward compatible)
- Hybrid search (dense + sparse with RRF fusion) for better exact term matching

Sparse embedding options:
- SPLADE (default): Client-side via fastembed, works with any Qdrant instance
- BM25: Server-side via Qdrant inference service (requires Qdrant Cloud with inference enabled)
"""
from qdrant_client import QdrantClient, models
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    SparseVectorParams, SparseVector, Modifier, Prefetch, FusionQuery, Fusion
)
from openai import OpenAI
from typing import List, Dict, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from memory.qdrant_config import QdrantConfig

logger = logging.getLogger(__name__)

# Optional fastembed for SPLADE sparse embeddings
try:
    from fastembed import SparseTextEmbedding
    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False
    logger.warning("fastembed not available - SPLADE hybrid search disabled")


class QdrantManager:
    """
    Qdrant client wrapper for semantic TM/Glossary search.

    Uses hybrid search combining:
    - Dense vectors: OpenAI text-embedding-3-small (semantic similarity)
    - Sparse vectors: SPLADE (client-side) or BM25 (server-side)

    Usage:
        # With SPLADE (default, client-side)
        manager = QdrantManager(
            qdrant_url="https://xxx.cloud.qdrant.io:6333",
            qdrant_api_key="xxx",
            openai_api_key="xxx",
            enable_hybrid=True,
            sparse_model="splade"  # default
        )

        # With BM25 (server-side, requires Qdrant inference)
        manager = QdrantManager(
            ...,
            sparse_model="bm25"
        )
    """

    # Qdrant's built-in BM25 model name (for server-side inference)
    BM25_MODEL = "Qdrant/bm25"

    # Default SPLADE model
    DEFAULT_SPLADE_MODEL = "prithvida/Splade_PP_en_v1"

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str,
        openai_api_key: str,
        embedding_model: str = "text-embedding-3-small",
        vector_size: int = 512,
        enable_hybrid: bool = True,
        sparse_model: str = "splade",
        splade_model_name: str = None
    ):
        """
        Initialize Qdrant manager with credentials.

        Args:
            qdrant_url: Qdrant Cloud URL (e.g., https://xxx.cloud.qdrant.io:6333)
            qdrant_api_key: Qdrant API key
            openai_api_key: OpenAI API key for dense embeddings
            embedding_model: OpenAI embedding model (default: text-embedding-3-small)
            vector_size: Embedding dimensions (default: 512)
            enable_hybrid: Enable hybrid search with sparse vectors (default: True)
            sparse_model: "splade" (client-side, default) or "bm25" (server-side)
            splade_model_name: SPLADE model name (default: prithvida/Splade_PP_en_v1)
        """
        self.qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self.openai = OpenAI(api_key=openai_api_key)
        self.embedding_model = embedding_model
        self.vector_size = vector_size
        self.sparse_model_type = sparse_model.lower()
        self.splade_model_name = splade_model_name or self.DEFAULT_SPLADE_MODEL

        # Initialize sparse embedding based on model type
        self.enable_hybrid = enable_hybrid
        self.splade_model = None

        if self.enable_hybrid:
            if self.sparse_model_type == "splade":
                if FASTEMBED_AVAILABLE:
                    try:
                        self.splade_model = SparseTextEmbedding(model_name=self.splade_model_name)
                        logger.info(f"SPLADE model loaded: {self.splade_model_name}")
                    except Exception as e:
                        logger.warning(f"Failed to load SPLADE model: {e}. Falling back to dense-only.")
                        self.enable_hybrid = False
                else:
                    logger.warning("fastembed not installed. Install with: pip install fastembed")
                    self.enable_hybrid = False
            elif self.sparse_model_type == "bm25":
                logger.info("BM25 mode: sparse embeddings will be generated server-side by Qdrant")
            else:
                logger.warning(f"Unknown sparse_model: {sparse_model}. Using dense-only.")
                self.enable_hybrid = False

        mode = f"hybrid (dense + {self.sparse_model_type.upper()})" if self.enable_hybrid else "dense-only"
        logger.info(f"QdrantManager initialized: model={embedding_model}, vector_size={vector_size}, mode={mode}")

    @classmethod
    def from_config(cls, config: "QdrantConfig") -> "QdrantManager":
        """
        Create QdrantManager from QdrantConfig.

        Args:
            config: QdrantConfig instance

        Returns:
            Configured QdrantManager instance
        """
        return cls(
            qdrant_url=config.qdrant_url,
            qdrant_api_key=config.qdrant_api_key,
            openai_api_key=config.openai_api_key,
            embedding_model=config.embedding_model,
            vector_size=config.vector_size,
            enable_hybrid=config.enable_hybrid,
            sparse_model=config.sparse_model,
            splade_model_name=config.splade_model_name
        )

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate dense embedding for text using OpenAI.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        text = text.replace("\n", " ").strip()
        if not text:
            return [0.0] * self.vector_size

        try:
            response = self.openai.embeddings.create(
                input=[text],
                model=self.embedding_model,
                dimensions=self.vector_size
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def get_embeddings_batch(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Generate dense embeddings for multiple texts in batches.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call (max 2048)

        Returns:
            List of embedding vectors
        """
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch = [t.replace("\n", " ").strip() if t else "" for t in batch]

            try:
                response = self.openai.embeddings.create(
                    input=batch,
                    model=self.embedding_model,
                    dimensions=self.vector_size
                )
                embeddings = [d.embedding for d in response.data]
                all_embeddings.extend(embeddings)

                if i % 1000 == 0 and i > 0:
                    logger.info(f"Generated {i + len(batch)}/{len(texts)} embeddings")

            except Exception as e:
                logger.error(f"Error generating batch embeddings at index {i}: {e}")
                all_embeddings.extend([[0.0] * self.vector_size] * len(batch))

        return all_embeddings

    def get_sparse_embedding(self, text: str) -> Optional[SparseVector]:
        """
        Generate sparse embedding for text using SPLADE.

        Only works when sparse_model="splade".

        Args:
            text: Text to embed

        Returns:
            SparseVector or None if SPLADE is not enabled
        """
        if not self.enable_hybrid or self.sparse_model_type != "splade" or not self.splade_model:
            return None

        text = text.replace("\n", " ").strip()
        if not text:
            return SparseVector(indices=[], values=[])

        try:
            embedding = next(self.splade_model.embed([text]))
            return SparseVector(
                indices=embedding.indices.tolist(),
                values=embedding.values.tolist()
            )
        except Exception as e:
            logger.error(f"Error generating SPLADE embedding: {e}")
            return None

    def get_sparse_embeddings_batch(self, texts: List[str]) -> List[Optional[SparseVector]]:
        """
        Generate sparse embeddings for multiple texts using SPLADE.

        Only works when sparse_model="splade".

        Args:
            texts: List of texts to embed

        Returns:
            List of SparseVector objects (or None for each if SPLADE not enabled)
        """
        if not self.enable_hybrid or self.sparse_model_type != "splade" or not self.splade_model:
            return [None] * len(texts)

        sparse_vectors = []
        cleaned_texts = [t.replace("\n", " ").strip() if t else "" for t in texts]

        try:
            embeddings = list(self.splade_model.embed(cleaned_texts))
            for emb in embeddings:
                sparse_vectors.append(SparseVector(
                    indices=emb.indices.tolist(),
                    values=emb.values.tolist()
                ))
            return sparse_vectors
        except Exception as e:
            logger.error(f"Error generating batch SPLADE embeddings: {e}")
            return [None] * len(texts)

    def create_collection_if_not_exists(self, collection_name: str, hybrid: bool = None) -> bool:
        """
        Create collection if it doesn't exist.

        Args:
            collection_name: Name of the collection
            hybrid: Use hybrid vectors (dense + sparse). Defaults to self.enable_hybrid

        Returns:
            True if created, False if already exists
        """
        use_hybrid = hybrid if hybrid is not None else self.enable_hybrid

        try:
            self.qdrant.get_collection(collection_name)
            logger.info(f"Collection '{collection_name}' already exists")
            return False
        except Exception:
            if use_hybrid:
                # Hybrid collection with dense + sparse vectors
                sparse_config = SparseVectorParams(
                    modifier=Modifier.IDF if self.sparse_model_type == "bm25" else None
                )
                self.qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(
                            size=self.vector_size,
                            distance=Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        "sparse": sparse_config
                    }
                )
                logger.info(f"Hybrid collection '{collection_name}' created (dense + {self.sparse_model_type.upper()})")
            else:
                # Dense-only collection (backward compatible)
                self.qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Dense-only collection '{collection_name}' created")
            return True

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if deleted, False if didn't exist
        """
        try:
            self.qdrant.delete_collection(collection_name)
            logger.info(f"Collection '{collection_name}' deleted")
            return True
        except Exception:
            logger.warning(f"Collection '{collection_name}' not found for deletion")
            return False

    def get_collection_count(self, collection_name: str) -> int:
        """
        Get number of points in collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Number of points, or 0 if collection doesn't exist
        """
        try:
            info = self.qdrant.get_collection(collection_name)
            return info.points_count
        except Exception:
            return 0

    def upsert_batch(
        self,
        collection_name: str,
        points: List[Dict],
        hybrid: bool = None
    ) -> int:
        """
        Upsert batch of points to collection.

        Args:
            collection_name: Target collection
            points: List of dicts with:
                - id: Point ID
                - vector: Dense vector
                - text: Text for sparse embedding (optional, used for BM25 or to generate SPLADE)
                - sparse_vector: Pre-computed sparse vector (optional, for SPLADE)
                - payload: Metadata dict
            hybrid: If True, include sparse vectors. Defaults to self.enable_hybrid

        Returns:
            Number of points upserted
        """
        if not points:
            return 0

        use_hybrid = hybrid if hybrid is not None else self.enable_hybrid

        point_structs = []
        for p in points:
            point_id = p['id']
            dense_vec = p.get('vector', p.get('dense_vector', [0.0] * self.vector_size))
            payload = p.get('payload', {})
            text = p.get('text', '')

            if use_hybrid:
                if self.sparse_model_type == "splade":
                    # SPLADE: Use pre-computed sparse vector or generate from text
                    sparse_vec = p.get('sparse_vector')
                    if sparse_vec is None and text:
                        sparse_vec = self.get_sparse_embedding(text)

                    if sparse_vec is not None:
                        if isinstance(sparse_vec, SparseVector):
                            sparse_dict = {"indices": sparse_vec.indices, "values": sparse_vec.values}
                        else:
                            sparse_dict = sparse_vec

                        point_structs.append(PointStruct(
                            id=point_id,
                            vector={
                                "dense": dense_vec,
                                "sparse": sparse_dict
                            },
                            payload=payload
                        ))
                    else:
                        # No sparse vector available, use dense only for this point
                        point_structs.append(PointStruct(
                            id=point_id,
                            vector={"dense": dense_vec},
                            payload=payload
                        ))

                elif self.sparse_model_type == "bm25":
                    # BM25: Pass text for server-side processing
                    if text:
                        point_structs.append(PointStruct(
                            id=point_id,
                            vector={
                                "dense": dense_vec,
                                "sparse": models.Document(text=text, model=self.BM25_MODEL)
                            },
                            payload=payload
                        ))
                    else:
                        # No text for BM25, use dense only
                        point_structs.append(PointStruct(
                            id=point_id,
                            vector={"dense": dense_vec},
                            payload=payload
                        ))
            else:
                # Dense-only
                point_structs.append(PointStruct(
                    id=point_id,
                    vector=dense_vec,
                    payload=payload
                ))

        try:
            self.qdrant.upsert(
                collection_name=collection_name,
                points=point_structs
            )
            return len(points)
        except Exception as e:
            logger.error(f"Error upserting to '{collection_name}': {e}")
            raise

    def search(
        self,
        collection_name: str,
        query_text: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[Dict]:
        """
        Dense-only search by query text.

        Args:
            collection_name: Collection to search
            query_text: Query text (will be embedded)
            limit: Maximum results to return
            score_threshold: Minimum score threshold (0.0-1.0 for cosine)

        Returns:
            List of {id, score, payload} dicts sorted by relevance
        """
        query_vector = self.get_embedding(query_text)

        try:
            # Check if collection is hybrid
            is_hybrid = self.is_collection_hybrid(collection_name)
            logger.debug(f"Search '{collection_name}': is_hybrid={is_hybrid}, query_len={len(query_text)}")

            if is_hybrid:
                # Use named vector for hybrid collections
                logger.debug(f"Using named vector 'dense' for hybrid collection '{collection_name}'")
                results = self.qdrant.search(
                    collection_name=collection_name,
                    query_vector=("dense", query_vector),
                    limit=limit,
                    score_threshold=score_threshold
                )
            else:
                # Standard search for dense-only collections
                logger.debug(f"Using unnamed vector for dense-only collection '{collection_name}'")
                results = self.qdrant.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    limit=limit,
                    score_threshold=score_threshold
                )

            logger.debug(f"Search '{collection_name}' returned {len(results)} results")
            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "payload": r.payload
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Error searching '{collection_name}': {e}")
            # Log additional context for debugging
            logger.error(f"  is_hybrid={is_hybrid if 'is_hybrid' in dir() else 'unknown'}")
            logger.error(f"  query_text[:50]={query_text[:50] if query_text else 'empty'}")
            return []

    def hybrid_search(
        self,
        collection_name: str,
        query_text: str,
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[Dict]:
        """
        Hybrid search using dense + sparse vectors with RRF fusion.

        Combines semantic similarity (dense vectors) with exact term matching
        (sparse vectors) using Reciprocal Rank Fusion (RRF).

        Args:
            collection_name: Collection to search
            query_text: Query text
            limit: Maximum results to return
            score_threshold: Optional minimum score threshold

        Returns:
            List of {id, score, payload} dicts sorted by relevance
        """
        if not self.enable_hybrid:
            logger.debug("Hybrid search not enabled, falling back to dense-only")
            return self.search(collection_name, query_text, limit, score_threshold)

        try:
            # Generate dense embedding
            dense_vec = self.get_embedding(query_text)

            # Prepare sparse query based on model type
            if self.sparse_model_type == "splade":
                sparse_vec = self.get_sparse_embedding(query_text)
                if sparse_vec is None:
                    logger.debug("SPLADE embedding failed, falling back to dense-only")
                    return self.search(collection_name, query_text, limit, score_threshold)
                sparse_query = {"indices": sparse_vec.indices, "values": sparse_vec.values}
            elif self.sparse_model_type == "bm25":
                sparse_query = models.Document(text=query_text, model=self.BM25_MODEL)
            else:
                return self.search(collection_name, query_text, limit, score_threshold)

            # Hybrid search with RRF fusion
            results = self.qdrant.query_points(
                collection_name=collection_name,
                prefetch=[
                    Prefetch(
                        query=dense_vec,
                        using="dense",
                        limit=limit * 2
                    ),
                    Prefetch(
                        query=sparse_query,
                        using="sparse",
                        limit=limit * 2
                    )
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                with_payload=True,
                limit=limit
            )

            search_results = []
            for result in results.points:
                if score_threshold is not None and result.score < score_threshold:
                    continue
                search_results.append({
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload
                })

            logger.debug(f"Hybrid search returned {len(search_results)} results for '{query_text[:50]}...'")
            return search_results

        except Exception as e:
            logger.warning(f"Hybrid search failed: {e}. Falling back to dense-only.")
            return self.search(collection_name, query_text, limit, score_threshold)

    def search_with_filter(
        self,
        collection_name: str,
        query_text: str,
        filter_conditions: Dict,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search with metadata filtering.

        Args:
            collection_name: Collection to search
            query_text: Query text
            filter_conditions: Qdrant filter dict
            limit: Maximum results

        Returns:
            Filtered search results
        """
        from qdrant_client.models import Filter

        query_vector = self.get_embedding(query_text)
        is_hybrid = self.is_collection_hybrid(collection_name)

        try:
            if is_hybrid:
                results = self.qdrant.search(
                    collection_name=collection_name,
                    query_vector=("dense", query_vector),
                    query_filter=Filter(**filter_conditions) if filter_conditions else None,
                    limit=limit
                )
            else:
                results = self.qdrant.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    query_filter=Filter(**filter_conditions) if filter_conditions else None,
                    limit=limit
                )

            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "payload": r.payload
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Error in filtered search: {e}")
            return []

    def is_collection_hybrid(self, collection_name: str) -> bool:
        """
        Check if a collection uses hybrid vectors.

        Args:
            collection_name: Name of the collection to check

        Returns:
            True if collection has sparse vectors configured
        """
        try:
            info = self.qdrant.get_collection(collection_name)
            # Check in config.params.sparse_vectors (qdrant-client 1.x)
            if (
                hasattr(info.config, 'params')
                and hasattr(info.config.params, 'sparse_vectors')
                and info.config.params.sparse_vectors is not None
                and len(info.config.params.sparse_vectors) > 0
            ):
                sparse_names = list(info.config.params.sparse_vectors.keys())
                logger.debug(f"Collection '{collection_name}' is hybrid (sparse vectors: {sparse_names})")
                return True
            # Fallback check for older versions
            if (
                hasattr(info.config, 'sparse_vectors')
                and info.config.sparse_vectors is not None
                and len(info.config.sparse_vectors) > 0
            ):
                sparse_names = list(info.config.sparse_vectors.keys())
                logger.debug(f"Collection '{collection_name}' is hybrid (legacy config, sparse: {sparse_names})")
                return True
            logger.debug(f"Collection '{collection_name}' is dense-only (no sparse vectors)")
            return False
        except Exception as e:
            logger.warning(f"Could not determine if '{collection_name}' is hybrid: {e}")
            return False

    def health_check(self) -> bool:
        """
        Check Qdrant connection health.

        Returns:
            True if connected, False otherwise
        """
        try:
            self.qdrant.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False
