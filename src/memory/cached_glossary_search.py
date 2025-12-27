"""
Cached Glossary Search Integration for Phase 2 MVP

This module integrates the glossary search engine with Valkey caching to provide
high-performance term lookup with intelligent cache management.

Key Features:
- Transparent caching layer over glossary search
- Cache warming and preloading strategies  
- Performance optimization for repeated searches
- Cache invalidation and refresh policies
- Integration with document session context
"""

import hashlib
import logging
import time
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from .valkey_manager import ValkeyManager
from glossary_search import GlossarySearchEngine, SearchResult


@dataclass
class CacheMetrics:
    """Cache performance metrics"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_time_saved_ms: float = 0.0
    search_times_ms: List[float] = None
    
    def __post_init__(self):
        if self.search_times_ms is None:
            self.search_times_ms = []
    
    @property
    def hit_rate(self) -> float:
        return self.cache_hits / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def average_search_time_ms(self) -> float:
        return sum(self.search_times_ms) / len(self.search_times_ms) if self.search_times_ms else 0.0


class CachedGlossarySearch:
    """High-performance cached glossary search engine"""
    
    def __init__(self, 
                 glossary_search_engine: GlossarySearchEngine,
                 valkey_manager: ValkeyManager,
                 cache_ttl_seconds: int = 7200,  # 2 hours
                 enable_preloading: bool = True,
                 max_cache_size: int = 10000):
        """
        Initialize cached glossary search
        
        Args:
            glossary_search_engine: Base glossary search engine
            valkey_manager: Valkey cache backend
            cache_ttl_seconds: Cache TTL in seconds
            enable_preloading: Enable cache preloading for common terms
            max_cache_size: Maximum cache entries
        """
        self.glossary_search = glossary_search_engine
        self.valkey = valkey_manager
        self.cache_ttl = cache_ttl_seconds
        self.enable_preloading = enable_preloading
        self.max_cache_size = max_cache_size
        self.logger = logging.getLogger(__name__)
        
        # Cache key prefix
        self.cache_prefix = "glossary_search"
        
        # Performance metrics
        self.metrics = CacheMetrics()
        
        # Preloading configuration
        self.preload_patterns = [
            "임상시험", "피험자", "시험대상자", "이상반응", "치료", "투여",
            "무작위배정", "이중눈가림", "위약", "대조군", "안전성", "유효성"
        ]
        
        self.logger.info("CachedGlossarySearch initialized")
        
        if enable_preloading:
            self._warm_cache()
    
    def _generate_cache_key(self, korean_text: str, max_results: int = 10, 
                           doc_id: Optional[str] = None) -> str:
        """Generate cache key for search parameters"""
        # Include doc_id for session-specific caching
        content = f"{korean_text}_{max_results}_{doc_id or 'global'}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _warm_cache(self) -> None:
        """Warm cache with common search terms"""
        self.logger.info("Warming glossary search cache...")
        
        warmed_count = 0
        for pattern in self.preload_patterns:
            try:
                # Perform search to populate cache
                self.search(pattern, max_results=10, use_cache=False, store_in_cache=True)
                warmed_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to warm cache for pattern '{pattern}': {e}")
        
        self.logger.info(f"Cache warmed with {warmed_count} patterns")
    
    def search(self, 
               korean_text: str,
               max_results: int = 10,
               doc_id: Optional[str] = None,
               use_cache: bool = True,
               store_in_cache: bool = True) -> List[SearchResult]:
        """
        Search glossary with caching
        
        Args:
            korean_text: Korean text to search
            max_results: Maximum results to return
            doc_id: Document ID for session-specific caching
            use_cache: Whether to use cached results
            store_in_cache: Whether to store results in cache
            
        Returns:
            List of SearchResult objects
        """
        start_time = time.time()
        self.metrics.total_requests += 1
        
        # Generate cache key
        cache_key = self._generate_cache_key(korean_text, max_results, doc_id)
        full_cache_key = f"{self.cache_prefix}:{cache_key}"
        
        # Try to get from cache first
        if use_cache:
            cached_results = self.valkey.get_cached_search_results(cache_key)
            if cached_results is not None:
                self.metrics.cache_hits += 1
                cache_time = (time.time() - start_time) * 1000
                self.metrics.cache_time_saved_ms += cache_time
                
                self.logger.debug(f"Cache hit for search: {korean_text[:50]}...")
                return cached_results
        
        # Cache miss - perform actual search
        self.metrics.cache_misses += 1
        
        try:
            # Perform search with original engine
            search_start = time.time()
            results = self.glossary_search.search(korean_text, max_results)
            search_time = (time.time() - search_start) * 1000
            
            self.metrics.search_times_ms.append(search_time)
            
            # Store in cache if enabled
            if store_in_cache and results:
                self.valkey.cache_search_results(cache_key, results, self.cache_ttl)
            
            total_time = (time.time() - start_time) * 1000
            self.logger.debug(f"Search completed: {korean_text[:50]}... "
                            f"({len(results)} results, {total_time:.1f}ms)")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Glossary search failed: {e}")
            return []
    
    def search_with_session_context(self, 
                                   korean_text: str,
                                   doc_id: str,
                                   segment_id: str,
                                   max_results: int = 10) -> Tuple[List[SearchResult], Set[str]]:
        """
        Search with document session context for enhanced relevance
        
        Args:
            korean_text: Korean text to search
            doc_id: Document ID for session context
            segment_id: Current segment ID
            max_results: Maximum results to return
            
        Returns:
            Tuple of (search_results, existing_terms_in_document)
        """
        # Get existing terms from document session
        existing_terms = set()
        try:
            term_mappings = self.valkey.get_all_term_mappings(doc_id)
            existing_terms = set(term_mappings.keys())
        except Exception as e:
            self.logger.warning(f"Failed to get existing terms for doc {doc_id}: {e}")
        
        # Perform search with session-specific caching
        results = self.search(korean_text, max_results, doc_id)
        
        # Boost relevance for terms already used in document
        for result in results:
            if result.term.korean in existing_terms:
                result.relevance_score *= 1.2  # Boost score for consistency
        
        # Re-sort by updated relevance scores
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return results, existing_terms
    
    def batch_search(self, 
                    search_queries: List[Tuple[str, int]],  # (korean_text, max_results)
                    doc_id: Optional[str] = None) -> Dict[str, List[SearchResult]]:
        """
        Perform batch search with optimized caching
        
        Args:
            search_queries: List of (korean_text, max_results) tuples
            doc_id: Optional document ID for session context
            
        Returns:
            Dictionary mapping query text to search results
        """
        results = {}
        cache_keys_to_queries = {}
        
        # Separate cached and uncached queries
        cached_queries = {}
        uncached_queries = []
        
        for korean_text, max_results in search_queries:
            cache_key = self._generate_cache_key(korean_text, max_results, doc_id)
            cache_keys_to_queries[cache_key] = korean_text
            
            cached_result = self.valkey.get_cached_search_results(cache_key)
            if cached_result is not None:
                results[korean_text] = cached_result
                cached_queries[korean_text] = cached_result
                self.metrics.cache_hits += 1
            else:
                uncached_queries.append((korean_text, max_results))
                self.metrics.cache_misses += 1
        
        # Process uncached queries
        for korean_text, max_results in uncached_queries:
            try:
                search_results = self.glossary_search.search(korean_text, max_results)
                results[korean_text] = search_results
                
                # Cache the results
                cache_key = self._generate_cache_key(korean_text, max_results, doc_id)
                self.valkey.cache_search_results(cache_key, search_results, self.cache_ttl)
                
            except Exception as e:
                self.logger.error(f"Batch search failed for '{korean_text}': {e}")
                results[korean_text] = []
        
        self.metrics.total_requests += len(search_queries)
        
        self.logger.info(f"Batch search completed: {len(cached_queries)} cached, "
                        f"{len(uncached_queries)} uncached")
        
        return results
    
    def preload_document_terms(self, doc_id: str, korean_segments: List[str]) -> int:
        """
        Preload cache for document-specific terms
        
        Args:
            doc_id: Document ID
            korean_segments: List of Korean text segments
            
        Returns:
            Number of terms preloaded
        """
        self.logger.info(f"Preloading cache for document {doc_id} with {len(korean_segments)} segments")
        
        # Extract unique terms from segments
        all_terms = set()
        for segment in korean_segments:
            # Extract potential terms (simple word extraction)
            words = segment.split()
            for word in words:
                cleaned_word = word.strip('.,!?()[]{}\"\'')
                if len(cleaned_word) >= 2:
                    all_terms.add(cleaned_word)
        
        # Batch search to populate cache
        search_queries = [(term, 5) for term in all_terms]  # 5 results per term
        
        try:
            self.batch_search(search_queries, doc_id)
            preloaded_count = len(all_terms)
            
            self.logger.info(f"Preloaded {preloaded_count} terms for document {doc_id}")
            return preloaded_count
            
        except Exception as e:
            self.logger.error(f"Failed to preload document terms: {e}")
            return 0
    
    def invalidate_cache(self, pattern: Optional[str] = None, doc_id: Optional[str] = None) -> int:
        """
        Invalidate cache entries
        
        Args:
            pattern: Optional pattern for targeted invalidation
            doc_id: Optional document ID for session-specific invalidation
            
        Returns:
            Number of cache entries invalidated
        """
        if doc_id:
            # Invalidate document-specific cache entries
            doc_pattern = f"*_{doc_id}"
            return self.valkey.invalidate_cache(doc_pattern)
        elif pattern:
            # Use provided pattern
            return self.valkey.invalidate_cache(pattern)
        else:
            # Invalidate all glossary cache
            return self.valkey.invalidate_cache()
    
    def refresh_cache_entry(self, korean_text: str, max_results: int = 10, 
                           doc_id: Optional[str] = None) -> bool:
        """
        Force refresh a specific cache entry
        
        Args:
            korean_text: Korean text to refresh
            max_results: Maximum results
            doc_id: Optional document ID
            
        Returns:
            True if refresh succeeded
        """
        try:
            # Invalidate existing cache entry
            cache_key = self._generate_cache_key(korean_text, max_results, doc_id)
            self.valkey.invalidate_cache(cache_key)
            
            # Perform fresh search and cache
            results = self.search(korean_text, max_results, doc_id, 
                                use_cache=False, store_in_cache=True)
            
            self.logger.info(f"Refreshed cache entry for: {korean_text[:50]}...")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to refresh cache entry: {e}")
            return False
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        # Get Valkey performance stats
        valkey_stats = self.valkey.get_performance_stats()
        
        # Get cache info from Redis
        cache_info = {}
        try:
            info = self.valkey.redis_client.info()
            cache_info = {
                "memory_used_mb": info.get('used_memory', 0) / (1024 * 1024),
                "total_keys": info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0),
                "keyspace_hit_ratio": (info.get('keyspace_hits', 0) / 
                                     max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1))
            }
        except Exception:
            cache_info = {"error": "Could not retrieve cache info"}
        
        # Calculate time savings
        uncached_time_estimate = len(self.metrics.search_times_ms) * self.metrics.average_search_time_ms
        actual_time = sum(self.metrics.search_times_ms) + self.metrics.cache_time_saved_ms
        time_savings_percent = ((uncached_time_estimate - actual_time) / uncached_time_estimate * 100 
                               if uncached_time_estimate > 0 else 0)
        
        return {
            "cache_performance": {
                "total_requests": self.metrics.total_requests,
                "cache_hits": self.metrics.cache_hits,
                "cache_misses": self.metrics.cache_misses,
                "hit_rate": self.metrics.hit_rate,
                "time_savings_percent": time_savings_percent
            },
            "search_performance": {
                "average_search_time_ms": self.metrics.average_search_time_ms,
                "total_search_time_ms": sum(self.metrics.search_times_ms),
                "cache_time_saved_ms": self.metrics.cache_time_saved_ms
            },
            "valkey_stats": valkey_stats,
            "cache_info": cache_info
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on cached search system"""
        health_status = {"status": "healthy", "checks": {}}
        
        # Test glossary search engine
        try:
            test_results = self.glossary_search.search("테스트", max_results=1)
            health_status["checks"]["glossary_search"] = "ok"
        except Exception as e:
            health_status["checks"]["glossary_search"] = f"error: {e}"
            health_status["status"] = "degraded"
        
        # Test Valkey connection
        try:
            valkey_health = self.valkey.health_check()
            health_status["checks"]["valkey"] = valkey_health["status"]
            if valkey_health["status"] != "healthy":
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["checks"]["valkey"] = f"error: {e}"
            health_status["status"] = "unhealthy"
        
        # Test cache operations
        try:
            test_key = f"health_check_{int(time.time())}"
            self.valkey.cache_search_results(test_key, ["test"], 1)
            cached = self.valkey.get_cached_search_results(test_key)
            self.valkey.invalidate_cache(test_key)
            
            if cached == ["test"]:
                health_status["checks"]["cache_operations"] = "ok"
            else:
                health_status["checks"]["cache_operations"] = "cache_data_mismatch"
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["checks"]["cache_operations"] = f"error: {e}"
            health_status["status"] = "degraded"
        
        return health_status
    
    def optimize_cache(self) -> Dict[str, Any]:
        """Optimize cache performance"""
        optimization_results = {
            "actions_taken": [],
            "cache_entries_before": 0,
            "cache_entries_after": 0,
            "memory_freed_mb": 0
        }
        
        try:
            # Get current cache info
            before_info = self.valkey.redis_client.info()
            memory_before = before_info.get('used_memory', 0)
            
            # Count current cache entries
            cache_keys = self.valkey.redis_client.keys(f"{self.valkey.GLOSSARY_CACHE_PREFIX}:*")
            optimization_results["cache_entries_before"] = len(cache_keys)
            
            # Remove expired entries (Redis should do this automatically, but ensure it)
            removed_expired = 0
            for key in cache_keys:
                ttl = self.valkey.redis_client.ttl(key)
                if ttl == -2:  # Key doesn't exist (expired)
                    removed_expired += 1
            
            if removed_expired > 0:
                optimization_results["actions_taken"].append(f"Cleaned {removed_expired} expired entries")
            
            # If cache is over size limit, remove least recently accessed
            if len(cache_keys) > self.max_cache_size:
                # This is a simple approach - in production you might want LRU tracking
                excess_keys = len(cache_keys) - self.max_cache_size
                keys_to_remove = cache_keys[:excess_keys]
                
                if keys_to_remove:
                    self.valkey.redis_client.delete(*keys_to_remove)
                    optimization_results["actions_taken"].append(f"Removed {len(keys_to_remove)} excess entries")
            
            # Get final cache info
            after_info = self.valkey.redis_client.info()
            memory_after = after_info.get('used_memory', 0)
            
            final_cache_keys = self.valkey.redis_client.keys(f"{self.valkey.GLOSSARY_CACHE_PREFIX}:*")
            optimization_results["cache_entries_after"] = len(final_cache_keys)
            optimization_results["memory_freed_mb"] = (memory_before - memory_after) / (1024 * 1024)
            
            if not optimization_results["actions_taken"]:
                optimization_results["actions_taken"].append("No optimization needed")
            
        except Exception as e:
            optimization_results["error"] = str(e)
        
        return optimization_results