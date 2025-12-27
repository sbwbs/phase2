#!/usr/bin/env python3
"""
Batch Processing System for Phase 2
Efficient processing of 1,400+ segments with memory management and progress tracking
"""

import time
import logging
from typing import Dict, List, Tuple, Optional, Generator, Callable, Any, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from pathlib import Path
import threading
import queue
import math
from collections import deque
import psutil
import os

from data_loader_enhanced import TestDataRow, GlossaryEntry, DocumentMetadata

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BatchConfig:
    """Configuration for batch processing"""
    batch_size: int = 50
    max_workers: int = 4
    memory_limit_mb: int = 1024
    timeout_seconds: int = 300
    retry_attempts: int = 3
    progress_callback: Optional[Callable] = None
    error_callback: Optional[Callable] = None

@dataclass
class ProcessingResult:
    """Result of a processing operation"""
    success: bool
    data: Any = None
    error_message: str = ""
    processing_time: float = 0.0
    metadata: Dict = field(default_factory=dict)

@dataclass
class BatchStats:
    """Statistics for batch processing"""
    total_items: int = 0
    processed_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    batches_processed: int = 0
    total_batches: int = 0
    processing_time: float = 0.0
    avg_batch_time: float = 0.0
    throughput_items_per_sec: float = 0.0
    memory_usage_mb: float = 0.0
    errors: List[str] = field(default_factory=list)

class MemoryMonitor:
    """Monitor memory usage during batch processing"""
    
    def __init__(self, limit_mb: int = 1024):
        self.limit_mb = limit_mb
        self.process = psutil.Process()
        self.peak_usage = 0.0
        self.warnings_issued = 0
    
    def get_current_usage_mb(self) -> float:
        """Get current memory usage in MB"""
        try:
            memory_info = self.process.memory_info()
            usage_mb = memory_info.rss / (1024 * 1024)
            self.peak_usage = max(self.peak_usage, usage_mb)
            return usage_mb
        except Exception:
            return 0.0
    
    def check_memory_limit(self) -> bool:
        """Check if memory usage is within limits"""
        current_usage = self.get_current_usage_mb()
        
        if current_usage > self.limit_mb:
            if self.warnings_issued < 5:  # Limit warning spam
                logger.warning(f"Memory usage ({current_usage:.1f}MB) exceeds limit ({self.limit_mb}MB)")
                self.warnings_issued += 1
            return False
        
        return True
    
    def get_stats(self) -> Dict[str, float]:
        """Get memory statistics"""
        return {
            "current_mb": self.get_current_usage_mb(),
            "peak_mb": self.peak_usage,
            "limit_mb": self.limit_mb,
            "utilization_percent": (self.get_current_usage_mb() / self.limit_mb) * 100
        }

class ProgressTracker:
    """Track and report processing progress"""
    
    def __init__(self, total_items: int, callback: Optional[Callable] = None):
        self.total_items = total_items
        self.processed_items = 0
        self.successful_items = 0
        self.failed_items = 0
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.callback = callback
        self._lock = threading.Lock()
    
    def update(self, success: bool, item_count: int = 1):
        """Update progress with new results"""
        with self._lock:
            self.processed_items += item_count
            if success:
                self.successful_items += item_count
            else:
                self.failed_items += item_count
            
            current_time = time.time()
            if current_time - self.last_update_time >= 5.0:  # Update every 5 seconds
                self._report_progress()
                self.last_update_time = current_time
    
    def _report_progress(self):
        """Report current progress"""
        elapsed_time = time.time() - self.start_time
        progress_percent = (self.processed_items / max(self.total_items, 1)) * 100
        
        if elapsed_time > 0:
            throughput = self.processed_items / elapsed_time
            eta_seconds = (self.total_items - self.processed_items) / max(throughput, 0.001)
        else:
            throughput = 0
            eta_seconds = 0
        
        logger.info(f"Progress: {self.processed_items}/{self.total_items} ({progress_percent:.1f}%) "
                   f"| Success: {self.successful_items} | Failed: {self.failed_items} "
                   f"| Throughput: {throughput:.1f} items/s | ETA: {eta_seconds:.0f}s")
        
        if self.callback:
            self.callback({
                "processed": self.processed_items,
                "total": self.total_items,
                "progress_percent": progress_percent,
                "successful": self.successful_items,
                "failed": self.failed_items,
                "throughput": throughput,
                "eta_seconds": eta_seconds
            })
    
    def finalize(self) -> Dict[str, Union[int, float]]:
        """Finalize tracking and return final stats"""
        elapsed_time = time.time() - self.start_time
        throughput = self.processed_items / max(elapsed_time, 0.001)
        
        final_stats = {
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "processing_time": elapsed_time,
            "throughput": throughput,
            "success_rate": (self.successful_items / max(self.processed_items, 1)) * 100
        }
        
        logger.info(f"Processing complete: {self.successful_items}/{self.total_items} successful "
                   f"({final_stats['success_rate']:.1f}%) in {elapsed_time:.2f}s "
                   f"({throughput:.1f} items/s)")
        
        return final_stats

