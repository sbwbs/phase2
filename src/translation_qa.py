#!/usr/bin/env python3
"""
Translation QA Validation Framework
Comprehensive quality assurance for clinical protocol translation
Includes: hallucination detection, terminology enforcement, and consistency validation
"""

import re
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class QAIssueType(Enum):
    """Types of QA issues that can be detected"""
    HALLUCINATION = "hallucination"
    TERMINOLOGY_VIOLATION = "terminology_violation"
    INFORMATION_ADDITION = "information_addition"
    SUBJECTIVE_LANGUAGE = "subjective_language"
    INCONSISTENT_ABBREVIATION = "inconsistent_abbreviation"
    EXCESSIVE_VERBOSITY = "excessive_verbosity"
    MISSING_MANDATORY_TERM = "missing_mandatory_term"
    TAG_PRESERVATION_FAILURE = "tag_preservation_failure"  # NEW: CAT tool tag validation

@dataclass
class QAIssue:
    """Represents a quality assurance issue"""
    issue_type: QAIssueType
    severity: str  # "critical", "high", "medium", "low"
    message: str
    source_text: str
    translated_text: str
    suggested_fix: Optional[str] = None

class StrictGlossaryEnforcer:
    """Enforces mandatory terminology usage with strict validation"""
    
    def __init__(self):
        # EN-KO mandatory terms (must be translated consistently)
        self.en_ko_mandatory = {
            "title page": "제목페이지",
            "sponsor representative": "의뢰자 대표자",
            "clinical study protocol": "임상시험계획서", 
            "informed consent": "동의서",
            "adverse event": "이상반응",
            "serious adverse event": "중대한 이상반응",
            "investigational product": "임상시험용 의약품",
            "phase 1": "제1상",
            "phase 2": "제2상",
            "phase 3": "제3상"
        }
        
        # KO-EN mandatory terms (prevent hallucination)
        self.ko_en_mandatory = {
            "임상시험": "clinical study",
            "임상시험계획서": "clinical study protocol",
            "이상반응": "adverse event", 
            "중대한 이상반응": "serious adverse event",
            "시험대상자": "study subject",
            "의뢰자": "sponsor",
            "의뢰자 대표자": "sponsor representative",
            "동의서": "informed consent",
            "교수": "Professor",  # CRITICAL: prevent MD/PhD addition
            "부교수": "Associate Professor",
            "조교수": "Assistant Professor"
        }
        
        # Prohibited translations (common mistakes)
        self.prohibited_translations = {
            "en-ko": {
                "title page": ["표지"],  # Should be 제목페이지
                "sponsor representative": ["의뢰자"],  # Should be 의뢰자 대표자
            },
            "ko-en": {
                "교수": ["MD", "PhD", "Dr.", "M.D.", "Ph.D."],  # Should only be Professor
            }
        }

    def validate_translation(self, source_text: str, translation: str, direction: str) -> List[str]:
        """Validate translation against mandatory terminology"""
        violations = []
        
        if direction == "en-ko":
            violations.extend(self._validate_en_ko_terms(source_text, translation))
        elif direction == "ko-en":
            violations.extend(self._validate_ko_en_terms(source_text, translation))
        
        return violations

    def _validate_en_ko_terms(self, source_en: str, translation_ko: str) -> List[str]:
        """Validate EN-KO mandatory term usage"""
        violations = []
        source_lower = source_en.lower()
        
        for en_term, required_ko in self.en_ko_mandatory.items():
            if en_term in source_lower:
                if required_ko not in translation_ko:
                    violations.append(
                        f"MANDATORY TERM MISSING: '{en_term}' must be translated as '{required_ko}'"
                    )
                
                # Check for prohibited translations
                if en_term in self.prohibited_translations["en-ko"]:
                    for prohibited in self.prohibited_translations["en-ko"][en_term]:
                        if prohibited in translation_ko:
                            violations.append(
                                f"PROHIBITED TRANSLATION: '{en_term}' translated as '{prohibited}' "
                                f"should be '{required_ko}'"
                            )
        
        return violations

    def _validate_ko_en_terms(self, source_ko: str, translation_en: str) -> List[str]:
        """Validate KO-EN mandatory term usage and prevent hallucination"""
        violations = []
        
        for ko_term, required_en in self.ko_en_mandatory.items():
            if ko_term in source_ko:
                if required_en.lower() not in translation_en.lower():
                    violations.append(
                        f"MANDATORY TERM MISSING: '{ko_term}' must be translated as '{required_en}'"
                    )
        
        # Check for hallucination (adding information not in source)
        if "교수" in source_ko:
            # Check if MD or PhD were added when not in Korean
            if any(degree in translation_en for degree in ["MD", "PhD", "Dr.", "M.D.", "Ph.D."]):
                if not any(korean_degree in source_ko for korean_degree in ["의학박사", "박사", "의사"]):
                    violations.append(
                        "HALLUCINATION DETECTED: Added MD/PhD degrees not present in Korean text"
                    )
        
        return violations

