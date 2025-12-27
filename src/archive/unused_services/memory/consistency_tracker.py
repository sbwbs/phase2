"""
Term Consistency Tracker for Phase 2 MVP

This module provides intelligent term consistency management with conflict detection,
resolution strategies, and integration with the glossary search engine.

Key Features:
- Real-time term consistency tracking
- Conflict detection and resolution
- Term frequency analysis
- Integration with glossary search
- Performance optimization for O(1) lookups
"""

import logging
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict, Counter

from .valkey_manager import ValkeyManager, TermMapping
from glossary_search import GlossarySearchEngine, SearchResult


class ConflictResolutionStrategy(Enum):
    """Term conflict resolution strategies"""
    FIRST_WINS = "first_wins"  # Keep first translation
    HIGHEST_CONFIDENCE = "highest_confidence"  # Use highest confidence translation
    MOST_FREQUENT = "most_frequent"  # Use most frequently occurring translation
    GLOSSARY_PREFERRED = "glossary_preferred"  # Prefer glossary matches
    MANUAL_REVIEW = "manual_review"  # Flag for manual review


@dataclass
class TermConflict:
    """Represents a term translation conflict"""
    source_term: str
    existing_translation: str
    conflicting_translation: str
    existing_confidence: float
    conflicting_confidence: float
    existing_segment: str
    conflicting_segment: str
    resolution_strategy: Optional[ConflictResolutionStrategy] = None
    resolved_translation: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None


@dataclass
class TermAnalytics:
    """Term usage analytics"""
    source_term: str
    translations: Dict[str, int]  # translation -> frequency
    total_occurrences: int
    first_seen: datetime
    last_seen: datetime
    segments_used: Set[str]
    confidence_scores: List[float]
    glossary_match: bool = False
    
    @property
    def most_frequent_translation(self) -> str:
        return max(self.translations.items(), key=lambda x: x[1])[0]
    
    @property
    def translation_consistency_score(self) -> float:
        """Score 0-1 indicating consistency (1 = single translation used)"""
        if not self.translations:
            return 0.0
        max_freq = max(self.translations.values())
        return max_freq / self.total_occurrences
    
    @property
    def average_confidence(self) -> float:
        return sum(self.confidence_scores) / len(self.confidence_scores) if self.confidence_scores else 0.0


