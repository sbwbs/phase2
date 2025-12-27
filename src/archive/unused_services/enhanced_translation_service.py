"""
Enhanced Translation Service for Phase 2 MVP

This service integrates all Phase 2 components (smart context building, Valkey session management,
cached glossary search) while maintaining full backward compatibility with Phase 1 operation.

Key Features:
- Dual mode operation: Phase 1 (full context) and Phase 2 (smart context)
- Integration with completed CE-001, CE-002, and BE-004 components
- Session-based document processing for 1,400+ segment workflows
- Advanced LLM provider support (GPT-5 family, o3 model constraints)
- Performance monitoring and comparison between phases
- Seamless fallback to Phase 1 mode if Phase 2 components unavailable
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Phase 1 compatibility imports
import sys
import os
sys.path.append(str(Path(__file__).parent.parent.parent / "phase1" / "src"))

from translation_service import (
    TranslationService as Phase1TranslationService,
    TranslationRequest,
    TranslationResult,
    BatchTranslationRequest
)

# Phase 2 component imports
from context_builder import ContextBuilder, ContextRequest, ContextBuildResult
from glossary_search import GlossarySearchEngine, create_sample_glossary
from memory.cached_glossary_search import CachedGlossarySearch
from memory.valkey_manager import ValkeyManager, SessionMetadata
from memory.session_manager import SessionManager


class OperationMode(Enum):
    """Translation service operation modes"""
    PHASE1_FULL_CONTEXT = "phase1_full_context"
    PHASE2_SMART_CONTEXT = "phase2_smart_context"
    AUTO_DETECT = "auto_detect"


@dataclass
class EnhancedTranslationRequest:
    """Enhanced translation request with Phase 2 capabilities"""
    korean_text: str
    model_name: str
    segment_id: str
    doc_id: str
    
    # Phase 1 compatibility fields
    glossary_context: str = ""
    tm_context: str = ""
    previous_context: str = ""
    
    # Phase 2 specific fields
    operation_mode: OperationMode = OperationMode.AUTO_DETECT
    context_optimization_target: int = 500
    enable_session_tracking: bool = True
    max_glossary_terms: int = 10
    domain: str = "clinical_trial"
    
    # Performance tracking
    track_performance: bool = True


@dataclass
class EnhancedTranslationResult:
    """Enhanced translation result with Phase 2 metrics"""
    # Core translation result
    english_translation: str
    model_used: str
    tokens_used: Optional[int] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None
    
    # Phase 2 enhancements
    operation_mode_used: OperationMode = OperationMode.PHASE1_FULL_CONTEXT
    context_build_result: Optional[ContextBuildResult] = None
    session_updated: bool = False
    cache_hits: int = 0
    
    # Performance comparison
    phase1_token_estimate: Optional[int] = None
    token_reduction_percent: Optional[float] = None
    context_build_time_ms: Optional[float] = None
    
    # Quality metrics
    term_consistency_score: Optional[float] = None
    glossary_terms_used: int = 0


class EnhancedTranslationService:
    """Production-ready translation service with Phase 2 smart context capabilities"""
    
    def __init__(self,
                 valkey_host: str = "localhost",
                 valkey_port: int = 6379,
                 valkey_db: int = 0,
                 glossary_files: Optional[List[str]] = None,
                 enable_valkey: bool = True,
                 enable_context_caching: bool = True,
                 fallback_to_phase1: bool = True,
                 default_mode: OperationMode = OperationMode.AUTO_DETECT):
        """
        Initialize enhanced translation service
        
        Args:
            valkey_host: Valkey server host
            valkey_port: Valkey server port  
            valkey_db: Valkey database number
            glossary_files: List of glossary file paths
            enable_valkey: Enable Valkey integration
            enable_context_caching: Enable context caching
            fallback_to_phase1: Fallback to Phase 1 mode on errors
            default_mode: Default operation mode
        """
        self.logger = logging.getLogger(__name__)
        self.fallback_to_phase1 = fallback_to_phase1
        self.default_mode = default_mode
        
        # Initialize Phase 1 service for compatibility
        self.phase1_service = Phase1TranslationService()
        
        # Initialize Phase 2 components
        self.phase2_available = False
        self.valkey_manager = None
        self.session_manager = None
        self.glossary_search = None
        self.cached_glossary_search = None
        self.context_builder = None
        
        # Performance tracking
        self.translation_count = 0
        self.phase1_count = 0
        self.phase2_count = 0
        self.total_tokens_saved = 0
        self.error_count = 0
        
        self.logger.info("Initializing Enhanced Translation Service")
        
        # Initialize Phase 2 components
        self._initialize_phase2_components(
            valkey_host, valkey_port, valkey_db,
            glossary_files, enable_valkey, enable_context_caching
        )
    
    def _initialize_phase2_components(self,
                                    valkey_host: str,
                                    valkey_port: int,
                                    valkey_db: int,
                                    glossary_files: Optional[List[str]],
                                    enable_valkey: bool,
                                    enable_context_caching: bool):
        """Initialize Phase 2 components with error handling"""
        try:
            # Initialize Valkey manager
            if enable_valkey:
                self.valkey_manager = ValkeyManager(
                    host=valkey_host,
                    port=valkey_port,
                    db=valkey_db
                )
                self.logger.info("Valkey manager initialized")
            
            # Initialize session manager
            if self.valkey_manager:
                self.session_manager = SessionManager(self.valkey_manager)
                self.logger.info("Session manager initialized")
            
            # Initialize glossary search engine
            self.glossary_search = GlossarySearchEngine()
            
            # Load glossary files or create sample data
            if glossary_files:
                loaded_count = self.glossary_search.load_glossaries(glossary_files)
                self.logger.info(f"Loaded {loaded_count} glossary terms from files")
            else:
                # Use sample glossary for testing
                sample_terms = create_sample_glossary()
                self.glossary_search.add_terms(sample_terms)
                self.logger.info(f"Loaded {len(sample_terms)} sample glossary terms")
            
            # Initialize cached glossary search
            if self.valkey_manager:
                self.cached_glossary_search = CachedGlossarySearch(
                    glossary_search_engine=self.glossary_search,
                    valkey_manager=self.valkey_manager,
                    enable_preloading=True
                )
                self.logger.info("Cached glossary search initialized")
            
            # Initialize context builder
            if (self.cached_glossary_search and 
                self.valkey_manager and 
                self.session_manager):
                
                self.context_builder = ContextBuilder(
                    glossary_search=self.cached_glossary_search,
                    valkey_manager=self.valkey_manager,
                    session_manager=self.session_manager,
                    enable_caching=enable_context_caching
                )
                self.logger.info("Context builder initialized")
                
                self.phase2_available = True
                self.logger.info("Phase 2 components fully initialized")
            
        except Exception as e:
            self.logger.error(f"Phase 2 initialization failed: {e}")
            if not self.fallback_to_phase1:
                raise
            self.logger.warning("Falling back to Phase 1 mode only")
    
    def get_available_models(self) -> List[str]:
        """Get list of available blinded model names"""
        return self.phase1_service.get_available_models()
    
    async def translate(self, request: EnhancedTranslationRequest) -> EnhancedTranslationResult:
        """
        Main translation method with intelligent mode selection
        
        Args:
            request: Enhanced translation request
            
        Returns:
            Enhanced translation result with Phase 2 metrics
        """
        start_time = time.time()
        self.translation_count += 1
        
        # Determine operation mode
        operation_mode = self._determine_operation_mode(request)
        
        try:
            if operation_mode == OperationMode.PHASE2_SMART_CONTEXT:
                result = await self._translate_phase2(request)
                self.phase2_count += 1
            else:
                result = await self._translate_phase1(request)
                self.phase1_count += 1
            
            result.operation_mode_used = operation_mode
            result.processing_time = time.time() - start_time
            
            # Update session if enabled
            if (request.enable_session_tracking and 
                self.session_manager and 
                not result.error):
                await self._update_session_with_result(request, result)
            
            return result
            
        except Exception as e:
            self.error_count += 1
            error_msg = str(e)
            
            self.logger.error(f"Translation failed for segment {request.segment_id}: {error_msg}")
            
            # Try fallback if Phase 2 failed
            if (operation_mode == OperationMode.PHASE2_SMART_CONTEXT and 
                self.fallback_to_phase1):
                
                self.logger.info("Attempting Phase 1 fallback")
                try:
                    result = await self._translate_phase1(request)
                    result.operation_mode_used = OperationMode.PHASE1_FULL_CONTEXT
                    result.processing_time = time.time() - start_time
                    result.error = f"Phase 2 failed, used Phase 1 fallback: {error_msg}"
                    return result
                except Exception as fallback_error:
                    error_msg = f"Both Phase 2 and Phase 1 failed: {error_msg}, {fallback_error}"
            
            return EnhancedTranslationResult(
                english_translation="",
                model_used=request.model_name,
                error=error_msg,
                processing_time=time.time() - start_time,
                operation_mode_used=operation_mode
            )
    
    def _determine_operation_mode(self, request: EnhancedTranslationRequest) -> OperationMode:
        """Determine which operation mode to use"""
        if request.operation_mode != OperationMode.AUTO_DETECT:
            return request.operation_mode
        
        # Auto-detect based on component availability
        if self.phase2_available and request.doc_id and request.segment_id:
            return OperationMode.PHASE2_SMART_CONTEXT
        else:
            return OperationMode.PHASE1_FULL_CONTEXT
    
    async def _translate_phase2(self, request: EnhancedTranslationRequest) -> EnhancedTranslationResult:
        """Translate using Phase 2 smart context"""
        if not self.phase2_available:
            raise RuntimeError("Phase 2 components not available")
        
        # Build optimized context
        context_request = ContextRequest(
            source_text=request.korean_text,
            segment_id=request.segment_id,
            doc_id=request.doc_id,
            domain=request.domain,
            max_glossary_terms=request.max_glossary_terms,
            optimization_target=request.context_optimization_target
        )
        
        context_result = await self.context_builder.build_context(context_request)
        
        # Create Phase 1 compatible request with optimized context
        phase1_request = TranslationRequest(
            korean_text=request.korean_text,
            glossary_context=self._extract_glossary_context(context_result),
            tm_context=self._extract_tm_context(context_result),
            model_name=request.model_name,
            previous_context=self._extract_previous_context(context_result)
        )
        
        # Execute translation using Phase 1 service
        translation_result = await self.phase1_service.translate(phase1_request)
        
        # Calculate token savings
        phase1_estimate = self._estimate_phase1_tokens(request)
        token_reduction = None
        if phase1_estimate and context_result.token_count:
            token_reduction = ((phase1_estimate - context_result.token_count) / 
                             phase1_estimate * 100)
            self.total_tokens_saved += phase1_estimate - context_result.token_count
        
        # Calculate term consistency score
        term_consistency_score = await self._calculate_term_consistency(request, translation_result)
        
        return EnhancedTranslationResult(
            english_translation=translation_result.english_translation,
            model_used=translation_result.model_used,
            tokens_used=translation_result.tokens_used,
            error=translation_result.error,
            context_build_result=context_result,
            session_updated=False,  # Will be updated later
            cache_hits=self._count_cache_hits(context_result),
            phase1_token_estimate=phase1_estimate,
            token_reduction_percent=token_reduction,
            context_build_time_ms=context_result.build_time_ms,
            term_consistency_score=term_consistency_score,
            glossary_terms_used=context_result.glossary_terms_included
        )
    
    async def _translate_phase1(self, request: EnhancedTranslationRequest) -> EnhancedTranslationResult:
        """Translate using Phase 1 full context mode"""
        
        # Create Phase 1 request
        phase1_request = TranslationRequest(
            korean_text=request.korean_text,
            glossary_context=request.glossary_context,
            tm_context=request.tm_context,
            model_name=request.model_name,
            previous_context=request.previous_context
        )
        
        # Execute translation
        translation_result = await self.phase1_service.translate(phase1_request)
        
        return EnhancedTranslationResult(
            english_translation=translation_result.english_translation,
            model_used=translation_result.model_used,
            tokens_used=translation_result.tokens_used,
            error=translation_result.error,
            operation_mode_used=OperationMode.PHASE1_FULL_CONTEXT
        )
    
    def _extract_glossary_context(self, context_result: ContextBuildResult) -> str:
        """Extract glossary context from optimized context"""
        # Simple extraction - in production, you might want more sophisticated parsing
        lines = context_result.optimized_context.split('\n')
        glossary_lines = []
        
        in_glossary_section = False
        for line in lines:
            if 'GLOSSARY' in line.upper() or 'KEY TERMS' in line.upper():
                in_glossary_section = True
                continue
            elif in_glossary_section and (line.startswith('PREVIOUS') or 
                                        line.startswith('INSTRUCTIONS') or
                                        line.startswith('KOREAN TEXT')):
                break
            elif in_glossary_section and line.strip():
                glossary_lines.append(line.strip())
        
        return '\n'.join(glossary_lines)
    
    def _extract_tm_context(self, context_result: ContextBuildResult) -> str:
        """Extract TM context from optimized context"""
        # Placeholder - Phase 2 context doesn't separate TM
        return ""
    
    def _extract_previous_context(self, context_result: ContextBuildResult) -> str:
        """Extract previous context from optimized context"""
        lines = context_result.optimized_context.split('\n')
        previous_lines = []
        
        in_previous_section = False
        for line in lines:
            if 'PREVIOUS' in line.upper() or 'CONTEXT' in line.upper():
                in_previous_section = True
                continue
            elif in_previous_section and (line.startswith('GLOSSARY') or 
                                        line.startswith('INSTRUCTIONS') or
                                        line.startswith('KOREAN TEXT')):
                break
            elif in_previous_section and line.strip():
                previous_lines.append(line.strip())
        
        return '\n'.join(previous_lines)
    
    def _estimate_phase1_tokens(self, request: EnhancedTranslationRequest) -> Optional[int]:
        """Estimate tokens that would be used in Phase 1 mode"""
        # Rough estimation based on Phase 1 context patterns
        estimated_tokens = (
            len(request.korean_text) // 2 +  # Korean text
            len(request.glossary_context) // 3 +  # Glossary context
            len(request.tm_context) // 3 +  # TM context
            len(request.previous_context) // 3 +  # Previous context
            200  # Instructions and formatting
        )
        return max(estimated_tokens, 100)  # Minimum estimate
    
    def _count_cache_hits(self, context_result: ContextBuildResult) -> int:
        """Count cache hits from context building"""
        cache_hits = 0
        if hasattr(context_result, 'cache_hit_rate'):
            cache_hits = int(context_result.cache_hit_rate * 10)  # Approximate
        return cache_hits
    
    async def _calculate_term_consistency(self, 
                                        request: EnhancedTranslationRequest, 
                                        translation_result: TranslationResult) -> Optional[float]:
        """Calculate term consistency score"""
        if not self.valkey_manager:
            return None
        
        try:
            # Get existing term mappings
            term_mappings = self.valkey_manager.get_all_term_mappings(request.doc_id)
            
            if not term_mappings:
                return 1.0  # Perfect score for first translation
            
            # Simple consistency check - count matching terms
            # In production, you'd want more sophisticated analysis
            consistency_score = 0.8  # Placeholder score
            
            return consistency_score
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate term consistency: {e}")
            return None
    
    async def _update_session_with_result(self, 
                                        request: EnhancedTranslationRequest,
                                        result: EnhancedTranslationResult):
        """Update session with translation result"""
        if not self.session_manager or result.error:
            return
        
        try:
            # Extract key terms from translation for consistency tracking
            await self._extract_and_store_terms(request, result)
            
            # Update session progress
            session_data = self.session_manager.get_session_data(request.doc_id)
            if session_data:
                processed_count = getattr(session_data, 'processed_segments', 0) + 1
                self.valkey_manager.update_session(
                    request.doc_id,
                    processed_segments=processed_count
                )
            
            result.session_updated = True
            
        except Exception as e:
            self.logger.warning(f"Failed to update session: {e}")
    
    async def _extract_and_store_terms(self, 
                                     request: EnhancedTranslationRequest,
                                     result: EnhancedTranslationResult):
        """Extract and store terms for consistency tracking"""
        # Simple term extraction - in production, use more sophisticated NLP
        korean_words = request.korean_text.split()
        english_words = result.english_translation.split()
        
        # Store significant terms (length > 2)
        for korean_word in korean_words:
            if len(korean_word) > 2:
                # Simple mapping - in production, use alignment algorithms
                english_word = english_words[0] if english_words else korean_word
                
                self.valkey_manager.add_term_mapping(
                    doc_id=request.doc_id,
                    source_term=korean_word,
                    target_term=english_word,
                    segment_id=request.segment_id,
                    confidence=0.8
                )
    
    # ========== Batch Processing ==========
    
    async def translate_batch(self, 
                            requests: List[EnhancedTranslationRequest],
                            max_concurrent: int = 10) -> List[EnhancedTranslationResult]:
        """Translate multiple requests concurrently"""
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def translate_with_semaphore(request):
            async with semaphore:
                return await self.translate(request)
        
        # Execute all translations concurrently
        tasks = [translate_with_semaphore(request) for request in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_result = EnhancedTranslationResult(
                    english_translation="",
                    model_used=requests[i].model_name,
                    error=str(result),
                    operation_mode_used=OperationMode.PHASE1_FULL_CONTEXT
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)
        
        success_count = len([r for r in processed_results if not r.error])
        self.logger.info(f"Batch translation completed: {len(requests)} requests, "
                        f"{success_count} successful")
        
        return processed_results
    
    # ========== Session Management ==========
    
    async def start_document_session(self,
                                   doc_id: str,
                                   total_segments: int,
                                   source_language: str = "korean",
                                   target_language: str = "english") -> bool:
        """Start a new document translation session"""
        if not self.session_manager:
            self.logger.warning("Session manager not available")
            return False
        
        try:
            session_metadata = self.valkey_manager.create_session(
                doc_id=doc_id,
                source_language=source_language,
                target_language=target_language,
                total_segments=total_segments
            )
            
            self.logger.info(f"Started session for document {doc_id} with {total_segments} segments")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start session: {e}")
            return False
    
    async def get_session_status(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get session status and progress"""
        if not self.valkey_manager:
            return None
        
        try:
            session = self.valkey_manager.get_session(doc_id)
            if not session:
                return None
            
            term_mappings = self.valkey_manager.get_all_term_mappings(doc_id)
            
            return {
                'doc_id': session.doc_id,
                'status': session.status,
                'total_segments': session.total_segments,
                'processed_segments': session.processed_segments,
                'completion_percent': (session.processed_segments / session.total_segments * 100
                                     if session.total_segments > 0 else 0),
                'term_count': len(term_mappings),
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get session status: {e}")
            return None
    
    async def cleanup_session(self, doc_id: str) -> bool:
        """Clean up session data"""
        if not self.valkey_manager:
            return False
        
        try:
            return self.valkey_manager.cleanup_session(doc_id)
        except Exception as e:
            self.logger.error(f"Failed to cleanup session: {e}")
            return False
    
    # ========== Performance and Health ==========
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        phase1_percentage = (self.phase1_count / max(self.translation_count, 1)) * 100
        phase2_percentage = (self.phase2_count / max(self.translation_count, 1)) * 100
        
        summary = {
            'overall_stats': {
                'total_translations': self.translation_count,
                'phase1_count': self.phase1_count,
                'phase2_count': self.phase2_count,
                'phase1_percentage': phase1_percentage,
                'phase2_percentage': phase2_percentage,
                'error_count': self.error_count,
                'total_tokens_saved': self.total_tokens_saved
            },
            'phase2_availability': {
                'phase2_available': self.phase2_available,
                'valkey_manager': self.valkey_manager is not None,
                'context_builder': self.context_builder is not None,
                'cached_glossary_search': self.cached_glossary_search is not None
            }
        }
        
        # Add Phase 2 component stats if available
        if self.context_builder:
            summary['context_builder_stats'] = self.context_builder.get_performance_summary()
        
        if self.valkey_manager:
            summary['valkey_stats'] = self.valkey_manager.get_performance_stats()
        
        if self.cached_glossary_search:
            summary['glossary_search_stats'] = self.cached_glossary_search.get_cache_statistics()
        
        return summary
    
    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health_status = {"status": "healthy", "components": {}}
        
        # Check Phase 1 service
        try:
            phase1_models = self.phase1_service.get_available_models()
            health_status["components"]["phase1_service"] = {
                "status": "healthy",
                "available_models": len(phase1_models)
            }
        except Exception as e:
            health_status["components"]["phase1_service"] = {
                "status": "error",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # Check Phase 2 components
        if self.phase2_available:
            try:
                if self.context_builder:
                    context_health = self.context_builder.health_check()
                    health_status["components"]["context_builder"] = context_health
                    if context_health["status"] != "healthy":
                        health_status["status"] = "degraded"
                
                if self.valkey_manager:
                    valkey_health = self.valkey_manager.health_check()
                    health_status["components"]["valkey_manager"] = valkey_health
                    if valkey_health["status"] != "healthy":
                        health_status["status"] = "degraded"
                        
            except Exception as e:
                health_status["components"]["phase2_components"] = {
                    "status": "error",
                    "error": str(e)
                }
                health_status["status"] = "degraded"
        else:
            health_status["components"]["phase2_components"] = {
                "status": "unavailable",
                "note": "Running in Phase 1 mode only"
            }
        
        return health_status


# Convenience functions for creating requests

def create_enhanced_request(korean_text: str,
                          model_name: str,
                          segment_id: str,
                          doc_id: str,
                          **kwargs) -> EnhancedTranslationRequest:
    """Create enhanced translation request with defaults"""
    return EnhancedTranslationRequest(
        korean_text=korean_text,
        model_name=model_name,
        segment_id=segment_id,
        doc_id=doc_id,
        operation_mode=kwargs.get('operation_mode', OperationMode.AUTO_DETECT),
        context_optimization_target=kwargs.get('context_optimization_target', 500),
        enable_session_tracking=kwargs.get('enable_session_tracking', True),
        max_glossary_terms=kwargs.get('max_glossary_terms', 10),
        domain=kwargs.get('domain', 'clinical_trial'),
        track_performance=kwargs.get('track_performance', True)
    )


def create_batch_requests_from_segments(segments: List[Tuple[str, str]],  # (segment_id, korean_text)
                                      model_name: str,
                                      doc_id: str,
                                      **kwargs) -> List[EnhancedTranslationRequest]:
    """Create batch of enhanced requests from segment data"""
    requests = []
    
    for segment_id, korean_text in segments:
        request = create_enhanced_request(
            korean_text=korean_text,
            model_name=model_name,
            segment_id=segment_id,
            doc_id=doc_id,
            **kwargs
        )
        requests.append(request)
    
    return requests