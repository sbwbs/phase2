"""
Document Session Manager for Phase 2 MVP

This module provides high-level document session management with automatic 
lifecycle handling, progress tracking, and integration with the translation pipeline.

Key Features:
- Automatic session lifecycle management
- Progress tracking and segment completion
- Error recovery and session resumption
- Integration with Valkey backend
- Performance monitoring
"""

import logging
import time
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .valkey_manager import ValkeyManager, SessionMetadata, TermMapping


class SessionStatus(Enum):
    """Session status enumeration"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    EXPIRED = "expired"


@dataclass
class SessionProgress:
    """Session progress tracking"""
    doc_id: str
    total_segments: int
    processed_segments: int
    successful_segments: int
    failed_segments: int
    current_segment: Optional[int]
    estimated_remaining_time: Optional[float]
    average_segment_time: float
    progress_percentage: float
    
    @property
    def is_complete(self) -> bool:
        return self.processed_segments >= self.total_segments
    
    @property
    def has_failures(self) -> bool:
        return self.failed_segments > 0


@dataclass
class SegmentResult:
    """Individual segment processing result"""
    segment_id: str
    source_text: str
    target_text: Optional[str]
    status: str  # 'pending', 'processing', 'completed', 'failed'
    processing_time: Optional[float]
    error_message: Optional[str]
    term_mappings: List[Tuple[str, str]]  # (source_term, target_term) pairs
    created_at: datetime
    updated_at: datetime


class SessionManager:
    """High-level document session management"""
    
    def __init__(self, valkey_manager: ValkeyManager, 
                 default_session_ttl: int = 3600,
                 auto_extend_threshold: int = 300,
                 cleanup_interval: int = 3600):
        """
        Initialize session manager
        
        Args:
            valkey_manager: Valkey backend manager
            default_session_ttl: Default session TTL in seconds
            auto_extend_threshold: Auto-extend TTL when below this threshold
            cleanup_interval: Cleanup expired sessions interval
        """
        self.valkey = valkey_manager
        self.default_session_ttl = default_session_ttl
        self.auto_extend_threshold = auto_extend_threshold
        self.cleanup_interval = cleanup_interval
        self.logger = logging.getLogger(__name__)
        
        # Session monitoring
        self.active_sessions: Dict[str, datetime] = {}  # doc_id -> last_activity
        self.segment_timings: Dict[str, List[float]] = {}  # doc_id -> processing times
        
        self.logger.info("SessionManager initialized")
    
    def create_document_session(self, 
                              doc_id: str,
                              source_language: str,
                              target_language: str,
                              segments: List[str],
                              ttl_seconds: Optional[int] = None) -> SessionProgress:
        """
        Create a new document translation session
        
        Args:
            doc_id: Unique document identifier
            source_language: Source language code (e.g., 'ko', 'en')
            target_language: Target language code
            segments: List of source text segments
            ttl_seconds: Custom TTL, uses default if not provided
            
        Returns:
            SessionProgress object
        """
        ttl = ttl_seconds or self.default_session_ttl
        total_segments = len(segments)
        
        # Create session in Valkey
        session_metadata = self.valkey.create_session(
            doc_id=doc_id,
            source_language=source_language,
            target_language=target_language,
            total_segments=total_segments,
            ttl_seconds=ttl
        )
        
        # Initialize segment tracking
        self._initialize_segments(doc_id, segments)
        
        # Track active session
        self.active_sessions[doc_id] = datetime.now()
        self.segment_timings[doc_id] = []
        
        progress = SessionProgress(
            doc_id=doc_id,
            total_segments=total_segments,
            processed_segments=0,
            successful_segments=0,
            failed_segments=0,
            current_segment=None,
            estimated_remaining_time=None,
            average_segment_time=0.0,
            progress_percentage=0.0
        )
        
        self.logger.info(f"Created document session {doc_id} with {total_segments} segments")
        return progress
    
    def _initialize_segments(self, doc_id: str, segments: List[str]) -> None:
        """Initialize segment tracking in Valkey"""
        segments_key = f"{self.valkey.DOC_SEGMENTS_PREFIX}:{doc_id}"
        
        # Store each segment with initial status
        for i, segment_text in enumerate(segments):
            segment_result = SegmentResult(
                segment_id=str(i),
                source_text=segment_text,
                target_text=None,
                status='pending',
                processing_time=None,
                error_message=None,
                term_mappings=[],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            segment_data = self.valkey._serialize_data(segment_result)
            self.valkey.valkey_client.hset(segments_key, str(i), segment_data)
    
    def get_session_progress(self, doc_id: str) -> Optional[SessionProgress]:
        """Get current session progress"""
        session = self.valkey.get_session(doc_id)
        if not session:
            return None
        
        # Get segment completion stats
        segments = self._get_all_segments(doc_id)
        
        successful_segments = sum(1 for s in segments.values() if s.status == 'completed')
        failed_segments = sum(1 for s in segments.values() if s.status == 'failed')
        processed_segments = successful_segments + failed_segments
        
        # Find current segment (first pending or processing)
        current_segment = None
        for seg_id, segment in segments.items():
            if segment.status in ['pending', 'processing']:
                current_segment = int(seg_id)
                break
        
        # Calculate timing estimates
        timings = self.segment_timings.get(doc_id, [])
        average_time = sum(timings) / len(timings) if timings else 0.0
        remaining_segments = session.total_segments - processed_segments
        estimated_remaining = average_time * remaining_segments if average_time > 0 else None
        
        progress_percentage = (processed_segments / session.total_segments) * 100 if session.total_segments > 0 else 0
        
        return SessionProgress(
            doc_id=doc_id,
            total_segments=session.total_segments,
            processed_segments=processed_segments,
            successful_segments=successful_segments,
            failed_segments=failed_segments,
            current_segment=current_segment,
            estimated_remaining_time=estimated_remaining,
            average_segment_time=average_time,
            progress_percentage=progress_percentage
        )
    
    def start_segment_processing(self, doc_id: str, segment_id: str) -> bool:
        """Mark segment as processing"""
        segment = self._get_segment(doc_id, segment_id)
        if not segment:
            return False
        
        segment.status = 'processing'
        segment.updated_at = datetime.now()
        
        self._update_segment(doc_id, segment_id, segment)
        self._update_session_activity(doc_id)
        
        return True
    
    def complete_segment_processing(self, 
                                  doc_id: str,
                                  segment_id: str,
                                  target_text: str,
                                  processing_time: float,
                                  term_mappings: List[Tuple[str, str]] = None) -> bool:
        """Complete segment processing successfully"""
        segment = self._get_segment(doc_id, segment_id)
        if not segment:
            return False
        
        segment.status = 'completed'
        segment.target_text = target_text
        segment.processing_time = processing_time
        segment.term_mappings = term_mappings or []
        segment.updated_at = datetime.now()
        
        self._update_segment(doc_id, segment_id, segment)
        
        # Track timing for estimates
        if doc_id not in self.segment_timings:
            self.segment_timings[doc_id] = []
        self.segment_timings[doc_id].append(processing_time)
        
        # Store term mappings in Valkey
        if term_mappings:
            for source_term, target_term in term_mappings:
                self.valkey.add_term_mapping(
                    doc_id=doc_id,
                    source_term=source_term,
                    target_term=target_term,
                    segment_id=segment_id,
                    confidence=1.0
                )
        
        # Update session
        self.valkey.update_session(doc_id, processed_segments=self._count_processed_segments(doc_id))
        self._update_session_activity(doc_id)
        
        return True
    
    def fail_segment_processing(self, 
                              doc_id: str,
                              segment_id: str,
                              error_message: str,
                              processing_time: Optional[float] = None) -> bool:
        """Mark segment processing as failed"""
        segment = self._get_segment(doc_id, segment_id)
        if not segment:
            return False
        
        segment.status = 'failed'
        segment.error_message = error_message
        segment.processing_time = processing_time
        segment.updated_at = datetime.now()
        
        self._update_segment(doc_id, segment_id, segment)
        
        # Update session
        self.valkey.update_session(doc_id, processed_segments=self._count_processed_segments(doc_id))
        self._update_session_activity(doc_id)
        
        self.logger.warning(f"Segment {segment_id} failed in document {doc_id}: {error_message}")
        return True
    
    def retry_failed_segments(self, doc_id: str) -> List[str]:
        """Reset failed segments for retry"""
        segments = self._get_all_segments(doc_id)
        retried_segments = []
        
        for seg_id, segment in segments.items():
            if segment.status == 'failed':
                segment.status = 'pending'
                segment.error_message = None
                segment.updated_at = datetime.now()
                
                self._update_segment(doc_id, seg_id, segment)
                retried_segments.append(seg_id)
        
        if retried_segments:
            self.logger.info(f"Reset {len(retried_segments)} failed segments for retry in document {doc_id}")
        
        return retried_segments
    
    def pause_session(self, doc_id: str) -> bool:
        """Pause document session"""
        return self.valkey.update_session(doc_id, status=SessionStatus.PAUSED.value)
    
    def resume_session(self, doc_id: str) -> bool:
        """Resume paused session"""
        return self.valkey.update_session(doc_id, status=SessionStatus.ACTIVE.value)
    
    def complete_session(self, doc_id: str) -> bool:
        """Mark session as completed"""
        success = self.valkey.update_session(doc_id, status=SessionStatus.COMPLETED.value)
        
        if success and doc_id in self.active_sessions:
            del self.active_sessions[doc_id]
        
        self.logger.info(f"Completed document session {doc_id}")
        return success
    
    def abort_session(self, doc_id: str, reason: str = "User requested") -> bool:
        """Abort session with cleanup"""
        # Update status first
        self.valkey.update_session(doc_id, status=SessionStatus.ERROR.value)
        
        # Clean up session data
        success = self.valkey.cleanup_session(doc_id)
        
        if doc_id in self.active_sessions:
            del self.active_sessions[doc_id]
        if doc_id in self.segment_timings:
            del self.segment_timings[doc_id]
        
        self.logger.info(f"Aborted document session {doc_id}: {reason}")
        return success
    
    def extend_session(self, doc_id: str, additional_seconds: int = None) -> bool:
        """Extend session TTL"""
        if additional_seconds is None:
            additional_seconds = self.default_session_ttl // 2  # Extend by half default TTL
        
        return self.valkey.extend_session_ttl(doc_id, additional_seconds)
    
    def get_session_segments(self, doc_id: str, 
                           status_filter: Optional[str] = None) -> Dict[str, SegmentResult]:
        """Get session segments with optional status filter"""
        segments = self._get_all_segments(doc_id)
        
        if status_filter:
            return {k: v for k, v in segments.items() if v.status == status_filter}
        
        return segments
    
    def get_pending_segments(self, doc_id: str) -> List[SegmentResult]:
        """Get segments that are pending processing"""
        segments = self.get_session_segments(doc_id, 'pending')
        return list(segments.values())
    
    def get_failed_segments(self, doc_id: str) -> List[SegmentResult]:
        """Get segments that failed processing"""
        segments = self.get_session_segments(doc_id, 'failed')
        return list(segments.values())
    
    def get_active_sessions_summary(self) -> List[Dict]:
        """Get summary of all active sessions"""
        active_doc_ids = self.valkey.get_active_sessions()
        summaries = []
        
        for doc_id in active_doc_ids:
            session = self.valkey.get_session(doc_id)
            if session:
                progress = self.get_session_progress(doc_id)
                summaries.append({
                    'doc_id': doc_id,
                    'status': session.status,
                    'source_language': session.source_language,
                    'target_language': session.target_language,
                    'total_segments': session.total_segments,
                    'processed_segments': progress.processed_segments if progress else 0,
                    'progress_percentage': progress.progress_percentage if progress else 0,
                    'created_at': session.created_at.isoformat(),
                    'last_activity': self.active_sessions.get(doc_id, session.updated_at).isoformat()
                })
        
        return summaries
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        cleaned_count = 0
        current_time = datetime.now()
        
        # Check active sessions for expiration
        expired_sessions = []
        for doc_id, last_activity in self.active_sessions.items():
            time_diff = current_time - last_activity
            if time_diff.total_seconds() > self.default_session_ttl:
                expired_sessions.append(doc_id)
        
        # Clean up expired sessions
        for doc_id in expired_sessions:
            self.valkey.update_session(doc_id, status=SessionStatus.EXPIRED.value)
            self.valkey.cleanup_session(doc_id)
            
            if doc_id in self.active_sessions:
                del self.active_sessions[doc_id]
            if doc_id in self.segment_timings:
                del self.segment_timings[doc_id]
            
            cleaned_count += 1
        
        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} expired sessions")
        
        return cleaned_count
    
    def _get_segment(self, doc_id: str, segment_id: str) -> Optional[SegmentResult]:
        """Get individual segment data"""
        segments_key = f"{self.valkey.DOC_SEGMENTS_PREFIX}:{doc_id}"
        segment_data = self.valkey.valkey_client.hget(segments_key, segment_id)
        
        if not segment_data:
            return None
        
        return self.valkey._deserialize_data(segment_data.decode(), SegmentResult)
    
    def _get_all_segments(self, doc_id: str) -> Dict[str, SegmentResult]:
        """Get all segments for document"""
        segments_key = f"{self.valkey.DOC_SEGMENTS_PREFIX}:{doc_id}"
        raw_segments = self.valkey.valkey_client.hgetall(segments_key)
        
        segments = {}
        for seg_id, segment_data in raw_segments.items():
            seg_id = seg_id.decode()
            segment = self.valkey._deserialize_data(segment_data.decode(), SegmentResult)
            segments[seg_id] = segment
        
        return segments
    
    def _update_segment(self, doc_id: str, segment_id: str, segment: SegmentResult) -> None:
        """Update segment data in Valkey"""
        segments_key = f"{self.valkey.DOC_SEGMENTS_PREFIX}:{doc_id}"
        segment_data = self.valkey._serialize_data(segment)
        self.valkey.valkey_client.hset(segments_key, segment_id, segment_data)
    
    def _count_processed_segments(self, doc_id: str) -> int:
        """Count processed segments (completed + failed)"""
        segments = self._get_all_segments(doc_id)
        return sum(1 for s in segments.values() if s.status in ['completed', 'failed'])
    
    def _update_session_activity(self, doc_id: str) -> None:
        """Update session activity timestamp"""
        self.active_sessions[doc_id] = datetime.now()
        
        # Auto-extend TTL if close to expiration
        session_key = f"{self.valkey.DOC_META_PREFIX}:{doc_id}:metadata"
        ttl = self.valkey.valkey_client.ttl(session_key)
        
        if 0 < ttl < self.auto_extend_threshold:
            self.extend_session(doc_id)
            self.logger.info(f"Auto-extended TTL for session {doc_id}")
    
    def get_performance_stats(self) -> Dict:
        """Get session manager performance statistics"""
        total_timings = []
        for timings in self.segment_timings.values():
            total_timings.extend(timings)
        
        if not total_timings:
            return {"status": "no_data"}
        
        avg_segment_time = sum(total_timings) / len(total_timings)
        max_segment_time = max(total_timings)
        min_segment_time = min(total_timings)
        
        return {
            "active_sessions": len(self.active_sessions),
            "total_segments_processed": len(total_timings),
            "average_segment_time_ms": avg_segment_time * 1000,
            "max_segment_time_ms": max_segment_time * 1000,
            "min_segment_time_ms": min_segment_time * 1000,
            "estimated_throughput_segments_per_hour": 3600 / avg_segment_time if avg_segment_time > 0 else 0
        }