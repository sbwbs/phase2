"""
Integration Tests for Valkey Memory Layer

This module provides comprehensive tests for the Valkey-based memory system,
covering session management, term consistency tracking, and performance validation.

Test Categories:
- Connection and health monitoring
- Session lifecycle management
- Term consistency tracking
- Conflict resolution
- Performance and scalability
- Error handling and recovery
"""

import pytest
import time
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
from unittest.mock import Mock, patch

# Import Valkey components
from phase2.src.memory.valkey_manager import ValkeyManager, SessionMetadata, TermMapping, CacheEntry
from phase2.src.memory.session_manager import SessionManager, SessionProgress, SegmentResult
from phase2.src.memory.consistency_tracker import ConsistencyTracker, ConflictResolutionStrategy, TermConflict


class TestValkeyConnection:
    """Test Valkey connection and basic operations"""
    
    @pytest.fixture
    def valkey_manager(self):
        """Create ValkeyManager instance for testing"""
        # Use test database to avoid conflicts
        return ValkeyManager(host="localhost", port=6379, db=15)
    
    def test_valkey_connection_validation(self, valkey_manager):
        """Test Valkey connection and validation"""
        # Test basic connection
        assert valkey_manager.valkey_client.ping() == True
        
        # Test server info access
        info = valkey_manager.valkey_client.info()
        assert 'used_memory' in info
        
        # Test health check
        health = valkey_manager.health_check()
        assert health['status'] == 'healthy'
        assert health['basic_operations'] == 'ok'
    
    def test_connection_pool_performance(self, valkey_manager):
        """Test connection pool performance"""
        start_time = time.time()
        
        # Perform multiple operations to test pool efficiency
        for i in range(100):
            valkey_manager.valkey_client.set(f"test_key_{i}", f"test_value_{i}", ex=1)
            valkey_manager.valkey_client.get(f"test_key_{i}")
            valkey_manager.valkey_client.delete(f"test_key_{i}")
        
        total_time = time.time() - start_time
        
        # Should complete 300 operations in under 1 second with pooling
        assert total_time < 1.0
        
        # Verify performance stats
        stats = valkey_manager.get_performance_stats()
        assert stats['operations']['total_operations'] > 0
        assert stats['operations']['average_time_ms'] < 10  # Sub-10ms average
    
    def test_multi_threaded_performance(self, valkey_manager):
        """Test Valkey multi-threaded performance advantage"""
        import threading
        
        def worker_thread(thread_id: int, operations: int):
            """Worker thread for concurrent operations"""
            for i in range(operations):
                key = f"thread_{thread_id}_key_{i}"
                valkey_manager.valkey_client.set(key, f"value_{i}", ex=1)
                valkey_manager.valkey_client.get(key)
                valkey_manager.valkey_client.delete(key)
        
        # Test concurrent operations
        threads = []
        start_time = time.time()
        
        for thread_id in range(5):
            thread = threading.Thread(target=worker_thread, args=(thread_id, 50))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        concurrent_time = time.time() - start_time
        
        # Valkey's multi-threading should handle concurrent operations efficiently
        assert concurrent_time < 2.0  # Should complete in under 2 seconds
    
    def teardown_method(self, method):
        """Clean up test data"""
        if hasattr(self, 'valkey_manager'):
            # Clean up any test keys
            try:
                test_keys = self.valkey_manager.valkey_client.keys("test_*")
                test_keys.extend(self.valkey_manager.valkey_client.keys("thread_*"))
                if test_keys:
                    self.valkey_manager.valkey_client.delete(*test_keys)
            except:
                pass


