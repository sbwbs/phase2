#!/usr/bin/env python3
"""
Data Integration Layer for Phase 2
Connects enhanced data loader with existing Phase 2 components:
- Context Builder (CE-002)
- Glossary Search Engine (CE-001) 
- Valkey Session Management (BE-004)
- Enhanced Translation Service (BE-001)
"""

import logging
import time
from typing import Dict, List, Tuple, Optional, Union, Any
from dataclasses import dataclass, field
from pathlib import Path
import asyncio

from data_loader_enhanced import (
    EnhancedDataLoader, TestDataRow, GlossaryEntry, DocumentMetadata,
    load_phase2_data
)
from data_validator import DataValidator, validate_phase2_data
from batch_processor import BatchProcessor, BatchConfig, ProcessingResult
from glossary_search import GlossarySearchEngine, GlossaryTerm, SearchResult
from context_builder import ContextBuilder, ContextRequest, ContextBuildResult
from memory.valkey_manager import ValkeyManager, SessionMetadata, TermMapping
from memory.session_manager import SessionManager
from memory.cached_glossary_search import CachedGlossarySearch

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class IntegrationConfig:
    """Configuration for data integration"""
    data_dir: str = "../Phase 2_AI testing kit/한영"
    batch_size: int = 50
    max_workers: int = 4
    memory_limit_mb: int = 1024
    validate_data: bool = True
    use_valkey_cache: bool = True
    enable_progress_tracking: bool = True
    session_ttl_hours: int = 24

@dataclass
class DataSetupResult:
    """Result of data setup process"""
    test_data: List[TestDataRow]
    glossary: List[GlossaryEntry]
    documents: Dict[str, DocumentMetadata]
    glossary_engine: GlossarySearchEngine
    session_manager: SessionManager
    context_builder: ContextBuilder
    validation_reports: Dict = field(default_factory=dict)
    setup_time: float = 0.0
    total_terms_loaded: int = 0
    total_segments_loaded: int = 0

