#!/usr/bin/env python3
"""
Enhanced Data Loading System for Phase 2
Handles large datasets (1,400+ segments, 2,794+ glossary terms) with efficient loading and validation
"""

import pandas as pd
import os
import time
import logging
from typing import Dict, List, Tuple, Optional, Generator, Union
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestDataRow:
    """Enhanced test data row with document metadata"""
    id: int
    korean_text: str
    english_text: str
    segment_id: Optional[str] = None
    source_file: str = ""
    document_id: str = ""
    confidence: float = 1.0
    metadata: Dict = field(default_factory=dict)

@dataclass
class GlossaryEntry:
    """Enhanced glossary entry with multiple source support"""
    korean_term: str
    english_term: str
    definition: str = ""
    category: str = ""
    source_file: str = ""
    confidence: float = 1.0
    variations: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

@dataclass
class DocumentMetadata:
    """Document-level metadata for batch processing"""
    document_id: str
    file_path: str
    total_segments: int
    language_pair: str
    domain: str
    created_at: str
    file_hash: str
    metadata: Dict = field(default_factory=dict)

@dataclass
class LoadingStats:
    """Statistics for data loading operations"""
    total_files: int = 0
    total_segments: int = 0
    total_glossary_terms: int = 0
    loading_time: float = 0.0
    validation_time: float = 0.0
    success_rate: float = 0.0
    errors: List[str] = field(default_factory=list)