class HallucinationDetector:
    """Detects hallucination in translations (adding information not in source)"""
    
    def __init__(self):
        # Common hallucination patterns
        self.ko_en_hallucination_patterns = [
            # Academic title additions
            {
                "source_pattern": r"교수(?!.*박사)(?!.*의사)",  # 교수 without 박사/의사
                "translation_pattern": r"(M\.?D\.?|Ph\.?D\.?|Dr\.)",
                "description": "Added medical degrees not in Korean"
            },
            # Department elaborations
            {
                "source_pattern": r"내과$",  # Just 내과
                "translation_pattern": r"Department of Internal Medicine.*(Division|Section)",
                "description": "Added subdivision not in Korean"
            }
        ]
    
    def detect_hallucination(self, source_text: str, translation: str, direction: str) -> Tuple[bool, str]:
        """Detect if translation contains hallucinated information"""
        if direction == "ko-en":
            return self._detect_ko_en_hallucination(source_text, translation)
        elif direction == "en-ko":
            return self._detect_en_ko_hallucination(source_text, translation)
        
        return False, ""
    
    def _detect_ko_en_hallucination(self, source_ko: str, translation_en: str) -> Tuple[bool, str]:
        """Detect hallucination in Korean to English translation"""
        for pattern in self.ko_en_hallucination_patterns:
            # Check if source matches the source pattern
            if re.search(pattern["source_pattern"], source_ko):
                # Check if translation contains the hallucinated pattern
                if re.search(pattern["translation_pattern"], translation_en):
                    return True, pattern["description"]
        
        # General length-based heuristic
        source_chars = len(source_ko)
        translation_words = len(translation_en.split())
        expected_ratio = 0.6  # Expected Korean char to English word ratio
        
        if translation_words > source_chars * expected_ratio * 1.8:  # 80% longer than expected
            return True, "Translation significantly longer than expected - possible information addition"
        
        return False, ""
    
    def _detect_en_ko_hallucination(self, source_en: str, translation_ko: str) -> Tuple[bool, str]:
        """Detect hallucination in English to Korean translation"""
        # Simple heuristic: if Korean translation is much longer than English source
        source_words = len(source_en.split())
        translation_chars = len(translation_ko)
        expected_ratio = 2.5  # Expected English word to Korean char ratio
        
        if translation_chars > source_words * expected_ratio * 1.5:  # 50% longer than expected
            return True, "Korean translation much longer than English source - possible addition"
        
        return False, ""

class VerbosityAnalyzer:
    """Analyzes and detects excessive verbosity in translations"""
    
    def __init__(self):
        self.verbose_phrases = [
            # English verbose phrases that should be avoided
            r"as mentioned above,?\s*",
            r"it should be noted that\s*",
            r"it is important to\s*", 
            r"please note that\s*",
            r"in this context,?\s*",
            r"for the purpose of\s*",
            r"in order to\s*"
        ]
    
    def calculate_verbosity_score(self, source_text: str, translation: str, direction: str) -> float:
        """Calculate verbosity score (1.0 = normal, >1.0 = verbose)"""
        if direction == "ko-en":
            source_chars = len(source_text)
            translation_words = len(translation.split())
            expected_words = source_chars * 0.6  # Korean char to English word ratio
            return translation_words / expected_words if expected_words > 0 else 1.0
        
        elif direction == "en-ko":
            source_words = len(source_text.split())
            translation_chars = len(translation)
            expected_chars = source_words * 2.5  # English word to Korean char ratio
            return translation_chars / expected_chars if expected_chars > 0 else 1.0
        
        return 1.0
    
    def detect_verbose_phrases(self, translation: str) -> List[str]:
        """Detect verbose phrases in translation"""
        found_phrases = []
        for pattern in self.verbose_phrases:
            matches = re.findall(pattern, translation, re.IGNORECASE)
            if matches:
                found_phrases.extend(matches)
        
        return found_phrases


