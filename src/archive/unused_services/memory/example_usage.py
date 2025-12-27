"""
Example Usage of Valkey Memory Layer Integration

This example demonstrates how to use the Valkey memory layer components
in a realistic translation workflow scenario using the valkey-py client.

Key Features Demonstrated:
- Valkey-based session management with multi-threading
- Term consistency tracking with conflict resolution
- O(1) lookup performance optimization
- Glossary search caching integration
- Production-ready error handling
"""

import asyncio
import sys
from pathlib import Path

# Add project paths
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append('/Users/won.suh/Project/translate-ai/src')

from .valkey_manager import ValkeyManager
from .session_manager import SessionManager
from .consistency_tracker import ConsistencyTracker, ConflictResolutionStrategy
from .cached_glossary_search import CachedGlossarySearch
try:
    from ..glossary_search import GlossarySearchEngine
except ImportError:
    # Fallback for testing
    from unittest.mock import Mock
    GlossarySearchEngine = Mock


class TranslationWorkflowExample:
    """Example translation workflow using Valkey memory layer"""
    
    def __init__(self):
        # Initialize Valkey manager with proper valkey-py client
        self.valkey = ValkeyManager(
            host="localhost",
            port=6379,
            db=0,  # Production database
            max_connections=20,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30
        )
        
        print(f"🔧 Initialized Valkey with multi-threading support")
        
        # Validate connection and performance
        health = self.valkey.health_check()
        if health['status'] != 'healthy':
            raise ConnectionError(f"Valkey connection unhealthy: {health}")
        
        print(f"✅ Valkey connection validated - {health['ping_time_ms']:.2f}ms ping")
        
        self.session_manager = SessionManager(
            self.valkey,
            default_session_ttl=3600  # 1 hour sessions
        )
        
        # Initialize glossary search (try real, fallback to mock)
        try:
            glossary_path = "/Users/won.suh/Project/translate-ai/data/processed/processed_glossary.pkl"
            base_glossary = GlossarySearchEngine(glossary_path)
        except:
            from unittest.mock import Mock
            base_glossary = Mock()
            base_glossary.search.return_value = []
        
        self.cached_glossary = CachedGlossarySearch(
            glossary_search_engine=base_glossary,
            valkey_manager=self.valkey,
            cache_ttl_seconds=7200,  # 2 hour cache
            enable_preloading=True
        )
        
        self.consistency_tracker = ConsistencyTracker(
            valkey_manager=self.valkey,
            glossary_search_engine=base_glossary,
            default_resolution_strategy=ConflictResolutionStrategy.GLOSSARY_PREFERRED
        )
    
    def translate_document(self, doc_id: str, korean_segments: list) -> dict:
        """
        Complete document translation workflow with memory layer integration
        
        Args:
            doc_id: Unique document identifier
            korean_segments: List of Korean text segments
            
        Returns:
            Translation results with performance metrics
        """
        print(f"🚀 Starting translation workflow for document: {doc_id}")
        
        # Step 1: Create document session
        print("📋 Creating document session...")
        progress = self.session_manager.create_document_session(
            doc_id=doc_id,
            source_language="ko",
            target_language="en",
            segments=korean_segments
        )
        
        # Step 2: Preload glossary cache for document terms
        print("🔄 Preloading glossary cache...")
        preloaded_count = self.cached_glossary.preload_document_terms(doc_id, korean_segments)
        print(f"   Preloaded {preloaded_count} terms")
        
        # Step 3: Process each segment
        print("📝 Processing segments...")
        results = {
            'doc_id': doc_id,
            'segments': [],
            'term_mappings': {},
            'conflicts': [],
            'performance': {}
        }
        
        for i, korean_text in enumerate(korean_segments):
            segment_id = str(i)
            print(f"   Processing segment {i+1}/{len(korean_segments)}")
            
            # Start segment processing
            self.session_manager.start_segment_processing(doc_id, segment_id)
            
            # Search for relevant glossary terms with session context
            glossary_results, existing_terms = self.cached_glossary.search_with_session_context(
                korean_text=korean_text,
                doc_id=doc_id,
                segment_id=segment_id,
                max_results=10
            )
            
            # Simulate translation process (in real implementation, this would call LLM)
            translated_text = self._simulate_translation(korean_text, glossary_results)
            
            # Extract term mappings from translation
            term_mappings = self._extract_term_mappings(korean_text, translated_text, glossary_results)
            
            # Track term consistency
            segment_conflicts = []
            for source_term, target_term in term_mappings:
                success, conflict = self.consistency_tracker.track_term_usage(
                    doc_id=doc_id,
                    source_term=source_term,
                    target_term=target_term,
                    segment_id=segment_id,
                    confidence=0.9
                )
                
                if conflict:
                    segment_conflicts.append({
                        'source_term': conflict.source_term,
                        'existing': conflict.existing_translation,
                        'conflicting': conflict.conflicting_translation,
                        'resolved': conflict.resolved_translation,
                        'strategy': conflict.resolution_strategy.value if conflict.resolution_strategy else None
                    })
            
            # Complete segment processing
            self.session_manager.complete_segment_processing(
                doc_id=doc_id,
                segment_id=segment_id,
                target_text=translated_text,
                processing_time=0.5,  # Simulated processing time
                term_mappings=term_mappings
            )
            
            # Store segment results
            results['segments'].append({
                'segment_id': segment_id,
                'source_text': korean_text,
                'target_text': translated_text,
                'glossary_terms_found': len(glossary_results),
                'term_mappings': term_mappings,
                'conflicts': segment_conflicts
            })
            
            results['conflicts'].extend(segment_conflicts)
        
        # Step 4: Finalize session
        print("✅ Finalizing session...")
        self.session_manager.complete_session(doc_id)
        
        # Step 5: Generate consistency report
        print("📊 Generating consistency report...")
        consistency_report = self.consistency_tracker.generate_consistency_report(doc_id)
        
        # Step 6: Collect performance metrics
        performance_metrics = self._collect_performance_metrics()
        
        results.update({
            'consistency_report': consistency_report,
            'performance': performance_metrics
        })
        
        print(f"🎉 Translation workflow completed for document: {doc_id}")
        return results
    
    def _simulate_translation(self, korean_text: str, glossary_results: list) -> str:
        """
        Simulate translation process (in real implementation, this would call LLM API)
        """
        # Simple simulation - in real implementation this would:
        # 1. Build context from glossary results
        # 2. Call LLM API with optimized prompt
        # 3. Parse and validate translation
        
        # Basic term replacement simulation
        text = korean_text
        for result in glossary_results:
            if result.term.korean in text:
                text = text.replace(result.term.korean, f"[{result.term.english}]")
        
        return f"Translated: {text}"
    
    def _extract_term_mappings(self, korean_text: str, translated_text: str, glossary_results: list) -> list:
        """
        Extract term mappings from translation (simplified simulation)
        """
        mappings = []
        
        # Extract from glossary results that appear in source text
        for result in glossary_results:
            if result.term.korean in korean_text:
                mappings.append((result.term.korean, result.term.english))
        
        # Add some common terms (simulation)
        common_terms = {
            "임상시험": "clinical trial",
            "피험자": "subject", 
            "이상반응": "adverse event",
            "치료": "treatment",
            "환자": "patient"
        }
        
        for korean, english in common_terms.items():
            if korean in korean_text and (korean, english) not in mappings:
                mappings.append((korean, english))
        
        return mappings
    
    def _collect_performance_metrics(self) -> dict:
        """Collect performance metrics from all components"""
        return {
            'valkey': self.valkey.get_performance_stats(),
            'session_manager': self.session_manager.get_performance_stats(),
            'consistency_tracker': self.consistency_tracker.get_performance_stats(),
            'cached_glossary': self.cached_glossary.get_cache_statistics()
        }
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            self.valkey.close()
        except:
            pass