class Phase2DataIntegrator:
    """
    Main integration class that coordinates data loading with Phase 2 components
    """
    
    def __init__(self, config: IntegrationConfig = None):
        """
        Initialize the data integrator
        
        Args:
            config: Integration configuration
        """
        self.config = config or IntegrationConfig()
        
        # Core components
        self.data_loader: Optional[EnhancedDataLoader] = None
        self.data_validator: Optional[DataValidator] = None
        self.batch_processor: Optional[BatchProcessor] = None
        self.glossary_engine: Optional[GlossarySearchEngine] = None
        self.valkey_manager: Optional[ValkeyManager] = None
        self.session_manager: Optional[SessionManager] = None
        self.context_builder: Optional[ContextBuilder] = None
        
        # Data storage
        self.test_data: List[TestDataRow] = []
        self.glossary: List[GlossaryEntry] = []
        self.documents: Dict[str, DocumentMetadata] = {}
        
        logger.info(f"Phase 2 Data Integrator initialized with config: {self.config}")

    def _convert_glossary_entry_to_term(self, entry: GlossaryEntry) -> GlossaryTerm:
        """Convert GlossaryEntry to GlossaryTerm for search engine"""
        return GlossaryTerm(
            korean=entry.korean_term,
            english=entry.english_term,
            source=entry.source_file,
            category=entry.category,
            frequency=1,  # Default frequency
            alternatives=entry.variations
        )

    def _initialize_components(self):
        """Initialize all Phase 2 components"""
        logger.info("Initializing Phase 2 components...")
        
        # Data loader
        self.data_loader = EnhancedDataLoader(
            data_dir=self.config.data_dir,
            chunk_size=self.config.batch_size,
            max_workers=self.config.max_workers,
            memory_limit_mb=self.config.memory_limit_mb
        )
        
        # Data validator
        if self.config.validate_data:
            self.data_validator = DataValidator(strict_mode=False)
        
        # Batch processor
        batch_config = BatchConfig(
            batch_size=self.config.batch_size,
            max_workers=self.config.max_workers,
            memory_limit_mb=self.config.memory_limit_mb
        )
        self.batch_processor = BatchProcessor(batch_config)
        
        # Valkey manager (if enabled)
        if self.config.use_valkey_cache:
            try:
                self.valkey_manager = ValkeyManager()
                logger.info("Valkey manager initialized successfully")
            except Exception as e:
                logger.warning(f"Could not initialize Valkey manager: {e}")
                self.valkey_manager = None
        
        logger.info("Core components initialized")

    def setup_phase2_data_pipeline(self) -> DataSetupResult:
        """
        Set up complete Phase 2 data pipeline with all components
        
        Returns:
            DataSetupResult with all initialized components and data
        """
        start_time = time.time()
        
        logger.info("Setting up Phase 2 data pipeline...")
        
        # Initialize components
        self._initialize_components()
        
        # Load data
        logger.info("Loading Phase 2 test data and glossaries...")
        self.test_data, self.glossary, self.documents = self.data_loader.load_all_data()
        
        # Validate data if enabled
        validation_reports = {}
        if self.config.validate_data and self.data_validator:
            logger.info("Validating loaded data...")
            validation_reports = self.data_validator.validate_all_data(
                self.test_data, self.glossary, self.documents
            )
            
            for data_type, report in validation_reports.items():
                logger.info(f"{data_type} validation: {report.success_rate:.1f}% success rate")
        
        # Convert glossary entries to search engine format
        logger.info("Setting up glossary search engine...")
        glossary_terms = [self._convert_glossary_entry_to_term(entry) for entry in self.glossary]
        self.glossary_engine = GlossarySearchEngine()
        self.glossary_engine.load_terms_from_list(glossary_terms)
        
        # Initialize session manager with Valkey if available
        logger.info("Setting up session management...")
        if self.valkey_manager:
            self.session_manager = SessionManager(
                valkey_manager=self.valkey_manager,
                default_ttl_hours=self.config.session_ttl_hours
            )
        else:
            # Fallback to memory-only session manager
            from memory.session_manager import InMemorySessionManager
            self.session_manager = InMemorySessionManager()
        
        # Initialize context builder
        logger.info("Setting up context builder...")
        cached_glossary = CachedGlossarySearch(
            search_engine=self.glossary_engine,
            valkey_manager=self.valkey_manager
        )
        
        self.context_builder = ContextBuilder(
            cached_glossary_search=cached_glossary,
            session_manager=self.session_manager
        )
        
        setup_time = time.time() - start_time
        
        logger.info(f"Phase 2 data pipeline setup complete in {setup_time:.2f}s")
        logger.info(f"Loaded: {len(self.test_data)} segments, {len(self.glossary)} terms")
        
        return DataSetupResult(
            test_data=self.test_data,
            glossary=self.glossary,
            documents=self.documents,
            glossary_engine=self.glossary_engine,
            session_manager=self.session_manager,
            context_builder=self.context_builder,
            validation_reports=validation_reports,
            setup_time=setup_time,
            total_terms_loaded=len(self.glossary),
            total_segments_loaded=len(self.test_data)
        )

    def initialize_document_session(self, 
                                   document_id: str, 
                                   doc_metadata: DocumentMetadata) -> bool:
        """
        Initialize a translation session for a document
        
        Args:
            document_id: Document identifier
            doc_metadata: Document metadata
        
        Returns:
            True if session was created successfully
        """
        if not self.session_manager:
            logger.error("Session manager not initialized")
            return False
        
        try:
            session_metadata = SessionMetadata(
                doc_id=document_id,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                source_language="korean",
                target_language="english",
                total_segments=doc_metadata.total_segments,
                processed_segments=0,
                term_count=0,
                status="active"
            )
            
            success = self.session_manager.create_session(document_id, session_metadata)
            
            if success:
                logger.info(f"Created session for document {document_id} with {doc_metadata.total_segments} segments")
            else:
                logger.error(f"Failed to create session for document {document_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error creating session for document {document_id}: {e}")
            return False

    def prepare_segments_for_translation(self, 
                                        segments: List[TestDataRow],
                                        document_id: str) -> List[ContextRequest]:
        """
        Prepare test data segments for translation by creating context requests
        
        Args:
            segments: List of test data segments
            document_id: Document identifier
        
        Returns:
            List of ContextRequest objects ready for translation
        """
        context_requests = []
        
        for segment in segments:
            request = ContextRequest(
                source_text=segment.korean_text,
                segment_id=segment.segment_id or str(segment.id),
                doc_id=document_id,
                source_language="korean",
                target_language="english",
                domain="clinical_trial",
                max_glossary_terms=10,
                include_previous_context=True,
                optimization_target=500
            )
            context_requests.append(request)
        
        logger.info(f"Prepared {len(context_requests)} context requests for document {document_id}")
        return context_requests

    def batch_build_contexts(self, 
                           context_requests: List[ContextRequest]) -> List[ContextBuildResult]:
        """
        Build translation contexts in batches for efficiency
        
        Args:
            context_requests: List of context requests
        
        Returns:
            List of context build results
        """
        if not self.context_builder:
            raise RuntimeError("Context builder not initialized")
        
        def build_single_context(request: ContextRequest) -> ProcessingResult:
            """Process a single context request"""
            try:
                start_time = time.time()
                result = self.context_builder.build_context(request)
                processing_time = time.time() - start_time
                
                return ProcessingResult(
                    success=True,
                    data=result,
                    processing_time=processing_time,
                    metadata={"segment_id": request.segment_id, "doc_id": request.doc_id}
                )
                
            except Exception as e:
                return ProcessingResult(
                    success=False,
                    error_message=f"Context building failed: {e}",
                    metadata={"segment_id": request.segment_id, "doc_id": request.doc_id}
                )
        
        logger.info(f"Building contexts for {len(context_requests)} segments...")
        
        # Process in batches
        processing_results, batch_stats = self.batch_processor.process_items_in_batches(
            context_requests, build_single_context
        )
        
        # Extract successful results
        context_results = []
        for result in processing_results:
            if result.success:
                context_results.append(result.data)
            else:
                logger.warning(f"Context building failed: {result.error_message}")
        
        logger.info(f"Built {len(context_results)} contexts successfully "
                   f"({batch_stats.success_rate:.1f}% success rate)")
        
        return context_results

    def load_and_prepare_document(self, 
                                 document_id: Optional[str] = None) -> Tuple[List[ContextRequest], DocumentMetadata]:
        """
        Load a document and prepare it for translation
        
        Args:
            document_id: Specific document ID to load (None for first available)
        
        Returns:
            Tuple of (context_requests, document_metadata)
        """
        if not self.test_data or not self.documents:
            raise RuntimeError("Data not loaded. Call setup_phase2_data_pipeline() first.")
        
        # Select document
        if document_id is None:
            document_id = list(self.documents.keys())[0]
        
        if document_id not in self.documents:
            raise ValueError(f"Document {document_id} not found")
        
        doc_metadata = self.documents[document_id]
        
        # Filter segments for this document
        doc_segments = [
            segment for segment in self.test_data 
            if segment.document_id == document_id
        ]
        
        if not doc_segments:
            logger.warning(f"No segments found for document {document_id}")
            return [], doc_metadata
        
        # Initialize session
        self.initialize_document_session(document_id, doc_metadata)
        
        # Prepare context requests
        context_requests = self.prepare_segments_for_translation(doc_segments, document_id)
        
        logger.info(f"Prepared document {document_id} with {len(context_requests)} segments")
        
        return context_requests, doc_metadata

    def get_integration_summary(self) -> Dict[str, Any]:
        """Get comprehensive summary of integrated data and components"""
        summary = {
            "data_summary": {
                "test_segments": len(self.test_data),
                "glossary_terms": len(self.glossary),
                "documents": len(self.documents),
                "total_korean_chars": sum(len(s.korean_text) for s in self.test_data),
                "total_english_chars": sum(len(s.english_text) for s in self.test_data),
            },
            "component_status": {
                "data_loader": self.data_loader is not None,
                "data_validator": self.data_validator is not None,
                "batch_processor": self.batch_processor is not None,
                "glossary_engine": self.glossary_engine is not None,
                "valkey_manager": self.valkey_manager is not None,
                "session_manager": self.session_manager is not None,
                "context_builder": self.context_builder is not None,
            },
            "configuration": {
                "data_dir": self.config.data_dir,
                "batch_size": self.config.batch_size,
                "max_workers": self.config.max_workers,
                "memory_limit_mb": self.config.memory_limit_mb,
                "use_valkey_cache": self.config.use_valkey_cache,
                "session_ttl_hours": self.config.session_ttl_hours,
            }
        }
        
        # Add glossary engine stats if available
        if self.glossary_engine:
            summary["glossary_engine_stats"] = {
                "total_terms": len(self.glossary_engine.terms),
                "korean_terms": len([t for t in self.glossary_engine.terms if t.korean]),
                "english_terms": len([t for t in self.glossary_engine.terms if t.english]),
                "categories": len(set(t.category for t in self.glossary_engine.terms if t.category)),
            }
        
        return summary

    def cleanup(self):
        """Cleanup resources and connections"""
        logger.info("Cleaning up data integration resources...")
        
        try:
            if self.session_manager:
                self.session_manager.cleanup()
            
            if self.valkey_manager:
                self.valkey_manager.close()
            
            logger.info("Cleanup completed successfully")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Convenience functions for easy integration
