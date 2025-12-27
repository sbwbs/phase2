"""
Document Processor for Phase 2 MVP - Large-Scale Translation Workflow Manager

This module handles document-level translation workflows for processing 1,400+ segments
with intelligent batching, progress tracking, error recovery, and performance optimization.

Key Features:
- Large document processing (1,400+ segments) with memory efficiency
- Intelligent batch sizing based on model capacity and performance
- Progress tracking with real-time updates and resumption capability
- Error recovery with segment-level retry logic
- Performance monitoring and optimization
- Integration with Valkey session management
- Support for both Phase 1 and Phase 2 operation modes
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import pandas as pd

from enhanced_translation_service import (
    EnhancedTranslationService, 
    EnhancedTranslationRequest,
    EnhancedTranslationResult,
    OperationMode,
    create_enhanced_request,
    create_batch_requests_from_segments
)


class ProcessingStatus(Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SegmentStatus(Enum):
    """Individual segment processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class DocumentMetadata:
    """Document processing metadata"""
    doc_id: str
    source_file: str
    target_file: str
    total_segments: int
    source_language: str = "korean"
    target_language: str = "english"
    domain: str = "clinical_trial"
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = self.created_at


@dataclass
class SegmentData:
    """Individual segment data"""
    segment_id: str
    korean_text: str
    english_translation: str = ""
    status: SegmentStatus = SegmentStatus.PENDING
    model_used: str = ""
    tokens_used: int = 0
    processing_time_ms: float = 0.0
    retry_count: int = 0
    error_message: str = ""
    operation_mode_used: str = ""
    token_reduction_percent: float = 0.0


@dataclass
class ProcessingProgress:
    """Processing progress tracking"""
    doc_id: str
    status: ProcessingStatus
    total_segments: int
    completed_segments: int
    failed_segments: int
    retrying_segments: int
    
    # Performance metrics
    total_processing_time_ms: float = 0.0
    total_tokens_used: int = 0
    total_tokens_saved: int = 0
    phase1_segments: int = 0
    phase2_segments: int = 0
    
    # Batch statistics
    total_batches: int = 0
    completed_batches: int = 0
    average_batch_time_ms: float = 0.0
    
    # Error tracking
    error_rate: float = 0.0
    common_errors: Dict[str, int] = None
    
    def __post_init__(self):
        if self.common_errors is None:
            self.common_errors = {}
    
    @property
    def completion_percent(self) -> float:
        return (self.completed_segments / self.total_segments * 100) if self.total_segments > 0 else 0.0
    
    @property
    def pending_segments(self) -> int:
        return self.total_segments - self.completed_segments - self.failed_segments - self.retrying_segments


@dataclass
class BatchConfiguration:
    """Batch processing configuration"""
    batch_size: int = 10
    max_concurrent_batches: int = 3
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    progress_update_interval: int = 10  # Update progress every N segments
    checkpoint_interval: int = 100  # Save checkpoint every N segments
    enable_adaptive_batching: bool = True
    target_batch_time_ms: float = 30000.0  # 30 seconds target per batch