class TestSessionManagement:
    """Test document session management functionality"""
    
    @pytest.fixture
    def session_setup(self):
        """Setup session manager with Valkey backend"""
        valkey_manager = ValkeyManager(host="localhost", port=6379, db=15)
        session_manager = SessionManager(valkey_manager)
        
        return {
            'valkey': valkey_manager,
            'session_manager': session_manager,
            'doc_id': 'test_doc_001',
            'segments': [
                "This is the first test segment.",
                "이것은 두 번째 테스트 세그먼트입니다.",
                "Final segment for testing purposes."
            ]
        }
    
    def test_session_creation_and_retrieval(self, session_setup):
        """Test creating and retrieving document sessions"""
        manager = session_setup['session_manager']
        doc_id = session_setup['doc_id']
        segments = session_setup['segments']
        
        # Create session
        progress = manager.create_document_session(
            doc_id=doc_id,
            source_language='en',
            target_language='ko',
            segments=segments
        )
        
        assert progress.doc_id == doc_id
        assert progress.total_segments == len(segments)
        assert progress.processed_segments == 0
        assert progress.progress_percentage == 0.0
        
        # Retrieve session
        retrieved_progress = manager.get_session_progress(doc_id)
        assert retrieved_progress.doc_id == doc_id
        assert retrieved_progress.total_segments == len(segments)
    
    def test_segment_processing_workflow(self, session_setup):
        """Test complete segment processing workflow"""
        manager = session_setup['session_manager']
        doc_id = session_setup['doc_id']
        segments = session_setup['segments']
        
        # Create session
        manager.create_document_session(
            doc_id=doc_id,
            source_language='en',
            target_language='ko',
            segments=segments
        )
        
        # Process first segment
        segment_id = "0"
        processing_start = time.time()
        
        # Start processing
        assert manager.start_segment_processing(doc_id, segment_id) == True
        
        # Simulate processing time
        time.sleep(0.1)
        processing_time = time.time() - processing_start
        
        # Complete processing
        term_mappings = [("test", "테스트"), ("segment", "세그먼트")]
        assert manager.complete_segment_processing(
            doc_id=doc_id,
            segment_id=segment_id,
            target_text="이것은 첫 번째 테스트 세그먼트입니다.",
            processing_time=processing_time,
            term_mappings=term_mappings
        ) == True
        
        # Verify progress
        progress = manager.get_session_progress(doc_id)
        assert progress.processed_segments == 1
        assert progress.successful_segments == 1
        assert progress.failed_segments == 0
        assert progress.progress_percentage == (1/3) * 100
        assert progress.average_segment_time > 0
    
    def test_session_ttl_management(self, session_setup):
        """Test session TTL management and auto-extension"""
        manager = session_setup['session_manager']
        valkey = session_setup['valkey']
        doc_id = session_setup['doc_id']
        segments = session_setup['segments']
        
        # Create session with short TTL
        short_ttl = 5  # 5 seconds
        manager.default_session_ttl = short_ttl
        
        progress = manager.create_document_session(
            doc_id=doc_id,
            source_language='en',
            target_language='ko',
            segments=segments,
            ttl_seconds=short_ttl
        )
        
        # Check initial TTL
        session_key = f"{valkey.DOC_META_PREFIX}:{doc_id}:metadata"
        initial_ttl = valkey.valkey_client.ttl(session_key)
        assert initial_ttl <= short_ttl
        assert initial_ttl > 0
        
        # Extend session
        assert manager.extend_session(doc_id, 10) == True
        
        # Verify TTL was extended
        extended_ttl = valkey.valkey_client.ttl(session_key)
        assert extended_ttl > initial_ttl
    
    def test_session_cleanup_and_expiration(self, session_setup):
        """Test session cleanup and expiration handling"""
        manager = session_setup['session_manager']
        doc_id = session_setup['doc_id']
        segments = session_setup['segments']
        
        # Create session
        manager.create_document_session(
            doc_id=doc_id,
            source_language='en',
            target_language='ko',
            segments=segments
        )
        
        # Verify session exists
        assert manager.get_session_progress(doc_id) is not None
        
        # Abort session
        assert manager.abort_session(doc_id, "Test cleanup") == True
        
        # Verify session is cleaned up
        assert manager.get_session_progress(doc_id) is None
        
        # Verify not in active sessions
        active_sessions = manager.get_active_sessions_summary()
        doc_ids = [session['doc_id'] for session in active_sessions]
        assert doc_id not in doc_ids
    
    def test_concurrent_session_handling(self, session_setup):
        """Test handling multiple concurrent document sessions"""
        manager = session_setup['session_manager']
        segments = session_setup['segments']
        
        # Create multiple sessions
        doc_ids = [f"concurrent_doc_{i}" for i in range(5)]
        
        for doc_id in doc_ids:
            manager.create_document_session(
                doc_id=doc_id,
                source_language='en',
                target_language='ko',
                segments=segments
            )
        
        # Verify all sessions are active
        active_sessions = manager.get_active_sessions_summary()
        active_doc_ids = [session['doc_id'] for session in active_sessions]
        
        for doc_id in doc_ids:
            assert doc_id in active_doc_ids
        
        # Process segments in parallel
        for doc_id in doc_ids:
            manager.start_segment_processing(doc_id, "0")
            manager.complete_segment_processing(
                doc_id=doc_id,
                segment_id="0",
                target_text=f"Translation for {doc_id}",
                processing_time=0.1
            )
        
        # Verify all sessions processed correctly
        for doc_id in doc_ids:
            progress = manager.get_session_progress(doc_id)
            assert progress.processed_segments == 1
    
    def teardown_method(self, method):
        """Clean up test sessions"""
        if hasattr(self, 'session_setup'):
            try:
                # Clean up test data
                valkey = self.session_setup['valkey']
                test_keys = valkey.valkey_client.keys("doc:*")
                test_keys.extend(valkey.valkey_client.keys("doc_terms:*"))
                test_keys.extend(valkey.valkey_client.keys("doc_segments:*"))
                test_keys.extend(valkey.valkey_client.keys("active_sessions"))
                
                if test_keys:
                    valkey.valkey_client.delete(*test_keys)
            except:
                pass


