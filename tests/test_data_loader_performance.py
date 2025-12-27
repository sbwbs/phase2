#!/usr/bin/env python3
"""
Performance Tests and Benchmarks for Enhanced Data Loader System
Tests the data loading performance with 1,400+ segments and 2,794+ glossary terms
"""

import time
import logging
import psutil
import os
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
import statistics
from pathlib import Path

from data_loader_enhanced import EnhancedDataLoader, get_phase2_data_summary
from data_validator import DataValidator, validate_phase2_data
from batch_processor import BatchProcessor, BatchConfig, ProcessingResult
from data_integration import Phase2DataIntegrator, IntegrationConfig, setup_phase2_integration

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Performance metrics for benchmarking"""
    operation_name: str
    execution_time: float
    items_processed: int
    throughput_items_per_sec: float
    memory_usage_mb: float
    peak_memory_mb: float
    success_rate: float
    cpu_usage_percent: float

@dataclass
class BenchmarkResult:
    """Complete benchmark result"""
    test_name: str
    total_time: float
    metrics: List[PerformanceMetrics]
    summary: Dict[str, Any]
    system_info: Dict[str, Any]

class PerformanceBenchmark:
    """
    Performance benchmark suite for Phase 2 data loading system
    """
    
    def __init__(self, data_dir: str = "../Phase 2_AI testing kit/한영"):
        self.data_dir = data_dir
        self.process = psutil.Process()
        self.metrics_history: List[PerformanceMetrics] = []
        
        # Target performance requirements
        self.targets = {
            "load_time_seconds": 10.0,  # Load 1,400+ segments in <10 seconds
            "success_rate_percent": 99.0,  # 99%+ success rate
            "memory_limit_mb": 1024,  # Stay under 1GB memory
            "throughput_items_per_sec": 140  # Process at least 140 items/second
        }
        
        logger.info(f"Performance benchmark initialized for {data_dir}")
        logger.info(f"Performance targets: {self.targets}")

    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information for benchmarking context"""
        return {
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": psutil.virtual_memory().total / (1024**3),
            "python_version": os.sys.version,
            "platform": os.sys.platform,
            "process_id": os.getpid()
        }

    def _start_monitoring(self) -> Tuple[float, float]:
        """Start performance monitoring"""
        start_time = time.time()
        initial_memory = self.process.memory_info().rss / (1024 * 1024)
        return start_time, initial_memory

    def _end_monitoring(self, 
                       start_time: float, 
                       initial_memory: float,
                       items_processed: int,
                       success_count: int,
                       operation_name: str) -> PerformanceMetrics:
        """End performance monitoring and calculate metrics"""
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Memory usage
        current_memory = self.process.memory_info().rss / (1024 * 1024)
        peak_memory = max(current_memory, initial_memory)
        
        # CPU usage (approximate)
        cpu_percent = self.process.cpu_percent()
        
        # Calculate metrics
        throughput = items_processed / max(execution_time, 0.001)
        success_rate = (success_count / max(items_processed, 1)) * 100
        
        metrics = PerformanceMetrics(
            operation_name=operation_name,
            execution_time=execution_time,
            items_processed=items_processed,
            throughput_items_per_sec=throughput,
            memory_usage_mb=current_memory,
            peak_memory_mb=peak_memory,
            success_rate=success_rate,
            cpu_usage_percent=cpu_percent
        )
        
        self.metrics_history.append(metrics)
        return metrics

    def benchmark_data_loading(self, chunk_sizes: List[int] = None) -> List[PerformanceMetrics]:
        """
        Benchmark data loading with different chunk sizes
        
        Args:
            chunk_sizes: List of chunk sizes to test
        
        Returns:
            List of performance metrics for each chunk size
        """
        if chunk_sizes is None:
            chunk_sizes = [100, 250, 500, 1000]
        
        logger.info(f"Benchmarking data loading with chunk sizes: {chunk_sizes}")
        
        results = []
        
        for chunk_size in chunk_sizes:
            logger.info(f"Testing chunk size: {chunk_size}")
            
            start_time, initial_memory = self._start_monitoring()
            
            try:
                # Create data loader
                loader = EnhancedDataLoader(
                    data_dir=self.data_dir,
                    chunk_size=chunk_size,
                    max_workers=4,
                    memory_limit_mb=1024
                )
                
                # Load all data
                test_data, glossary, documents = loader.load_all_data()
                
                total_items = len(test_data) + len(glossary)
                success_count = total_items  # Assume all successful if no exceptions
                
                metrics = self._end_monitoring(
                    start_time, initial_memory, total_items, success_count,
                    f"data_loading_chunk_{chunk_size}"
                )
                
                logger.info(f"Chunk {chunk_size}: {metrics.execution_time:.2f}s, "
                           f"{metrics.throughput_items_per_sec:.1f} items/s, "
                           f"{metrics.memory_usage_mb:.1f}MB")
                
                results.append(metrics)
                
            except Exception as e:
                logger.error(f"Chunk size {chunk_size} failed: {e}")
                # Create error metrics
                metrics = self._end_monitoring(
                    start_time, initial_memory, 0, 0,
                    f"data_loading_chunk_{chunk_size}_failed"
                )
                results.append(metrics)
        
        return results

    def benchmark_data_validation(self) -> PerformanceMetrics:
        """
        Benchmark data validation performance
        
        Returns:
            Performance metrics for validation
        """
        logger.info("Benchmarking data validation...")
        
        start_time, initial_memory = self._start_monitoring()
        
        try:
            # Load data first
            loader = EnhancedDataLoader(data_dir=self.data_dir)
            test_data, glossary, documents = loader.load_all_data()
            
            # Validate data
            validator = DataValidator(strict_mode=False)
            reports = validator.validate_all_data(test_data, glossary, documents)
            
            # Calculate totals
            total_items = sum(report.total_items for report in reports.values())
            valid_items = sum(report.valid_items for report in reports.values())
            
            metrics = self._end_monitoring(
                start_time, initial_memory, total_items, valid_items,
                "data_validation"
            )
            
            logger.info(f"Validation: {metrics.execution_time:.2f}s, "
                       f"{metrics.success_rate:.1f}% success rate, "
                       f"{metrics.throughput_items_per_sec:.1f} items/s")
            
            return metrics
            
        except Exception as e:
            logger.error(f"Data validation benchmark failed: {e}")
            return self._end_monitoring(
                start_time, initial_memory, 0, 0, "data_validation_failed"
            )

    def benchmark_batch_processing(self, batch_sizes: List[int] = None) -> List[PerformanceMetrics]:
        """
        Benchmark batch processing with different batch sizes
        
        Args:
            batch_sizes: List of batch sizes to test
        
        Returns:
            List of performance metrics for each batch size
        """
        if batch_sizes is None:
            batch_sizes = [25, 50, 100, 200]
        
        logger.info(f"Benchmarking batch processing with sizes: {batch_sizes}")
        
        # Load test data once
        loader = EnhancedDataLoader(data_dir=self.data_dir)
        test_data, _, _ = loader.load_all_data()
        
        # Dummy processor for testing
        def dummy_processor(item) -> ProcessingResult:
            # Simulate some processing
            time.sleep(0.001)  # 1ms processing time
            return ProcessingResult(success=True, data=item)
        
        results = []
        
        for batch_size in batch_sizes:
            logger.info(f"Testing batch size: {batch_size}")
            
            start_time, initial_memory = self._start_monitoring()
            
            try:
                config = BatchConfig(batch_size=batch_size, max_workers=4)
                processor = BatchProcessor(config)
                
                processing_results, batch_stats = processor.process_items_in_batches(
                    test_data[:500],  # Test with first 500 items
                    dummy_processor
                )
                
                metrics = self._end_monitoring(
                    start_time, initial_memory, 
                    batch_stats.processed_items, batch_stats.successful_items,
                    f"batch_processing_{batch_size}"
                )
                
                logger.info(f"Batch {batch_size}: {metrics.execution_time:.2f}s, "
                           f"{metrics.throughput_items_per_sec:.1f} items/s")
                
                results.append(metrics)
                
            except Exception as e:
                logger.error(f"Batch size {batch_size} failed: {e}")
                metrics = self._end_monitoring(
                    start_time, initial_memory, 0, 0,
                    f"batch_processing_{batch_size}_failed"
                )
                results.append(metrics)
        
        return results

    def benchmark_full_integration(self) -> PerformanceMetrics:
        """
        Benchmark full Phase 2 integration setup
        
        Returns:
            Performance metrics for full integration
        """
        logger.info("Benchmarking full Phase 2 integration...")
        
        start_time, initial_memory = self._start_monitoring()
        
        try:
            # Set up full integration
            config = IntegrationConfig(
                data_dir=self.data_dir,
                batch_size=100,
                use_valkey_cache=False,  # Disable Valkey for benchmark
                validate_data=True
            )
            
            integrator = Phase2DataIntegrator(config)
            setup_result = integrator.setup_phase2_data_pipeline()
            
            # Calculate total items processed
            total_items = setup_result.total_segments_loaded + setup_result.total_terms_loaded
            
            metrics = self._end_monitoring(
                start_time, initial_memory, total_items, total_items,
                "full_integration"
            )
            
            logger.info(f"Full integration: {metrics.execution_time:.2f}s, "
                       f"{total_items} items processed")
            
            # Cleanup
            integrator.cleanup()
            
            return metrics
            
        except Exception as e:
            logger.error(f"Full integration benchmark failed: {e}")
            return self._end_monitoring(
                start_time, initial_memory, 0, 0, "full_integration_failed"
            )

    def run_comprehensive_benchmark(self) -> BenchmarkResult:
        """
        Run comprehensive benchmark suite
        
        Returns:
            Complete benchmark results
        """
        logger.info("Starting comprehensive performance benchmark...")
        
        benchmark_start = time.time()
        all_metrics = []
        
        # Individual benchmarks
        logger.info("\n=== Data Loading Benchmark ===")
        loading_metrics = self.benchmark_data_loading()
        all_metrics.extend(loading_metrics)
        
        logger.info("\n=== Data Validation Benchmark ===")
        validation_metrics = self.benchmark_data_validation()
        all_metrics.append(validation_metrics)
        
        logger.info("\n=== Batch Processing Benchmark ===")
        batch_metrics = self.benchmark_batch_processing()
        all_metrics.extend(batch_metrics)
        
        logger.info("\n=== Full Integration Benchmark ===")
        integration_metrics = self.benchmark_full_integration()
        all_metrics.append(integration_metrics)
        
        total_benchmark_time = time.time() - benchmark_start
        
        # Calculate summary statistics
        successful_metrics = [m for m in all_metrics if m.success_rate > 0]
        
        if successful_metrics:
            avg_throughput = statistics.mean(m.throughput_items_per_sec for m in successful_metrics)
            max_memory = max(m.peak_memory_mb for m in all_metrics)
            avg_success_rate = statistics.mean(m.success_rate for m in all_metrics)
        else:
            avg_throughput = 0
            max_memory = 0
            avg_success_rate = 0
        
        summary = {
            "total_tests": len(all_metrics),
            "successful_tests": len(successful_metrics),
            "avg_throughput_items_per_sec": avg_throughput,
            "max_memory_usage_mb": max_memory,
            "avg_success_rate": avg_success_rate,
            "performance_targets_met": self._check_performance_targets(all_metrics)
        }
        
        return BenchmarkResult(
            test_name="comprehensive_phase2_benchmark",
            total_time=total_benchmark_time,
            metrics=all_metrics,
            summary=summary,
            system_info=self._get_system_info()
        )

    def _check_performance_targets(self, metrics: List[PerformanceMetrics]) -> Dict[str, bool]:
        """Check if performance targets are met"""
        targets_met = {}
        
        # Find best loading performance
        loading_metrics = [m for m in metrics if "data_loading" in m.operation_name and m.success_rate > 0]
        if loading_metrics:
            best_loading = min(loading_metrics, key=lambda x: x.execution_time)
            targets_met["load_time_under_10s"] = best_loading.execution_time <= self.targets["load_time_seconds"]
            targets_met["throughput_over_140_per_sec"] = best_loading.throughput_items_per_sec >= self.targets["throughput_items_per_sec"]
        
        # Check success rates
        if metrics:
            avg_success_rate = statistics.mean(m.success_rate for m in metrics)
            targets_met["success_rate_over_99pct"] = avg_success_rate >= self.targets["success_rate_percent"]
            
            max_memory = max(m.peak_memory_mb for m in metrics)
            targets_met["memory_under_1gb"] = max_memory <= self.targets["memory_limit_mb"]
        
        return targets_met

    def print_benchmark_report(self, result: BenchmarkResult):
        """Print comprehensive benchmark report"""
        print("\n" + "="*60)
        print("PHASE 2 DATA LOADER PERFORMANCE BENCHMARK REPORT")
        print("="*60)
        
        print(f"\nBenchmark: {result.test_name}")
        print(f"Total Time: {result.total_time:.2f} seconds")
        print(f"System: {result.system_info['cpu_count']} CPUs, {result.system_info['memory_total_gb']:.1f}GB RAM")
        
        print(f"\nSUMMARY:")
        print(f"  Tests Run: {result.summary['total_tests']}")
        print(f"  Successful: {result.summary['successful_tests']}")
        print(f"  Average Throughput: {result.summary['avg_throughput_items_per_sec']:.1f} items/sec")
        print(f"  Peak Memory: {result.summary['max_memory_usage_mb']:.1f}MB")
        print(f"  Average Success Rate: {result.summary['avg_success_rate']:.1f}%")
        
        print(f"\nPERFORMANCE TARGETS:")
        targets = result.summary['performance_targets_met']
        for target, met in targets.items():
            status = "✅ PASS" if met else "❌ FAIL"
            print(f"  {target}: {status}")
        
        print(f"\nDETAILED RESULTS:")
        for metric in result.metrics:
            print(f"  {metric.operation_name}:")
            print(f"    Time: {metric.execution_time:.2f}s")
            print(f"    Items: {metric.items_processed}")
            print(f"    Throughput: {metric.throughput_items_per_sec:.1f} items/s")
            print(f"    Memory: {metric.memory_usage_mb:.1f}MB")
            print(f"    Success Rate: {metric.success_rate:.1f}%")
            print()


