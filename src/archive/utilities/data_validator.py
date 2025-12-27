#!/usr/bin/env python3
"""
Data Validation System for Phase 2
Ensures data integrity and quality with 99%+ success rate validation
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Set, Union
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
from collections import Counter
import time

from data_loader_enhanced import TestDataRow, GlossaryEntry, DocumentMetadata

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of a validation check"""
    is_valid: bool
    error_message: str = ""
    warning_message: str = ""
    metadata: Dict = field(default_factory=dict)

@dataclass
class ValidationReport:
    """Comprehensive validation report"""
    total_items: int
    valid_items: int
    invalid_items: int
    warnings: int
    success_rate: float
    validation_time: float
    detailed_results: Dict[str, List[ValidationResult]] = field(default_factory=dict)
    summary: Dict[str, Union[int, float, str]] = field(default_factory=dict)

class DataValidator:
    """
    Comprehensive data validation system for Phase 2 translation data
    """
    
    def __init__(self, 
                 strict_mode: bool = False,
                 language_detection: bool = True,
                 min_text_length: int = 1,
                 max_text_length: int = 10000):
        """
        Initialize data validator
        
        Args:
            strict_mode: Enable strict validation rules
            language_detection: Enable basic language detection
            min_text_length: Minimum acceptable text length
            max_text_length: Maximum acceptable text length
        """
        self.strict_mode = strict_mode
        self.language_detection = language_detection
        self.min_text_length = min_text_length
        self.max_text_length = max_text_length
        
        # Korean character patterns
        self.korean_pattern = re.compile(r'[가-힣ㄱ-ㅎㅏ-ㅣ]')
        self.english_pattern = re.compile(r'[a-zA-Z]')
        self.special_chars_pattern = re.compile(r'[<>{}[\]\\|`~!@#$%^&*()]')
        
        # Common validation patterns
        self.html_pattern = re.compile(r'<[^>]+>')
        self.control_chars_pattern = re.compile(r'[\x00-\x1f\x7f-\x9f]')
        self.excessive_whitespace_pattern = re.compile(r'\s{3,}')
        
        logger.info(f"Data validator initialized (strict_mode={strict_mode})")

    def validate_text_content(self, text: str, expected_language: str = "auto") -> ValidationResult:
        """
        Validate text content for basic requirements
        
        Args:
            text: Text to validate
            expected_language: Expected language ("korean", "english", "auto")
        
        Returns:
            ValidationResult object
        """
        if not isinstance(text, str):
            return ValidationResult(False, f"Text must be string, got {type(text)}")
        
        text = text.strip()
        
        # Check length requirements
        if len(text) < self.min_text_length:
            return ValidationResult(False, f"Text too short: {len(text)} < {self.min_text_length}")
        
        if len(text) > self.max_text_length:
            return ValidationResult(False, f"Text too long: {len(text)} > {self.max_text_length}")
        
        # Check for empty or whitespace-only content
        if not text or text.isspace():
            return ValidationResult(False, "Text is empty or whitespace-only")
        
        # Check for control characters
        if self.control_chars_pattern.search(text):
            return ValidationResult(False, "Text contains control characters")
        
        # Check for HTML tags (usually not wanted in translation data)
        if self.html_pattern.search(text):
            if self.strict_mode:
                return ValidationResult(False, "Text contains HTML tags")
            else:
                return ValidationResult(True, "", "Text contains HTML tags")
        
        # Language detection
        warnings = []
        if self.language_detection and expected_language != "auto":
            korean_chars = len(self.korean_pattern.findall(text))
            english_chars = len(self.english_pattern.findall(text))
            total_chars = len(text)
            
            korean_ratio = korean_chars / max(total_chars, 1)
            english_ratio = english_chars / max(total_chars, 1)
            
            if expected_language == "korean" and korean_ratio < 0.1:
                if korean_chars == 0:
                    if self.strict_mode:
                        return ValidationResult(False, "No Korean characters found in Korean text")
                    else:
                        warnings.append("No Korean characters found in Korean text")
                else:
                    warnings.append(f"Low Korean character ratio: {korean_ratio:.1%}")
            
            elif expected_language == "english" and english_ratio < 0.1:
                if english_chars == 0:
                    if self.strict_mode:
                        return ValidationResult(False, "No English characters found in English text")
                    else:
                        warnings.append("No English characters found in English text")
                else:
                    warnings.append(f"Low English character ratio: {english_ratio:.1%}")
        
        # Check for excessive whitespace
        if self.excessive_whitespace_pattern.search(text):
            warnings.append("Text contains excessive whitespace")
        
        # Check for suspicious patterns
        if text.count('\n') > 10:
            warnings.append("Text contains many line breaks")
        
        if len(set(text)) < 3:  # Very low character diversity
            warnings.append("Text has very low character diversity")
        
        warning_message = "; ".join(warnings) if warnings else ""
        
        return ValidationResult(
            True, 
            "", 
            warning_message,
            {
                "length": len(text),
                "korean_chars": korean_chars if self.language_detection else None,
                "english_chars": english_chars if self.language_detection else None
            }
        )

    def validate_test_data_row(self, row: TestDataRow) -> ValidationResult:
        """
        Validate a single test data row
        
        Args:
            row: TestDataRow to validate
        
        Returns:
            ValidationResult object
        """
        errors = []
        warnings = []
        metadata = {}
        
        # Basic structure validation
        if not isinstance(row.id, int) or row.id <= 0:
            errors.append(f"Invalid ID: {row.id}")
        
        if not isinstance(row.korean_text, str):
            errors.append(f"Korean text must be string, got {type(row.korean_text)}")
        
        if not isinstance(row.english_text, str):
            errors.append(f"English text must be string, got {type(row.english_text)}")
        
        if errors:
            return ValidationResult(False, "; ".join(errors))
        
        # Content validation
        korean_result = self.validate_text_content(row.korean_text, "korean")
        if not korean_result.is_valid:
            errors.append(f"Korean text invalid: {korean_result.error_message}")
        elif korean_result.warning_message:
            warnings.append(f"Korean text warning: {korean_result.warning_message}")
        
        english_result = self.validate_text_content(row.english_text, "english")
        if not english_result.is_valid:
            errors.append(f"English text invalid: {english_result.error_message}")
        elif english_result.warning_message:
            warnings.append(f"English text warning: {english_result.warning_message}")
        
        # Cross-language validation
        korean_len = len(row.korean_text.strip())
        english_len = len(row.english_text.strip())
        
        # Check for extreme length differences (might indicate issues)
        if korean_len > 0 and english_len > 0:
            length_ratio = max(korean_len, english_len) / min(korean_len, english_len)
            if length_ratio > 10:  # More than 10x difference
                warnings.append(f"Extreme length difference: KO({korean_len}) vs EN({english_len})")
        
        # Check for identical content (shouldn't happen in translation)
        if row.korean_text.strip() == row.english_text.strip():
            if len(row.korean_text.strip()) > 5:  # Allow short identical strings
                warnings.append("Korean and English text are identical")
        
        # Check confidence score
        if not (0.0 <= row.confidence <= 1.0):
            warnings.append(f"Invalid confidence score: {row.confidence}")
        
        # Metadata validation
        metadata.update({
            "korean_length": korean_len,
            "english_length": english_len,
            "length_ratio": length_ratio if korean_len > 0 and english_len > 0 else None,
            "confidence": row.confidence
        })
        
        if korean_result.metadata:
            metadata["korean_analysis"] = korean_result.metadata
        if english_result.metadata:
            metadata["english_analysis"] = english_result.metadata
        
        if errors:
            return ValidationResult(False, "; ".join(errors), "; ".join(warnings), metadata)
        
        return ValidationResult(True, "", "; ".join(warnings), metadata)

    def validate_glossary_entry(self, entry: GlossaryEntry) -> ValidationResult:
        """
        Validate a single glossary entry
        
        Args:
            entry: GlossaryEntry to validate
        
        Returns:
            ValidationResult object
        """
        errors = []
        warnings = []
        metadata = {}
        
        # Basic structure validation
        if not isinstance(entry.korean_term, str):
            errors.append(f"Korean term must be string, got {type(entry.korean_term)}")
        
        if not isinstance(entry.english_term, str):
            errors.append(f"English term must be string, got {type(entry.english_term)}")
        
        if errors:
            return ValidationResult(False, "; ".join(errors))
        
        # Content validation
        korean_term = entry.korean_term.strip()
        english_term = entry.english_term.strip()
        
        if not korean_term and not english_term:
            return ValidationResult(False, "Both Korean and English terms are empty")
        
        # Validate Korean term if present
        if korean_term:
            korean_result = self.validate_text_content(korean_term, "korean")
            if not korean_result.is_valid:
                errors.append(f"Korean term invalid: {korean_result.error_message}")
            elif korean_result.warning_message:
                warnings.append(f"Korean term warning: {korean_result.warning_message}")
        
        # Validate English term if present
        if english_term:
            english_result = self.validate_text_content(english_term, "english")
            if not english_result.is_valid:
                errors.append(f"English term invalid: {english_result.error_message}")
            elif english_result.warning_message:
                warnings.append(f"English term warning: {english_result.warning_message}")
        
        # Term-specific validation
        if korean_term and len(korean_term.split()) > 10:
            warnings.append("Korean term is very long (>10 words)")
        
        if english_term and len(english_term.split()) > 15:
            warnings.append("English term is very long (>15 words)")
        
        # Check for suspicious patterns in terms
        if korean_term and any(char in korean_term for char in '[](){}'):
            warnings.append("Korean term contains brackets")
        
        if english_term and any(char in english_term for char in '[](){}'):
            warnings.append("English term contains brackets")
        
        # Validate variations
        if entry.variations:
            for i, variation in enumerate(entry.variations):
                if not isinstance(variation, str) or not variation.strip():
                    warnings.append(f"Invalid variation {i+1}")
        
        # Check confidence score
        if not (0.0 <= entry.confidence <= 1.0):
            warnings.append(f"Invalid confidence score: {entry.confidence}")
        
        metadata.update({
            "korean_length": len(korean_term),
            "english_length": len(english_term),
            "has_variations": len(entry.variations) > 0,
            "variation_count": len(entry.variations),
            "confidence": entry.confidence
        })
        
        if errors:
            return ValidationResult(False, "; ".join(errors), "; ".join(warnings), metadata)
        
        return ValidationResult(True, "", "; ".join(warnings), metadata)

    def validate_test_data_collection(self, test_data: List[TestDataRow]) -> ValidationReport:
        """
        Validate a collection of test data rows
        
        Args:
            test_data: List of TestDataRow objects
        
        Returns:
            ValidationReport object
        """
        start_time = time.time()
        
        results = []
        valid_count = 0
        warning_count = 0
        
        # Track duplicates and IDs
        seen_ids = set()
        korean_texts = []
        english_texts = []
        
        for i, row in enumerate(test_data):
            result = self.validate_test_data_row(row)
            results.append(result)
            
            if result.is_valid:
                valid_count += 1
                if result.warning_message:
                    warning_count += 1
            
            # Check for duplicate IDs
            if row.id in seen_ids:
                result.warning_message += f"; Duplicate ID: {row.id}"
                warning_count += 1
            seen_ids.add(row.id)
            
            # Collect texts for duplicate analysis
            if result.is_valid:
                korean_texts.append(row.korean_text.strip())
                english_texts.append(row.english_text.strip())
        
        # Analyze duplicates
        korean_duplicates = [text for text, count in Counter(korean_texts).items() if count > 1]
        english_duplicates = [text for text, count in Counter(english_texts).items() if count > 1]
        
        validation_time = time.time() - start_time
        success_rate = (valid_count / max(len(test_data), 1)) * 100
        
        summary = {
            "duplicate_korean_texts": len(korean_duplicates),
            "duplicate_english_texts": len(english_duplicates),
            "id_range": f"{min(row.id for row in test_data)}-{max(row.id for row in test_data)}" if test_data else "N/A",
            "avg_korean_length": sum(len(row.korean_text) for row in test_data) / max(len(test_data), 1),
            "avg_english_length": sum(len(row.english_text) for row in test_data) / max(len(test_data), 1),
        }
        
        return ValidationReport(
            total_items=len(test_data),
            valid_items=valid_count,
            invalid_items=len(test_data) - valid_count,
            warnings=warning_count,
            success_rate=success_rate,
            validation_time=validation_time,
            detailed_results={"test_data": results},
            summary=summary
        )

    def validate_glossary_collection(self, glossary: List[GlossaryEntry]) -> ValidationReport:
        """
        Validate a collection of glossary entries
        
        Args:
            glossary: List of GlossaryEntry objects
        
        Returns:
            ValidationReport object
        """
        start_time = time.time()
        
        results = []
        valid_count = 0
        warning_count = 0
        
        # Track duplicates
        korean_terms = []
        english_terms = []
        term_pairs = []
        
        for entry in glossary:
            result = self.validate_glossary_entry(entry)
            results.append(result)
            
            if result.is_valid:
                valid_count += 1
                if result.warning_message:
                    warning_count += 1
                
                # Collect terms for duplicate analysis
                if entry.korean_term:
                    korean_terms.append(entry.korean_term.strip())
                if entry.english_term:
                    english_terms.append(entry.english_term.strip())
                if entry.korean_term and entry.english_term:
                    term_pairs.append((entry.korean_term.strip(), entry.english_term.strip()))
        
        # Analyze duplicates
        korean_duplicates = [term for term, count in Counter(korean_terms).items() if count > 1]
        english_duplicates = [term for term, count in Counter(english_terms).items() if count > 1]
        pair_duplicates = [pair for pair, count in Counter(term_pairs).items() if count > 1]
        
        validation_time = time.time() - start_time
        success_rate = (valid_count / max(len(glossary), 1)) * 100
        
        # Analyze categories
        categories = [entry.category for entry in glossary if entry.category]
        category_counts = Counter(categories)
        
        summary = {
            "duplicate_korean_terms": len(korean_duplicates),
            "duplicate_english_terms": len(english_duplicates),
            "duplicate_pairs": len(pair_duplicates),
            "categories": list(category_counts.keys()),
            "category_distribution": dict(category_counts),
            "total_variations": sum(len(entry.variations) for entry in glossary),
        }
        
        return ValidationReport(
            total_items=len(glossary),
            valid_items=valid_count,
            invalid_items=len(glossary) - valid_count,
            warnings=warning_count,
            success_rate=success_rate,
            validation_time=validation_time,
            detailed_results={"glossary": results},
            summary=summary
        )

    def validate_all_data(self, 
                         test_data: List[TestDataRow], 
                         glossary: List[GlossaryEntry],
                         documents: Dict[str, DocumentMetadata]) -> Dict[str, ValidationReport]:
        """
        Validate all data collections
        
        Args:
            test_data: List of test data rows
            glossary: List of glossary entries
            documents: Dictionary of document metadata
        
        Returns:
            Dictionary of validation reports by data type
        """
        logger.info("Starting comprehensive data validation...")
        
        reports = {}
        
        # Validate test data
        if test_data:
            logger.info(f"Validating {len(test_data)} test data rows...")
            reports["test_data"] = self.validate_test_data_collection(test_data)
        
        # Validate glossary
        if glossary:
            logger.info(f"Validating {len(glossary)} glossary entries...")
            reports["glossary"] = self.validate_glossary_collection(glossary)
        
        # Log summary
        for data_type, report in reports.items():
            logger.info(f"{data_type} validation: {report.success_rate:.1f}% success rate "
                       f"({report.valid_items}/{report.total_items} valid, "
                       f"{report.warnings} warnings)")
        
        return reports

    def print_validation_summary(self, reports: Dict[str, ValidationReport]):
        """
        Print a comprehensive validation summary
        
        Args:
            reports: Dictionary of validation reports
        """
        print("\nData Validation Summary")
        print("=" * 50)
        
        total_items = sum(report.total_items for report in reports.values())
        total_valid = sum(report.valid_items for report in reports.values())
        total_warnings = sum(report.warnings for report in reports.values())
        
        overall_success_rate = (total_valid / max(total_items, 1)) * 100
        
        print(f"Overall: {overall_success_rate:.1f}% success rate")
        print(f"Total items: {total_items}")
        print(f"Valid items: {total_valid}")
        print(f"Warnings: {total_warnings}")
        print()
        
        for data_type, report in reports.items():
            print(f"{data_type.title()}:")
            print(f"  Items: {report.total_items}")
            print(f"  Valid: {report.valid_items} ({report.success_rate:.1f}%)")
            print(f"  Invalid: {report.invalid_items}")
            print(f"  Warnings: {report.warnings}")
            print(f"  Validation time: {report.validation_time:.2f}s")
            
            if report.summary:
                print(f"  Summary: {report.summary}")
            print()