class ConsistencyTracker:
    """Advanced term consistency tracking and conflict resolution"""
    
    def __init__(self, 
                 valkey_manager: ValkeyManager,
                 glossary_search_engine: Optional[GlossarySearchEngine] = None,
                 default_resolution_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.GLOSSARY_PREFERRED,
                 confidence_threshold: float = 0.8,
                 consistency_threshold: float = 0.7):
        """
        Initialize consistency tracker
        
        Args:
            valkey_manager: Valkey backend manager
            glossary_search_engine: Glossary search for conflict resolution
            default_resolution_strategy: Default conflict resolution strategy
            confidence_threshold: Minimum confidence for automatic resolution
            consistency_threshold: Minimum consistency score for term stability
        """
        self.valkey = valkey_manager
        self.glossary_search = glossary_search_engine
        self.default_resolution_strategy = default_resolution_strategy
        self.confidence_threshold = confidence_threshold
        self.consistency_threshold = consistency_threshold
        self.logger = logging.getLogger(__name__)
        
        # Performance tracking
        self.lookup_times: List[float] = []
        self.conflict_count = 0
        self.auto_resolved_count = 0
        self.manual_review_count = 0
        
        self.logger.info("ConsistencyTracker initialized")
    
    def track_term_usage(self, 
                        doc_id: str,
                        source_term: str,
                        target_term: str,
                        segment_id: str,
                        confidence: float = 1.0,
                        force_override: bool = False) -> Tuple[bool, Optional[TermConflict]]:
        """
        Track term usage and detect conflicts
        
        Args:
            doc_id: Document ID
            source_term: Source language term
            target_term: Target language term
            segment_id: Current segment ID
            confidence: Translation confidence score
            force_override: Force override existing mapping
            
        Returns:
            Tuple of (success, conflict_if_any)
        """
        start_time = time.time()
        
        try:
            # Check for existing mapping
            existing_mapping = self.valkey.get_term_mapping(doc_id, source_term)
            
            if existing_mapping and existing_mapping.target_term != target_term:
                if existing_mapping.locked and not force_override:
                    self.logger.info(f"Term {source_term} is locked to {existing_mapping.target_term}")
                    return False, None
                
                # Handle conflict
                conflict = self._handle_term_conflict(
                    doc_id, source_term, target_term, segment_id, 
                    confidence, existing_mapping
                )
                
                self.conflict_count += 1
                
                if conflict.resolved_translation:
                    # Use resolved translation
                    success = self.valkey.add_term_mapping(
                        doc_id, source_term, conflict.resolved_translation,
                        segment_id, confidence, lock_term=False
                    )
                    
                    if conflict.resolution_strategy != ConflictResolutionStrategy.MANUAL_REVIEW:
                        self.auto_resolved_count += 1
                    else:
                        self.manual_review_count += 1
                    
                    self._update_term_analytics(doc_id, source_term, conflict.resolved_translation, segment_id, confidence)
                    return success, conflict
                else:
                    # No resolution, flag for manual review
                    self.manual_review_count += 1
                    return False, conflict
            else:
                # No conflict, add mapping
                success = self.valkey.add_term_mapping(
                    doc_id, source_term, target_term, segment_id, confidence
                )
                
                if success:
                    self._update_term_analytics(doc_id, source_term, target_term, segment_id, confidence)
                
                return success, None
                
        finally:
            self.lookup_times.append(time.time() - start_time)
    
    def _handle_term_conflict(self, 
                             doc_id: str,
                             source_term: str,
                             new_translation: str,
                             segment_id: str,
                             confidence: float,
                             existing_mapping: TermMapping) -> TermConflict:
        """Handle term translation conflict"""
        conflict = TermConflict(
            source_term=source_term,
            existing_translation=existing_mapping.target_term,
            conflicting_translation=new_translation,
            existing_confidence=existing_mapping.confidence,
            conflicting_confidence=confidence,
            existing_segment=existing_mapping.segment_id,
            conflicting_segment=segment_id
        )
        
        # Apply resolution strategy
        strategy = self.default_resolution_strategy
        
        if strategy == ConflictResolutionStrategy.FIRST_WINS:
            conflict.resolved_translation = existing_mapping.target_term
            conflict.resolution_strategy = strategy
        
        elif strategy == ConflictResolutionStrategy.HIGHEST_CONFIDENCE:
            if confidence > existing_mapping.confidence:
                conflict.resolved_translation = new_translation
            else:
                conflict.resolved_translation = existing_mapping.target_term
            conflict.resolution_strategy = strategy
        
        elif strategy == ConflictResolutionStrategy.GLOSSARY_PREFERRED:
            resolved = self._resolve_with_glossary(source_term, 
                                                 existing_mapping.target_term, 
                                                 new_translation)
            if resolved:
                conflict.resolved_translation = resolved
                conflict.resolution_strategy = strategy
            else:
                # Fall back to highest confidence
                conflict.resolved_translation = (new_translation if confidence > existing_mapping.confidence 
                                               else existing_mapping.target_term)
                conflict.resolution_strategy = ConflictResolutionStrategy.HIGHEST_CONFIDENCE
        
        elif strategy == ConflictResolutionStrategy.MOST_FREQUENT:
            # Get term analytics to determine most frequent
            analytics = self.get_term_analytics(doc_id, source_term)
            if analytics and analytics.most_frequent_translation:
                conflict.resolved_translation = analytics.most_frequent_translation
            else:
                conflict.resolved_translation = existing_mapping.target_term
            conflict.resolution_strategy = strategy
        
        else:  # MANUAL_REVIEW
            conflict.resolution_strategy = ConflictResolutionStrategy.MANUAL_REVIEW
            # Store conflict for manual review
            self._store_conflict_for_review(doc_id, conflict)
        
        if conflict.resolved_translation:
            conflict.resolved_at = datetime.now()
        
        self.logger.info(f"Term conflict resolved: {source_term} -> {conflict.resolved_translation} "
                        f"(strategy: {conflict.resolution_strategy.value})")
        
        return conflict
    
    def _resolve_with_glossary(self, source_term: str, 
                              translation1: str, 
                              translation2: str) -> Optional[str]:
        """Resolve conflict using glossary search"""
        if not self.glossary_search:
            return None
        
        try:
            # Search for the source term in glossary
            results = self.glossary_search.search(source_term, max_results=5)
            
            # Check if either translation matches glossary
            glossary_translations = {result.term.english.lower() for result in results}
            
            if translation1.lower() in glossary_translations:
                return translation1
            elif translation2.lower() in glossary_translations:
                return translation2
            
            # If no exact match, check for partial matches
            for translation in [translation1, translation2]:
                for result in results:
                    if (translation.lower() in result.term.english.lower() or 
                        result.term.english.lower() in translation.lower()):
                        return translation
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error resolving with glossary: {e}")
            return None
    
    def _update_term_analytics(self, 
                              doc_id: str,
                              source_term: str,
                              target_term: str,
                              segment_id: str,
                              confidence: float) -> None:
        """Update term usage analytics"""
        analytics_key = f"{self.valkey.TERM_FREQ_PREFIX}:{doc_id}:{source_term}"
        
        # Get existing analytics
        existing_data = self.valkey.valkey_client.get(analytics_key)
        
        if existing_data:
            analytics = self.valkey._deserialize_data(existing_data.decode(), TermAnalytics)
        else:
            analytics = TermAnalytics(
                source_term=source_term,
                translations={},
                total_occurrences=0,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                segments_used=set(),
                confidence_scores=[]
            )
        
        # Update analytics
        analytics.translations[target_term] = analytics.translations.get(target_term, 0) + 1
        analytics.total_occurrences += 1
        analytics.last_seen = datetime.now()
        analytics.segments_used.add(segment_id)
        analytics.confidence_scores.append(confidence)
        
        # Check if term matches glossary
        if self.glossary_search and not analytics.glossary_match:
            results = self.glossary_search.search(source_term, max_results=1)
            if results and results[0].term.english.lower() == target_term.lower():
                analytics.glossary_match = True
        
        # Store updated analytics
        analytics_data = self.valkey._serialize_data(analytics)
        self.valkey.valkey_client.setex(analytics_key, self.valkey.DEFAULT_CACHE_TTL, analytics_data)
    
    def _store_conflict_for_review(self, doc_id: str, conflict: TermConflict) -> None:
        """Store conflict for manual review"""
        conflicts_key = f"conflicts:{doc_id}"
        conflict_id = f"{conflict.source_term}_{int(time.time())}"
        conflict_data = self.valkey._serialize_data(conflict)
        
        self.valkey.valkey_client.hset(conflicts_key, conflict_id, conflict_data)
        self.valkey.valkey_client.expire(conflicts_key, self.valkey.DEFAULT_CACHE_TTL)
    
    def get_term_consistency(self, doc_id: str, source_term: str) -> Optional[TermMapping]:
        """Get current term mapping with O(1) lookup"""
        start_time = time.time()
        
        try:
            mapping = self.valkey.get_term_mapping(doc_id, source_term)
            return mapping
        finally:
            self.lookup_times.append(time.time() - start_time)
    
    def get_term_analytics(self, doc_id: str, source_term: str) -> Optional[TermAnalytics]:
        """Get detailed term usage analytics"""
        analytics_key = f"{self.valkey.TERM_FREQ_PREFIX}:{doc_id}:{source_term}"
        analytics_data = self.valkey.valkey_client.get(analytics_key)
        
        if not analytics_data:
            return None
        
        return self.valkey._deserialize_data(analytics_data.decode(), TermAnalytics)
    
    def get_inconsistent_terms(self, doc_id: str, 
                              consistency_threshold: Optional[float] = None) -> List[TermAnalytics]:
        """Get terms with low consistency scores"""
        threshold = consistency_threshold or self.consistency_threshold
        inconsistent_terms = []
        
        # Get all term analytics for document
        pattern = f"{self.valkey.TERM_FREQ_PREFIX}:{doc_id}:*"
        keys = self.valkey.valkey_client.keys(pattern)
        
        for key in keys:
            analytics_data = self.valkey.valkey_client.get(key)
            if analytics_data:
                analytics = self.valkey._deserialize_data(analytics_data.decode(), TermAnalytics)
                if analytics.translation_consistency_score < threshold:
                    inconsistent_terms.append(analytics)
        
        # Sort by consistency score (lowest first)
        return sorted(inconsistent_terms, key=lambda x: x.translation_consistency_score)
    
    def get_document_conflicts(self, doc_id: str) -> List[TermConflict]:
        """Get all unresolved conflicts for document"""
        conflicts_key = f"conflicts:{doc_id}"
        raw_conflicts = self.valkey.valkey_client.hgetall(conflicts_key)
        
        conflicts = []
        for conflict_id, conflict_data in raw_conflicts.items():
            conflict = self.valkey._deserialize_data(conflict_data.decode(), TermConflict)
            conflicts.append(conflict)
        
        return conflicts
    
    def resolve_conflict_manually(self, 
                                 doc_id: str,
                                 conflict_id: str,
                                 chosen_translation: str) -> bool:
        """Manually resolve a term conflict"""
        conflicts_key = f"conflicts:{doc_id}"
        conflict_data = self.valkey.valkey_client.hget(conflicts_key, conflict_id)
        
        if not conflict_data:
            return False
        
        conflict = self.valkey._deserialize_data(conflict_data.decode(), TermConflict)
        
        # Update term mapping
        success = self.valkey.add_term_mapping(
            doc_id, conflict.source_term, chosen_translation,
            conflict.conflicting_segment, 1.0, lock_term=True
        )
        
        if success:
            # Mark conflict as resolved
            conflict.resolved_translation = chosen_translation
            conflict.resolved_at = datetime.now()
            
            # Remove from pending conflicts
            self.valkey.valkey_client.hdel(conflicts_key, conflict_id)
            
            # Update analytics
            self._update_term_analytics(doc_id, conflict.source_term, chosen_translation, 
                                      conflict.conflicting_segment, 1.0)
            
            self.logger.info(f"Manually resolved conflict: {conflict.source_term} -> {chosen_translation}")
        
        return success
    
    def lock_term_consistency(self, doc_id: str, source_term: str) -> bool:
        """Lock term to prevent further changes"""
        return self.valkey.lock_term(doc_id, source_term)
    
    def unlock_term_consistency(self, doc_id: str, source_term: str) -> bool:
        """Unlock term to allow changes"""
        return self.valkey.unlock_term(doc_id, source_term)
    
    def suggest_term_standardization(self, doc_id: str) -> List[Dict[str, Any]]:
        """Suggest term standardizations based on analytics"""
        suggestions = []
        
        # Get all terms with multiple translations
        pattern = f"{self.valkey.TERM_FREQ_PREFIX}:{doc_id}:*"
        keys = self.valkey.valkey_client.keys(pattern)
        
        for key in keys:
            analytics_data = self.valkey.valkey_client.get(key)
            if analytics_data:
                analytics = self.valkey._deserialize_data(analytics_data.decode(), TermAnalytics)
                
                if len(analytics.translations) > 1:
                    # Suggest most frequent or glossary-matched translation
                    if analytics.glossary_match:
                        # Find glossary match
                        if self.glossary_search:
                            results = self.glossary_search.search(analytics.source_term, max_results=1)
                            if results:
                                suggested = results[0].term.english
                                confidence = "high_glossary_match"
                            else:
                                suggested = analytics.most_frequent_translation
                                confidence = "most_frequent"
                        else:
                            suggested = analytics.most_frequent_translation
                            confidence = "most_frequent"
                    else:
                        suggested = analytics.most_frequent_translation
                        confidence = "most_frequent"
                    
                    suggestions.append({
                        'source_term': analytics.source_term,
                        'current_translations': dict(analytics.translations),
                        'suggested_translation': suggested,
                        'confidence_basis': confidence,
                        'consistency_score': analytics.translation_consistency_score,
                        'total_occurrences': analytics.total_occurrences
                    })
        
        # Sort by impact (total occurrences * consistency_score)
        return sorted(suggestions, 
                     key=lambda x: x['total_occurrences'] * (1 - x['consistency_score']), 
                     reverse=True)
    
    def apply_standardization_batch(self, doc_id: str, 
                                   standardizations: List[Tuple[str, str]]) -> Dict[str, bool]:
        """Apply multiple term standardizations"""
        results = {}
        
        for source_term, target_term in standardizations:
            # Get current mapping
            current_mapping = self.valkey.get_term_mapping(doc_id, source_term)
            
            if current_mapping:
                # Update mapping
                success = self.valkey.add_term_mapping(
                    doc_id, source_term, target_term,
                    current_mapping.segment_id, 1.0, lock_term=True
                )
                results[source_term] = success
                
                if success:
                    self.logger.info(f"Standardized term: {source_term} -> {target_term}")
            else:
                results[source_term] = False
        
        return results
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get consistency tracker performance statistics"""
        if not self.lookup_times:
            return {"status": "no_operations_yet"}
        
        avg_lookup_time = sum(self.lookup_times) / len(self.lookup_times)
        max_lookup_time = max(self.lookup_times)
        min_lookup_time = min(self.lookup_times)
        
        return {
            "total_lookups": len(self.lookup_times),
            "average_lookup_time_ms": avg_lookup_time * 1000,
            "max_lookup_time_ms": max_lookup_time * 1000,
            "min_lookup_time_ms": min_lookup_time * 1000,
            "conflicts": {
                "total_conflicts": self.conflict_count,
                "auto_resolved": self.auto_resolved_count,
                "manual_review_required": self.manual_review_count,
                "auto_resolution_rate": (self.auto_resolved_count / self.conflict_count 
                                       if self.conflict_count > 0 else 0)
            },
            "performance": {
                "sub_millisecond_lookups": sum(1 for t in self.lookup_times if t < 0.001),
                "lookups_per_second": len(self.lookup_times) / sum(self.lookup_times) if self.lookup_times else 0
            }
        }
    
    def generate_consistency_report(self, doc_id: str) -> Dict[str, Any]:
        """Generate comprehensive consistency report for document"""
        # Get all term mappings
        all_mappings = self.valkey.get_all_term_mappings(doc_id)
        
        # Get conflicts
        conflicts = self.get_document_conflicts(doc_id)
        
        # Get inconsistent terms
        inconsistent_terms = self.get_inconsistent_terms(doc_id)
        
        # Calculate overall consistency score
        if all_mappings:
            locked_terms = sum(1 for mapping in all_mappings.values() if mapping.locked)
            consistency_scores = []
            
            for source_term in all_mappings.keys():
                analytics = self.get_term_analytics(doc_id, source_term)
                if analytics:
                    consistency_scores.append(analytics.translation_consistency_score)
            
            overall_consistency = sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0
        else:
            locked_terms = 0
            overall_consistency = 0
        
        return {
            "document_id": doc_id,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_terms": len(all_mappings),
                "locked_terms": locked_terms,
                "pending_conflicts": len(conflicts),
                "inconsistent_terms": len(inconsistent_terms),
                "overall_consistency_score": overall_consistency
            },
            "conflicts": [
                {
                    "source_term": c.source_term,
                    "existing": c.existing_translation,
                    "conflicting": c.conflicting_translation,
                    "strategy": c.resolution_strategy.value if c.resolution_strategy else "unresolved"
                }
                for c in conflicts
            ],
            "inconsistent_terms": [
                {
                    "source_term": t.source_term,
                    "translations": t.translations,
                    "consistency_score": t.translation_consistency_score,
                    "total_occurrences": t.total_occurrences
                }
                for t in inconsistent_terms[:10]  # Top 10 most inconsistent
            ],
            "recommendations": self.suggest_term_standardization(doc_id)[:5]  # Top 5 recommendations
        }