def setup_phase2_integration(data_dir: str = "../Phase 2_AI testing kit/한영",
                            batch_size: int = 50,
                            use_valkey: bool = True,
                            validate_data: bool = True) -> Phase2DataIntegrator:
    """
    Convenience function to set up Phase 2 integration
    
    Args:
        data_dir: Directory containing Phase 2 test data
        batch_size: Batch size for processing
        use_valkey: Whether to use Valkey caching
        validate_data: Whether to validate loaded data
    
    Returns:
        Configured Phase2DataIntegrator
    """
    config = IntegrationConfig(
        data_dir=data_dir,
        batch_size=batch_size,
        use_valkey_cache=use_valkey,
        validate_data=validate_data
    )
    
    integrator = Phase2DataIntegrator(config)
    setup_result = integrator.setup_phase2_data_pipeline()
    
    logger.info(f"Phase 2 integration setup complete: "
               f"{setup_result.total_segments_loaded} segments, "
               f"{setup_result.total_terms_loaded} terms loaded "
               f"in {setup_result.setup_time:.2f}s")
    
    return integrator


def quick_load_and_validate_phase2_data(data_dir: str = "../Phase 2_AI testing kit/한영") -> Dict[str, Any]:
    """
    Quick function to load and validate Phase 2 data without full integration
    
    Returns:
        Dictionary with data summary and validation results
    """
    # Load data
    test_data, glossary, documents = load_phase2_data(data_dir)
    
    # Validate data
    validation_reports = validate_phase2_data(test_data, glossary, documents)
    
    # Calculate summary
    total_items = sum(report.total_items for report in validation_reports.values())
    total_valid = sum(report.valid_items for report in validation_reports.values())
    overall_success_rate = (total_valid / max(total_items, 1)) * 100
    
    return {
        "data_counts": {
            "test_segments": len(test_data),
            "glossary_terms": len(glossary),
            "documents": len(documents)
        },
        "validation_summary": {
            "total_items": total_items,
            "valid_items": total_valid,
            "overall_success_rate": overall_success_rate,
            "reports": {k: v.__dict__ for k, v in validation_reports.items()}
        },
        "sample_data": {
            "first_test_segment": test_data[0].__dict__ if test_data else None,
            "first_glossary_term": glossary[0].__dict__ if glossary else None,
            "document_ids": list(documents.keys())
        }
    }


