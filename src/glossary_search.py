"""
Glossary Search Engine for Phase 2 MVP - Smart Glossary Term Retrieval

This module provides intelligent glossary term search capabilities with fuzzy matching,
relevance scoring, and clinical trial domain optimization. It serves as the foundation
for the cached glossary search system.

Key Features:
- Fuzzy string matching for Korean/English term pairs
- Relevance scoring based on term frequency and context
- Clinical trial domain specialization
- Support for multiple glossary sources
- Efficient search algorithms for real-time performance
"""

import re
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd


@dataclass
class GlossaryTerm:
    """Individual glossary term with metadata"""
    korean: str
    english: str
    source: Optional[str] = None
    category: Optional[str] = None
    frequency: int = 0
    alternatives: List[str] = None
    
    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []


@dataclass
class SearchResult:
    """Search result with relevance scoring"""
    term: GlossaryTerm
    relevance_score: float
    match_type: str  # 'exact', 'partial', 'fuzzy'
    matched_segment: str
    confidence: float


class GlossarySearchEngine:
    """Intelligent glossary term search engine"""
    
    def __init__(self, 
                 glossary_files: Optional[List[str]] = None,
                 min_term_length: int = 2,
                 fuzzy_threshold: float = 0.6,
                 enable_preprocessing: bool = True):
        """
        Initialize glossary search engine
        
        Args:
            glossary_files: List of glossary file paths
            min_term_length: Minimum term length for indexing
            fuzzy_threshold: Minimum similarity for fuzzy matching
            enable_preprocessing: Enable text preprocessing
        """
        self.logger = logging.getLogger(__name__)
        self.min_term_length = min_term_length
        self.fuzzy_threshold = fuzzy_threshold
        self.enable_preprocessing = enable_preprocessing
        
        # Storage for glossary terms
        self.terms: List[GlossaryTerm] = []
        self.korean_index: Dict[str, List[GlossaryTerm]] = {}
        self.english_index: Dict[str, List[GlossaryTerm]] = {}
        
        # Search performance tracking
        self.search_count = 0
        self.total_search_time = 0.0
        
        # Clinical trial specific patterns
        self.clinical_patterns = {
            '임상시험': ['clinical trial', 'clinical study'],
            '피험자': ['subject', 'participant'],
            '시험대상자': ['study subject', 'test subject'],
            '이상반응': ['adverse event', 'adverse reaction'],
            '치료': ['treatment', 'therapy'],
            '투여': ['administration', 'dosing'],
            '무작위배정': ['randomization', 'random assignment'],
            '이중눈가림': ['double blind', 'double blinding'],
            '위약': ['placebo'],
            '대조군': ['control group'],
            '안전성': ['safety'],
            '유효성': ['efficacy', 'effectiveness']
        }
        
        self.logger.info("GlossarySearchEngine initialized")
        
        # Load glossary files if provided
        if glossary_files:
            self.load_glossaries(glossary_files)
    
    def load_glossaries(self, file_paths: List[str]) -> int:
        """
        Load glossary terms from files
        
        Args:
            file_paths: List of file paths to load
            
        Returns:
            Number of terms loaded
        """
        total_loaded = 0
        
        for file_path in file_paths:
            try:
                loaded_count = self._load_single_glossary(file_path)
                total_loaded += loaded_count
                self.logger.info(f"Loaded {loaded_count} terms from {file_path}")
            except Exception as e:
                self.logger.error(f"Failed to load glossary {file_path}: {e}")
        
        # Build search indices
        self._build_indices()
        
        self.logger.info(f"Total glossary terms loaded: {total_loaded}")
        return total_loaded
    
    def _load_single_glossary(self, file_path: str) -> int:
        """Load terms from a single glossary file"""
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {file_path}")
        
        if file_path.suffix.lower() == '.xlsx':
            return self._load_from_excel(file_path)
        elif file_path.suffix.lower() == '.csv':
            return self._load_from_csv(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
    
    def _load_from_excel(self, file_path: Path) -> int:
        """Load terms from Excel file"""
        df = pd.read_excel(file_path)
        return self._process_dataframe(df, str(file_path.name))
    
    def _load_from_csv(self, file_path: Path) -> int:
        """Load terms from CSV file"""
        df = pd.read_csv(file_path)
        return self._process_dataframe(df, str(file_path.name))
    
    def _process_dataframe(self, df: pd.DataFrame, source_name: str) -> int:
        """Process DataFrame to extract glossary terms"""
        loaded_count = 0
        
        # Try to detect Korean and English columns
        korean_col = self._detect_korean_column(df)
        english_col = self._detect_english_column(df)
        
        if not korean_col or not english_col:
            self.logger.warning(f"Could not detect Korean/English columns in {source_name}")
            return 0
        
        # Extract terms
        for idx, row in df.iterrows():
            try:
                korean_term = str(row[korean_col]).strip()
                english_term = str(row[english_col]).strip()
                
                # Skip invalid entries
                if (not korean_term or not english_term or 
                    korean_term == 'nan' or english_term == 'nan' or
                    len(korean_term) < self.min_term_length):
                    continue
                
                # Create glossary term
                term = GlossaryTerm(
                    korean=korean_term,
                    english=english_term,
                    source=source_name,
                    category=self._detect_category(korean_term, english_term)
                )
                
                self.terms.append(term)
                loaded_count += 1
                
            except Exception as e:
                self.logger.warning(f"Failed to process row {idx} in {source_name}: {e}")
        
        return loaded_count
    
    def _detect_korean_column(self, df: pd.DataFrame) -> Optional[str]:
        """Detect column containing Korean text"""
        korean_patterns = [
            'korean', '한국어', '한글', 'ko', 'kr', '원문', '출발어'
        ]
        
        # Check column names first
        for col in df.columns:
            col_lower = str(col).lower()
            if any(pattern in col_lower for pattern in korean_patterns):
                return col
        
        # Check content for Korean characters
        for col in df.columns:
            if df[col].dtype == 'object':
                sample_text = ' '.join(df[col].astype(str).head(10))
                korean_chars = len(re.findall(r'[가-힣]', sample_text))
                if korean_chars > 10:  # Threshold for Korean content
                    return col
        
        return None
    
    def _detect_english_column(self, df: pd.DataFrame) -> Optional[str]:
        """Detect column containing English text"""
        english_patterns = [
            'english', 'eng', 'en', 'target', '영어', '목표어', 'translation'
        ]
        
        # Check column names first
        for col in df.columns:
            col_lower = str(col).lower()
            if any(pattern in col_lower for pattern in english_patterns):
                return col
        
        # Check content for English characters
        for col in df.columns:
            if df[col].dtype == 'object':
                sample_text = ' '.join(df[col].astype(str).head(10))
                english_chars = len(re.findall(r'[a-zA-Z]', sample_text))
                korean_chars = len(re.findall(r'[가-힣]', sample_text))
                if english_chars > korean_chars and english_chars > 20:
                    return col
        
        return None
    
    def _detect_category(self, korean_term: str, english_term: str) -> str:
        """Detect term category based on content"""
        clinical_keywords = [
            '임상', '시험', '치료', '투여', '환자', '피험자', '이상', '반응',
            'clinical', 'trial', 'treatment', 'patient', 'subject', 'adverse'
        ]
        
        combined_text = f"{korean_term} {english_term}".lower()
        
        if any(keyword in combined_text for keyword in clinical_keywords):
            return 'clinical_trial'
        
        return 'general'
    
    def _build_indices(self) -> None:
        """Build search indices for fast lookup"""
        self.korean_index.clear()
        self.english_index.clear()
        
        for term in self.terms:
            # Index Korean terms
            korean_words = self._tokenize_korean(term.korean)
            for word in korean_words:
                if word not in self.korean_index:
                    self.korean_index[word] = []
                self.korean_index[word].append(term)
            
            # Index English terms
            english_words = self._tokenize_english(term.english)
            for word in english_words:
                word_lower = word.lower()
                if word_lower not in self.english_index:
                    self.english_index[word_lower] = []
                self.english_index[word_lower].append(term)
        
        self.logger.info(f"Built indices: {len(self.korean_index)} Korean, {len(self.english_index)} English")
    
    def _tokenize_korean(self, text: str) -> List[str]:
        """Tokenize Korean text into searchable components"""
        if not self.enable_preprocessing:
            return [text]
        
        # Clean text
        cleaned = re.sub(r'[^\w\s가-힣]', ' ', text)
        
        # Split by whitespace and extract meaningful segments
        words = []
        for word in cleaned.split():
            if len(word) >= self.min_term_length:
                words.append(word)
                
                # Add substrings for compound terms
                if len(word) > 4:
                    for i in range(len(word) - 1):
                        for j in range(i + 2, len(word) + 1):
                            substring = word[i:j]
                            if len(substring) >= self.min_term_length:
                                words.append(substring)
        
        return list(set(words))  # Remove duplicates
    
    def _tokenize_english(self, text: str) -> List[str]:
        """Tokenize English text into searchable components"""
        if not self.enable_preprocessing:
            return [text]
        
        # Clean and split text
        cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
        words = [word for word in cleaned.split() if len(word) >= self.min_term_length]
        
        return words
    
    def search(self, korean_text: str, max_results: int = 10) -> List[SearchResult]:
        """
        Search for relevant glossary terms
        
        Args:
            korean_text: Korean text to search for
            max_results: Maximum number of results to return
            
        Returns:
            List of SearchResult objects sorted by relevance
        """
        import time
        start_time = time.time()
        
        try:
            results = self._perform_search(korean_text, max_results)
            
            # Update performance tracking
            search_time = time.time() - start_time
            self.search_count += 1
            self.total_search_time += search_time
            
            self.logger.debug(f"Search completed: '{korean_text[:30]}...' -> {len(results)} results in {search_time:.3f}s")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Search failed for '{korean_text}': {e}")
            return []
    
    def _perform_search(self, korean_text: str, max_results: int) -> List[SearchResult]:
        """Perform the actual search operation"""
        all_results = []
        
        # 1. Exact matches
        exact_results = self._find_exact_matches(korean_text)
        all_results.extend(exact_results)
        
        # 2. Partial matches
        if len(all_results) < max_results:
            partial_results = self._find_partial_matches(korean_text)
            all_results.extend(partial_results)
        
        # 3. Fuzzy matches
        if len(all_results) < max_results:
            fuzzy_results = self._find_fuzzy_matches(korean_text, max_results - len(all_results))
            all_results.extend(fuzzy_results)
        
        # 4. Clinical pattern matches
        clinical_results = self._find_clinical_pattern_matches(korean_text)
        all_results.extend(clinical_results)
        
        # Remove duplicates and sort by relevance
        unique_results = self._deduplicate_results(all_results)
        sorted_results = sorted(unique_results, key=lambda x: x.relevance_score, reverse=True)
        
        return sorted_results[:max_results]
    
    def _find_exact_matches(self, korean_text: str) -> List[SearchResult]:
        """Find exact term matches"""
        results = []
        
        for term in self.terms:
            if term.korean == korean_text:
                result = SearchResult(
                    term=term,
                    relevance_score=1.0,
                    match_type='exact',
                    matched_segment=korean_text,
                    confidence=1.0
                )
                results.append(result)
        
        return results
    
    def _find_partial_matches(self, korean_text: str) -> List[SearchResult]:
        """Find partial matches using index"""
        results = []
        tokens = self._tokenize_korean(korean_text)
        
        candidate_terms = set()
        for token in tokens:
            if token in self.korean_index:
                candidate_terms.update(self.korean_index[token])
        
        for term in candidate_terms:
            # Calculate partial match score
            score = self._calculate_partial_score(korean_text, term.korean)
            if score > 0.3:  # Minimum threshold
                result = SearchResult(
                    term=term,
                    relevance_score=score,
                    match_type='partial',
                    matched_segment=self._find_matching_segment(korean_text, term.korean),
                    confidence=score
                )
                results.append(result)
        
        return results
    
    def _find_fuzzy_matches(self, korean_text: str, max_results: int) -> List[SearchResult]:
        """Find fuzzy matches using similarity scoring"""
        results = []
        
        for term in self.terms:
            similarity = SequenceMatcher(None, korean_text, term.korean).ratio()
            
            if similarity >= self.fuzzy_threshold:
                result = SearchResult(
                    term=term,
                    relevance_score=similarity * 0.8,  # Slight penalty for fuzzy matches
                    match_type='fuzzy',
                    matched_segment=term.korean,
                    confidence=similarity
                )
                results.append(result)
        
        # Sort by similarity and return top results
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results[:max_results]
    
    def _find_clinical_pattern_matches(self, korean_text: str) -> List[SearchResult]:
        """Find matches using clinical trial patterns"""
        results = []
        
        for korean_pattern, english_translations in self.clinical_patterns.items():
            if korean_pattern in korean_text:
                # Create synthetic term for pattern match
                for english_term in english_translations:
                    synthetic_term = GlossaryTerm(
                        korean=korean_pattern,
                        english=english_term,
                        source='clinical_patterns',
                        category='clinical_trial'
                    )
                    
                    result = SearchResult(
                        term=synthetic_term,
                        relevance_score=0.9,  # High relevance for clinical patterns
                        match_type='pattern',
                        matched_segment=korean_pattern,
                        confidence=0.9
                    )
                    results.append(result)
        
        return results
    
    def _calculate_partial_score(self, query: str, term: str) -> float:
        """Calculate partial match score"""
        # Check for substring matches
        if query in term or term in query:
            overlap = min(len(query), len(term))
            max_length = max(len(query), len(term))
            return overlap / max_length
        
        # Token overlap score
        query_tokens = set(self._tokenize_korean(query))
        term_tokens = set(self._tokenize_korean(term))
        
        if not query_tokens or not term_tokens:
            return 0.0
        
        overlap = len(query_tokens.intersection(term_tokens))
        union = len(query_tokens.union(term_tokens))
        
        return overlap / union if union > 0 else 0.0
    
    def _find_matching_segment(self, query: str, term: str) -> str:
        """Find the specific segment that matched"""
        # Simple implementation - return the overlapping part
        if query in term:
            return query
        elif term in query:
            return term
        else:
            # Find longest common substring
            matcher = SequenceMatcher(None, query, term)
            match = matcher.find_longest_match(0, len(query), 0, len(term))
            if match.size > 0:
                return query[match.a:match.a + match.size]
        
        return query[:10] + "..." if len(query) > 10 else query
    
    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove duplicate results"""
        seen_terms = set()
        unique_results = []
        
        for result in results:
            term_key = (result.term.korean, result.term.english)
            if term_key not in seen_terms:
                seen_terms.add(term_key)
                unique_results.append(result)
            else:
                # Keep result with higher score
                for i, existing in enumerate(unique_results):
                    existing_key = (existing.term.korean, existing.term.english)
                    if existing_key == term_key and result.relevance_score > existing.relevance_score:
                        unique_results[i] = result
                        break
        
        return unique_results
    
    def add_terms(self, terms: List[GlossaryTerm]) -> int:
        """Add new terms to the glossary"""
        added_count = 0
        
        for term in terms:
            # Check for duplicates
            existing = any(
                t.korean == term.korean and t.english == term.english 
                for t in self.terms
            )
            
            if not existing:
                self.terms.append(term)
                added_count += 1
        
        if added_count > 0:
            self._build_indices()
            self.logger.info(f"Added {added_count} new terms")
        
        return added_count
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get search engine statistics"""
        categories = {}
        sources = {}
        
        for term in self.terms:
            # Count categories
            category = term.category or 'unknown'
            categories[category] = categories.get(category, 0) + 1
            
            # Count sources
            source = term.source or 'unknown'
            sources[source] = sources.get(source, 0) + 1
        
        avg_search_time = (self.total_search_time / self.search_count 
                          if self.search_count > 0 else 0)
        
        return {
            'total_terms': len(self.terms),
            'categories': categories,
            'sources': sources,
            'search_performance': {
                'total_searches': self.search_count,
                'average_search_time_ms': avg_search_time * 1000,
                'korean_index_size': len(self.korean_index),
                'english_index_size': len(self.english_index)
            }
        }
    
    def clear_cache(self) -> None:
        """Clear all cached data"""
        self.korean_index.clear()
        self.english_index.clear()
        self.search_count = 0
        self.total_search_time = 0.0
        self.logger.info("Glossary search cache cleared")


# Utility functions for creating test data

def create_sample_glossary() -> List[GlossaryTerm]:
    """Create sample glossary terms for testing"""
    sample_terms = [
        GlossaryTerm("임상시험", "clinical trial", "sample", "clinical_trial"),
        GlossaryTerm("피험자", "subject", "sample", "clinical_trial"),
        GlossaryTerm("이상반응", "adverse event", "sample", "clinical_trial"),
        GlossaryTerm("무작위배정", "randomization", "sample", "clinical_trial"),
        GlossaryTerm("이중눈가림", "double blind", "sample", "clinical_trial"),
        GlossaryTerm("위약", "placebo", "sample", "clinical_trial"),
        GlossaryTerm("치료", "treatment", "sample", "clinical_trial"),
        GlossaryTerm("투여", "administration", "sample", "clinical_trial"),
        GlossaryTerm("안전성", "safety", "sample", "clinical_trial"),
        GlossaryTerm("유효성", "efficacy", "sample", "clinical_trial")
    ]
    return sample_terms


def create_glossary_from_dict(term_dict: Dict[str, str], 
                             source: str = "manual") -> List[GlossaryTerm]:
    """Create glossary terms from dictionary"""
    terms = []
    for korean, english in term_dict.items():
        term = GlossaryTerm(
            korean=korean,
            english=english,
            source=source,
            category="general"
        )
        terms.append(term)
    
    return terms