def run_performance_tests():
    """Run performance tests and generate report"""
    print("Phase 2 Enhanced Data Loader Performance Tests")
    print("=" * 50)
    
    # Check if test data exists
    data_dir = "../Phase 2_AI testing kit/한영"
    if not Path(data_dir).exists():
        print(f"Test data directory not found: {data_dir}")
        print("Please ensure Phase 2 test data is available")
        return
    
    # Quick data summary first
    print("Analyzing test data...")
    try:
        summary = get_phase2_data_summary(data_dir)
        print("Test Data Summary:")
        for file_type, info in summary.get("files", {}).items():
            rows = info.get('rows', info.get('total_rows', 0))
            print(f"  {file_type}: {rows} rows, {info['size_mb']:.1f}MB")
    except Exception as e:
        print(f"Could not analyze test data: {e}")
        return
    
    # Run benchmarks
    benchmark = PerformanceBenchmark(data_dir)
    result = benchmark.run_comprehensive_benchmark()
    
    # Print report
    benchmark.print_benchmark_report(result)
    
    # Overall assessment
    targets_met = result.summary['performance_targets_met']
    passed_targets = sum(targets_met.values())
    total_targets = len(targets_met)
    
    print(f"\nOVERALL ASSESSMENT:")
    if passed_targets == total_targets:
        print("🎉 ALL PERFORMANCE TARGETS MET!")
        print("The enhanced data loader meets all Phase 2 requirements.")
    elif passed_targets >= total_targets * 0.75:
        print("✅ PERFORMANCE ACCEPTABLE")
        print(f"Met {passed_targets}/{total_targets} targets. Some optimization may be needed.")
    else:
        print("⚠️  PERFORMANCE NEEDS IMPROVEMENT")
        print(f"Only met {passed_targets}/{total_targets} targets. Significant optimization required.")


if __name__ == "__main__":
    run_performance_tests()