class TagPreservationValidator:
    """Validates tag preservation in CAT tool translations"""

    def __init__(self):
        """Initialize tag preservation validator"""
        # Import tag handler (lazy import to avoid circular dependencies)
        try:
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
            from tag_handler import TagHandler
            self.tag_handler = TagHandler()
        except ImportError:
            logging.warning("TagHandler not available - tag validation will be skipped")
            self.tag_handler = None

    def validate_tags(self, source_text: str, translation: str) -> List[QAIssue]:
        """
        Validate tag preservation between source and target

        Returns list of QA issues related to tag preservation
        """
        issues = []

        # Skip if tag handler not available
        if not self.tag_handler:
            return issues

        # Check if source has tags
        if not self.tag_handler.has_tags(source_text):
            return issues

        # Run comprehensive tag validation
        validation_result = self.tag_handler.validate_tags(source_text, translation)

        if not validation_result.is_valid:
            # Create QA issue for tag preservation failure
            severity = "critical" if validation_result.severity else "high"

            issue = QAIssue(
                issue_type=QAIssueType.TAG_PRESERVATION_FAILURE,
                severity=severity,
                message=f"Tag preservation failed: {'; '.join(validation_result.issues)}",
                source_text=source_text[:100] + "..." if len(source_text) > 100 else source_text,
                translated_text=translation[:100] + "..." if len(translation) > 100 else translation,
                suggested_fix="Review and correct tag placement according to source text"
            )
            issues.append(issue)

            # Add specific issues for missing tags
            if validation_result.missing_tags:
                issue = QAIssue(
                    issue_type=QAIssueType.TAG_PRESERVATION_FAILURE,
                    severity="critical",
                    message=f"Missing tags in translation: {validation_result.missing_tags}",
                    source_text=source_text,
                    translated_text=translation,
                    suggested_fix=f"Add missing tags: {validation_result.missing_tags}"
                )
                issues.append(issue)

            # Add specific issues for extra tags
            if validation_result.extra_tags:
                issue = QAIssue(
                    issue_type=QAIssueType.TAG_PRESERVATION_FAILURE,
                    severity="critical",
                    message=f"Extra tags in translation: {validation_result.extra_tags}",
                    source_text=source_text,
                    translated_text=translation,
                    suggested_fix=f"Remove extra tags: {validation_result.extra_tags}"
                )
                issues.append(issue)

            # Add specific issues for changed tags
            if validation_result.changed_tags:
                issue = QAIssue(
                    issue_type=QAIssueType.TAG_PRESERVATION_FAILURE,
                    severity="high",
                    message=f"Tag IDs or formats changed: {validation_result.changed_tags}",
                    source_text=source_text,
                    translated_text=translation,
                    suggested_fix="Preserve exact tag numbers and formats from source"
                )
                issues.append(issue)

        return issues

    def get_tag_statistics(self, source_text: str, translation: str) -> Dict:
        """Get detailed tag statistics for reporting"""
        if not self.tag_handler:
            return {"tag_handler_available": False}

        source_stats = self.tag_handler.get_tag_statistics(source_text)
        target_stats = self.tag_handler.get_tag_statistics(translation)

        return {
            "source_tags": source_stats,
            "target_tags": target_stats,
            "tag_count_match": source_stats['total_tags'] == target_stats['total_tags']
        }


