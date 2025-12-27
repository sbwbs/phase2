#!/usr/bin/env python3
"""
Modal Verb Validator for Translation Quality Assurance
Validates ICH GCP regulatory modal verb hierarchy
"""

import re
import logging
from typing import List, Optional, Dict
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

class ModalVerbValidator:
    """
    Validates modal verb usage per ICH GCP E6(R2) guidelines
    Ensures regulatory compliance and proper Korean-to-English mapping
    """

    # ICH GCP Modal Verb Hierarchy (strength order)
    MODAL_VERB_HIERARCHY = {
        'must': {
            'strength': 5,
            'usage': 'Legal/regulatory requirements - absolute necessity',
            'korean_map': ['반드시', '필수적으로']
        },
        'shall': {
            'strength': 4,
            'usage': 'Mandatory protocol procedures - required action',
            'korean_map': ['~해야 한다', '~수 없다', '의무적으로']
        },
        'should': {
            'strength': 3,
            'usage': 'Strong recommendations - highly advised',
            'korean_map': ['권장된다', '권장하는', '~하는 것이 좋다']
        },
        'may': {
            'strength': 2,
            'usage': 'Permission/optional - allowed but not required',
            'korean_map': ['~할 수 있다', '가능하다', '선택사항']
        },
        'will': {
            'strength': 1,
            'usage': 'Factual statements - future fact',
            'korean_map': ['~할 것이다', '~된다', '~된다']
        }
    }

    # Mapping from Korean modal expressions to English modal verbs
    KOREAN_MODAL_MAPPING = {
        '반드시': 'must',
        '필수적으로': 'must',
        '~해야 한다': 'shall',
        '~해야': 'shall',
        '~할 수 없다': 'shall not',
        '~할 수 없어야': 'shall not',
        '의무적으로': 'shall',
        '권장된다': 'should',
        '권장하는': 'should',
        '~하는 것이 좋다': 'should',
        '~할 수 있다': 'may',
        '가능하다': 'may',
        '선택사항': 'may',
        '~할 것이다': 'will',
        '~된다': 'will',
        '~습니다': 'will'
    }

    # Regex patterns for modal verb detection
    MODAL_PATTERNS = {
        'must': r'\bmust\b',
        'shall': r'\bshall\b',
        'should': r'\bshould\b',
        'may': r'\bmay\b',
        'will': r'\bwill\b',
        'must_not': r'\bmust\s+not\b',
        'shall_not': r'\bshall\s+not\b',
        'should_not': r'\bshould\s+not\b'
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def validate_modal_verb_consistency(self, source_ko: str, target_en: str) -> List[ValidationIssue]:
        """
        Check if Korean modal expressions map correctly to English modal verbs
        Example: "반드시" should map to "must", not "should"
        """
        issues = []

        # Extract Korean modal expressions from source
        korean_modals = self._extract_korean_modals(source_ko)

        # Extract English modal verbs from target
        english_modals = self._extract_english_modals(target_en)

        # If Korean has modals, target must also have corresponding English modals
        if korean_modals and not english_modals:
            issues.append(ValidationIssue(
                category="missing_modal_verb",
                message=f"Korean has modal expression(s) but English lacks modal verb: {', '.join(korean_modals)}",
                severity=IssueSeverity.HIGH,
                source_text=source_ko,
                target_text=target_en,
                expected="English modal verb",
                found="No modal verb found"
            ))

        # Validate mapping consistency
        for ko_modal, en_modal in zip(korean_modals, english_modals):
            expected_en_modal = self._get_expected_english_modal(ko_modal)

            if expected_en_modal and en_modal.lower() != expected_en_modal:
                issues.append(ValidationIssue(
                    category="incorrect_modal_mapping",
                    message=f"Korean '{ko_modal}' maps to '{en_modal}' but should map to '{expected_en_modal}'",
                    severity=IssueSeverity.HIGH,
                    source_text=source_ko,
                    target_text=target_en,
                    expected=expected_en_modal,
                    found=en_modal
                ))

        return issues

    def detect_modal_verb_downgrade(self, source: str, target: str) -> List[ValidationIssue]:
        """
        Flag if mandatory 'shall' becomes optional 'may'
        This is a critical regulatory violation
        """
        issues = []

        # Extract modal strength from source
        source_strength = self._get_modal_strength(source)

        # Extract modal strength from target
        target_strength = self._get_modal_strength(target)

        # Check for downgrade (mandatory → optional)
        if source_strength > 0 and target_strength >= 0 and target_strength < source_strength:
            source_modal = self._find_modal_verb(source)
            target_modal = self._find_modal_verb(target)

            issues.append(ValidationIssue(
                category="modal_verb_downgrade",
                message=f"Modal verb downgraded from '{source_modal}' (strength {source_strength}) to '{target_modal}' (strength {target_strength})",
                severity=IssueSeverity.CRITICAL,
                source_text=source,
                target_text=target,
                expected=source_modal,
                found=target_modal
            ))

        return issues

    def validate_ich_gcp_compliance(self, text: str, context: str = "") -> List[ValidationIssue]:
        """
        Check modal verb usage aligns with ICH GCP regulatory context
        Ensures appropriate strength for clinical trial documentation
        """
        issues = []

        # Find all modal verbs
        modals = self._extract_english_modals(text)

        # Context-specific validation rules
        if 'protocol procedure' in context.lower() or 'mandatory' in context.lower():
            # Protocol procedures typically require 'shall'
            for modal in modals:
                if modal.lower() in ['may', 'will']:
                    issues.append(ValidationIssue(
                        category="ich_gcp_compliance_violation",
                        message=f"Protocol procedure should use 'shall', not '{modal}'",
                        severity=IssueSeverity.HIGH,
                        source_text=text,
                        target_text=text,
                        expected="shall",
                        found=modal
                    ))

        elif 'recommendation' in context.lower():
            # Recommendations should use 'should'
            for modal in modals:
                if modal.lower() in ['must', 'shall']:
                    issues.append(ValidationIssue(
                        category="ich_gcp_compliance_violation",
                        message=f"Recommendation should use 'should', not '{modal}'",
                        severity=IssueSeverity.MEDIUM,
                        source_text=text,
                        target_text=text,
                        expected="should",
                        found=modal
                    ))

        elif 'optional' in context.lower():
            # Optional items should use 'may'
            for modal in modals:
                if modal.lower() in ['must', 'shall']:
                    issues.append(ValidationIssue(
                        category="ich_gcp_compliance_violation",
                        message=f"Optional item should use 'may', not '{modal}'",
                        severity=IssueSeverity.MEDIUM,
                        source_text=text,
                        target_text=text,
                        expected="may",
                        found=modal
                    ))

        return issues

    def validate_modal_consistency_across_segments(self, segments: List[Dict]) -> List[ValidationIssue]:
        """
        Ensure consistent modal verb usage across related segments
        All references to the same requirement should use same modal verb
        """
        issues = []

        # Group segments by key terms to check consistency
        term_modals = {}

        for seg in segments:
            source = seg.get('source', '')
            target = seg.get('target', '')
            segment_id = seg.get('segment_id', '')

            # Extract key terms and their associated modals
            terms = self._extract_key_terms(source)

            for term in terms:
                if term not in term_modals:
                    term_modals[term] = []

                modal = self._find_modal_verb(target)
                if modal:
                    term_modals[term].append({
                        'segment_id': segment_id,
                        'modal': modal,
                        'text': target
                    })

        # Check for inconsistencies
        for term, occurrences in term_modals.items():
            if len(occurrences) > 1:
                modals_used = [occ['modal'] for occ in occurrences]
                unique_modals = set(modals_used)

                if len(unique_modals) > 1:
                    issues.append(ValidationIssue(
                        category="modal_inconsistency_across_segments",
                        message=f"Term '{term}' uses inconsistent modals: {', '.join(unique_modals)}",
                        severity=IssueSeverity.MEDIUM,
                        source_text=term,
                        target_text=', '.join([f"{o['segment_id']}: {o['modal']}" for o in occurrences])
                    ))

        return issues

    # Helper Methods

    def _extract_korean_modals(self, text: str) -> List[str]:
        """Extract Korean modal expressions from text"""
        modals = []
        for ko_modal in self.KOREAN_MODAL_MAPPING.keys():
            if ko_modal in text:
                modals.append(ko_modal)
        return modals

    def _extract_english_modals(self, text: str) -> List[str]:
        """Extract English modal verbs from text"""
        modals = []
        for modal, pattern in self.MODAL_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            modals.extend(matches)
        return modals

    def _get_expected_english_modal(self, korean_modal: str) -> Optional[str]:
        """Get expected English modal verb for Korean modal expression"""
        return self.KOREAN_MODAL_MAPPING.get(korean_modal)

    def _get_modal_strength(self, text: str) -> int:
        """Get the strength level of modal verbs in text (0-5)"""
        max_strength = 0
        for modal, properties in self.MODAL_VERB_HIERARCHY.items():
            pattern = re.compile(rf'\b{modal}\b', re.IGNORECASE)
            if pattern.search(text):
                max_strength = max(max_strength, properties['strength'])
        return max_strength

    def _find_modal_verb(self, text: str) -> Optional[str]:
        """Find the primary modal verb in text"""
        for modal in ['must', 'shall', 'should', 'may', 'will']:
            pattern = re.compile(rf'\b{modal}\b', re.IGNORECASE)
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms from segment (nouns/verbs before modals)"""
        # Simple extraction: words before modal verbs
        terms = []
        words = text.split()

        for i, word in enumerate(words):
            # Check if next word is a modal verb pattern
            if i < len(words) - 1:
                next_word = words[i + 1]
                if any(modal in next_word.lower() for modal in self.MODAL_VERB_HIERARCHY.keys()):
                    # This word precedes a modal verb
                    terms.append(word)

        return terms
