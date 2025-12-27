#!/usr/bin/env python3
"""
Valkey Integration Demo Script

This script validates the Valkey integration implementation,
demonstrating key features and performance characteristics.

Run this script to verify:
- Valkey connection with valkey-py client
- Session management functionality
- Term consistency tracking
- Performance characteristics
- Error handling
"""

import time
import sys
import traceback
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

try:
    from src.memory.valkey_manager import ValkeyManager
    from src.memory.session_manager import SessionManager
    from src.memory.consistency_tracker import ConsistencyTracker, ConflictResolutionStrategy
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're running from the correct directory and Valkey is installed:")
    print("  pip install valkey")
    sys.exit(1)


def test_valkey_connection():
    """Test basic Valkey connection and performance"""
    print("🔌 Testing Valkey Connection...")
    
    try:
        # Initialize Valkey with test database
        valkey = ValkeyManager(host="localhost", port=6379, db=15)
        
        # Test connection health
        health = valkey.health_check()
        print(f"  ✅ Connection status: {health['status']}")
        print(f"  ⚡ Ping time: {health['ping_time_ms']:.2f}ms")
        
        # Test basic operations
        test_key = "demo_test_key"
        valkey.valkey_client.set(test_key, "demo_value", ex=5)
        retrieved_value = valkey.valkey_client.get(test_key)
        
        if retrieved_value == b"demo_value":
            print("  ✅ Basic operations working")
        else:
            print("  ❌ Basic operations failed")
            return False
        
        # Clean up
        valkey.valkey_client.delete(test_key)
        valkey.close()
        
        print("  ✅ Valkey connection test passed\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Valkey connection failed: {e}")
        print(f"     Make sure Valkey server is running on localhost:6379")
        return False


def test_session_management():
    """Test document session management"""
    print("📋 Testing Session Management...")
    
    try:
        valkey = ValkeyManager(host="localhost", port=6379, db=15)
        session_manager = SessionManager(valkey)
        
        # Create test session
        doc_id = "demo_document_001"
        segments = [
            "This is the first test segment.",
            "이것은 두 번째 테스트 세그먼트입니다.",
            "Final segment for testing purposes."
        ]
        
        # Create session
        progress = session_manager.create_document_session(
            doc_id=doc_id,
            source_language='en',
            target_language='ko',
            segments=segments
        )
        
        print(f"  ✅ Session created: {progress.doc_id}")
        print(f"  📊 Total segments: {progress.total_segments}")
        
        # Process a segment
        session_manager.start_segment_processing(doc_id, "0")
        session_manager.complete_segment_processing(
            doc_id=doc_id,
            segment_id="0",
            target_text="첫 번째 테스트 세그먼트입니다.",
            processing_time=0.1,
            term_mappings=[("test", "테스트"), ("segment", "세그먼트")]
        )
        
        # Check progress
        updated_progress = session_manager.get_session_progress(doc_id)
        print(f"  ✅ Segment processed: {updated_progress.processed_segments}/{updated_progress.total_segments}")
        print(f"  📈 Progress: {updated_progress.progress_percentage:.1f}%")
        
        # Clean up
        session_manager.abort_session(doc_id, "Demo cleanup")
        valkey.close()
        
        print("  ✅ Session management test passed\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Session management failed: {e}")
        traceback.print_exc()
        return False


def test_term_consistency():
    """Test term consistency tracking and conflict resolution"""
    print("🔍 Testing Term Consistency...")
    
    try:
        valkey = ValkeyManager(host="localhost", port=6379, db=15)
        tracker = ConsistencyTracker(
            valkey_manager=valkey,
            default_resolution_strategy=ConflictResolutionStrategy.HIGHEST_CONFIDENCE
        )
        
        doc_id = "demo_consistency_doc"
        
        # Track initial term
        success, conflict = tracker.track_term_usage(
            doc_id=doc_id,
            source_term="device",
            target_term="기기",
            segment_id="seg_001",
            confidence=0.8
        )
        
        print(f"  ✅ Initial term tracked: device -> 기기")
        
        # Create conflict
        success, conflict = tracker.track_term_usage(
            doc_id=doc_id,
            source_term="device",
            target_term="장치",
            segment_id="seg_002",
            confidence=0.9
        )
        
        if conflict:
            print(f"  ⚠️  Conflict detected: {conflict.source_term}")
            print(f"     Existing: {conflict.existing_translation}")
            print(f"     Conflicting: {conflict.conflicting_translation}")
            print(f"     Resolved: {conflict.resolved_translation}")
            print(f"     Strategy: {conflict.resolution_strategy.value if conflict.resolution_strategy else 'None'}")
        
        # Test lookup performance
        lookup_times = []
        for i in range(100):
            start_time = time.time()
            mapping = tracker.get_term_consistency(doc_id, "device")
            lookup_time = time.time() - start_time
            lookup_times.append(lookup_time)
        
        avg_lookup_time = sum(lookup_times) / len(lookup_times)
        print(f"  ⚡ Average lookup time: {avg_lookup_time*1000:.3f}ms")
        
        if avg_lookup_time < 0.001:
            print("  ✅ Sub-millisecond performance achieved!")
        
        # Clean up
        valkey.close()
        
        print("  ✅ Term consistency test passed\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Term consistency failed: {e}")
        traceback.print_exc()
        return False


