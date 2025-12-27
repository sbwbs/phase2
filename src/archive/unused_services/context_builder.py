"""
Context Builder for Phase 2 MVP - Smart Context Assembly Pipeline

This module orchestrates the assembly of optimized translation contexts by combining
glossary search results, session data from Valkey, and previous translations into
prompts that stay under 500 tokens while maintaining translation quality.

Key Features:
- Integration with completed glossary search engine (CE-001)
- Integration with Valkey session management (BE-004)
- Priority-based context assembly with token optimization
- 90%+ token reduction from baseline (20k+ tokens → <500 tokens)
- Adaptive context adjustment based on content complexity
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from datetime import datetime
import asyncio
from pathlib import Path

from token_optimizer import (
    TokenOptimizer, ContextComponent, ContextPriority, TokenOptimizationResult,
    create_source_component, create_glossary_component, create_locked_terms_component,
    create_previous_context_component, create_instructions_component
)
from memory.cached_glossary_search import CachedGlossarySearch
from memory.valkey_manager import ValkeyManager
from memory.session_manager import SessionManager


@dataclass
class ContextRequest:
    """Request for building translation context"""
    source_text: str
    segment_id: str
    doc_id: str
    source_language: str = "korean"
    target_language: str = "english" 
    domain: str = "clinical_trial"
    max_glossary_terms: int = 10
    include_previous_context: bool = True
    optimization_target: int = 500  # Target token limit
    target_model: Optional[str] = None  # Target model for optimization (e.g., "gpt-5")


@dataclass
class ContextBuildResult:
    """Result of context building process"""
    optimized_context: str
    token_count: int
    glossary_terms_included: int
    locked_terms_included: int
    previous_segments_included: int
    optimization_result: TokenOptimizationResult
    performance_metrics: Dict[str, Any]
    cache_hit_rate: float
    build_time_ms: float


class ContextBuilder:
    """Smart context assembly pipeline for translation optimization"""
    
    def __init__(self,
                 glossary_search: CachedGlossarySearch,
                 valkey_manager: ValkeyManager,
                 session_manager: SessionManager,
                 default_model: str = "gpt-4o",
                 default_token_limit: int = 500,
                 enable_caching: bool = True,
                 cache_ttl: int = 3600):
        """
        Initialize context builder with integrated components
        
        Args:
            glossary_search: Cached glossary search engine (CE-001)
            valkey_manager: Valkey session manager (BE-004)
            session_manager: Document session manager
            default_model: Default GPT model for token optimization
            default_token_limit: Default token limit for contexts
            enable_caching: Enable context caching
            cache_ttl: Cache TTL in seconds
        """
        self.glossary_search = glossary_search
        self.valkey_manager = valkey_manager
        self.session_manager = session_manager
        self.token_optimizer = TokenOptimizer(
            model_name=default_model,
            target_token_limit=default_token_limit
        )
        
        self.enable_caching = enable_caching
        self.cache_ttl = cache_ttl
        
        self.logger = logging.getLogger(__name__)
        
        # Performance tracking
        self.build_count = 0
        self.total_build_time = 0.0
        self.cache_hits = 0
        self.average_token_reduction = 0.0
        
        self.logger.info("ContextBuilder initialized with integrated components")
    
    async def build_context(self, request: ContextRequest) -> ContextBuildResult:
        """
        Build optimized translation context for a segment
        
        Args:
            request: Context build request
            
        Returns:
            ContextBuildResult with optimized context and metrics
        """
        start_time = datetime.now()
        
        try:
            # Check cache first if enabled
            if self.enable_caching:
                cached_result = await self._get_cached_context(request)
                if cached_result:
                    self.cache_hits += 1
                    build_time = (datetime.now() - start_time).total_seconds() * 1000
                    cached_result.build_time_ms = build_time
                    cached_result.cache_hit_rate = self.cache_hits / max(self.build_count + 1, 1)
                    return cached_result
            
            # Build context components with enhanced session integration
            components = await self._assemble_context_components(request)
            
            # GPT-5 OWL specific optimization: prioritize locked terms and recent context
            if hasattr(request, 'target_model') and 'gpt-5' in request.target_model.lower():
                components = self._reorder_components_for_gpt5(components)
            
            # Optimize token usage
            optimization_result = self.token_optimizer.optimize_context(
                components, request.optimization_target
            )
            
            # Calculate performance metrics
            performance_metrics = await self._calculate_performance_metrics(
                request, components, optimization_result
            )
            
            # Build final result
            build_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = ContextBuildResult(
                optimized_context=optimization_result.optimized_context,
                token_count=optimization_result.total_tokens,
                glossary_terms_included=self._count_component_type(
                    optimization_result.components_included, 'glossary'
                ),
                locked_terms_included=self._count_component_type(
                    optimization_result.components_included, 'locked'
                ),
                previous_segments_included=self._count_component_type(
                    optimization_result.components_included, 'previous'
                ),
                optimization_result=optimization_result,
                performance_metrics=performance_metrics,
                cache_hit_rate=self.cache_hits / max(self.build_count + 1, 1),
                build_time_ms=build_time
            )
            
            # Cache result if enabled
            if self.enable_caching:
                await self._cache_context_result(request, result)
            
            # Update performance tracking
            self._update_performance_tracking(result)
            
            self.logger.debug(f"Context built for segment {request.segment_id}: "
                            f"{result.token_count} tokens, {build_time:.1f}ms")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Context building failed for segment {request.segment_id}: {e}")
            raise
    
    async def _assemble_context_components(self, request: ContextRequest) -> List[ContextComponent]:
        """Assemble all context components from various sources"""
        components = []
        
        # 1. Source text component (always critical priority)
        source_component = create_source_component(
            request.source_text, request.segment_id
        )
        components.append(source_component)
        
        # 2. Get glossary terms from search engine (CE-001)
        glossary_component = await self._get_glossary_component(request)
        if glossary_component:
            components.append(glossary_component)
        
        # 3. Get locked terms from Valkey session (BE-004)
        locked_component = await self._get_locked_terms_component(request)
        if locked_component:
            components.append(locked_component)
        
        # 4. Get previous context if requested
        if request.include_previous_context:
            previous_component = await self._get_previous_context_component(request)
            if previous_component:
                components.append(previous_component)
        
        # 5. Add domain-specific instructions
        instructions_component = create_instructions_component(request.domain)
        components.append(instructions_component)
        
        self.logger.debug(f"Assembled {len(components)} context components for {request.segment_id}")
        
        return components
    
    async def _get_glossary_component(self, request: ContextRequest) -> Optional[ContextComponent]:
        """Get glossary terms component from search engine"""
        try:
            # Use cached glossary search with session context
            search_results, existing_terms = self.glossary_search.search_with_session_context(
                korean_text=request.source_text,
                doc_id=request.doc_id,
                segment_id=request.segment_id,
                max_results=request.max_glossary_terms
            )
            
            if not search_results:
                return None
            
            # Extract terms and relevance scores
            glossary_terms = []
            relevance_scores = []
            
            for result in search_results:
                # Format: Korean → English (Source: glossary_name)
                term_line = f"{result.term.korean} → {result.term.english}"
                if result.term.source:
                    term_line += f" (Source: {result.term.source})"
                
                glossary_terms.append(term_line)
                relevance_scores.append(result.relevance_score)
            
            component = create_glossary_component(glossary_terms, relevance_scores)
            
            # Add metadata about search performance
            component.metadata.update({
                'search_results_count': len(search_results),
                'existing_terms_in_doc': len(existing_terms),
                'cache_hit': False  # Will be updated by search engine
            })
            
            return component
            
        except Exception as e:
            self.logger.error(f"Failed to get glossary component: {e}")
            return None
    
    async def _get_locked_terms_component(self, request: ContextRequest) -> Optional[ContextComponent]:
        """Get locked terms component from Valkey session"""
        try:
            # Get all term mappings for this document
            term_mappings = self.valkey_manager.get_all_term_mappings(request.doc_id)
            
            if not term_mappings:
                return None
            
            # Filter for locked terms only
            locked_terms = {}
            for korean_term, mapping in term_mappings.items():
                if mapping.locked:
                    locked_terms[korean_term] = mapping.target_term
            
            if not locked_terms:
                return None
            
            component = create_locked_terms_component(locked_terms)
            
            # Add session metadata
            component.metadata.update({
                'total_term_mappings': len(term_mappings),
                'locked_terms_count': len(locked_terms),
                'doc_id': request.doc_id
            })
            
            return component
            
        except Exception as e:
            self.logger.error(f"Failed to get locked terms component: {e}")
            return None
    
    async def _get_previous_context_component(self, request: ContextRequest) -> Optional[ContextComponent]:
        """Get previous translation context component"""
        try:
            # Get recent segment history from session manager
            session_data = self.session_manager.get_session_data(request.doc_id)
            
            if not session_data or not hasattr(session_data, 'segment_history'):
                return None
            
            # Get last 2-3 segments for context
            segment_history = session_data.segment_history
            current_index = None
            
            # Find current segment index
            for i, (seg_id, korean, english) in enumerate(segment_history):
                if seg_id == request.segment_id:
                    current_index = i
                    break
            
            if current_index is None or current_index == 0:
                return None  # No previous context available
            
            # Get previous segments (up to 2)
            start_index = max(0, current_index - 2)
            previous_segments = []
            
            for i in range(start_index, current_index):
                seg_id, korean, english = segment_history[i]
                if korean and english:  # Only include completed translations
                    previous_segments.append((korean, english))
            
            if not previous_segments:
                return None
            
            component = create_previous_context_component(previous_segments, max_segments=2)
            
            # Add context metadata
            component.metadata.update({
                'previous_segments_available': len(previous_segments),
                'current_segment_index': current_index,
                'total_segments_in_session': len(segment_history)
            })
            
            return component
            
        except Exception as e:
            self.logger.error(f"Failed to get previous context component: {e}")
            return None
    
    async def _calculate_performance_metrics(self,
                                           request: ContextRequest,
                                           components: List[ContextComponent],
                                           optimization_result: TokenOptimizationResult) -> Dict[str, Any]:
        """Calculate detailed performance metrics"""
        
        # Calculate baseline token count (what it would be without optimization)
        baseline_tokens = sum(comp.token_count for comp in components)
        
        # Component type breakdown
        component_breakdown = {}
        for comp in components:
            comp_type = comp.component_type
            if comp_type not in component_breakdown:
                component_breakdown[comp_type] = {
                    'count': 0, 'tokens': 0, 'included': 0, 'excluded': 0
                }
            component_breakdown[comp_type]['count'] += 1
            component_breakdown[comp_type]['tokens'] += comp.token_count
        
        # Update included/excluded counts
        for comp in optimization_result.components_included:
            component_breakdown[comp.component_type]['included'] += 1
        
        for comp in optimization_result.components_excluded:
            component_breakdown[comp.component_type]['excluded'] += 1
        
        # Token reduction metrics
        token_reduction_absolute = baseline_tokens - optimization_result.total_tokens
        token_reduction_percent = (token_reduction_absolute / baseline_tokens * 100 
                                 if baseline_tokens > 0 else 0)
        
        # Efficiency metrics
        target_achievement = optimization_result.total_tokens <= request.optimization_target
        efficiency_ratio = optimization_result.total_tokens / request.optimization_target
        
        return {
            'baseline_tokens': baseline_tokens,
            'optimized_tokens': optimization_result.total_tokens,
            'token_reduction_absolute': token_reduction_absolute,
            'token_reduction_percent': token_reduction_percent,
            'target_achievement': target_achievement,
            'efficiency_ratio': efficiency_ratio,
            'component_breakdown': component_breakdown,
            'optimization_strategy': optimization_result.optimization_strategy,
            'components_total': len(components),
            'components_included': len(optimization_result.components_included),
            'components_excluded': len(optimization_result.components_excluded)
        }
    
    def _count_component_type(self, components: List[ContextComponent], component_type: str) -> int:
        """Count components of specific type"""
        count = 0
        for comp in components:
            if comp.component_type == component_type:
                if component_type == 'glossary':
                    # For glossary, count actual terms
                    count += comp.metadata.get('term_count', 1)
                elif component_type == 'locked':
                    count += comp.metadata.get('locked_count', 1)
                elif component_type == 'previous':
                    count += comp.metadata.get('segment_count', 1)
                else:
                    count += 1
        return count
    
    async def _get_cached_context(self, request: ContextRequest) -> Optional[ContextBuildResult]:
        """Get cached context result if available"""
        if not self.enable_caching:
            return None
        
        try:
            # Generate cache key based on request parameters
            cache_key = self._generate_context_cache_key(request)
            
            # Try to get from Valkey cache
            cached_data = self.valkey_manager.get_cached_data(
                f"context_cache:{cache_key}"
            )
            
            if cached_data:
                # Deserialize and return cached result
                # Note: In production, you'd want proper serialization
                self.logger.debug(f"Cache hit for context {request.segment_id}")
                return cached_data  # Placeholder - implement proper serialization
            
        except Exception as e:
            self.logger.warning(f"Failed to get cached context: {e}")
        
        return None
    
    async def _cache_context_result(self, request: ContextRequest, result: ContextBuildResult):
        """Cache context result for future use"""
        if not self.enable_caching:
            return
        
        try:
            cache_key = self._generate_context_cache_key(request)
            
            # Cache the result (simplified - implement proper serialization in production)
            self.valkey_manager.cache_data(
                f"context_cache:{cache_key}",
                result,  # Should be serialized properly
                ttl=self.cache_ttl
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to cache context result: {e}")
    
    def _generate_context_cache_key(self, request: ContextRequest) -> str:
        """Generate cache key for context request"""
        import hashlib
        
        key_components = [
            request.source_text,
            request.doc_id,
            request.domain,
            str(request.max_glossary_terms),
            str(request.include_previous_context),
            str(request.optimization_target)
        ]
        
        key_string = "|".join(key_components)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _update_performance_tracking(self, result: ContextBuildResult):
        """Update internal performance tracking"""
        self.build_count += 1
        self.total_build_time += result.build_time_ms
        
        # Update average token reduction
        token_reduction = result.performance_metrics['token_reduction_percent']
        self.average_token_reduction = (
            (self.average_token_reduction * (self.build_count - 1) + token_reduction) 
            / self.build_count
        )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        return {
            'build_count': self.build_count,
            'total_build_time_ms': self.total_build_time,
            'average_build_time_ms': self.total_build_time / max(self.build_count, 1),
            'cache_hit_rate': self.cache_hits / max(self.build_count, 1),
            'average_token_reduction_percent': self.average_token_reduction,
            'glossary_search_stats': self.glossary_search.get_cache_statistics(),
            'valkey_stats': self.valkey_manager.get_performance_stats(),
            'token_optimizer_stats': self.token_optimizer.get_cache_stats()
        }
    
    async def build_batch_contexts(self, 
                                 requests: List[ContextRequest],
                                 max_concurrent: int = 10) -> List[ContextBuildResult]:
        """
        Build contexts for multiple requests concurrently
        
        Args:
            requests: List of context requests
            max_concurrent: Maximum concurrent builds
            
        Returns:
            List of context build results
        """
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def build_with_semaphore(request):
            async with semaphore:
                return await self.build_context(request)
        
        # Execute all builds concurrently
        tasks = [build_with_semaphore(request) for request in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        successful_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Batch build failed for request {i}: {result}")
                # Create a failed result placeholder
                failed_result = ContextBuildResult(
                    optimized_context="",
                    token_count=0,
                    glossary_terms_included=0,
                    locked_terms_included=0,
                    previous_segments_included=0,
                    optimization_result=None,
                    performance_metrics={'error': str(result)},
                    cache_hit_rate=0.0,
                    build_time_ms=0.0
                )
                successful_results.append(failed_result)
            else:
                successful_results.append(result)
        
        self.logger.info(f"Batch context build completed: {len(requests)} requests, "
                        f"{len([r for r in results if not isinstance(r, Exception)])} successful")
        
        return successful_results
    
    def _reorder_components_for_gpt5(self, components: List[ContextComponent]) -> List[ContextComponent]:
        """
        Reorder components for optimal GPT-5 OWL processing
        
        GPT-5 OWL benefits from:
        1. Locked terms first (highest consistency priority)
        2. Relevant glossary terms  
        3. Previous context
        4. Instructions last
        """
        ordered_components = []
        locked_components = []
        glossary_components = []
        previous_components = []
        instruction_components = []
        source_components = []
        
        # Categorize components
        for comp in components:
            if comp.component_type == 'locked':
                locked_components.append(comp)
            elif comp.component_type == 'glossary':
                glossary_components.append(comp)
            elif comp.component_type == 'previous':
                previous_components.append(comp)
            elif comp.component_type == 'instructions':
                instruction_components.append(comp)
            elif comp.component_type == 'source':
                source_components.append(comp)
            else:
                ordered_components.append(comp)
        
        # Optimal order for GPT-5 OWL medical translation
        ordered_components.extend(locked_components)      # Consistency critical
        ordered_components.extend(glossary_components)    # Terminology reference
        ordered_components.extend(previous_components)    # Context continuity
        ordered_components.extend(source_components)      # Source text
        ordered_components.extend(instruction_components) # Processing instructions
        
        return ordered_components
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on all integrated components"""
        health_status = {"status": "healthy", "components": {}}
        
        # Check glossary search engine
        try:
            search_health = self.glossary_search.health_check()
            health_status["components"]["glossary_search"] = search_health
            if search_health["status"] != "healthy":
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["components"]["glossary_search"] = {"status": "error", "error": str(e)}
            health_status["status"] = "unhealthy"
        
        # Check Valkey manager
        try:
            valkey_health = self.valkey_manager.health_check()
            health_status["components"]["valkey_manager"] = valkey_health
            if valkey_health["status"] != "healthy":
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["components"]["valkey_manager"] = {"status": "error", "error": str(e)}
            health_status["status"] = "unhealthy"
        
        # Check token optimizer
        try:
            optimizer_stats = self.token_optimizer.get_cache_stats()
            health_status["components"]["token_optimizer"] = {
                "status": "healthy",
                "cache_entries": optimizer_stats["cache_entries"]
            }
        except Exception as e:
            health_status["components"]["token_optimizer"] = {"status": "error", "error": str(e)}
            health_status["status"] = "degraded"
        
        # Add performance metrics
        health_status["performance"] = {
            "build_count": self.build_count,
            "average_build_time_ms": self.total_build_time / max(self.build_count, 1),
            "cache_hit_rate": self.cache_hits / max(self.build_count, 1),
            "average_token_reduction": self.average_token_reduction
        }
        
        return health_status