class BatchProcessor:
    """
    High-performance batch processor for large translation datasets
    """
    
    def __init__(self, config: BatchConfig = None):
        """
        Initialize batch processor
        
        Args:
            config: Batch processing configuration
        """
        self.config = config or BatchConfig()
        self.memory_monitor = MemoryMonitor(self.config.memory_limit_mb)
        self.processing_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self._shutdown = False
        
        logger.info(f"Batch processor initialized with config: {self.config}")
    
    def create_batches(self, items: List[Any], batch_size: Optional[int] = None) -> List[List[Any]]:
        """
        Create batches from a list of items
        
        Args:
            items: List of items to batch
            batch_size: Size of each batch (defaults to config batch_size)
        
        Returns:
            List of batches
        """
        batch_size = batch_size or self.config.batch_size
        batches = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batches.append(batch)
        
        logger.info(f"Created {len(batches)} batches from {len(items)} items "
                   f"(batch_size={batch_size})")
        
        return batches
    
    def process_batch(self, 
                     batch: List[Any], 
                     processor_func: Callable[[Any], ProcessingResult],
                     batch_id: int = 0) -> List[ProcessingResult]:
        """
        Process a single batch of items
        
        Args:
            batch: List of items to process
            processor_func: Function to process each item
            batch_id: Identifier for this batch
        
        Returns:
            List of processing results
        """
        start_time = time.time()
        results = []
        
        logger.debug(f"Processing batch {batch_id} with {len(batch)} items")
        
        for i, item in enumerate(batch):
            try:
                # Check memory before processing
                if not self.memory_monitor.check_memory_limit():
                    # Force garbage collection if memory is high
                    import gc
                    gc.collect()
                
                result = processor_func(item)
                results.append(result)
                
            except Exception as e:
                error_msg = f"Error processing item {i} in batch {batch_id}: {e}"
                logger.error(error_msg)
                
                results.append(ProcessingResult(
                    success=False,
                    error_message=error_msg,
                    metadata={"batch_id": batch_id, "item_index": i}
                ))
                
                if self.config.error_callback:
                    self.config.error_callback(error_msg)
        
        processing_time = time.time() - start_time
        
        logger.debug(f"Batch {batch_id} completed in {processing_time:.2f}s "
                    f"({len([r for r in results if r.success])}/{len(results)} successful)")
        
        return results
    
    def process_batches_concurrent(self, 
                                  batches: List[List[Any]], 
                                  processor_func: Callable[[Any], ProcessingResult],
                                  use_processes: bool = False) -> List[List[ProcessingResult]]:
        """
        Process multiple batches concurrently
        
        Args:
            batches: List of batches to process
            processor_func: Function to process each item
            use_processes: Whether to use process pool (vs thread pool)
        
        Returns:
            List of result lists (one per batch)
        """
        start_time = time.time()
        
        # Choose executor type
        executor_class = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        max_workers = min(self.config.max_workers, len(batches))
        
        logger.info(f"Processing {len(batches)} batches with {max_workers} workers "
                   f"({'processes' if use_processes else 'threads'})")
        
        # Set up progress tracking
        total_items = sum(len(batch) for batch in batches)
        progress_tracker = ProgressTracker(total_items, self.config.progress_callback)
        
        batch_results = [None] * len(batches)
        
        with executor_class(max_workers=max_workers) as executor:
            # Submit all batch processing tasks
            future_to_batch = {
                executor.submit(self.process_batch, batch, processor_func, i): i
                for i, batch in enumerate(batches)
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_batch, timeout=self.config.timeout_seconds):
                batch_id = future_to_batch[future]
                
                try:
                    results = future.result()
                    batch_results[batch_id] = results
                    
                    # Update progress
                    successful_count = sum(1 for r in results if r.success)
                    progress_tracker.update(True, successful_count)
                    progress_tracker.update(False, len(results) - successful_count)
                    
                except Exception as e:
                    error_msg = f"Batch {batch_id} failed: {e}"
                    logger.error(error_msg)
                    
                    # Create error results for the entire batch
                    batch_size = len(batches[batch_id])
                    error_results = [
                        ProcessingResult(False, error_message=error_msg)
                        for _ in range(batch_size)
                    ]
                    batch_results[batch_id] = error_results
                    
                    progress_tracker.update(False, batch_size)
        
        # Finalize progress tracking
        final_stats = progress_tracker.finalize()
        
        processing_time = time.time() - start_time
        logger.info(f"Concurrent batch processing completed in {processing_time:.2f}s")
        
        return batch_results
    
    def process_items_in_batches(self, 
                                items: List[Any], 
                                processor_func: Callable[[Any], ProcessingResult],
                                batch_size: Optional[int] = None,
                                use_processes: bool = False) -> Tuple[List[ProcessingResult], BatchStats]:
        """
        Process a list of items in batches
        
        Args:
            items: List of items to process
            processor_func: Function to process each item
            batch_size: Size of each batch
            use_processes: Whether to use process pool
        
        Returns:
            Tuple of (all_results, batch_stats)
        """
        start_time = time.time()
        
        # Create batches
        batch_size = batch_size or self.config.batch_size
        batches = self.create_batches(items, batch_size)
        
        # Process batches
        batch_results = self.process_batches_concurrent(
            batches, processor_func, use_processes
        )
        
        # Flatten results
        all_results = []
        for batch_result in batch_results:
            if batch_result:
                all_results.extend(batch_result)
        
        # Calculate statistics
        processing_time = time.time() - start_time
        successful_items = sum(1 for r in all_results if r.success)
        failed_items = len(all_results) - successful_items
        
        stats = BatchStats(
            total_items=len(items),
            processed_items=len(all_results),
            successful_items=successful_items,
            failed_items=failed_items,
            batches_processed=len([b for b in batch_results if b is not None]),
            total_batches=len(batches),
            processing_time=processing_time,
            avg_batch_time=processing_time / max(len(batches), 1),
            throughput_items_per_sec=len(all_results) / max(processing_time, 0.001),
            memory_usage_mb=self.memory_monitor.get_current_usage_mb(),
            errors=[r.error_message for r in all_results if not r.success and r.error_message]
        )
        
        logger.info(f"Batch processing complete: {successful_items}/{len(items)} successful "
                   f"({(successful_items/max(len(items), 1))*100:.1f}%) "
                   f"in {processing_time:.2f}s ({stats.throughput_items_per_sec:.1f} items/s)")
        
        return all_results, stats
    
    def process_test_data_segments(self, 
                                  test_data: List[TestDataRow],
                                  processor_func: Callable[[TestDataRow], ProcessingResult],
                                  batch_size: Optional[int] = None) -> Tuple[List[ProcessingResult], BatchStats]:
        """
        Process test data segments in batches
        
        Args:
            test_data: List of test data rows
            processor_func: Function to process each test data row
            batch_size: Size of each batch
        
        Returns:
            Tuple of (results, stats)
        """
        logger.info(f"Processing {len(test_data)} test data segments in batches")
        
        return self.process_items_in_batches(
            test_data, processor_func, batch_size, use_processes=False
        )
    
    def process_glossary_terms(self, 
                              glossary: List[GlossaryEntry],
                              processor_func: Callable[[GlossaryEntry], ProcessingResult],
                              batch_size: Optional[int] = None) -> Tuple[List[ProcessingResult], BatchStats]:
        """
        Process glossary terms in batches
        
        Args:
            glossary: List of glossary entries
            processor_func: Function to process each glossary entry
            batch_size: Size of each batch
        
        Returns:
            Tuple of (results, stats)
        """
        logger.info(f"Processing {len(glossary)} glossary terms in batches")
        
        return self.process_items_in_batches(
            glossary, processor_func, batch_size, use_processes=False
        )