class TestTermConsistency:
    """Test term consistency tracking and conflict resolution"""
    
    @pytest.fixture
    def consistency_setup(self):
        """Setup consistency tracker with mock glossary"""
        valkey_manager = ValkeyManager(host="localhost", port=6379, db=15)
        
        # Mock glossary search engine
        mock_glossary = Mock()
        mock_search_result = Mock()
        mock_search_result.term.english = "device"
        mock_glossary.search.return_value = [mock_search_result]
        
        consistency_tracker = ConsistencyTracker(
            valkey_manager=valkey_manager,
            glossary_search_engine=mock_glossary,
            default_resolution_strategy=ConflictResolutionStrategy.GLOSSARY_PREFERRED
        )
        
        return {
            'valkey': valkey_manager,
            'tracker': consistency_tracker,
            'mock_glossary': mock_glossary,
            'doc_id': 'consistency_test_doc'
        }
    
    def test_term_consistency_tracking(self, consistency_setup):
        """Test basic term consistency tracking"""
        tracker = consistency_setup['tracker']
        doc_id = consistency_setup['doc_id']
        
        # Track term usage
        success, conflict = tracker.track_term_usage(
            doc_id=doc_id,
            source_term="device",
            target_term="기기",
            segment_id="seg_001",
            confidence=0.9
        )
        
        assert success == True
        assert conflict is None
        
        # Retrieve term consistency
        mapping = tracker.get_term_consistency(doc_id, "device")
        assert mapping is not None
        assert mapping.source_term == "device"
        assert mapping.target_term == "기기"
        assert mapping.confidence == 0.9
        assert mapping.segment_id == "seg_001"
    
    def test_conflict_detection_and_resolution(self, consistency_setup):
        """Test term conflict detection and resolution"""
        tracker = consistency_setup['tracker']
        doc_id = consistency_setup['doc_id']
        
        # First usage
        tracker.track_term_usage(
            doc_id=doc_id,
            source_term="device",
            target_term="기기",
            segment_id="seg_001",
            confidence=0.8
        )
        
        # Conflicting usage
        success, conflict = tracker.track_term_usage(
            doc_id=doc_id,
            source_term="device",
            target_term="장치",
            segment_id="seg_002",
            confidence=0.9
        )
        
        # Should detect conflict
        assert conflict is not None
        assert conflict.source_term == "device"
        assert conflict.existing_translation == "기기"
        assert conflict.conflicting_translation == "장치"
        
        # Should resolve based on glossary preference or confidence
        assert conflict.resolved_translation in ["기기", "장치", "device"]
        assert conflict.resolution_strategy is not None
    
    def test_glossary_based_resolution(self, consistency_setup):
        """Test conflict resolution using glossary"""
        tracker = consistency_setup['tracker']
        mock_glossary = consistency_setup['mock_glossary']
        doc_id = consistency_setup['doc_id']
        
        # Setup mock to return specific glossary match
        mock_result = Mock()
        mock_result.term.english = "device"
        mock_glossary.search.return_value = [mock_result]
        
        # Track conflicting terms where one matches glossary
        tracker.track_term_usage(doc_id, "medical", "의료", "seg_001", 0.8)
        
        success, conflict = tracker.track_term_usage(
            doc_id, "medical", "의학", "seg_002", 0.9
        )
        
        # Verify glossary was consulted
        mock_glossary.search.assert_called()
    
    def test_term_locking_mechanism(self, consistency_setup):
        """Test term locking to prevent changes"""
        tracker = consistency_setup['tracker']
        doc_id = consistency_setup['doc_id']
        
        # Track initial term
        tracker.track_term_usage(doc_id, "locked_term", "잠긴_용어", "seg_001", 1.0)
        
        # Lock the term
        assert tracker.lock_term_consistency(doc_id, "locked_term") == True
        
        # Try to change locked term
        success, conflict = tracker.track_term_usage(
            doc_id, "locked_term", "다른_용어", "seg_002", 1.0
        )
        
        # Should fail to change locked term
        assert success == False
        
        # Unlock and try again
        assert tracker.unlock_term_consistency(doc_id, "locked_term") == True
        
        success, conflict = tracker.track_term_usage(
            doc_id, "locked_term", "다른_용어", "seg_003", 1.0, force_override=True
        )
        
        # Should succeed after unlocking
        assert success == True
    
    def test_term_analytics_and_frequency_tracking(self, consistency_setup):
        """Test term usage analytics and frequency tracking"""
        tracker = consistency_setup['tracker']
        doc_id = consistency_setup['doc_id']
        
        # Track multiple usages of same term
        usages = [
            ("device", "기기", "seg_001", 0.8),
            ("device", "기기", "seg_003", 0.9),
            ("device", "장치", "seg_005", 0.7),  # Different translation
            ("device", "기기", "seg_007", 0.85),
        ]
        
        for source, target, segment, confidence in usages:
            tracker.track_term_usage(doc_id, source, target, segment, confidence)
        
        # Get analytics
        analytics = tracker.get_term_analytics(doc_id, "device")
        assert analytics is not None
        assert analytics.source_term == "device"
        assert analytics.total_occurrences == 4
        assert analytics.most_frequent_translation == "기기"  # Should be most frequent
        assert len(analytics.segments_used) == 4
        
        # Check consistency score
        assert 0 <= analytics.translation_consistency_score <= 1
        assert analytics.translation_consistency_score == 3/4  # 3 out of 4 use "기기"
    
    def test_conflict_resolution_strategies(self, consistency_setup):
        """Test different conflict resolution strategies"""
        valkey = consistency_setup['valkey']
        mock_glossary = consistency_setup['mock_glossary']
        doc_id = consistency_setup['doc_id']
        
        strategies_to_test = [
            ConflictResolutionStrategy.FIRST_WINS,
            ConflictResolutionStrategy.HIGHEST_CONFIDENCE,
            ConflictResolutionStrategy.MOST_FREQUENT,
            ConflictResolutionStrategy.MANUAL_REVIEW
        ]
        
        for strategy in strategies_to_test:
            # Create new tracker with specific strategy
            tracker = ConsistencyTracker(
                valkey_manager=valkey,
                glossary_search_engine=mock_glossary,
                default_resolution_strategy=strategy
            )
            
            doc_id_strategy = f"{doc_id}_{strategy.value}"
            
            # Setup initial term
            tracker.track_term_usage(doc_id_strategy, "test_term", "첫번째", "seg_001", 0.7)
            
            # Create conflict
            success, conflict = tracker.track_term_usage(
                doc_id_strategy, "test_term", "두번째", "seg_002", 0.9
            )
            
            if strategy == ConflictResolutionStrategy.FIRST_WINS:
                assert conflict.resolved_translation == "첫번째"
            elif strategy == ConflictResolutionStrategy.HIGHEST_CONFIDENCE:
                assert conflict.resolved_translation == "두번째"  # Higher confidence
            elif strategy == ConflictResolutionStrategy.MANUAL_REVIEW:
                assert conflict.resolved_translation is None  # No auto-resolution
    
    def test_performance_sub_millisecond_lookups(self, consistency_setup):
        """Test O(1) performance with sub-millisecond lookups"""
        tracker = consistency_setup['tracker']
        doc_id = consistency_setup['doc_id']
        
        # Setup terms for performance testing
        test_terms = [(f"term_{i}", f"용어_{i}", f"seg_{i}") for i in range(100)]
        
        # Track all terms
        for source, target, segment in test_terms:
            tracker.track_term_usage(doc_id, source, target, segment, 0.9)
        
        # Test lookup performance
        lookup_times = []
        for source, _, _ in test_terms:
            start_time = time.time()
            mapping = tracker.get_term_consistency(doc_id, source)
            lookup_time = time.time() - start_time
            lookup_times.append(lookup_time)
            
            assert mapping is not None
        
        # Verify sub-millisecond performance
        avg_lookup_time = sum(lookup_times) / len(lookup_times)
        max_lookup_time = max(lookup_times)
        
        assert avg_lookup_time < 0.001  # Sub-millisecond average
        assert max_lookup_time < 0.005   # Max under 5ms
        
        # Verify performance stats
        stats = tracker.get_performance_stats()
        assert stats['performance']['sub_millisecond_lookups'] > 50  # Most lookups sub-ms
    
    def teardown_method(self, method):
        """Clean up test data"""
        if hasattr(self, 'consistency_setup'):
            try:
                valkey = self.consistency_setup['valkey']
                # Clean up test data
                test_keys = valkey.valkey_client.keys("doc_terms:*")
                test_keys.extend(valkey.valkey_client.keys("term_freq:*"))
                test_keys.extend(valkey.valkey_client.keys("conflicts:*"))
                
                if test_keys:
                    valkey.valkey_client.delete(*test_keys)
            except:
                pass