if __name__ == "__main__":
    # Demo usage
    print("Phase 2 Data Integration Demo")
    print("=" * 40)
    
    # Quick validation
    print("Quick data validation...")
    validation_summary = quick_load_and_validate_phase2_data()
    
    print(f"Data loaded: {validation_summary['data_counts']['test_segments']} segments, "
          f"{validation_summary['data_counts']['glossary_terms']} terms")
    print(f"Validation: {validation_summary['validation_summary']['overall_success_rate']:.1f}% success rate")
    
    # Full integration setup
    print("\nSetting up full integration...")
    
    try:
        integrator = setup_phase2_integration(
            batch_size=100,
            use_valkey=False,  # Disable for demo if Valkey not available
            validate_data=True
        )
        
        # Get integration summary
        summary = integrator.get_integration_summary()
        
        print("\nIntegration Summary:")
        print(f"  Components initialized: {sum(summary['component_status'].values())}/7")
        print(f"  Glossary engine: {summary['glossary_engine_stats']['total_terms']} terms loaded")
        print(f"  Ready for translation: {summary['data_summary']['test_segments']} segments")
        
        # Demo document preparation
        print("\nPreparing document for translation...")
        context_requests, doc_metadata = integrator.load_and_prepare_document()
        
        print(f"  Document: {doc_metadata.document_id}")
        print(f"  Total segments: {len(context_requests)}")
        print(f"  Language pair: {doc_metadata.language_pair}")
        
        # Cleanup
        integrator.cleanup()
        
    except Exception as e:
        print(f"Integration demo failed: {e}")
        logger.error(f"Demo error: {e}")