class AdaptiveBatchProcessor(BatchProcessor):
    """
    Adaptive batch processor that adjusts batch size based on performance
    """
    
    def __init__(self, config: BatchConfig = None):
        super().__init__(config)
        self.performance_history = deque(maxlen=10)
        self.min_batch_size = 10
        self.max_batch_size = 200
        self.adaptation_enabled = True
    
    def _analyze_performance(self, stats: BatchStats) -> float:
        """Analyze performance and return a score"""
        if stats.processing_time == 0:
            return 0.0
        
        # Score based on throughput and success rate
        throughput_score = stats.throughput_items_per_sec
        success_score = (stats.successful_items / max(stats.processed_items, 1)) * 100
        
        # Combined score (weighted towards throughput)
        return (throughput_score * 0.7) + (success_score * 0.3)
    
    def _adapt_batch_size(self) -> int:
        """Adapt batch size based on performance history"""
        if not self.adaptation_enabled or len(self.performance_history) < 3:
            return self.config.batch_size
        
        # Get recent performance scores
        recent_scores = list(self.performance_history)[-3:]
        
        # If performance is improving, try increasing batch size
        if recent_scores[-1] > recent_scores[0]:
            new_batch_size = min(
                int(self.config.batch_size * 1.2), 
                self.max_batch_size
            )
        # If performance is declining, try decreasing batch size
        elif recent_scores[-1] < recent_scores[0] * 0.9:
            new_batch_size = max(
                int(self.config.batch_size * 0.8), 
                self.min_batch_size
            )
        else:
            new_batch_size = self.config.batch_size
        
        if new_batch_size != self.config.batch_size:
            logger.info(f"Adapting batch size: {self.config.batch_size} -> {new_batch_size}")
            self.config.batch_size = new_batch_size
        
        return new_batch_size
    
    def process_items_in_batches(self, 
                                items: List[Any], 
                                processor_func: Callable[[Any], ProcessingResult],
                                batch_size: Optional[int] = None,
                                use_processes: bool = False) -> Tuple[List[ProcessingResult], BatchStats]:
        """
        Process items with adaptive batch sizing
        """
        # Use adaptive batch size if not specified
        if batch_size is None:
            batch_size = self._adapt_batch_size()
        
        # Process normally
        results, stats = super().process_items_in_batches(
            items, processor_func, batch_size, use_processes
        )
        
        # Record performance for future adaptation
        if self.adaptation_enabled:
            performance_score = self._analyze_performance(stats)
            self.performance_history.append(performance_score)
            
            logger.debug(f"Performance score: {performance_score:.2f} "
                        f"(batch_size={batch_size}, throughput={stats.throughput_items_per_sec:.1f})")
        
        return results, stats