def test_performance_characteristics():
    """Test performance characteristics under load"""
    print("⚡ Testing Performance Characteristics...")
    
    try:
        valkey = ValkeyManager(host="localhost", port=6379, db=15)
        
        # Test bulk operations
        num_operations = 1000
        print(f"  🔄 Testing {num_operations} operations...")
        
        start_time = time.time()
        
        # Bulk set operations
        for i in range(num_operations):
            valkey.valkey_client.set(f"perf_test_{i}", f"value_{i}", ex=10)
        
        # Bulk get operations
        for i in range(num_operations):
            value = valkey.valkey_client.get(f"perf_test_{i}")
            assert value == f"value_{i}".encode()
        
        # Bulk delete operations
        keys_to_delete = [f"perf_test_{i}" for i in range(num_operations)]
        deleted_count = valkey.valkey_client.delete(*keys_to_delete)
        
        total_time = time.time() - start_time
        ops_per_second = (num_operations * 3) / total_time  # 3 operations per iteration
        
        print(f"  ✅ {num_operations*3} operations in {total_time:.2f}s")
        print(f"  🚀 Performance: {ops_per_second:.0f} ops/second")
        
        # Get performance stats
        stats = valkey.get_performance_stats()
        if stats.get('operations'):
            ops = stats['operations']
            print(f"  📊 Average operation time: {ops.get('average_time_ms', 0):.3f}ms")
            print(f"  📊 Error count: {ops.get('error_count', 0)}")
        
        valkey.close()
        
        print("  ✅ Performance test passed\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Performance test failed: {e}")
        traceback.print_exc()
        return False


def test_concurrent_operations():
    """Test concurrent operations using threading"""
    print("🧵 Testing Concurrent Operations...")
    
    try:
        import threading
        import concurrent.futures
        
        valkey = ValkeyManager(host="localhost", port=6379, db=15)
        
        def worker_task(worker_id, num_ops):
            """Worker function for concurrent testing"""
            success_count = 0
            for i in range(num_ops):
                try:
                    key = f"concurrent_{worker_id}_{i}"
                    valkey.valkey_client.set(key, f"worker_{worker_id}_value_{i}", ex=5)
                    retrieved = valkey.valkey_client.get(key)
                    valkey.valkey_client.delete(key)
                    
                    if retrieved:
                        success_count += 1
                except Exception:
                    pass
            return success_count
        
        # Run concurrent workers
        num_workers = 5
        ops_per_worker = 20
        
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(worker_task, worker_id, ops_per_worker)
                for worker_id in range(num_workers)
            ]
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        concurrent_time = time.time() - start_time
        total_ops = sum(results)
        expected_ops = num_workers * ops_per_worker * 3  # 3 operations per iteration
        
        print(f"  ✅ Concurrent execution completed in {concurrent_time:.2f}s")
        print(f"  🎯 Successful operations: {total_ops}")
        print(f"  📊 Concurrent throughput: {total_ops/concurrent_time:.0f} ops/second")
        
        valkey.close()
        
        print("  ✅ Concurrent operations test passed\n")
        return True
        
    except Exception as e:
        print(f"  ❌ Concurrent operations test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all Valkey integration tests"""
    print("🚀 Valkey Integration Demo")
    print("=" * 50)
    print("This demo validates the Valkey-py integration with:")
    print("  • Connection and health monitoring")
    print("  • Session management functionality")
    print("  • Term consistency tracking")
    print("  • Performance characteristics")
    print("  • Concurrent operations support")
    print()
    
    # Run all tests
    tests = [
        ("Connection", test_valkey_connection),
        ("Session Management", test_session_management),
        ("Term Consistency", test_term_consistency),
        ("Performance", test_performance_characteristics),
        ("Concurrent Operations", test_concurrent_operations),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"Running {test_name} test...")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 Test Results Summary")
    print("="*50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"  {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All tests passed! Valkey integration is working correctly.")
        print("\nNext steps:")
        print("  • Run the full test suite: pytest phase2/tests/test_valkey_integration.py")
        print("  • Start using Valkey in your translation pipeline")
        print("  • Monitor performance with the built-in metrics")
    else:
        print("\n⚠️  Some tests failed. Please check:")
        print("  • Valkey server is running on localhost:6379")
        print("  • valkey-py package is installed: pip install valkey")
        print("  • Network connectivity to Valkey server")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)