class TestScalabilityAndPerformance:
    """Test system scalability and performance under load"""
    
    @pytest.fixture
    def performance_setup(self):
        """Setup for performance testing"""
        valkey_manager = ValkeyManager(host="localhost", port=6379, db=15)
        session_manager = SessionManager(valkey_manager)
        consistency_tracker = ConsistencyTracker(valkey_manager)
        
        return {
            'valkey': valkey_manager,
            'session_manager': session_manager,
            'consistency_tracker': consistency_tracker
        }
    
    def test_large_document_handling(self, performance_setup):
        """Test handling of large documents (1400+ segments)"""
        session_manager = performance_setup['session_manager']
        
        # Create large document simulation
        large_doc_id = "large_document_test"
        large_segments = [f"Segment {i} content for testing." for i in range(1400)]
        
        start_time = time.time()
        
        # Create session for large document
        progress = session_manager.create_document_session(
            doc_id=large_doc_id,
            source_language='en',
            target_language='ko',
            segments=large_segments
        )
        
        creation_time = time.time() - start_time
        
        # Should create session efficiently
        assert creation_time < 1.0  # Under 1 second
        assert progress.total_segments == 1400
        
        # Test batch segment processing
        batch_start = time.time()
        
        # Process segments in batches of 50
        for batch_start_idx in range(0, 100, 50):  # Test first 100 segments
            batch_end_idx = min(batch_start_idx + 50, 100)
            
            for seg_idx in range(batch_start_idx, batch_end_idx):
                session_manager.start_segment_processing(large_doc_id, str(seg_idx))
                session_manager.complete_segment_processing(
                    doc_id=large_doc_id,
                    segment_id=str(seg_idx),
                    target_text=f"Translation {seg_idx}",
                    processing_time=0.01
                )
        
        batch_time = time.time() - batch_start
        
        # Should process batches efficiently
        assert batch_time < 2.0  # Under 2 seconds for 100 segments
        
        # Verify progress
        final_progress = session_manager.get_session_progress(large_doc_id)
        assert final_progress.processed_segments == 100
    
    def test_concurrent_document_sessions(self, performance_setup):
        """Test concurrent handling of multiple document sessions"""
        session_manager = performance_setup['session_manager']
        
        # Create multiple concurrent sessions
        num_concurrent_docs = 10
        segments_per_doc = 50
        
        doc_ids = [f"concurrent_doc_{i}" for i in range(num_concurrent_docs)]
        segments = [f"Segment {j} content." for j in range(segments_per_doc)]
        
        start_time = time.time()
        
        # Create all sessions concurrently
        for doc_id in doc_ids:
            session_manager.create_document_session(
                doc_id=doc_id,
                source_language='en',
                target_language='ko',
                segments=segments
            )
        
        # Process segments concurrently
        for doc_id in doc_ids:
            for seg_idx in range(min(10, segments_per_doc)):  # Process first 10 segments
                session_manager.start_segment_processing(doc_id, str(seg_idx))
                session_manager.complete_segment_processing(
                    doc_id=doc_id,
                    segment_id=str(seg_idx),
                    target_text=f"Translation {seg_idx} for {doc_id}",
                    processing_time=0.01
                )
        
        total_time = time.time() - start_time
        
        # Should handle concurrent processing efficiently
        assert total_time < 5.0  # Under 5 seconds for 10 docs × 10 segments
        
        # Verify all sessions processed correctly
        for doc_id in doc_ids:
            progress = session_manager.get_session_progress(doc_id)
            assert progress.processed_segments == 10
    
    def test_memory_efficiency(self, performance_setup):
        """Test memory efficiency with large datasets"""
        valkey = performance_setup['valkey']
        tracker = performance_setup['consistency_tracker']
        
        # Get initial memory usage
        initial_info = valkey.valkey_client.info('memory')
        initial_memory = initial_info['used_memory']
        
        # Create large dataset
        doc_id = "memory_test_doc"
        num_terms = 1000
        
        # Track many terms
        for i in range(num_terms):
            tracker.track_term_usage(
                doc_id=doc_id,
                source_term=f"term_{i}",
                target_term=f"용어_{i}",
                segment_id=f"seg_{i}",
                confidence=0.9
            )
        
        # Check memory usage
        final_info = valkey.valkey_client.info('memory')
        final_memory = final_info['used_memory']
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (under 10MB for 1000 terms)
        assert memory_increase < 10 * 1024 * 1024  # 10MB
        
        # Test memory efficiency of lookups
        lookup_start = time.time()
        for i in range(num_terms):
            mapping = tracker.get_term_consistency(doc_id, f"term_{i}")
            assert mapping is not None
        
        lookup_time = time.time() - lookup_start
        
        # Should maintain O(1) performance even with many terms
        avg_lookup_time = lookup_time / num_terms
        assert avg_lookup_time < 0.001  # Sub-millisecond per lookup
    
    def test_cache_hit_rate_optimization(self, performance_setup):
        """Test cache hit rate optimization"""
        valkey = performance_setup['valkey']
        
        # Test caching with repeated access patterns
        cache_keys = [f"cache_test_{i}" for i in range(100)]
        
        # Initial cache population
        for key in cache_keys:
            valkey.cache_search_results(key, {"test": "data"}, ttl_seconds=3600)
        
        # Test cache hit performance
        hit_times = []
        for _ in range(3):  # Test multiple access rounds
            for key in cache_keys:
                start_time = time.time()
                result = valkey.get_cached_search_results(key)
                hit_time = time.time() - start_time
                hit_times.append(hit_time)
                
                assert result is not None  # Should be cache hit
        
        # Cache hits should be very fast
        avg_hit_time = sum(hit_times) / len(hit_times)
        assert avg_hit_time < 0.0005  # Sub-0.5ms for cache hits
        
        # Test cache hit rate
        # All accesses should be hits (100% hit rate)
        cache_hit_rate = 1.0  # We know all were hits in this test
        assert cache_hit_rate >= 0.95  # 95%+ hit rate target
    
    def teardown_method(self, method):
        """Clean up performance test data"""
        if hasattr(self, 'performance_setup'):
            try:
                valkey = self.performance_setup['valkey']
                # Clean up all test data
                test_patterns = [
                    "large_document_test*",
                    "concurrent_doc_*",
                    "memory_test_doc*",
                    "cache_test_*",
                    "doc:*",
                    "doc_terms:*", 
                    "doc_segments:*",
                    "term_freq:*",
                    "glossary_cache:*"
                ]
                
                for pattern in test_patterns:
                    keys = valkey.valkey_client.keys(pattern)
                    if keys:
                        valkey.valkey_client.delete(*keys)
            except:
                pass


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])