# Convenience functions
def create_batch_config(batch_size: int = 50,
                       max_workers: int = 4,
                       memory_limit_mb: int = 1024,
                       progress_callback: Optional[Callable] = None) -> BatchConfig:
    """Create a batch configuration with common settings"""
    return BatchConfig(
        batch_size=batch_size,
        max_workers=max_workers,
        memory_limit_mb=memory_limit_mb,
        progress_callback=progress_callback
    )

def process_large_dataset(items: List[Any],
                         processor_func: Callable[[Any], ProcessingResult],
                         batch_size: int = 50,
                         max_workers: int = 4,
                         adaptive: bool = True) -> Tuple[List[ProcessingResult], BatchStats]:
    """
    Convenience function to process large datasets
    
    Args:
        items: List of items to process
        processor_func: Function to process each item
        batch_size: Initial batch size
        max_workers: Maximum number of concurrent workers
        adaptive: Whether to use adaptive batch sizing
    
    Returns:
        Tuple of (results, stats)
    """
    config = create_batch_config(batch_size, max_workers)
    
    if adaptive:
        processor = AdaptiveBatchProcessor(config)
    else:
        processor = BatchProcessor(config)
    
    return processor.process_items_in_batches(items, processor_func)


if __name__ == "__main__":
    # Demo usage
    import random
    
    def dummy_processor(item: int) -> ProcessingResult:
        """Dummy processor for demonstration"""
        # Simulate some processing time
        processing_time = random.uniform(0.01, 0.1)
        time.sleep(processing_time)
        
        # Simulate occasional failures
        success = random.random() > 0.05  # 95% success rate
        
        return ProcessingResult(
            success=success,
            data=item * 2 if success else None,
            error_message="Random failure" if not success else "",
            processing_time=processing_time
        )
    
    print("Batch Processing Demo")
    print("=" * 30)
    
    # Create test data
    test_items = list(range(1000))
    
    # Progress callback
    def progress_callback(progress_info):
        print(f"Progress: {progress_info['progress_percent']:.1f}% "
              f"({progress_info['processed']}/{progress_info['total']})")
    
    # Process with adaptive batch processor
    results, stats = process_large_dataset(
        test_items, 
        dummy_processor, 
        batch_size=50,
        max_workers=4,
        adaptive=True
    )
    
    print(f"\nProcessing Results:")
    print(f"  Total items: {stats.total_items}")
    print(f"  Successful: {stats.successful_items}")
    print(f"  Failed: {stats.failed_items}")
    print(f"  Success rate: {(stats.successful_items/stats.total_items)*100:.1f}%")
    print(f"  Processing time: {stats.processing_time:.2f}s")
    print(f"  Throughput: {stats.throughput_items_per_sec:.1f} items/s")
    print(f"  Memory usage: {stats.memory_usage_mb:.1f}MB")