class EnhancedDataLoader:
    """
    Enhanced data loader for Phase 2 supporting large datasets and concurrent processing
    """
    
    def __init__(self, 
                 data_dir: str = "../Phase 2_AI testing kit/한영",
                 chunk_size: int = 500,
                 max_workers: int = 4,
                 memory_limit_mb: int = 1024):
        """
        Initialize enhanced data loader
        
        Args:
            data_dir: Directory containing Phase 2 test data
            chunk_size: Number of rows to process in each chunk
            max_workers: Maximum number of concurrent workers
            memory_limit_mb: Memory limit for large file processing
        """
        self.data_dir = Path(data_dir)
        self.chunk_size = chunk_size
        self.max_workers = max_workers
        self.memory_limit_mb = memory_limit_mb
        
        # Data storage
        self.test_data: List[TestDataRow] = []
        self.glossary: List[GlossaryEntry] = []
        self.documents: Dict[str, DocumentMetadata] = {}
        self.loading_stats = LoadingStats()
        
        # Thread safety
        self._lock = threading.Lock()
        
        # File paths
        self.test_file = self.data_dir / "1_테스트용_Generated_Preview_KO-EN.xlsx"
        self.glossary_files = [
            self.data_dir / "2_용어집_Coding Form.xlsx",
            self.data_dir / "2_용어집_LDE KO-EN Clinical Trials TB_20250421.xlsx"
        ]
        
        logger.info(f"Enhanced data loader initialized for {self.data_dir}")
        logger.info(f"Configuration: chunk_size={chunk_size}, max_workers={max_workers}, memory_limit={memory_limit_mb}MB")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file for integrity checking"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return ""

    def _detect_columns(self, df: pd.DataFrame, column_patterns: Dict[str, List[str]]) -> Dict[str, str]:
        """
        Detect column names based on patterns
        
        Args:
            df: DataFrame to analyze
            column_patterns: Dictionary mapping target column to search patterns
        
        Returns:
            Dictionary mapping target column to actual column name
        """
        detected = {}
        df_columns_lower = [col.lower().strip() for col in df.columns]
        
        for target_col, patterns in column_patterns.items():
            for col, col_lower in zip(df.columns, df_columns_lower):
                if any(pattern.lower() in col_lower for pattern in patterns):
                    detected[target_col] = col
                    break
        
        return detected

    def load_test_data_chunked(self) -> Generator[List[TestDataRow], None, None]:
        """
        Load test data in chunks for memory efficiency
        
        Yields:
            Chunks of TestDataRow objects
        """
        start_time = time.time()
        
        if not self.test_file.exists():
            raise FileNotFoundError(f"Test data file not found: {self.test_file}")
        
        # Calculate file hash for integrity
        file_hash = self._calculate_file_hash(self.test_file)
        
        try:
            # Read Excel file in chunks if large
            file_size_mb = os.path.getsize(self.test_file) / (1024 * 1024)
            
            if file_size_mb > self.memory_limit_mb:
                logger.info(f"Large file detected ({file_size_mb:.1f}MB), using chunked reading")
                # For very large files, we'd need to implement custom chunked Excel reading
                # For now, read normally but process in chunks
            
            df = pd.read_excel(self.test_file)
            logger.info(f"Loaded Excel file with {len(df)} rows and {len(df.columns)} columns")
            
            # Clean column names
            df.columns = df.columns.str.strip()
            
            # Detect columns
            column_patterns = {
                'segment_id': ['segment', 'id', 'number'],
                'korean': ['source', 'korean', '한국어', 'kr', 'ko'],
                'english': ['target', 'english', 'en', 'translation']
            }
            
            detected_cols = self._detect_columns(df, column_patterns)
            
            # Map to actual column names
            segment_col = detected_cols.get('segment_id', df.columns[0] if len(df.columns) > 0 else None)
            korean_col = detected_cols.get('korean', df.columns[1] if len(df.columns) > 1 else None)
            english_col = detected_cols.get('english', df.columns[2] if len(df.columns) > 2 else None)
            
            if not all([segment_col, korean_col, english_col]):
                logger.warning(f"Could not detect all required columns. Using: {segment_col}, {korean_col}, {english_col}")
            
            # Create document metadata
            document_id = f"phase2_test_data_{int(time.time())}"
            doc_metadata = DocumentMetadata(
                document_id=document_id,
                file_path=str(self.test_file),
                total_segments=len(df),
                language_pair="ko-en",
                domain="clinical_trials",
                created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                file_hash=file_hash,
                metadata={"original_file": self.test_file.name}
            )
            
            with self._lock:
                self.documents[document_id] = doc_metadata
            
            # Process data in chunks
            total_chunks = (len(df) + self.chunk_size - 1) // self.chunk_size
            logger.info(f"Processing {len(df)} segments in {total_chunks} chunks of {self.chunk_size}")
            
            for chunk_idx in range(0, len(df), self.chunk_size):
                chunk_df = df.iloc[chunk_idx:chunk_idx + self.chunk_size]
                chunk_data = []
                
                for idx, row in chunk_df.iterrows():
                    try:
                        # Extract segment data
                        segment_id = str(row[segment_col]).strip() if pd.notna(row[segment_col]) else str(idx + 1)
                        korean_text = str(row[korean_col]).strip() if pd.notna(row[korean_col]) else ""
                        english_text = str(row[english_col]).strip() if pd.notna(row[english_col]) else ""
                        
                        if korean_text and english_text:  # Only include valid pairs
                            test_row = TestDataRow(
                                id=idx + 1,
                                korean_text=korean_text,
                                english_text=english_text,
                                segment_id=segment_id,
                                source_file=self.test_file.name,
                                document_id=document_id,
                                confidence=1.0,
                                metadata={"row_index": idx}
                            )
                            chunk_data.append(test_row)
                    
                    except Exception as e:
                        logger.warning(f"Error processing row {idx}: {e}")
                        with self._lock:
                            self.loading_stats.errors.append(f"Row {idx}: {e}")
                
                if chunk_data:
                    with self._lock:
                        self.test_data.extend(chunk_data)
                        self.loading_stats.total_segments += len(chunk_data)
                    
                    logger.info(f"Processed chunk {chunk_idx // self.chunk_size + 1}/{total_chunks} with {len(chunk_data)} segments")
                    yield chunk_data
                
                # Small delay to prevent overwhelming the system
                time.sleep(0.001)
            
            loading_time = time.time() - start_time
            with self._lock:
                self.loading_stats.loading_time += loading_time
                self.loading_stats.total_files += 1
            
            logger.info(f"Completed loading test data: {len(self.test_data)} segments in {loading_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Error loading test data: {e}")
            with self._lock:
                self.loading_stats.errors.append(f"Test data loading: {e}")
            raise

    def load_test_data(self) -> List[TestDataRow]:
        """
        Load all test data (convenience method)
        
        Returns:
            List of all TestDataRow objects
        """
        if self.test_data:
            return self.test_data
        
        # Load all chunks
        for chunk in self.load_test_data_chunked():
            pass  # Data is already stored in self.test_data
        
        return self.test_data

    def load_glossary_concurrent(self) -> List[GlossaryEntry]:
        """
        Load glossary data from multiple files concurrently
        
        Returns:
            List of all GlossaryEntry objects
        """
        start_time = time.time()
        
        def load_single_glossary(file_path: Path) -> List[GlossaryEntry]:
            """Load glossary from a single file"""
            if not file_path.exists():
                logger.warning(f"Glossary file not found: {file_path}")
                return []
            
            try:
                # Read all sheets if multiple exist
                xl_file = pd.ExcelFile(file_path)
                entries = []
                
                for sheet_name in xl_file.sheet_names:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                    df.columns = df.columns.str.strip()
                    
                    # Detect Korean and English columns
                    column_patterns = {
                        'korean': ['kr', 'ko', 'korean', '한국어', 'source'],
                        'english': ['en', 'english', 'target', 'translation']
                    }
                    
                    detected_cols = self._detect_columns(df, column_patterns)
                    korean_col = detected_cols.get('korean', df.columns[0] if len(df.columns) > 0 else None)
                    english_col = detected_cols.get('english', df.columns[1] if len(df.columns) > 1 else None)
                    
                    if not korean_col or not english_col:
                        logger.warning(f"Could not detect required columns in {file_path}, sheet {sheet_name}")
                        continue
                    
                    # Process entries
                    for idx, row in df.iterrows():
                        try:
                            korean_term = str(row[korean_col]).strip() if pd.notna(row[korean_col]) else ""
                            english_term = str(row[english_col]).strip() if pd.notna(row[english_col]) else ""
                            
                            if korean_term and english_term:
                                # Handle multiple English variations (separated by |)
                                english_variations = [term.strip() for term in english_term.split('|')]
                                main_english = english_variations[0]
                                other_variations = english_variations[1:] if len(english_variations) > 1 else []
                                
                                entry = GlossaryEntry(
                                    korean_term=korean_term,
                                    english_term=main_english,
                                    definition="",
                                    category=sheet_name,
                                    source_file=file_path.name,
                                    confidence=1.0,
                                    variations=other_variations,
                                    metadata={
                                        "row_index": idx,
                                        "original_english": english_term
                                    }
                                )
                                entries.append(entry)
                        
                        except Exception as e:
                            logger.warning(f"Error processing glossary row {idx} in {file_path}: {e}")
                
                logger.info(f"Loaded {len(entries)} glossary entries from {file_path}")
                return entries
                
            except Exception as e:
                logger.error(f"Error loading glossary file {file_path}: {e}")
                with self._lock:
                    self.loading_stats.errors.append(f"Glossary {file_path}: {e}")
                return []
        
        # Load glossaries concurrently
        all_entries = []
        
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(self.glossary_files))) as executor:
            # Submit all glossary loading tasks
            future_to_file = {
                executor.submit(load_single_glossary, file_path): file_path 
                for file_path in self.glossary_files if file_path.exists()
            }
            
            # Collect results
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    entries = future.result()
                    all_entries.extend(entries)
                    
                    with self._lock:
                        self.loading_stats.total_files += 1
                    
                except Exception as e:
                    logger.error(f"Error loading glossary {file_path}: {e}")
                    with self._lock:
                        self.loading_stats.errors.append(f"Glossary {file_path}: {e}")
        
        loading_time = time.time() - start_time
        
        with self._lock:
            self.glossary = all_entries
            self.loading_stats.total_glossary_terms = len(all_entries)
            self.loading_stats.loading_time += loading_time
        
        logger.info(f"Loaded total {len(all_entries)} glossary entries in {loading_time:.2f}s")
        return all_entries

    def load_all_data(self) -> Tuple[List[TestDataRow], List[GlossaryEntry], Dict[str, DocumentMetadata]]:
        """
        Load all data concurrently
        
        Returns:
            Tuple of (test_data, glossary, documents)
        """
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit concurrent loading tasks
            test_future = executor.submit(self.load_test_data)
            glossary_future = executor.submit(self.load_glossary_concurrent)
            
            # Wait for completion
            test_data = test_future.result()
            glossary = glossary_future.result()
        
        total_time = time.time() - start_time
        
        # Calculate success rate
        total_expected = len(test_data) + len(glossary)
        total_errors = len(self.loading_stats.errors)
        success_rate = ((total_expected - total_errors) / max(total_expected, 1)) * 100
        
        with self._lock:
            self.loading_stats.loading_time = total_time
            self.loading_stats.success_rate = success_rate
        
        logger.info(f"Data loading complete: {len(test_data)} segments, {len(glossary)} terms")
        logger.info(f"Total time: {total_time:.2f}s, Success rate: {success_rate:.1f}%")
        
        return test_data, glossary, self.documents

    def get_loading_stats(self) -> LoadingStats:
        """Get detailed loading statistics"""
        return self.loading_stats

    def get_data_summary(self) -> Dict[str, Union[int, float, str]]:
        """Get comprehensive data summary"""
        return {
            "test_segments": len(self.test_data),
            "glossary_terms": len(self.glossary),
            "documents": len(self.documents),
            "loading_time_seconds": self.loading_stats.loading_time,
            "validation_time_seconds": self.loading_stats.validation_time,
            "success_rate_percent": self.loading_stats.success_rate,
            "total_errors": len(self.loading_stats.errors),
            "memory_usage_mb": self._estimate_memory_usage()
        }

    def _estimate_memory_usage(self) -> float:
        """Estimate current memory usage in MB"""
        import sys
        
        total_size = 0
        total_size += sys.getsizeof(self.test_data)
        total_size += sum(sys.getsizeof(item) for item in self.test_data)
        total_size += sys.getsizeof(self.glossary)
        total_size += sum(sys.getsizeof(item) for item in self.glossary)
        total_size += sys.getsizeof(self.documents)
        
        return total_size / (1024 * 1024)

    def export_to_format(self, 
                        format_type: str = "pandas",
                        include_metadata: bool = True) -> Union[Dict, pd.DataFrame]:
        """
        Export data in various formats for integration
        
        Args:
            format_type: Export format ("pandas", "dict", "json")
            include_metadata: Whether to include metadata
        
        Returns:
            Data in requested format
        """
        if format_type == "pandas":
            # Convert to pandas DataFrames
            test_df = pd.DataFrame([
                {
                    "id": item.id,
                    "korean_text": item.korean_text,
                    "english_text": item.english_text,
                    "segment_id": item.segment_id,
                    "document_id": item.document_id,
                    "confidence": item.confidence,
                    **(item.metadata if include_metadata else {})
                }
                for item in self.test_data
            ])
            
            glossary_df = pd.DataFrame([
                {
                    "korean_term": item.korean_term,
                    "english_term": item.english_term,
                    "definition": item.definition,
                    "category": item.category,
                    "source_file": item.source_file,
                    "variations": "|".join(item.variations),
                    **(item.metadata if include_metadata else {})
                }
                for item in self.glossary
            ])
            
            return {"test_data": test_df, "glossary": glossary_df}
        
        elif format_type == "dict":
            return {
                "test_data": [item.__dict__ for item in self.test_data],
                "glossary": [item.__dict__ for item in self.glossary],
                "documents": {k: v.__dict__ for k, v in self.documents.items()},
                "stats": self.loading_stats.__dict__
            }
        
        else:
            raise ValueError(f"Unsupported format type: {format_type}")