# Utility functions for common context building patterns

async def build_simple_context(korean_text: str,
                             glossary_search: CachedGlossarySearch,
                             target_tokens: int = 500) -> str:
    """
    Build a simple optimized context for quick translation
    
    Args:
        korean_text: Source Korean text
        glossary_search: Glossary search engine
        target_tokens: Target token limit
        
    Returns:
        Optimized context string
    """
    # Create minimal context builder
    token_optimizer = TokenOptimizer(target_token_limit=target_tokens)
    
    # Create basic components
    components = []
    
    # Source text
    source_comp = create_source_component(korean_text)
    components.append(source_comp)
    
    # Quick glossary search
    try:
        search_results = glossary_search.search(korean_text, max_results=5)
        if search_results:
            terms = [f"{r.term.korean} → {r.term.english}" for r in search_results]
            glossary_comp = create_glossary_component(terms)
            components.append(glossary_comp)
    except Exception:
        pass  # Skip glossary if search fails
    
    # Basic instructions
    instructions_comp = create_instructions_component()
    components.append(instructions_comp)
    
    # Optimize and return
    result = token_optimizer.optimize_context(components, target_tokens)
    return result.optimized_context


def create_context_request(korean_text: str,
                         segment_id: str,
                         doc_id: str,
                         **kwargs) -> ContextRequest:
    """
    Create a context request with sensible defaults
    
    Args:
        korean_text: Source Korean text
        segment_id: Segment identifier
        doc_id: Document identifier
        **kwargs: Additional parameters
        
    Returns:
        ContextRequest object
    """
    return ContextRequest(
        source_text=korean_text,
        segment_id=segment_id,
        doc_id=doc_id,
        source_language=kwargs.get('source_language', 'korean'),
        target_language=kwargs.get('target_language', 'english'),
        domain=kwargs.get('domain', 'clinical_trial'),
        max_glossary_terms=kwargs.get('max_glossary_terms', 10),
        include_previous_context=kwargs.get('include_previous_context', True),
        optimization_target=kwargs.get('optimization_target', 500)
    )