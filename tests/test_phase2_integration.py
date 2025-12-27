"""
Phase 2 MVP Integration Test - Complete Pipeline Validation

This test validates the complete Phase 2 translation pipeline with:
- Enhanced translation service integration
- Context builder and smart context generation
- Valkey session management
- Document processor for large-scale workflows
- Model adapter integration (GPT-4, GPT-5, o3)
- Performance comparison between Phase 1 and Phase 2

Test Scenarios:
1. Basic Phase 2 vs Phase 1 comparison
2. Document-level session processing
3. Large batch processing (simulating 1,400+ segments)
4. Error recovery and retry logic
5. Performance metrics validation
"""

import asyncio
import logging
import json
import time
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd

# Import Phase 2 components
from enhanced_translation_service import (
    EnhancedTranslationService, 
    EnhancedTranslationRequest,
    OperationMode,
    create_enhanced_request
)
from document_processor import (
    DocumentProcessor, 
    BatchConfiguration,
    ProcessingStatus,
    process_document_simple
)
from model_adapters.openai_adapter import OpenAIAdapter
from memory.valkey_manager import ValkeyManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Phase2IntegrationTest:
    """Comprehensive Phase 2 integration test suite"""
    
    def __init__(self):
        self.test_results = {}
        self.translation_service = None
        self.document_processor = None
        self.test_data_dir = Path("./test_data")
        self.output_dir = Path("./test_output")
        
        # Create test directories
        self.test_data_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
    
    async def setup_test_environment(self):
        """Setup test environment with Phase 2 components"""
        logger.info("Setting up Phase 2 test environment...")
        
        try:
            # Initialize enhanced translation service
            self.translation_service = EnhancedTranslationService(
                valkey_host="localhost",
                valkey_port=6379,
                valkey_db=1,  # Use separate DB for testing
                enable_valkey=True,
                enable_context_caching=True,
                fallback_to_phase1=True,
                default_mode=OperationMode.AUTO_DETECT
            )
            
            # Initialize document processor
            self.document_processor = DocumentProcessor(
                translation_service=self.translation_service,
                output_directory=str(self.output_dir),
                checkpoint_directory=str(self.output_dir / "checkpoints"),
                enable_checkpointing=True
            )
            
            logger.info("Phase 2 components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup test environment: {e}")
            return False
    
    def create_test_data(self) -> str:
        """Create test data file simulating large document"""
        logger.info("Creating test data for integration test...")
        
        # Sample Korean medical device segments
        sample_segments = [
            "이 의료기기는 임상시험에서 안전성과 유효성이 입증되었습니다.",
            "피험자는 무작위배정 방법을 통해 선정되었습니다.", 
            "이상반응 발생 시 즉시 의료진에게 보고해야 합니다.",
            "치료 과정에서 정기적인 모니터링이 필요합니다.",
            "투여량은 환자의 체중과 연령을 고려하여 결정됩니다.",
            "이중눈가림 연구 설계를 통해 객관성을 확보했습니다.",
            "위약 대조군과 비교하여 유의미한 효과를 보였습니다.",
            "안전성 프로파일은 기존 치료법과 유사합니다.",
            "효과의 지속성은 추가 연구가 필요합니다.",
            "부작용은 대부분 경미하고 일시적이었습니다."
        ]
        
        # Create larger dataset by repeating and modifying segments
        test_segments = []
        for i in range(100):  # Create 1000 segments total
            for j, segment in enumerate(sample_segments):
                segment_id = f"seg_{i:03d}_{j:02d}"
                # Add variation to text
                modified_segment = segment + f" (섹션 {i+1})"
                test_segments.append({
                    'segment_id': segment_id,
                    'korean_text': modified_segment,
                    'english_text': '',  # To be filled by translation
                    'status': 'pending'
                })
        
        # Save to Excel file
        test_file = self.test_data_dir / "large_document_test.xlsx"
        df = pd.DataFrame(test_segments)
        df.to_excel(test_file, index=False)
        
        logger.info(f"Created test data with {len(test_segments)} segments: {test_file}")
        return str(test_file)
    
    async def test_basic_phase2_vs_phase1(self) -> Dict[str, Any]:
        """Test basic Phase 2 vs Phase 1 translation comparison"""
        logger.info("Testing Phase 2 vs Phase 1 comparison...")
        
        test_korean = "이 의료기기는 임상시험에서 안전성과 유효성이 입증되었습니다."
        model_name = "Falcon"  # GPT-4o
        
        try:
            # Test Phase 1 mode
            phase1_request = create_enhanced_request(
                korean_text=test_korean,
                model_name=model_name,
                segment_id="test_p1",
                doc_id="test_doc_basic",
                operation_mode=OperationMode.PHASE1_FULL_CONTEXT
            )
            
            start_time = time.time()
            phase1_result = await self.translation_service.translate(phase1_request)
            phase1_time = time.time() - start_time
            
            # Test Phase 2 mode
            # First start a session
            await self.translation_service.start_document_session(
                doc_id="test_doc_basic_p2",
                total_segments=1
            )
            
            phase2_request = create_enhanced_request(
                korean_text=test_korean,
                model_name=model_name,
                segment_id="test_p2",
                doc_id="test_doc_basic_p2",
                operation_mode=OperationMode.PHASE2_SMART_CONTEXT
            )
            
            start_time = time.time()
            phase2_result = await self.translation_service.translate(phase2_request)
            phase2_time = time.time() - start_time
            
            # Compare results
            comparison = {
                'phase1': {
                    'translation': phase1_result.english_translation,
                    'tokens_used': phase1_result.tokens_used,
                    'processing_time_ms': phase1_time * 1000,
                    'error': phase1_result.error,
                    'mode_used': phase1_result.operation_mode_used.value
                },
                'phase2': {
                    'translation': phase2_result.english_translation,
                    'tokens_used': phase2_result.tokens_used,
                    'processing_time_ms': phase2_time * 1000,
                    'error': phase2_result.error,
                    'mode_used': phase2_result.operation_mode_used.value,
                    'token_reduction_percent': phase2_result.token_reduction_percent,
                    'context_build_time_ms': phase2_result.context_build_time_ms,
                    'glossary_terms_used': phase2_result.glossary_terms_used
                },
                'comparison': {
                    'translation_quality_similar': (
                        len(phase1_result.english_translation) > 0 and 
                        len(phase2_result.english_translation) > 0
                    ),
                    'phase2_faster': phase2_time < phase1_time,
                    'phase2_successful': not phase2_result.error,
                    'phase1_successful': not phase1_result.error
                }
            }
            
            # Cleanup sessions
            await self.translation_service.cleanup_session("test_doc_basic_p2")
            
            logger.info("Phase 2 vs Phase 1 comparison completed")
            return comparison
            
        except Exception as e:
            logger.error(f"Phase 2 vs Phase 1 test failed: {e}")
            return {'error': str(e)}
    
    async def test_document_processing(self, test_file: str) -> Dict[str, Any]:
        """Test document-level processing with large batch"""
        logger.info(f"Testing document processing with file: {test_file}")
        
        try:
            # Test with Phase 2 mode
            doc_id = "large_doc_test_phase2"
            model_name = "Falcon"  # GPT-4o
            
            # Configure for faster testing (smaller batches)
            batch_config = BatchConfiguration(
                batch_size=5,
                max_concurrent_batches=2,
                max_retries=2,
                retry_delay_seconds=1.0,
                progress_update_interval=5,
                checkpoint_interval=20,
                enable_adaptive_batching=True,
                target_batch_time_ms=10000.0  # 10 seconds
            )
            
            # Process document
            start_time = time.time()
            progress = await self.document_processor.process_document(
                doc_id=doc_id,
                input_file=test_file,
                model_name=model_name,
                operation_mode=OperationMode.PHASE2_SMART_CONTEXT,
                batch_config=batch_config,
                resume_from_checkpoint=False
            )
            processing_time = time.time() - start_time
            
            # Analyze results
            results = {
                'processing_time_seconds': processing_time,
                'total_segments': progress.total_segments,
                'completed_segments': progress.completed_segments,
                'failed_segments': progress.failed_segments,
                'completion_rate': progress.completion_percent,
                'phase1_segments': progress.phase1_segments,
                'phase2_segments': progress.phase2_segments,
                'total_tokens_used': progress.total_tokens_used,
                'total_tokens_saved': progress.total_tokens_saved,
                'total_batches': progress.total_batches,
                'completed_batches': progress.completed_batches,
                'average_batch_time_ms': progress.average_batch_time_ms,
                'error_rate': progress.error_rate,
                'common_errors': progress.common_errors,
                'status': progress.status.value,
                'segments_per_second': progress.completed_segments / processing_time if processing_time > 0 else 0
            }
            
            logger.info(f"Document processing completed: {results['completion_rate']:.1f}% success rate")
            return results
            
        except Exception as e:
            logger.error(f"Document processing test failed: {e}")
            return {'error': str(e)}
    
    async def test_model_adapters(self) -> Dict[str, Any]:
        """Test different model adapters"""
        logger.info("Testing model adapters...")
        
        test_korean = "안전성 프로파일은 기존 치료법과 유사합니다."
        models_to_test = ["Falcon", "Eagle", "Swan"]  # GPT-4o, o3, Gemini
        
        results = {}
        
        for model_name in models_to_test:
            try:
                # Test if model is available
                available_models = self.translation_service.get_available_models()
                if model_name not in available_models:
                    results[model_name] = {'error': 'Model not available', 'available': False}
                    continue
                
                # Create request
                request = create_enhanced_request(
                    korean_text=test_korean,
                    model_name=model_name,
                    segment_id=f"test_model_{model_name.lower()}",
                    doc_id=f"test_doc_model_{model_name.lower()}",
                    operation_mode=OperationMode.PHASE2_SMART_CONTEXT
                )
                
                # Start session
                await self.translation_service.start_document_session(
                    doc_id=request.doc_id,
                    total_segments=1
                )
                
                # Test translation
                start_time = time.time()
                result = await self.translation_service.translate(request)
                processing_time = time.time() - start_time
                
                results[model_name] = {
                    'available': True,
                    'translation': result.english_translation,
                    'tokens_used': result.tokens_used,
                    'processing_time_ms': processing_time * 1000,
                    'error': result.error,
                    'mode_used': result.operation_mode_used.value,
                    'token_reduction_percent': result.token_reduction_percent,
                    'successful': not result.error
                }
                
                # Cleanup session
                await self.translation_service.cleanup_session(request.doc_id)
                
            except Exception as e:
                results[model_name] = {'error': str(e), 'available': False}
        
        logger.info(f"Model adapter testing completed for {len(results)} models")
        return results
    
    async def test_performance_metrics(self) -> Dict[str, Any]:
        """Test performance monitoring and metrics"""
        logger.info("Testing performance metrics...")
        
        try:
            # Get translation service performance summary
            service_performance = self.translation_service.get_performance_summary()
            
            # Get document processor statistics
            processor_stats = self.document_processor.get_processor_statistics()
            
            # Perform health checks
            service_health = self.translation_service.health_check()
            
            metrics = {
                'translation_service': {
                    'performance': service_performance,
                    'health': service_health
                },
                'document_processor': {
                    'statistics': processor_stats
                },
                'system_health': {
                    'overall_status': service_health.get('status', 'unknown'),
                    'phase2_available': service_performance.get('phase2_availability', {}).get('phase2_available', False),
                    'components_healthy': all(
                        component.get('status') in ['healthy', 'degraded']
                        for component in service_health.get('components', {}).values()
                        if isinstance(component, dict)
                    )
                }
            }
            
            logger.info("Performance metrics collection completed")
            return metrics
            
        except Exception as e:
            logger.error(f"Performance metrics test failed: {e}")
            return {'error': str(e)}
    
    async def test_error_recovery(self) -> Dict[str, Any]:
        """Test error recovery and retry mechanisms"""
        logger.info("Testing error recovery mechanisms...")
        
        try:
            # Create a test scenario with invalid model
            invalid_request = create_enhanced_request(
                korean_text="테스트 문장입니다.",
                model_name="InvalidModel",
                segment_id="error_test",
                doc_id="error_test_doc",
                operation_mode=OperationMode.PHASE2_SMART_CONTEXT
            )
            
            # Test error handling
            start_time = time.time()
            result = await self.translation_service.translate(invalid_request)
            processing_time = time.time() - start_time
            
            error_recovery = {
                'error_handled_gracefully': result.error is not None,
                'response_time_reasonable': processing_time < 5.0,
                'fallback_attempted': 'fallback' in result.error.lower() if result.error else False,
                'error_message': result.error,
                'processing_time_ms': processing_time * 1000
            }
            
            logger.info("Error recovery testing completed")
            return error_recovery
            
        except Exception as e:
            logger.error(f"Error recovery test failed: {e}")
            return {'error': str(e)}
    
    async def run_complete_integration_test(self) -> Dict[str, Any]:
        """Run complete integration test suite"""
        logger.info("Starting complete Phase 2 integration test...")
        
        # Setup environment
        setup_success = await self.setup_test_environment()
        if not setup_success:
            return {'error': 'Failed to setup test environment'}
        
        test_results = {}
        
        try:
            # 1. Basic Phase 2 vs Phase 1 comparison
            logger.info("Running basic comparison test...")
            test_results['basic_comparison'] = await self.test_basic_phase2_vs_phase1()
            
            # 2. Model adapter testing
            logger.info("Running model adapter tests...")
            test_results['model_adapters'] = await self.test_model_adapters()
            
            # 3. Performance metrics
            logger.info("Running performance metrics test...")
            test_results['performance_metrics'] = await self.test_performance_metrics()
            
            # 4. Error recovery
            logger.info("Running error recovery test...")
            test_results['error_recovery'] = await self.test_error_recovery()
            
            # 5. Document processing (smaller scale for testing)
            logger.info("Running document processing test...")
            test_file = self.create_test_data()
            test_results['document_processing'] = await self.test_document_processing(test_file)
            
            # Generate summary
            test_results['summary'] = self.generate_test_summary(test_results)
            
            # Save results
            results_file = self.output_dir / "integration_test_results.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(test_results, f, indent=2, default=str)
            
            logger.info(f"Integration test completed. Results saved to: {results_file}")
            return test_results
            
        except Exception as e:
            logger.error(f"Integration test failed: {e}")
            test_results['error'] = str(e)
            return test_results
    
    def generate_test_summary(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive test summary"""
        
        summary = {
            'overall_status': 'PASS',
            'test_count': len([k for k in test_results.keys() if not k.startswith('_')]),
            'passed_tests': 0,
            'failed_tests': 0,
            'test_details': {}
        }
        
        # Analyze each test
        for test_name, test_result in test_results.items():
            if test_name == 'summary':
                continue
                
            if isinstance(test_result, dict) and 'error' not in test_result:
                summary['passed_tests'] += 1
                summary['test_details'][test_name] = 'PASS'
            else:
                summary['failed_tests'] += 1
                summary['test_details'][test_name] = 'FAIL'
                summary['overall_status'] = 'FAIL'
        
        # Add specific insights
        if 'basic_comparison' in test_results:
            comparison = test_results['basic_comparison']
            if 'comparison' in comparison:
                summary['phase2_vs_phase1'] = {
                    'phase2_successful': comparison['comparison'].get('phase2_successful', False),
                    'phase1_successful': comparison['comparison'].get('phase1_successful', False),
                    'phase2_faster': comparison['comparison'].get('phase2_faster', False)
                }
        
        if 'document_processing' in test_results:
            doc_result = test_results['document_processing']
            if 'completion_rate' in doc_result:
                summary['document_processing_performance'] = {
                    'completion_rate': doc_result['completion_rate'],
                    'segments_per_second': doc_result.get('segments_per_second', 0),
                    'phase2_efficiency': doc_result.get('phase2_segments', 0) > doc_result.get('phase1_segments', 0)
                }
        
        return summary


async def main():
    """Main test execution function"""
    print("=" * 80)
    print("Phase 2 MVP Integration Test - Enhanced Translation Pipeline")
    print("=" * 80)
    
    # Create test instance
    test_suite = Phase2IntegrationTest()
    
    # Run complete test suite
    results = await test_suite.run_complete_integration_test()
    
    # Print summary
    print("\n" + "=" * 80)
    print("INTEGRATION TEST RESULTS SUMMARY")
    print("=" * 80)
    
    if 'summary' in results:
        summary = results['summary']
        print(f"Overall Status: {summary['overall_status']}")
        print(f"Tests Run: {summary['test_count']}")
        print(f"Passed: {summary['passed_tests']}")
        print(f"Failed: {summary['failed_tests']}")
        
        print("\nTest Details:")
        for test_name, status in summary.get('test_details', {}).items():
            print(f"  {test_name}: {status}")
        
        if 'phase2_vs_phase1' in summary:
            p2p1 = summary['phase2_vs_phase1']
            print(f"\nPhase 2 vs Phase 1 Comparison:")
            print(f"  Phase 2 Successful: {p2p1.get('phase2_successful')}")
            print(f"  Phase 1 Successful: {p2p1.get('phase1_successful')}")
            print(f"  Phase 2 Faster: {p2p1.get('phase2_faster')}")
        
        if 'document_processing_performance' in summary:
            doc_perf = summary['document_processing_performance']
            print(f"\nDocument Processing Performance:")
            print(f"  Completion Rate: {doc_perf.get('completion_rate', 0):.1f}%")
            print(f"  Segments/Second: {doc_perf.get('segments_per_second', 0):.2f}")
            print(f"  Phase 2 Efficiency: {doc_perf.get('phase2_efficiency')}")
    
    if 'error' in results:
        print(f"\nGlobal Error: {results['error']}")
    
    print("\n" + "=" * 80)
    print("Integration test completed. Check test_output/ for detailed results.")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    # Ensure required environment variables are set
    required_env_vars = ['OPENAI_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {missing_vars}")
        print("Please set these variables before running the integration test.")
        exit(1)
    
    # Run the test
    asyncio.run(main())