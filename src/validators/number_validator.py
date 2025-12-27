#!/usr/bin/env python3
"""
Number Validator for Translation Quality Assurance
Validates numeric accuracy, dosages, ratios, and units
"""

import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class IssueSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class ValidationIssue:
    category: str
    message: str
    severity: IssueSeverity
    source_text: str
    target_text: str
    expected: Optional[str] = None
    found: Optional[str] = None

class NumberValidator:
    """Validates numeric accuracy between source and target translations"""

    # Regex patterns for numeric detection
    NUMERIC_PATTERNS = {
        'integers': r'\b(\d+)\b',
        'decimals': r'\b(\d+\.\d+)\b',
        'dosages': r'\b(\d+(?:\.\d+)?)\s*(mg|mL|mcg|μg|g|kg|IU|units?)\b',
        'ratios': r'\b(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\b',
        'per_expressions': r'\b(\d+(?:\.\d+)?)\s*(?:per|/)\s*(\w+)\b',
        'ranges': r'\b(\d+(?:\.\d+)?)\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\b',
        'percentages': r'\b(\d+(?:\.\d+)?)\s*%\b',
        'p_values': r'\bp\s*([<>=]+)\s*(0\.\d+)\b',
        'units_only': r'\b(mg/kg|mg/m²|m²|mL/min|μg/dL|kg/m²)\b'
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def validate_numbers(self, source: str, target: str) -> List[ValidationIssue]:
        """Check all numeric values match exactly"""
        issues = []

        # Extract all numbers from source and target
        source_numbers = self._extract_all_numbers(source)
        target_numbers = self._extract_all_numbers(target)

        # Check if number counts match
        if len(source_numbers) != len(target_numbers):
            issues.append(ValidationIssue(
                category="numeric_count_mismatch",
                message=f"Number count differs: source has {len(source_numbers)}, target has {len(target_numbers)}",
                severity=IssueSeverity.CRITICAL,
                source_text=source,
                target_text=target,
                expected=f"{len(source_numbers)} numbers",
                found=f"{len(target_numbers)} numbers"
            ))
            return issues

        # Check if actual numbers match
        for i, (src_num, tgt_num) in enumerate(zip(source_numbers, target_numbers)):
            if src_num != tgt_num:
                issues.append(ValidationIssue(
                    category="numeric_mismatch",
                    message=f"Numeric value {i+1} doesn't match: {src_num} vs {tgt_num}",
                    severity=IssueSeverity.CRITICAL,
                    source_text=source,
                    target_text=target,
                    expected=src_num,
                    found=tgt_num
                ))

        return issues

    def validate_dosages(self, source: str, target: str) -> List[ValidationIssue]:
        """Validate medication dosages: 100 mg, 5 mL, 50 mg/kg"""
        issues = []

        # Extract dosages with units
        source_dosages = re.findall(
            r'\b(\d+(?:\.\d+)?)\s*(mg|mL|mcg|μg|g|kg|IU|units?)\b',
            source,
            re.IGNORECASE
        )
        target_dosages = re.findall(
            r'\b(\d+(?:\.\d+)?)\s*(mg|mL|mcg|μg|g|kg|IU|units?)\b',
            target,
            re.IGNORECASE
        )

        # Normalize for comparison (case-insensitive)
        source_dosages = [(num, unit.lower()) for num, unit in source_dosages]
        target_dosages = [(num, unit.lower()) for num, unit in target_dosages]

        if len(source_dosages) != len(target_dosages):
            issues.append(ValidationIssue(
                category="dosage_count_mismatch",
                message=f"Dosage count differs: source has {len(source_dosages)}, target has {len(target_dosages)}",
                severity=IssueSeverity.CRITICAL,
                source_text=source,
                target_text=target
            ))
            return issues

        for i, (src_dosage, tgt_dosage) in enumerate(zip(source_dosages, target_dosages)):
            if src_dosage != tgt_dosage:
                src_num, src_unit = src_dosage
                tgt_num, tgt_unit = tgt_dosage

                if src_num != tgt_num:
                    issues.append(ValidationIssue(
                        category="dosage_value_mismatch",
                        message=f"Dosage {i+1} value differs: {src_num}{src_unit} vs {tgt_num}{tgt_unit}",
                        severity=IssueSeverity.CRITICAL,
                        source_text=source,
                        target_text=target,
                        expected=f"{src_num}{src_unit}",
                        found=f"{tgt_num}{tgt_unit}"
                    ))

                if src_unit != tgt_unit:
                    issues.append(ValidationIssue(
                        category="dosage_unit_mismatch",
                        message=f"Dosage {i+1} unit differs: {src_unit} vs {tgt_unit}",
                        severity=IssueSeverity.HIGH,
                        source_text=source,
                        target_text=target,
                        expected=src_unit,
                        found=tgt_unit
                    ))

        return issues

    def validate_ratios(self, source: str, target: str) -> List[ValidationIssue]:
        """Check mathematical ratios: mg/kg, mg/m², μg/dL"""
        issues = []

        # Extract ratio expressions (X/Y format)
        source_ratios = re.findall(r'\b(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\b', source)
        target_ratios = re.findall(r'\b(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\b', target)

        if len(source_ratios) != len(target_ratios):
            issues.append(ValidationIssue(
                category="ratio_count_mismatch",
                message=f"Ratio count differs: source has {len(source_ratios)}, target has {len(target_ratios)}",
                severity=IssueSeverity.HIGH,
                source_text=source,
                target_text=target
            ))

        for i, (src_ratio, tgt_ratio) in enumerate(zip(source_ratios, target_ratios)):
            if src_ratio != tgt_ratio:
                src_x, src_y = src_ratio
                tgt_x, tgt_y = tgt_ratio
                issues.append(ValidationIssue(
                    category="ratio_mismatch",
                    message=f"Ratio {i+1} differs: {src_x}/{src_y} vs {tgt_x}/{tgt_y}",
                    severity=IssueSeverity.HIGH,
                    source_text=source,
                    target_text=target,
                    expected=f"{src_x}/{src_y}",
                    found=f"{tgt_x}/{tgt_y}"
                ))

        return issues

    def validate_units(self, source: str, target: str) -> List[ValidationIssue]:
        """Verify unit consistency and correct abbreviations"""
        issues = []

        # Units that should be preserved exactly
        critical_units = ['mg/kg', 'mg/m²', 'm²', 'mL/min', 'μg/dL', 'kg/m²', 'IU/mL']

        for unit in critical_units:
            source_count = len(re.findall(re.escape(unit), source, re.IGNORECASE))
            target_count = len(re.findall(re.escape(unit), target, re.IGNORECASE))

            if source_count > 0 and target_count != source_count:
                issues.append(ValidationIssue(
                    category="unit_mismatch",
                    message=f"Unit '{unit}' count differs: source has {source_count}, target has {target_count}",
                    severity=IssueSeverity.HIGH,
                    source_text=source,
                    target_text=target,
                    expected=f"{source_count}x {unit}",
                    found=f"{target_count}x {unit}"
                ))

        return issues

    def validate_percentages(self, source: str, target: str) -> List[ValidationIssue]:
        """Check percentage values: 95%, 0.05, p<0.001"""
        issues = []

        # Extract percentages
        source_percentages = re.findall(r'(\d+(?:\.\d+)?)\s*%', source)
        target_percentages = re.findall(r'(\d+(?:\.\d+)?)\s*%', target)

        if len(source_percentages) != len(target_percentages):
            issues.append(ValidationIssue(
                category="percentage_count_mismatch",
                message=f"Percentage count differs: source has {len(source_percentages)}, target has {len(target_percentages)}",
                severity=IssueSeverity.HIGH,
                source_text=source,
                target_text=target
            ))

        for i, (src_pct, tgt_pct) in enumerate(zip(source_percentages, target_percentages)):
            if src_pct != tgt_pct:
                issues.append(ValidationIssue(
                    category="percentage_mismatch",
                    message=f"Percentage {i+1} differs: {src_pct}% vs {tgt_pct}%",
                    severity=IssueSeverity.HIGH,
                    source_text=source,
                    target_text=target,
                    expected=f"{src_pct}%",
                    found=f"{tgt_pct}%"
                ))

        # Extract p-values
        source_pvalues = re.findall(r'p\s*([<>=]+)\s*(0\.\d+)', source, re.IGNORECASE)
        target_pvalues = re.findall(r'p\s*([<>=]+)\s*(0\.\d+)', target, re.IGNORECASE)

        if len(source_pvalues) != len(target_pvalues):
            issues.append(ValidationIssue(
                category="pvalue_count_mismatch",
                message=f"P-value count differs: source has {len(source_pvalues)}, target has {len(target_pvalues)}",
                severity=IssueSeverity.HIGH,
                source_text=source,
                target_text=target
            ))

        for i, (src_pv, tgt_pv) in enumerate(zip(source_pvalues, target_pvalues)):
            if src_pv != tgt_pv:
                issues.append(ValidationIssue(
                    category="pvalue_mismatch",
                    message=f"P-value {i+1} differs: p{src_pv[0]}{src_pv[1]} vs p{tgt_pv[0]}{tgt_pv[1]}",
                    severity=IssueSeverity.HIGH,
                    source_text=source,
                    target_text=target,
                    expected=f"p{src_pv[0]}{src_pv[1]}",
                    found=f"p{tgt_pv[0]}{tgt_pv[1]}"
                ))

        return issues

    def validate_all(self, source: str, target: str) -> List[ValidationIssue]:
        """Run all numeric validations"""
        issues = []
        issues.extend(self.validate_numbers(source, target))
        if not issues:  # Only proceed if basic numbers match
            issues.extend(self.validate_dosages(source, target))
            issues.extend(self.validate_ratios(source, target))
            issues.extend(self.validate_units(source, target))
            issues.extend(self.validate_percentages(source, target))

        return issues

    def _extract_all_numbers(self, text: str) -> List[str]:
        """Extract all standalone numbers from text"""
        # Extract integers and decimals, but not those that are part of other constructs
        numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', text)
        return numbers