# Convenience functions
def validate_phase2_data(test_data: List[TestDataRow], 
                        glossary: List[GlossaryEntry],
                        documents: Dict[str, DocumentMetadata] = None,
                        strict_mode: bool = False) -> Dict[str, ValidationReport]:
    """
    Convenience function to validate Phase 2 data
    
    Returns:
        Dictionary of validation reports
    """
    validator = DataValidator(strict_mode=strict_mode)
    return validator.validate_all_data(test_data, glossary, documents or {})


def get_validation_summary(reports: Dict[str, ValidationReport]) -> Dict[str, Union[int, float]]:
    """
    Get numerical validation summary
    
    Returns:
        Dictionary with validation metrics
    """
    total_items = sum(report.total_items for report in reports.values())
    total_valid = sum(report.valid_items for report in reports.values())
    total_warnings = sum(report.warnings for report in reports.values())
    
    return {
        "total_items": total_items,
        "valid_items": total_valid,
        "invalid_items": total_items - total_valid,
        "warnings": total_warnings,
        "overall_success_rate": (total_valid / max(total_items, 1)) * 100,
        "validation_time": sum(report.validation_time for report in reports.values())
    }


if __name__ == "__main__":
    # Demo usage
    from data_loader_enhanced import load_phase2_data
    
    print("Phase 2 Data Validation Demo")
    print("=" * 40)
    
    # Load data
    test_data, glossary, documents = load_phase2_data()
    
    # Validate data
    validator = DataValidator(strict_mode=False)
    reports = validator.validate_all_data(test_data, glossary, documents)
    
    # Print summary
    validator.print_validation_summary(reports)
    
    # Show specific issues
    for data_type, report in reports.items():
        invalid_items = [i for i, result in enumerate(report.detailed_results[data_type]) 
                        if not result.is_valid]
        
        if invalid_items:
            print(f"\nFirst 5 invalid {data_type} items:")
            for i in invalid_items[:5]:
                result = report.detailed_results[data_type][i]
                print(f"  Item {i+1}: {result.error_message}")