# Convenience functions for backward compatibility and easy integration
def load_phase2_data(data_dir: str = "../Phase 2_AI testing kit/한영",
                     chunk_size: int = 500) -> Tuple[List[TestDataRow], List[GlossaryEntry], Dict[str, DocumentMetadata]]:
    """
    Convenience function to load Phase 2 data
    
    Returns:
        Tuple of (test_data, glossary, documents)
    """
    loader = EnhancedDataLoader(data_dir=data_dir, chunk_size=chunk_size)
    return loader.load_all_data()


def get_phase2_data_summary(data_dir: str = "../Phase 2_AI testing kit/한영") -> Dict:
    """
    Get quick summary of Phase 2 data without loading everything
    
    Returns:
        Dictionary with data summary
    """
    loader = EnhancedDataLoader(data_dir=data_dir)
    
    # Quick file analysis
    summary = {"files": {}}
    
    if loader.test_file.exists():
        df = pd.read_excel(loader.test_file)
        summary["files"]["test_data"] = {
            "file": str(loader.test_file),
            "rows": len(df),
            "columns": list(df.columns),
            "size_mb": os.path.getsize(loader.test_file) / (1024 * 1024)
        }
    
    for i, glossary_file in enumerate(loader.glossary_files):
        if glossary_file.exists():
            xl_file = pd.ExcelFile(glossary_file)
            total_rows = 0
            for sheet in xl_file.sheet_names:
                df = pd.read_excel(glossary_file, sheet_name=sheet)
                total_rows += len(df)
            
            summary["files"][f"glossary_{i+1}"] = {
                "file": str(glossary_file),
                "sheets": xl_file.sheet_names,
                "total_rows": total_rows,
                "size_mb": os.path.getsize(glossary_file) / (1024 * 1024)
            }
    
    return summary


if __name__ == "__main__":
    # Demo usage
    print("Phase 2 Enhanced Data Loader Demo")
    print("=" * 50)
    
    # Quick summary
    summary = get_phase2_data_summary()
    print("Data Summary:")
    for file_type, info in summary["files"].items():
        print(f"  {file_type}: {info['rows'] if 'rows' in info else info['total_rows']} rows, {info['size_mb']:.1f}MB")
    
    print("\nLoading data...")
    
    # Load data
    loader = EnhancedDataLoader(chunk_size=100, max_workers=2)
    test_data, glossary, documents = loader.load_all_data()
    
    # Print statistics
    stats = loader.get_loading_stats()
    print(f"\nLoading Results:")
    print(f"  Test segments: {len(test_data)}")
    print(f"  Glossary terms: {len(glossary)}")
    print(f"  Documents: {len(documents)}")
    print(f"  Loading time: {stats.loading_time:.2f}s")
    print(f"  Success rate: {stats.success_rate:.1f}%")
    print(f"  Errors: {len(stats.errors)}")
    
    if stats.errors:
        print("\nErrors encountered:")
        for error in stats.errors[:5]:  # Show first 5 errors
            print(f"  - {error}")