def main():
    """Run example translation workflow with Valkey memory layer"""
    
    print("🚀 Valkey Memory Layer Integration Example")
    print("==========================================\n")
    print("This example demonstrates:")
    print("  • Valkey-py client with multi-threading support")
    print("  • Session-based term consistency tracking")
    print("  • O(1) lookup performance optimization")
    print("  • Glossary search result caching")
    print("  • Conflict resolution with strategies\n")
    
    # Sample Korean clinical trial document segments
    korean_segments = [
        "이 임상시험은 무작위배정, 이중눈가림, 위약대조 임상시험으로 진행됩니다.",
        "모든 피험자는 시험 참여 전에 충분한 설명을 듣고 동의서에 서명해야 합니다.",
        "이상반응이 발생할 경우 즉시 임상시험 담당자에게 보고해야 합니다.",
        "피험자의 안전성 모니터링이 임상시험 기간 동안 지속적으로 실시됩니다.",
        "치료 효과는 정해진 평가 일정에 따라 객관적으로 측정됩니다."
    ]
    
    # Initialize workflow
    workflow = TranslationWorkflowExample()
    
    try:
        # Run translation workflow
        results = workflow.translate_document("example_doc_001", korean_segments)
        
        # Display results
        print("\n" + "="*60)
        print("📊 TRANSLATION WORKFLOW RESULTS")
        print("="*60)
        
        print(f"\n📋 Document: {results['doc_id']}")
        print(f"📝 Segments processed: {len(results['segments'])}")
        print(f"⚠️  Conflicts detected: {len(results['conflicts'])}")
        
        # Show segment results
        print(f"\n🔍 Segment Details:")
        for segment in results['segments']:
            print(f"  Segment {segment['segment_id']}:")
            print(f"    Source: {segment['source_text'][:50]}...")
            print(f"    Target: {segment['target_text'][:50]}...")
            print(f"    Terms found: {segment['glossary_terms_found']}")
            print(f"    Mappings: {len(segment['term_mappings'])}")
            if segment['conflicts']:
                print(f"    Conflicts: {len(segment['conflicts'])}")
        
        # Show consistency report summary
        consistency = results['consistency_report']['summary']
        print(f"\n📈 Consistency Summary:")
        print(f"  Total terms: {consistency['total_terms']}")
        print(f"  Locked terms: {consistency['locked_terms']}")
        print(f"  Pending conflicts: {consistency['pending_conflicts']}")
        print(f"  Overall consistency: {consistency['overall_consistency_score']:.2f}")
        
        # Show performance metrics
        perf = results['performance']
        print(f"\n⚡ Performance Metrics:")
        
        if 'valkey' in perf and perf['valkey'].get('operations'):
            valkey_ops = perf['valkey']['operations']
            print(f"  Valkey avg operation: {valkey_ops.get('average_time_ms', 0):.2f}ms")
        
        if 'cached_glossary' in perf and perf['cached_glossary'].get('cache_performance'):
            cache_perf = perf['cached_glossary']['cache_performance']
            print(f"  Cache hit rate: {cache_perf.get('hit_rate', 0):.1%}")
        
        if 'consistency_tracker' in perf and perf['consistency_tracker'].get('average_lookup_time_ms'):
            print(f"  Term lookup: {perf['consistency_tracker']['average_lookup_time_ms']:.2f}ms")
        
        print(f"\n✅ Workflow completed successfully!")
        
    except Exception as e:
        print(f"❌ Workflow failed: {e}")
        raise
    finally:
        workflow.cleanup()


if __name__ == "__main__":
    main()