class DocumentProcessor:
    """Large-scale document translation processor"""
    
    def __init__(self,
                 translation_service: EnhancedTranslationService,
                 output_directory: str = "./output",
                 checkpoint_directory: str = "./checkpoints",
                 enable_checkpointing: bool = True,
                 progress_callback: Optional[Callable[[ProcessingProgress], None]] = None):
        """
        Initialize document processor
        
        Args:
            translation_service: Enhanced translation service
            output_directory: Directory for output files
            checkpoint_directory: Directory for checkpoint files
            enable_checkpointing: Enable checkpoint saving/loading
            progress_callback: Optional callback for progress updates
        """
        self.translation_service = translation_service
        self.output_directory = Path(output_directory)
        self.checkpoint_directory = Path(checkpoint_directory)
        self.enable_checkpointing = enable_checkpointing
        self.progress_callback = progress_callback
        
        self.logger = logging.getLogger(__name__)
        
        # Create directories
        self.output_directory.mkdir(parents=True, exist_ok=True)
        if enable_checkpointing:
            self.checkpoint_directory.mkdir(parents=True, exist_ok=True)
        
        # Processing state
        self.active_documents: Dict[str, ProcessingProgress] = {}
        self.document_segments: Dict[str, List[SegmentData]] = {}
        self.document_metadata: Dict[str, DocumentMetadata] = {}
        
        # Performance tracking
        self.total_documents_processed = 0
        self.total_segments_processed = 0
        self.total_processing_time = 0.0
        
        self.logger.info("DocumentProcessor initialized")
    
    async def process_document(self,
                             doc_id: str,
                             input_file: str,
                             model_name: str,
                             operation_mode: OperationMode = OperationMode.AUTO_DETECT,
                             batch_config: Optional[BatchConfiguration] = None,
                             resume_from_checkpoint: bool = True) -> ProcessingProgress:
        """
        Process a complete document with translation
        
        Args:
            doc_id: Unique document identifier
            input_file: Path to input file (Excel/CSV)
            model_name: Model to use for translation
            operation_mode: Operation mode (Phase 1/Phase 2)
            batch_config: Batch processing configuration
            resume_from_checkpoint: Resume from checkpoint if available
            
        Returns:
            Final processing progress
        """
        start_time = time.time()
        
        try:
            # Load or resume document
            if resume_from_checkpoint:
                progress = await self._load_checkpoint(doc_id)
                if progress:
                    self.logger.info(f"Resuming document {doc_id} from checkpoint")
                    return await self._resume_document_processing(
                        doc_id, model_name, operation_mode, batch_config
                    )
            
            # Load document segments
            segments = await self._load_document_segments(input_file)
            metadata = DocumentMetadata(
                doc_id=doc_id,
                source_file=input_file,
                target_file=str(self.output_directory / f"{doc_id}_translated.xlsx"),
                total_segments=len(segments)
            )
            
            # Initialize processing state
            segment_data = []
            for i, (segment_id, korean_text) in enumerate(segments):
                segment_data.append(SegmentData(
                    segment_id=segment_id or f"segment_{i+1:04d}",
                    korean_text=korean_text
                ))
            
            self.document_segments[doc_id] = segment_data
            self.document_metadata[doc_id] = metadata
            
            # Initialize progress tracking
            progress = ProcessingProgress(
                doc_id=doc_id,
                status=ProcessingStatus.PROCESSING,
                total_segments=len(segments),
                completed_segments=0,
                failed_segments=0,
                retrying_segments=0
            )
            self.active_documents[doc_id] = progress
            
            # Start document session in translation service
            await self.translation_service.start_document_session(
                doc_id=doc_id,
                total_segments=len(segments),
                source_language=metadata.source_language,
                target_language=metadata.target_language
            )
            
            # Process document in batches
            progress = await self._process_document_batches(
                doc_id, model_name, operation_mode, batch_config or BatchConfiguration()
            )
            
            # Save final results
            await self._save_document_results(doc_id)
            
            # Update final status
            progress.status = ProcessingStatus.COMPLETED
            progress.total_processing_time_ms = (time.time() - start_time) * 1000
            
            # Clean up
            await self._cleanup_document_processing(doc_id)
            
            self.total_documents_processed += 1
            self.logger.info(f"Document {doc_id} processing completed")
            
            return progress
            
        except Exception as e:
            self.logger.error(f"Document processing failed for {doc_id}: {e}")
            
            if doc_id in self.active_documents:
                self.active_documents[doc_id].status = ProcessingStatus.FAILED
            
            raise
    
    async def _load_document_segments(self, input_file: str) -> List[Tuple[str, str]]:
        """Load document segments from input file"""
        file_path = Path(input_file)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")
        
        # Load based on file extension
        if file_path.suffix.lower() == '.xlsx':
            df = pd.read_excel(input_file)
        elif file_path.suffix.lower() == '.csv':
            df = pd.read_csv(input_file)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
        
        # Detect columns
        korean_col = self._detect_korean_column(df)
        segment_id_col = self._detect_segment_id_column(df)
        
        if not korean_col:
            raise ValueError("Could not detect Korean text column")
        
        segments = []
        for idx, row in df.iterrows():
            korean_text = str(row[korean_col]).strip()
            segment_id = str(row[segment_id_col]).strip() if segment_id_col else f"segment_{idx+1:04d}"
            
            if korean_text and korean_text != 'nan':
                segments.append((segment_id, korean_text))
        
        self.logger.info(f"Loaded {len(segments)} segments from {input_file}")
        return segments
    
    def _detect_korean_column(self, df: pd.DataFrame) -> Optional[str]:
        """Detect column containing Korean text"""
        # Check column names first
        korean_patterns = ['korean', '한국어', '한글', 'ko', 'kr', '원문', '출발어', 'source']
        
        for col in df.columns:
            col_lower = str(col).lower()
            if any(pattern in col_lower for pattern in korean_patterns):
                return col
        
        # Check content for Korean characters
        for col in df.columns:
            if df[col].dtype == 'object':
                sample_text = ' '.join(df[col].astype(str).head(10))
                korean_chars = len([c for c in sample_text if '가' <= c <= '힣'])
                if korean_chars > 10:
                    return col
        
        return None
    
    def _detect_segment_id_column(self, df: pd.DataFrame) -> Optional[str]:
        """Detect column containing segment IDs"""
        id_patterns = ['id', 'segment', 'index', '번호', 'no', 'number']
        
        for col in df.columns:
            col_lower = str(col).lower()
            if any(pattern in col_lower for pattern in id_patterns):
                return col
        
        return None
    
    async def _process_document_batches(self,
                                      doc_id: str,
                                      model_name: str,
                                      operation_mode: OperationMode,
                                      batch_config: BatchConfiguration) -> ProcessingProgress:
        """Process document segments in optimized batches"""
        
        segments = self.document_segments[doc_id]
        progress = self.active_documents[doc_id]
        
        # Calculate batch parameters
        batch_size = batch_config.batch_size
        if batch_config.enable_adaptive_batching:
            batch_size = self._calculate_optimal_batch_size(model_name, operation_mode)
        
        # Create batches
        pending_segments = [s for s in segments if s.status == SegmentStatus.PENDING]
        batches = [pending_segments[i:i+batch_size] for i in range(0, len(pending_segments), batch_size)]
        
        progress.total_batches = len(batches)
        
        # Process batches with concurrency control
        semaphore = asyncio.Semaphore(batch_config.max_concurrent_batches)
        
        async def process_batch_with_semaphore(batch_segments, batch_index):
            async with semaphore:
                return await self._process_batch(
                    doc_id, batch_segments, batch_index, model_name, 
                    operation_mode, batch_config
                )
        
        # Execute batches
        batch_tasks = [
            process_batch_with_semaphore(batch, i) 
            for i, batch in enumerate(batches)
        ]
        
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # Process batch results
        successful_batches = 0
        total_batch_time = 0.0
        
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                self.logger.error(f"Batch {i} failed: {result}")
                # Mark segments as failed
                for segment in batches[i]:
                    segment.status = SegmentStatus.FAILED
                    segment.error_message = str(result)
                    progress.failed_segments += 1
            else:
                successful_batches += 1
                total_batch_time += result
        
        # Update progress
        progress.completed_batches = successful_batches
        progress.average_batch_time_ms = total_batch_time / max(successful_batches, 1)
        progress.error_rate = progress.failed_segments / progress.total_segments
        
        # Handle retries for failed segments
        await self._retry_failed_segments(doc_id, model_name, operation_mode, batch_config)
        
        return progress
    
    async def _process_batch(self,
                           doc_id: str,
                           batch_segments: List[SegmentData],
                           batch_index: int,
                           model_name: str,
                           operation_mode: OperationMode,
                           batch_config: BatchConfiguration) -> float:
        """Process a single batch of segments"""
        
        start_time = time.time()
        progress = self.active_documents[doc_id]
        
        try:
            # Mark segments as processing
            for segment in batch_segments:
                segment.status = SegmentStatus.PROCESSING
            
            # Create translation requests
            requests = []
            for segment in batch_segments:
                request = create_enhanced_request(
                    korean_text=segment.korean_text,
                    model_name=model_name,
                    segment_id=segment.segment_id,
                    doc_id=doc_id,
                    operation_mode=operation_mode
                )
                requests.append(request)
            
            # Execute batch translation
            results = await self.translation_service.translate_batch(requests)
            
            # Process results
            for segment, result in zip(batch_segments, results):
                if result.error:
                    segment.status = SegmentStatus.FAILED
                    segment.error_message = result.error
                    progress.failed_segments += 1
                    
                    # Track common errors
                    error_key = result.error[:50]  # First 50 chars
                    progress.common_errors[error_key] = progress.common_errors.get(error_key, 0) + 1
                else:
                    segment.status = SegmentStatus.COMPLETED
                    segment.english_translation = result.english_translation
                    segment.model_used = result.model_used
                    segment.tokens_used = result.tokens_used or 0
                    segment.processing_time_ms = (result.processing_time or 0) * 1000
                    segment.operation_mode_used = result.operation_mode_used.value
                    segment.token_reduction_percent = result.token_reduction_percent or 0.0
                    
                    progress.completed_segments += 1
                    progress.total_tokens_used += segment.tokens_used
                    
                    if result.token_reduction_percent:
                        estimated_original = segment.tokens_used / (1 - result.token_reduction_percent / 100)
                        progress.total_tokens_saved += int(estimated_original - segment.tokens_used)
                    
                    if result.operation_mode_used == OperationMode.PHASE1_FULL_CONTEXT:
                        progress.phase1_segments += 1
                    else:
                        progress.phase2_segments += 1
            
            # Update progress callback
            if self.progress_callback and batch_index % batch_config.progress_update_interval == 0:
                self.progress_callback(progress)
            
            # Save checkpoint
            if (self.enable_checkpointing and 
                batch_index % batch_config.checkpoint_interval == 0):
                await self._save_checkpoint(doc_id)
            
            batch_time = time.time() - start_time
            progress.total_processing_time_ms += batch_time * 1000
            
            self.logger.debug(f"Batch {batch_index} completed: {len(batch_segments)} segments in {batch_time:.2f}s")
            
            return batch_time * 1000  # Return batch time in ms
            
        except Exception as e:
            # Mark all segments in batch as failed
            for segment in batch_segments:
                segment.status = SegmentStatus.FAILED
                segment.error_message = str(e)
                progress.failed_segments += 1
            
            self.logger.error(f"Batch {batch_index} processing failed: {e}")
            raise
    
    async def _retry_failed_segments(self,
                                   doc_id: str,
                                   model_name: str,
                                   operation_mode: OperationMode,
                                   batch_config: BatchConfiguration):
        """Retry failed segments with exponential backoff"""
        
        segments = self.document_segments[doc_id]
        progress = self.active_documents[doc_id]
        
        failed_segments = [s for s in segments if s.status == SegmentStatus.FAILED]
        
        if not failed_segments:
            return
        
        self.logger.info(f"Retrying {len(failed_segments)} failed segments")
        
        for retry_attempt in range(batch_config.max_retries):
            if not failed_segments:
                break
            
            # Wait before retry
            if retry_attempt > 0:
                delay = batch_config.retry_delay_seconds * (2 ** retry_attempt)
                await asyncio.sleep(delay)
            
            # Mark segments as retrying
            for segment in failed_segments:
                segment.status = SegmentStatus.RETRYING
                segment.retry_count += 1
                progress.retrying_segments += 1
                progress.failed_segments -= 1
            
            # Process failed segments individually for better error isolation
            for segment in failed_segments[:]:  # Copy list to allow modification
                try:
                    request = create_enhanced_request(
                        korean_text=segment.korean_text,
                        model_name=model_name,
                        segment_id=segment.segment_id,
                        doc_id=doc_id,
                        operation_mode=operation_mode
                    )
                    
                    result = await self.translation_service.translate(request)
                    
                    if not result.error:
                        segment.status = SegmentStatus.COMPLETED
                        segment.english_translation = result.english_translation
                        segment.model_used = result.model_used
                        segment.tokens_used = result.tokens_used or 0
                        segment.error_message = ""
                        
                        progress.completed_segments += 1
                        progress.retrying_segments -= 1
                        failed_segments.remove(segment)
                        
                        self.logger.debug(f"Retry successful for segment {segment.segment_id}")
                    else:
                        segment.error_message = f"Retry {retry_attempt + 1}: {result.error}"
                
                except Exception as e:
                    segment.error_message = f"Retry {retry_attempt + 1}: {str(e)}"
            
            # Update failed segments list
            still_failed = []
            for segment in failed_segments:
                if segment.status == SegmentStatus.RETRYING:
                    segment.status = SegmentStatus.FAILED
                    progress.retrying_segments -= 1
                    progress.failed_segments += 1
                    still_failed.append(segment)
            
            failed_segments = still_failed
        
        if failed_segments:
            self.logger.warning(f"{len(failed_segments)} segments failed after all retries")
    
    def _calculate_optimal_batch_size(self, model_name: str, operation_mode: OperationMode) -> int:
        """Calculate optimal batch size based on model and mode"""
        
        # Base batch sizes
        base_batch_sizes = {
            "Falcon": 8,    # GPT-4o
            "Sparrow": 8,   # GPT-4.1
            "Eagle": 6,     # o3 (more conservative due to reasoning)
            "Owl": 10,      # GPT-5
            "Kestrel": 12,  # GPT-5 Mini
            "Wren": 15,     # GPT-5 Nano
            "Swan": 10,     # Gemini 2.5 Flash
            "Phoenix": 6,   # Claude (rate limited)
            "Robin": 8      # Upstage Solar
        }
        
        batch_size = base_batch_sizes.get(model_name, 10)
        
        # Adjust for operation mode
        if operation_mode == OperationMode.PHASE2_SMART_CONTEXT:
            batch_size = int(batch_size * 1.5)  # Phase 2 is more efficient
        
        return max(batch_size, 5)  # Minimum batch size
    
    async def _save_document_results(self, doc_id: str):
        """Save translated document to output file"""
        
        if doc_id not in self.document_segments or doc_id not in self.document_metadata:
            raise ValueError(f"Document data not found for {doc_id}")
        
        segments = self.document_segments[doc_id]
        metadata = self.document_metadata[doc_id]
        
        # Prepare data for export
        export_data = []
        for segment in segments:
            export_data.append({
                'segment_id': segment.segment_id,
                'korean_text': segment.korean_text,
                'english_translation': segment.english_translation,
                'status': segment.status.value,
                'model_used': segment.model_used,
                'tokens_used': segment.tokens_used,
                'processing_time_ms': segment.processing_time_ms,
                'retry_count': segment.retry_count,
                'error_message': segment.error_message,
                'operation_mode': segment.operation_mode_used,
                'token_reduction_percent': segment.token_reduction_percent
            })
        
        # Save to Excel
        df = pd.DataFrame(export_data)
        df.to_excel(metadata.target_file, index=False)
        
        # Save metadata
        metadata_file = self.output_directory / f"{doc_id}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(metadata), f, indent=2, default=str)
        
        # Save progress summary
        if doc_id in self.active_documents:
            progress = self.active_documents[doc_id]
            progress_file = self.output_directory / f"{doc_id}_progress.json"
            with open(progress_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(progress), f, indent=2, default=str)
        
        self.logger.info(f"Document results saved: {metadata.target_file}")
    
    async def _save_checkpoint(self, doc_id: str):
        """Save processing checkpoint"""
        if not self.enable_checkpointing:
            return
        
        checkpoint_data = {
            'doc_id': doc_id,
            'timestamp': datetime.now().isoformat(),
            'metadata': asdict(self.document_metadata[doc_id]) if doc_id in self.document_metadata else None,
            'progress': asdict(self.active_documents[doc_id]) if doc_id in self.active_documents else None,
            'segments': [asdict(s) for s in self.document_segments.get(doc_id, [])]
        }
        
        checkpoint_file = self.checkpoint_directory / f"{doc_id}_checkpoint.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2, default=str)
        
        self.logger.debug(f"Checkpoint saved: {checkpoint_file}")
    
    async def _load_checkpoint(self, doc_id: str) -> Optional[ProcessingProgress]:
        """Load processing checkpoint"""
        if not self.enable_checkpointing:
            return None
        
        checkpoint_file = self.checkpoint_directory / f"{doc_id}_checkpoint.json"
        if not checkpoint_file.exists():
            return None
        
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            
            # Restore document state
            if checkpoint_data.get('metadata'):
                metadata_dict = checkpoint_data['metadata']
                metadata_dict['created_at'] = datetime.fromisoformat(metadata_dict['created_at'])
                metadata_dict['updated_at'] = datetime.fromisoformat(metadata_dict['updated_at'])
                self.document_metadata[doc_id] = DocumentMetadata(**metadata_dict)
            
            if checkpoint_data.get('segments'):
                segments = []
                for seg_dict in checkpoint_data['segments']:
                    segments.append(SegmentData(
                        segment_id=seg_dict['segment_id'],
                        korean_text=seg_dict['korean_text'],
                        english_translation=seg_dict.get('english_translation', ''),
                        status=SegmentStatus(seg_dict.get('status', 'pending')),
                        model_used=seg_dict.get('model_used', ''),
                        tokens_used=seg_dict.get('tokens_used', 0),
                        processing_time_ms=seg_dict.get('processing_time_ms', 0.0),
                        retry_count=seg_dict.get('retry_count', 0),
                        error_message=seg_dict.get('error_message', ''),
                        operation_mode_used=seg_dict.get('operation_mode_used', ''),
                        token_reduction_percent=seg_dict.get('token_reduction_percent', 0.0)
                    ))
                self.document_segments[doc_id] = segments
            
            if checkpoint_data.get('progress'):
                progress_dict = checkpoint_data['progress']
                progress = ProcessingProgress(**progress_dict)
                progress.status = ProcessingStatus.PENDING  # Reset to pending for resumption
                self.active_documents[doc_id] = progress
                return progress
            
        except Exception as e:
            self.logger.error(f"Failed to load checkpoint for {doc_id}: {e}")
        
        return None
    
    async def _resume_document_processing(self,
                                        doc_id: str,
                                        model_name: str,
                                        operation_mode: OperationMode,
                                        batch_config: Optional[BatchConfiguration]) -> ProcessingProgress:
        """Resume document processing from checkpoint"""
        
        progress = self.active_documents[doc_id]
        progress.status = ProcessingStatus.PROCESSING
        
        # Continue processing from where we left off
        return await self._process_document_batches(
            doc_id, model_name, operation_mode, batch_config or BatchConfiguration()
        )
    
    async def _cleanup_document_processing(self, doc_id: str):
        """Clean up document processing resources"""
        
        # Clean up session in translation service
        await self.translation_service.cleanup_session(doc_id)
        
        # Remove from active processing (keep in memory for stats)
        if doc_id in self.active_documents:
            self.active_documents[doc_id].status = ProcessingStatus.COMPLETED
        
        self.logger.debug(f"Cleaned up processing for document {doc_id}")
    
    # ========== Status and Monitoring ==========
    
    def get_processing_status(self, doc_id: str) -> Optional[ProcessingProgress]:
        """Get current processing status for document"""
        return self.active_documents.get(doc_id)
    
    def get_all_processing_status(self) -> Dict[str, ProcessingProgress]:
        """Get processing status for all documents"""
        return self.active_documents.copy()
    
    def get_processor_statistics(self) -> Dict[str, Any]:
        """Get comprehensive processor statistics"""
        
        total_segments = sum(p.total_segments for p in self.active_documents.values())
        completed_segments = sum(p.completed_segments for p in self.active_documents.values())
        failed_segments = sum(p.failed_segments for p in self.active_documents.values())
        
        return {
            'documents': {
                'total_processed': self.total_documents_processed,
                'currently_active': len([p for p in self.active_documents.values() 
                                       if p.status == ProcessingStatus.PROCESSING]),
                'completed': len([p for p in self.active_documents.values() 
                                if p.status == ProcessingStatus.COMPLETED]),
                'failed': len([p for p in self.active_documents.values() 
                             if p.status == ProcessingStatus.FAILED])
            },
            'segments': {
                'total_segments': total_segments,
                'completed_segments': completed_segments,
                'failed_segments': failed_segments,
                'completion_rate': (completed_segments / total_segments * 100) if total_segments > 0 else 0
            },
            'performance': {
                'total_processing_time_ms': self.total_processing_time,
                'average_document_time_ms': (self.total_processing_time / 
                                           max(self.total_documents_processed, 1)),
                'segments_per_second': (completed_segments / 
                                      (self.total_processing_time / 1000)) if self.total_processing_time > 0 else 0
            }
        }
    
    async def pause_document_processing(self, doc_id: str) -> bool:
        """Pause document processing"""
        if doc_id in self.active_documents:
            progress = self.active_documents[doc_id]
            if progress.status == ProcessingStatus.PROCESSING:
                progress.status = ProcessingStatus.PAUSED
                await self._save_checkpoint(doc_id)
                self.logger.info(f"Document {doc_id} processing paused")
                return True
        return False
    
    async def cancel_document_processing(self, doc_id: str) -> bool:
        """Cancel document processing"""
        if doc_id in self.active_documents:
            progress = self.active_documents[doc_id]
            progress.status = ProcessingStatus.CANCELLED
            await self._cleanup_document_processing(doc_id)
            self.logger.info(f"Document {doc_id} processing cancelled")
            return True
        return False


# Utility functions

async def process_document_simple(input_file: str,
                                 output_file: str,
                                 model_name: str,
                                 translation_service: EnhancedTranslationService,
                                 operation_mode: OperationMode = OperationMode.AUTO_DETECT) -> ProcessingProgress:
    """
    Simple document processing function for basic use cases
    
    Args:
        input_file: Path to input Excel/CSV file
        output_file: Path to output Excel file  
        model_name: Model to use for translation
        translation_service: Translation service instance
        operation_mode: Operation mode
        
    Returns:
        Final processing progress
    """
    
    # Create processor
    processor = DocumentProcessor(
        translation_service=translation_service,
        output_directory=str(Path(output_file).parent),
        enable_checkpointing=False
    )
    
    # Generate document ID from file name
    doc_id = Path(input_file).stem
    
    # Process document
    return await processor.process_document(
        doc_id=doc_id,
        input_file=input_file,
        model_name=model_name,
        operation_mode=operation_mode
    )