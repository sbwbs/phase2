"""
GPT-5 OWL Cost Optimization Module

This module implements advanced caching and batching strategies specifically
optimized for GPT-5 OWL's pricing model and capabilities for medical translation.

Key Features:
- Context-aware caching for recurring medical terms
- Session-based cost tracking and optimization  
- Intelligent prompt reuse detection
- Response API specific optimizations
"""

import logging
import time
import hashlib
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from memory.valkey_manager import ValkeyManager


class CacheType(Enum):
    """Types of caching strategies for GPT-5 OWL"""
    TRANSLATION_CACHE = "translation_cache"
    CONTEXT_CACHE = "context_cache" 
    TERMINOLOGY_CACHE = "terminology_cache"
    SESSION_CACHE = "session_cache"


@dataclass
class CostMetrics:
    """Cost tracking metrics for GPT-5 OWL"""
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    cache_hits: int = 0
    cache_savings_usd: float = 0.0
    average_context_tokens: float = 0.0
    session_efficiency_score: float = 0.0


@dataclass
class CachedTranslation:
    """Cached translation result"""
    korean_text: str
    english_translation: str
    context_hash: str
    model_used: str
    timestamp: datetime
    confidence_score: float
    usage_count: int = 1
    cost_saved_usd: float = 0.0


