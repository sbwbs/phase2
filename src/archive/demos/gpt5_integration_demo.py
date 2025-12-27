"""
GPT-5 OWL Integration Demo - Complete Production Workflow

This demo showcases the complete integration of GPT-5 OWL with the Phase 2
context management architecture, demonstrating:

- 98% token reduction achievement (20,473 → 413 tokens)
- Session-based processing for 1,400 medical segments
- Advanced cost optimization with caching
- Production-grade error handling and monitoring
- Medical terminology consistency tracking

Usage:
    python gpt5_integration_demo.py --doc-id "IFU_50_pages" --segments 1400
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import List, Dict, Any
import argparse

# Core Phase 2 imports
from enhanced_translation_service import (
    EnhancedTranslationService, EnhancedTranslationRequest, 
    create_enhanced_request, OperationMode
)
from context_builder import ContextBuilder, ContextRequest
from memory.valkey_manager import ValkeyManager
from memory.cached_glossary_search import CachedGlossarySearch
from memory.session_manager import SessionManager
from glossary_search import GlossarySearchEngine, create_sample_glossary

# GPT-5 OWL specific imports
from gpt5_cost_optimizer import GPT5CostOptimizer
from gpt5_monitor import GPT5Monitor, setup_production_monitoring
from model_adapters.openai_adapter import OpenAIAdapter


# Sample medical device segments for demo
SAMPLE_MEDICAL_SEGMENTS = [
    "이 의료기기는 임상 환경에서 사용하도록 설계되었습니다.",
    "수술 전에 기기의 안전성을 확인해야 합니다.",
    "멸균 포장을 개봉한 후 즉시 사용하십시오.",
    "환자의 생체 신호를 지속적으로 모니터링하십시오.",
    "의료진은 기기 사용 전 교육을 받아야 합니다.",
    "이상 증상 발생 시 즉시 사용을 중단하십시오.",
    "기기 청소 시 승인된 소독제만 사용하십시오.",
    "정기적인 유지보수가 필요합니다.",
    "사용 후 적절히 폐기해야 합니다.",
    "의료기기 라벨의 지침을 따르십시오."
]


class GPT5IntegrationDemo:
    """Complete GPT-5 OWL integration demonstration"""
    
    def __init__(self, openai_api_key: str, enable_valkey: bool = True):
        """
        Initialize demo with GPT-5 OWL integration
        
        Args:
            openai_api_key: OpenAI API key
            enable_valkey: Enable Valkey for session management
        """
        self.openai_api_key = openai_api_key
        self.enable_valkey = enable_valkey
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.valkey_manager = None
        self.session_manager = None
        self.cost_optimizer = None
        self.monitor = None
        self.translation_service = None
        
        # Demo metrics
        self.demo_start_time = None
        self.total_segments_processed = 0
        self.total_cost_usd = 0.0
        self.total_tokens_saved = 0
        self.error_count = 0
        
    async def initialize_components(self):
        """Initialize all GPT-5 OWL integration components"""
        self.logger.info("Initializing GPT-5 OWL integration components...")
        
        try:
            # Initialize Valkey manager
            if self.enable_valkey:
                self.valkey_manager = ValkeyManager(
                    host="localhost",
                    port=6379,
                    db=0
                )
                await self._test_valkey_connection()
                
                self.session_manager = SessionManager(self.valkey_manager)
                self.logger.info("✓ Valkey and session management initialized")
            
            # Initialize cost optimizer
            if self.valkey_manager:
                self.cost_optimizer = GPT5CostOptimizer(
                    valkey_manager=self.valkey_manager,
                    cache_ttl_hours=24,
                    similarity_threshold=0.85
                )
                self.logger.info("✓ GPT-5 cost optimizer initialized")
            
            # Initialize monitoring
            if self.cost_optimizer:
                self.monitor = setup_production_monitoring(
                    valkey_manager=self.valkey_manager,
                    cost_optimizer=self.cost_optimizer,
                    log_dir="/tmp/gpt5_demo_logs"
                )
                await self.monitor.start_monitoring()
                self.logger.info("✓ Production monitoring initialized")
            
            # Initialize enhanced translation service
            self.translation_service = EnhancedTranslationService(
                valkey_host="localhost" if self.enable_valkey else None,
                valkey_port=6379,
                valkey_db=0,
                glossary_files=None,  # Use sample glossary
                enable_valkey=self.enable_valkey,
                enable_context_caching=True,
                fallback_to_phase1=True,
                default_mode=OperationMode.PHASE2_SMART_CONTEXT
            )
            self.logger.info("✓ Enhanced translation service initialized")
            
            # Verify GPT-5 OWL access
            await self._verify_gpt5_access()
            
            self.logger.info("🚀 All components initialized successfully!")
            
        except Exception as e:
            self.logger.error(f"Component initialization failed: {e}")
            raise
    
    async def run_complete_demo(self, 
                              doc_id: str = "DEMO_IFU_50_PAGES",
                              target_segments: int = 50,
                              model_name: str = "Owl"):  # GPT-5 OWL
        """
        Run complete GPT-5 OWL integration demo
        
        Args:
            doc_id: Document identifier
            target_segments: Number of segments to process
            model_name: Model name (should be "Owl" for GPT-5)
        """
        self.demo_start_time = time.time()
        self.logger.info(f"🎯 Starting GPT-5 OWL Demo: {target_segments} segments")
        
        try:
            # Phase 1: Setup session
            await self._setup_demo_session(doc_id, target_segments)
            
            # Phase 2: Demonstrate context optimization
            await self._demonstrate_context_optimization(doc_id)
            
            # Phase 3: Process segments with GPT-5 OWL
            await self._process_segments_with_gpt5(doc_id, target_segments, model_name)
            
            # Phase 4: Demonstrate cost optimization
            await self._demonstrate_cost_optimization(doc_id)
            
            # Phase 5: Show monitoring and health metrics
            await self._demonstrate_monitoring_capabilities(doc_id)
            
            # Phase 6: Generate final report
            await self._generate_demo_report(doc_id)
            
        except Exception as e:
            self.logger.error(f"Demo execution failed: {e}")
            self.error_count += 1
            raise
    
    async def _setup_demo_session(self, doc_id: str, total_segments: int):
        """Setup demo session with metadata"""
        self.logger.info(f"📋 Setting up session: {doc_id}")
        
        # Start document session
        success = await self.translation_service.start_document_session(
            doc_id=doc_id,
            total_segments=total_segments,
            source_language="korean",
            target_language="english"
        )
        
        if not success:
            raise RuntimeError("Failed to start document session")
        
        self.logger.info(f"✓ Session initialized for {total_segments} segments")
    
    async def _demonstrate_context_optimization(self, doc_id: str):
        """Demonstrate the 98% token reduction achievement"""
        self.logger.info("🎯 Demonstrating 98% token reduction...")
        
        sample_text = SAMPLE_MEDICAL_SEGMENTS[0]
        
        # Simulate Phase 1 context (full context loading)
        phase1_context_size = 20473  # Your research finding
        
        # Create Phase 2 optimized context request
        context_request = ContextRequest(
            source_text=sample_text,
            segment_id="DEMO_001",
            doc_id=doc_id,
            domain="clinical_trial",
            max_glossary_terms=10,
            optimization_target=413,  # Target from your research
            target_model="gpt-5"  # GPT-5 specific optimization
        )
        
        # Build optimized context (if context builder available)
        if hasattr(self.translation_service, 'context_builder') and self.translation_service.context_builder:
            result = await self.translation_service.context_builder.build_context(context_request)
            
            token_reduction = ((phase1_context_size - result.token_count) / phase1_context_size) * 100
            
            self.logger.info(f"📊 Context Optimization Results:")
            self.logger.info(f"   Phase 1 Context: {phase1_context_size:,} tokens")
            self.logger.info(f"   Phase 2 Context: {result.token_count:,} tokens")
            self.logger.info(f"   Token Reduction: {token_reduction:.1f}%")
            self.logger.info(f"   Glossary Terms: {result.glossary_terms_included}")
            self.logger.info(f"   Build Time: {result.build_time_ms:.1f}ms")
            
            self.total_tokens_saved += (phase1_context_size - result.token_count)
        else:
            self.logger.warning("Context builder not available - using Phase 1 mode")
    
    async def _process_segments_with_gpt5(self, 
                                        doc_id: str, 
                                        target_segments: int, 
                                        model_name: str):
        """Process segments using GPT-5 OWL with full pipeline"""
        self.logger.info(f"🔄 Processing {target_segments} segments with GPT-5 OWL...")
        
        # Create segments from sample data (cycling through samples)
        segments_to_process = []
        for i in range(target_segments):
            korean_text = SAMPLE_MEDICAL_SEGMENTS[i % len(SAMPLE_MEDICAL_SEGMENTS)]
            segment_id = f"DEMO_{i+1:03d}"
            
            # Create enhanced request with GPT-5 optimization
            request = create_enhanced_request(
                korean_text=korean_text,
                model_name=model_name,  # "Owl" -> GPT-5
                segment_id=segment_id,
                doc_id=doc_id,
                operation_mode=OperationMode.PHASE2_SMART_CONTEXT,
                context_optimization_target=413,  # Your target token count
                enable_session_tracking=True,
                max_glossary_terms=10,
                domain="clinical_trial"
            )
            
            segments_to_process.append(request)
        
        # Process in batches for efficiency
        batch_size = 5
        batches = [segments_to_process[i:i+batch_size] 
                  for i in range(0, len(segments_to_process), batch_size)]
        
        successful_translations = 0
        total_cost = 0.0
        
        for i, batch in enumerate(batches):
            self.logger.info(f"   Processing batch {i+1}/{len(batches)} ({len(batch)} segments)")
            
            try:
                # Process batch
                results = await self.translation_service.translate_batch(
                    batch, max_concurrent=3
                )
                
                # Analyze results
                for j, result in enumerate(results):
                    if not result.error:
                        successful_translations += 1
                        if result.tokens_used:
                            # Estimate cost (GPT-5 pricing)
                            estimated_cost = (result.tokens_used * 0.020) / 1000  # Rough estimate
                            total_cost += estimated_cost
                        
                        # Log translation metrics
                        if i == 0 and j == 0:  # Log first translation details
                            self.logger.info(f"   First translation sample:")
                            self.logger.info(f"     Korean: {batch[j].korean_text}")
                            self.logger.info(f"     English: {result.english_translation}")
                            self.logger.info(f"     Mode: {result.operation_mode_used.value}")
                            self.logger.info(f"     Tokens: {result.tokens_used}")
                            if result.token_reduction_percent:
                                self.logger.info(f"     Token Reduction: {result.token_reduction_percent:.1f}%")
                    else:
                        self.error_count += 1
                        self.logger.warning(f"   Translation failed: {result.error}")
                
                # Brief pause between batches to avoid rate limits
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Batch {i+1} failed: {e}")
                self.error_count += 1
        
        self.total_segments_processed = successful_translations
        self.total_cost_usd = total_cost
        
        success_rate = (successful_translations / target_segments) * 100
        self.logger.info(f"✓ Segment processing completed:")
        self.logger.info(f"   Success Rate: {success_rate:.1f}% ({successful_translations}/{target_segments})")
        self.logger.info(f"   Total Cost: ${total_cost:.2f}")
        self.logger.info(f"   Errors: {self.error_count}")
    
    async def _demonstrate_cost_optimization(self, doc_id: str):
        """Demonstrate cost optimization capabilities"""
        self.logger.info("💰 Demonstrating cost optimization...")
        
        if self.cost_optimizer:
            # Get session cost analysis
            cost_analysis = await self.cost_optimizer.get_session_cost_analysis(doc_id)
            
            if "error" not in cost_analysis:
                self.logger.info(f"📊 Cost Analysis for {doc_id}:")
                self.logger.info(f"   Total Requests: {cost_analysis['total_requests']}")
                self.logger.info(f"   Total Cost: ${cost_analysis['total_cost_usd']:.2f}")
                self.logger.info(f"   Cache Savings: ${cost_analysis.get('cache_savings_usd', 0):.2f}")
                self.logger.info(f"   Efficiency Ratio: {cost_analysis.get('efficiency_ratio', 0):.2f}")
                self.logger.info(f"   Avg Cost/Request: ${cost_analysis['average_cost_per_request']:.3f}")
            
            # Get global cost summary
            global_summary = self.cost_optimizer.get_global_cost_summary()
            self.logger.info(f"🌐 Global Cost Summary:")
            self.logger.info(f"   Total Savings: ${global_summary['total_savings_usd']:.2f}")
            self.logger.info(f"   Overall Efficiency: {global_summary['overall_efficiency']:.2f}")
            for cache_type, hit_rate in global_summary['cache_hit_rates'].items():
                self.logger.info(f"   {cache_type} Cache Hit Rate: {hit_rate:.2f}")
        else:
            self.logger.warning("Cost optimizer not available")
    
    async def _demonstrate_monitoring_capabilities(self, doc_id: str):
        """Demonstrate monitoring and health check capabilities"""
        self.logger.info("📊 Demonstrating monitoring capabilities...")
        
        if self.monitor:
            # Get session health
            session_health = await self.monitor.get_session_health(doc_id)
            if session_health:
                self.logger.info(f"🏥 Session Health for {doc_id}:")
                self.logger.info(f"   Success Rate: {session_health.success_rate:.1%}")
                self.logger.info(f"   Completed: {session_health.completed_segments}/{session_health.total_segments}")
                self.logger.info(f"   Avg Processing Time: {session_health.average_processing_time_ms:.1f}ms")
                self.logger.info(f"   Quality Score: {session_health.quality_score:.2f}")
                self.logger.info(f"   Error Count: {session_health.error_count}")
            
            # Get system health
            system_health = await self.monitor.get_system_health()
            self.logger.info(f"🖥️  System Health:")
            self.logger.info(f"   Active Sessions: {system_health.active_sessions}")
            self.logger.info(f"   Success Rate (1h): {system_health.success_rate_last_hour:.1%}")
            self.logger.info(f"   Avg Response Time: {system_health.average_response_time_ms:.1f}ms")
            self.logger.info(f"   Error Rate: {system_health.error_rate:.1%}")
            self.logger.info(f"   Cache Hit Rate: {system_health.cache_hit_rate:.1%}")
        else:
            self.logger.warning("Monitor not available")
    
    async def _generate_demo_report(self, doc_id: str):
        """Generate comprehensive demo report"""
        demo_duration = time.time() - self.demo_start_time
        
        self.logger.info("📋 GPT-5 OWL Integration Demo Report")
        self.logger.info("=" * 50)
        self.logger.info(f"Document ID: {doc_id}")
        self.logger.info(f"Demo Duration: {demo_duration:.1f} seconds")
        self.logger.info(f"Segments Processed: {self.total_segments_processed}")
        self.logger.info(f"Total Cost: ${self.total_cost_usd:.2f}")
        self.logger.info(f"Tokens Saved: {self.total_tokens_saved:,}")
        self.logger.info(f"Error Count: {self.error_count}")
        
        if self.total_segments_processed > 0:
            avg_cost_per_segment = self.total_cost_usd / self.total_segments_processed
            avg_time_per_segment = demo_duration / self.total_segments_processed
            
            self.logger.info(f"Avg Cost/Segment: ${avg_cost_per_segment:.3f}")
            self.logger.info(f"Avg Time/Segment: {avg_time_per_segment:.1f}s")
            
            # Project costs for 1,400 segments
            projected_cost_1400 = avg_cost_per_segment * 1400
            projected_time_1400 = avg_time_per_segment * 1400 / 60  # minutes
            
            self.logger.info("🎯 Projections for 1,400 segments:")
            self.logger.info(f"   Projected Cost: ${projected_cost_1400:.2f}")
            self.logger.info(f"   Projected Time: {projected_time_1400:.1f} minutes")
        
        # Component health summary
        if self.translation_service:
            perf_summary = self.translation_service.get_performance_summary()
            self.logger.info(f"Phase 2 Usage: {perf_summary['overall_stats']['phase2_percentage']:.1f}%")
        
        self.logger.info("=" * 50)
        self.logger.info("✅ Demo completed successfully!")
    
    async def _test_valkey_connection(self):
        """Test Valkey connection"""
        try:
            health = self.valkey_manager.health_check()
            if health["status"] != "healthy":
                raise RuntimeError(f"Valkey unhealthy: {health}")
        except Exception as e:
            self.logger.warning(f"Valkey connection failed: {e}")
            self.logger.warning("Demo will run without session management")
            self.enable_valkey = False
            self.valkey_manager = None
    
    async def _verify_gpt5_access(self):
        """Verify GPT-5 OWL access"""
        try:
            # Check if GPT-5 is available in the model list
            available_models = self.translation_service.get_available_models()
            if "Owl" not in available_models:
                self.logger.warning("GPT-5 OWL (Owl) not found in available models")
                self.logger.warning(f"Available models: {available_models}")
                raise RuntimeError("GPT-5 OWL not available")
            
            self.logger.info("✓ GPT-5 OWL access verified")
            
        except Exception as e:
            self.logger.error(f"GPT-5 verification failed: {e}")
            raise


async def main():
    """Main demo function"""
    parser = argparse.ArgumentParser(description='GPT-5 OWL Integration Demo')
    parser.add_argument('--doc-id', default='DEMO_IFU_50_PAGES', help='Document ID')
    parser.add_argument('--segments', type=int, default=50, help='Number of segments to process')
    parser.add_argument('--model', default='Owl', help='Model name (Owl for GPT-5)')
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    parser.add_argument('--disable-valkey', action='store_true', help='Disable Valkey integration')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Check for OpenAI API key
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        logger.error("OPENAI_API_KEY environment variable required")
        return 1
    
    # Run demo
    try:
        demo = GPT5IntegrationDemo(
            openai_api_key=openai_api_key,
            enable_valkey=not args.disable_valkey
        )
        
        await demo.initialize_components()
        await demo.run_complete_demo(
            doc_id=args.doc_id,
            target_segments=args.segments,
            model_name=args.model
        )
        
        logger.info("🎉 Demo completed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))