class TranslationQAChecker:
    """Comprehensive QA checker combining all validation methods"""
    
    def __init__(self):
        self.glossary_enforcer = StrictGlossaryEnforcer()
        self.hallucination_detector = HallucinationDetector()
        self.verbosity_analyzer = VerbosityAnalyzer()
        self.tag_validator = TagPreservationValidator()  # NEW: Tag preservation validation
        self.logger = logging.getLogger(__name__)
    
    def run_comprehensive_qa(self, source_text: str, translation: str, direction: str) -> List[QAIssue]:
        """Run all QA checks and return issues"""
        issues = []
        
        # 1. Terminology validation
        term_violations = self.glossary_enforcer.validate_translation(source_text, translation, direction)
        for violation in term_violations:
            issues.append(QAIssue(
                issue_type=QAIssueType.TERMINOLOGY_VIOLATION,
                severity="critical" if "MANDATORY" in violation else "high",
                message=violation,
                source_text=source_text,
                translated_text=translation
            ))
        
        # 2. Hallucination detection
        hallucination_detected, details = self.hallucination_detector.detect_hallucination(
            source_text, translation, direction
        )
        if hallucination_detected:
            issues.append(QAIssue(
                issue_type=QAIssueType.HALLUCINATION,
                severity="critical",
                message=f"HALLUCINATION: {details}",
                source_text=source_text,
                translated_text=translation
            ))
        
        # 3. Verbosity analysis
        verbosity_score = self.verbosity_analyzer.calculate_verbosity_score(source_text, translation, direction)
        if verbosity_score > 1.5:
            issues.append(QAIssue(
                issue_type=QAIssueType.EXCESSIVE_VERBOSITY,
                severity="medium",
                message=f"EXCESSIVE VERBOSITY: Translation {verbosity_score:.1f}x expected length",
                source_text=source_text,
                translated_text=translation
            ))
        
        # 4. Verbose phrase detection
        verbose_phrases = self.verbosity_analyzer.detect_verbose_phrases(translation)
        if verbose_phrases:
            issues.append(QAIssue(
                issue_type=QAIssueType.EXCESSIVE_VERBOSITY,
                severity="low",
                message=f"VERBOSE PHRASES: Found {', '.join(verbose_phrases)}",
                source_text=source_text,
                translated_text=translation
            ))
        
        # 5. Subjective language detection (for EN-KO)
        if direction == "en-ko":
            subjective_patterns = ['적정함', '우수함', '양호함', '바람직함', '만족스러움']
            found_subjective = [p for p in subjective_patterns if p in translation]
            if found_subjective:
                issues.append(QAIssue(
                    issue_type=QAIssueType.SUBJECTIVE_LANGUAGE,
                    severity="high",
                    message=f"SUBJECTIVE LANGUAGE: Found {', '.join(found_subjective)}",
                    source_text=source_text,
                    translated_text=translation,
                    suggested_fix="Use objective, factual language only"
                ))

        # 6. Tag preservation validation (NEW - CAT tool integration)
        tag_issues = self.tag_validator.validate_tags(source_text, translation)
        issues.extend(tag_issues)

        return issues
    
    def generate_qa_report(self, issues: List[QAIssue]) -> str:
        """Generate a formatted QA report"""
        if not issues:
            return "✅ No QA issues detected"
        
        report = f"⚠️  Found {len(issues)} QA issues:\n"
        
        # Group by severity
        critical = [i for i in issues if i.severity == "critical"]
        high = [i for i in issues if i.severity == "high"]
        medium = [i for i in issues if i.severity == "medium"]
        low = [i for i in issues if i.severity == "low"]
        
        if critical:
            report += f"\n🚨 CRITICAL Issues ({len(critical)}):\n"
            for issue in critical:
                report += f"  - {issue.message}\n"
        
        if high:
            report += f"\n⚠️ HIGH Priority Issues ({len(high)}):\n"
            for issue in high:
                report += f"  - {issue.message}\n"
        
        if medium:
            report += f"\n⚡ MEDIUM Priority Issues ({len(medium)}):\n"
            for issue in medium:
                report += f"  - {issue.message}\n"
        
        if low:
            report += f"\n📝 LOW Priority Issues ({len(low)}):\n"
            for issue in low:
                report += f"  - {issue.message}\n"
        
        return report

# Usage example and testing
if __name__ == "__main__":
    # Initialize QA checker
    qa_checker = TranslationQAChecker()
    
    # Test hallucination detection (Segment 60 type issue)
    print("🧪 Testing Hallucination Detection:")
    ko_source = "원광대학교병원 소화기내과 최석채 교수"
    bad_translation = "Seok-Chae Choi, MD, PhD, Professor, Division of Gastroenterology, Wonkwang University Hospital"
    good_translation = "Professor Seok-Chae Choi, Division of Gastroenterology, Wonkwang University Hospital"
    
    # Test bad translation
    issues_bad = qa_checker.run_comprehensive_qa(ko_source, bad_translation, "ko-en")
    print(f"\nBAD Translation Issues:")
    print(qa_checker.generate_qa_report(issues_bad))
    
    # Test good translation
    issues_good = qa_checker.run_comprehensive_qa(ko_source, good_translation, "ko-en")
    print(f"\nGOOD Translation Issues:")
    print(qa_checker.generate_qa_report(issues_good))
    
    # Test EN-KO terminology enforcement
    print("\n🧪 Testing EN-KO Terminology Enforcement:")
    en_source = "Title Page of Clinical Study Protocol"
    bad_ko_translation = "임상시험 연구의 표지"  # Wrong: 표지 instead of 제목페이지
    good_ko_translation = "임상시험계획서의 제목페이지"
    
    # Test bad translation
    issues_bad_ko = qa_checker.run_comprehensive_qa(en_source, bad_ko_translation, "en-ko")
    print(f"\nBAD KO Translation Issues:")
    print(qa_checker.generate_qa_report(issues_bad_ko))
    
    # Test good translation
    issues_good_ko = qa_checker.run_comprehensive_qa(en_source, good_ko_translation, "en-ko")
    print(f"\nGOOD KO Translation Issues:")
    print(qa_checker.generate_qa_report(issues_good_ko))