class GPT5CostOptimizer:
    """Advanced cost optimization for GPT-5 OWL medical translations"""
    
    def __init__(self,
                 valkey_manager: ValkeyManager,
                 cache_ttl_hours: int = 24,
                 similarity_threshold: float = 0.85,
                 max_cache_size: int = 10000):
        """
        Initialize GPT-5 cost optimizer
        
        Args:
            valkey_manager: Valkey cache manager
            cache_ttl_hours: Cache time-to-live in hours
            similarity_threshold: Text similarity threshold for cache hits
            max_cache_size: Maximum number of cached entries per type
        """
        self.valkey_manager = valkey_manager
        self.cache_ttl = cache_ttl_hours * 3600  # Convert to seconds
        self.similarity_threshold = similarity_threshold
        self.max_cache_size = max_cache_size
        
        self.logger = logging.getLogger(__name__)
        
        # Cost tracking
        self.cost_metrics = CostMetrics()
        self.session_costs = {}  # doc_id -> cost metrics
        
        # Cache statistics
        self.cache_hit_rates = {cache_type: 0.0 for cache_type in CacheType}
        
        # GPT-5 OWL specific pricing (as of the model configuration)
        self.input_token_cost = 0.010 / 1000  # $0.010 per 1K input tokens
        self.output_token_cost = 0.030 / 1000  # $0.030 per 1K output tokens
        
        self.logger.info("GPT-5 Cost Optimizer initialized")
    
    async def check_translation_cache(self,
                                    korean_text: str,
                                    context_hash: str,
                                    doc_id: str) -> Optional[CachedTranslation]:
        """
        Check if translation exists in cache
        
        Args:
            korean_text: Source Korean text
            context_hash: Hash of the context used
            doc_id: Document ID for session-based caching
            
        Returns:
            Cached translation if found, None otherwise
        """
        try:
            # Generate cache key
            cache_key = self._generate_translation_cache_key(korean_text, context_hash)
            
            # Check session-specific cache first (highest precision)
            session_cache_key = f"session:{doc_id}:{cache_key}"
            cached_data = self.valkey_manager.get_cached_data(session_cache_key)
            
            if cached_data:
                cached_translation = self._deserialize_cached_translation(cached_data)
                if cached_translation:
                    # Update usage statistics
                    cached_translation.usage_count += 1
                    await self._update_cached_translation(session_cache_key, cached_translation)
                    
                    self.cost_metrics.cache_hits += 1
                    self._update_cache_hit_rate(CacheType.SESSION_CACHE)
                    
                    return cached_translation
            
            # Check global translation cache
            global_cache_key = f"global:{cache_key}"
            cached_data = self.valkey_manager.get_cached_data(global_cache_key)
            
            if cached_data:
                cached_translation = self._deserialize_cached_translation(cached_data)
                if cached_translation:
                    # Check if similar enough for reuse
                    if await self._is_context_similar(cached_translation.context_hash, context_hash):
                        cached_translation.usage_count += 1
                        await self._update_cached_translation(global_cache_key, cached_translation)
                        
                        self.cost_metrics.cache_hits += 1
                        self._update_cache_hit_rate(CacheType.TRANSLATION_CACHE)
                        
                        return cached_translation
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Failed to check translation cache: {e}")
            return None
    
    async def cache_translation(self,
                              korean_text: str,
                              english_translation: str,
                              context_hash: str,
                              doc_id: str,
                              model_used: str,
                              input_tokens: int,
                              output_tokens: int,
                              confidence_score: float = 0.9) -> bool:
        """
        Cache a successful translation result
        
        Args:
            korean_text: Source Korean text
            english_translation: Target English translation
            context_hash: Hash of the context used
            doc_id: Document ID
            model_used: Model identifier
            input_tokens: Input tokens used
            output_tokens: Output tokens generated
            confidence_score: Quality confidence score
            
        Returns:
            True if cached successfully
        """
        try:
            # Calculate cost savings
            cost_saved = self._calculate_cost(input_tokens, output_tokens)
            
            # Create cached translation
            cached_translation = CachedTranslation(
                korean_text=korean_text,
                english_translation=english_translation,
                context_hash=context_hash,
                model_used=model_used,
                timestamp=datetime.now(),
                confidence_score=confidence_score,
                cost_saved_usd=cost_saved
            )
            
            # Generate cache keys
            cache_key = self._generate_translation_cache_key(korean_text, context_hash)
            session_cache_key = f"session:{doc_id}:{cache_key}"
            global_cache_key = f"global:{cache_key}"
            
            # Cache in both session and global caches
            serialized_data = self._serialize_cached_translation(cached_translation)
            
            # Session cache (higher priority, shorter TTL)
            self.valkey_manager.cache_data(
                session_cache_key,
                serialized_data,
                ttl=self.cache_ttl // 2  # Shorter TTL for session cache
            )
            
            # Global cache (longer TTL, lower priority)
            self.valkey_manager.cache_data(
                global_cache_key,
                serialized_data,
                ttl=self.cache_ttl
            )
            
            # Update session cost tracking
            if doc_id not in self.session_costs:
                self.session_costs[doc_id] = CostMetrics()
            
            session_metrics = self.session_costs[doc_id]
            session_metrics.total_requests += 1
            session_metrics.total_input_tokens += input_tokens
            session_metrics.total_output_tokens += output_tokens
            session_metrics.total_cost_usd += cost_saved
            
            self.logger.debug(f"Cached translation for {doc_id}: {len(korean_text)} chars")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cache translation: {e}")
            return False
    
    async def optimize_context_for_cost(self,
                                      context: str,
                                      korean_text: str,
                                      target_tokens: int = 413) -> Tuple[str, float]:
        """
        Optimize context to minimize cost while maintaining quality
        
        Args:
            context: Original context
            korean_text: Korean text to translate
            target_tokens: Target token count
            
        Returns:
            Tuple of (optimized_context, estimated_cost_savings)
        """
        try:
            # Check if this context pattern has been optimized before
            context_hash = self._generate_context_hash(context)
            cache_key = f"context_opt:{context_hash}"
            
            cached_optimization = self.valkey_manager.get_cached_data(cache_key)
            if cached_optimization:
                self._update_cache_hit_rate(CacheType.CONTEXT_CACHE)
                return cached_optimization['optimized_context'], cached_optimization['savings']
            
            # Perform context optimization
            optimized_context = await self._optimize_context_tokens(context, target_tokens)
            
            # Calculate cost savings
            original_tokens = self._estimate_tokens(context)
            optimized_tokens = self._estimate_tokens(optimized_context)
            token_savings = original_tokens - optimized_tokens
            cost_savings = token_savings * self.input_token_cost
            
            # Cache the optimization
            optimization_data = {
                'optimized_context': optimized_context,
                'savings': cost_savings,
                'token_reduction': token_savings
            }
            
            self.valkey_manager.cache_data(
                cache_key,
                optimization_data,
                ttl=self.cache_ttl * 2  # Longer TTL for context optimizations
            )
            
            return optimized_context, cost_savings
            
        except Exception as e:
            self.logger.error(f"Failed to optimize context: {e}")
            return context, 0.0
    
    async def get_session_cost_analysis(self, doc_id: str) -> Dict[str, Any]:
        """Get detailed cost analysis for a document session"""
        if doc_id not in self.session_costs:
            return {"error": "Session not found"}
        
        session_metrics = self.session_costs[doc_id]
        
        # Calculate efficiency metrics
        total_cost = session_metrics.total_cost_usd
        potential_cost = (session_metrics.total_input_tokens * self.input_token_cost + 
                         session_metrics.total_output_tokens * self.output_token_cost)
        
        efficiency_ratio = session_metrics.cache_savings_usd / max(potential_cost, 0.001)
        
        # Get session-specific cache hits
        session_cache_hits = await self._get_session_cache_hits(doc_id)
        
        return {
            'session_id': doc_id,
            'total_requests': session_metrics.total_requests,
            'total_cost_usd': total_cost,
            'potential_cost_usd': potential_cost,
            'cache_savings_usd': session_metrics.cache_savings_usd,
            'efficiency_ratio': efficiency_ratio,
            'average_cost_per_request': total_cost / max(session_metrics.total_requests, 1),
            'cache_hit_rate': session_cache_hits / max(session_metrics.total_requests, 1),
            'input_tokens': session_metrics.total_input_tokens,
            'output_tokens': session_metrics.total_output_tokens,
            'average_context_tokens': session_metrics.average_context_tokens
        }
    
    def get_global_cost_summary(self) -> Dict[str, Any]:
        """Get global cost optimization summary"""
        total_potential_cost = (self.cost_metrics.total_input_tokens * self.input_token_cost + 
                               self.cost_metrics.total_output_tokens * self.output_token_cost)
        
        return {
            'total_requests': self.cost_metrics.total_requests,
            'total_cost_usd': self.cost_metrics.total_cost_usd,
            'total_potential_cost_usd': total_potential_cost,
            'total_savings_usd': self.cost_metrics.cache_savings_usd,
            'overall_efficiency': self.cost_metrics.cache_savings_usd / max(total_potential_cost, 0.001),
            'cache_hit_rates': dict(self.cache_hit_rates),
            'average_request_cost': self.cost_metrics.total_cost_usd / max(self.cost_metrics.total_requests, 1),
            'active_sessions': len(self.session_costs)
        }
    
    # Helper methods
    
    def _generate_translation_cache_key(self, korean_text: str, context_hash: str) -> str:
        """Generate cache key for translation"""
        key_string = f"{korean_text}:{context_hash}"
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]
    
    def _generate_context_hash(self, context: str) -> str:
        """Generate hash for context"""
        return hashlib.md5(context.encode()).hexdigest()
    
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for token usage"""
        return (input_tokens * self.input_token_cost + 
                output_tokens * self.output_token_cost)
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        # Rough estimation: 1 token ≈ 3.5 characters for Korean/English mixed text
        return len(text) // 3
    
    async def _optimize_context_tokens(self, context: str, target_tokens: int) -> str:
        """Optimize context to target token count"""
        # Simple optimization: truncate while preserving key sections
        lines = context.split('\n')
        optimized_lines = []
        current_tokens = 0
        
        # Always include headers and critical terms
        for line in lines:
            line_tokens = self._estimate_tokens(line)
            if (current_tokens + line_tokens <= target_tokens or 
                any(keyword in line.upper() for keyword in ['LOCKED', 'CRITICAL', 'KEY TERMS'])):
                optimized_lines.append(line)
                current_tokens += line_tokens
            elif current_tokens < target_tokens * 0.8:  # Still have room
                # Truncate line to fit
                remaining_tokens = target_tokens - current_tokens
                max_chars = remaining_tokens * 3
                if len(line) > max_chars:
                    line = line[:max_chars].rsplit(' ', 1)[0] + '...'
                optimized_lines.append(line)
                break
        
        return '\n'.join(optimized_lines)
    
    async def _is_context_similar(self, hash1: str, hash2: str) -> bool:
        """Check if two context hashes are similar enough for cache reuse"""
        # Simple check: exact match for now, could be enhanced with similarity analysis
        return hash1 == hash2
    
    def _serialize_cached_translation(self, cached_translation: CachedTranslation) -> Dict[str, Any]:
        """Serialize cached translation for storage"""
        return {
            'korean_text': cached_translation.korean_text,
            'english_translation': cached_translation.english_translation,
            'context_hash': cached_translation.context_hash,
            'model_used': cached_translation.model_used,
            'timestamp': cached_translation.timestamp.isoformat(),
            'confidence_score': cached_translation.confidence_score,
            'usage_count': cached_translation.usage_count,
            'cost_saved_usd': cached_translation.cost_saved_usd
        }
    
    def _deserialize_cached_translation(self, data: Dict[str, Any]) -> Optional[CachedTranslation]:
        """Deserialize cached translation from storage"""
        try:
            return CachedTranslation(
                korean_text=data['korean_text'],
                english_translation=data['english_translation'],
                context_hash=data['context_hash'],
                model_used=data['model_used'],
                timestamp=datetime.fromisoformat(data['timestamp']),
                confidence_score=data['confidence_score'],
                usage_count=data.get('usage_count', 1),
                cost_saved_usd=data.get('cost_saved_usd', 0.0)
            )
        except Exception as e:
            self.logger.warning(f"Failed to deserialize cached translation: {e}")
            return None
    
    async def _update_cached_translation(self, cache_key: str, cached_translation: CachedTranslation):
        """Update cached translation usage statistics"""
        serialized_data = self._serialize_cached_translation(cached_translation)
        self.valkey_manager.cache_data(cache_key, serialized_data, ttl=self.cache_ttl)
    
    def _update_cache_hit_rate(self, cache_type: CacheType):
        """Update cache hit rate for specific cache type"""
        current_rate = self.cache_hit_rates[cache_type]
        self.cache_hit_rates[cache_type] = (current_rate * 0.9) + (1.0 * 0.1)  # Exponential moving average
    
    async def _get_session_cache_hits(self, doc_id: str) -> int:
        """Get cache hit count for specific session"""
        # This would be tracked separately in a real implementation
        return self.session_costs.get(doc_id, CostMetrics()).cache_hits