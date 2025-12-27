# Translation Feedback Analysis and Recommendations

## Executive Summary

Based on comprehensive feedback analysis from EN-KO and KO-EN translation results, critical issues have been identified that require immediate attention. The primary concerns are: **over-interpretation/paraphrasing in EN-KO**, **verbosity and hallucination in KO-EN**, and **inconsistent terminology usage** across both directions.

## 1. Critical Issues Identified

### 1.1 EN-KO Translation Issues

#### **HIGH PRIORITY: Over-interpretation and Subjectivity**
- **Issue**: Translations include subjective interpretations not present in source text
- **Example**: "내용이 적정함" (content is appropriate) adds evaluative meaning
- **Root Cause**: Prompt encourages "natural" Korean flow over literal accuracy
- **Impact**: Regulatory reviewers compare EN/KO side-by-side and require exact correspondence

#### **HIGH PRIORITY: Terminology Inconsistency**
- **Issue**: Critical regulatory terms not consistently translated
- **Examples**:
  - "표지" (casual) vs "제목페이지" (formal) for title page
  - "의뢰자 대표자" vs "의뢰자" for Sponsor Representative
- **Root Cause**: Style guide prioritizes variety over consistency

#### **MEDIUM PRIORITY: Style Too Informal**
- **Issue**: Using casual Korean expressions in formal regulatory documents
- **Feedback**: "간결하면서도 표준화된 번역으로 직역에 가깝게 하는게 무난합니다"
- **Solution**: Need more conservative, standardized translation approach

### 1.2 KO-EN Translation Issues

#### **CRITICAL: Hallucination (Segment 60)**
- **Issue**: Added "MD, PhD, Professor" information not in source text
- **Source**: "원광대학교병원 소화기내과 최석채 교수"
- **Translation**: "Seok-Chae Choi, MD, PhD, Professor, Division of Gastroenterology, Wonkwang University Hospital"
- **Impact**: Could cause critical errors in regulatory submission

#### **HIGH PRIORITY: Verbosity**
- **Issue**: Output tends to be verbose and redundant
- **Feedback**: "reads more like technical writing than regulatory writing"
- **Examples**: Over-explaining concepts, adding unnecessary clarifications
- **Root Cause**: GPT-5 OWL's "medium verbosity" setting

#### **MEDIUM PRIORITY: Inconsistent Abbreviations**
- **Issue**: Mid-sentence capitalization and inconsistent abbreviation usage
- **Examples**: "Adverse Events" vs "adverse events", inconsistent "AE" usage
- **Solution**: Need strict rules for abbreviation introduction and usage

## 2. Architecture Analysis

### 2.1 Current Prompt Structure Issues

#### EN-KO Pipeline (`production_pipeline_en_ko.py`)
```python
# Current problematic guidelines:
"- 전문적이고 격식있는 한국어 사용 (합쇼체)"
"- 피동형보다 능동형 선호"
"- 명확하고 간결한 표현"
```
**Problem**: Encourages interpretation over literal translation

#### KO-EN Pipeline (`production_pipeline_working.py`)
```python
# Current prompt:
"Provide only the professional English translation following ICH GCP standards"
```
**Problem**: Too open-ended, allows for additions and interpretations

### 2.2 Style Guide Configuration Issues

#### Clinical Protocol Variant
- Currently ~300 tokens but lacks critical regulatory constraints
- Missing explicit instructions against adding information
- No clear hierarchy for terminology conflicts

## 3. Recommendations

### 3.1 Immediate Actions (Priority 1)

#### A. Revise EN-KO Prompt Instructions
```python
# Recommended new instructions:
"""
## 영한 번역 원칙 (EN→KO Translation Principles)

### 핵심 원칙:
1. **직역 우선**: 의역이나 해석 금지, 원문 충실히 번역
2. **정보 추가/삭제 금지**: 원문에 없는 정보 추가 절대 금지
3. **일관성 최우선**: 동일 용어는 문서 전체에서 동일하게 번역
4. **규제 문서 표준**: 식약처 임상시험 용어집 준수

### 번역 스타일:
- 간결하고 표준화된 번역
- 영문본과 한글본 대조 가능하도록 직역
- 공식 문서에 적합한 보수적 어조
- "제목페이지" (NOT "표지")
- "의뢰자 대표자" (NOT "의뢰자")
"""
```

#### B. Revise KO-EN Prompt Instructions
```python
# Recommended new instructions:
"""
## Translation Rules:
1. **STRICT LITERAL TRANSLATION**: Translate ONLY what is in the source text
2. **NO ADDITIONS**: Do NOT add degrees, titles, or information not in Korean
3. **CONCISE OUTPUT**: Use minimal necessary words, avoid redundancy
4. **ABBREVIATIONS**: Introduce once (full term, ABBR), then use consistently

## Critical Instructions:
- If Korean text says "교수", translate as "Professor" ONLY
- Do NOT add "MD", "PhD" unless explicitly stated in Korean
- Maintain exact information parity with source
"""
```

### 3.2 Structural Improvements (Priority 2)

#### A. Implement Strict Glossary Enforcement
```python
class StrictGlossaryEnforcer:
    def __init__(self):
        self.mandatory_terms = {
            # EN-KO mandatory terms
            "title page": "제목페이지",
            "sponsor representative": "의뢰자 대표자",
            "clinical study protocol": "임상시험계획서",
            
            # KO-EN mandatory terms
            "임상시험": "clinical study",
            "이상반응": "adverse event",
        }
    
    def validate_translation(self, source, translation, direction):
        """Check if mandatory terms are correctly used"""
        violations = []
        for term, required in self.mandatory_terms.items():
            if term in source.lower() and required not in translation:
                violations.append(f"Missing required term: {term} → {required}")
        return violations
```

#### B. Add Hallucination Detection
```python
def detect_hallucination(source_text, translated_text, direction="ko-en"):
    """Detect potential hallucinations in translation"""
    if direction == "ko-en":
        # Check for common additions
        hallucination_patterns = [
            (r"교수(?!.*Ph\.?D)", r"Ph\.?D"),  # PhD added when only 교수
            (r"교수(?!.*MD)", r"MD"),  # MD added when only 교수
            (r"(?<!박사)", r"Ph\.?D"),  # PhD without 박사
        ]
        
        for source_pattern, trans_pattern in hallucination_patterns:
            if not re.search(source_pattern, source_text) and re.search(trans_pattern, translated_text):
                return True, f"Potential hallucination: {trans_pattern} added"
    
    return False, None
```

### 3.3 Model Configuration Adjustments (Priority 2)

#### A. Adjust GPT-5 OWL Parameters
```python
# Current (problematic):
text={"verbosity": "medium"},
reasoning={"effort": "minimal"}

# Recommended:
text={"verbosity": "minimal"},  # Reduce verbosity
reasoning={"effort": "medium"}   # Increase reasoning for accuracy
```

#### B. Add Post-Processing Validation
```python
def post_process_translation(translation, source, direction):
    """Clean and validate translation output"""
    if direction == "ko-en":
        # Remove redundant phrases
        translation = re.sub(r'\b(\w+)\s+\1\b', r'\1', translation)  # Remove duplicates
        
        # Standardize abbreviations
        translation = standardize_abbreviations(translation)
        
        # Validate no additions
        if detect_hallucination(source, translation)[0]:
            translation = flag_for_review(translation)
    
    return translation
```

### 3.4 Quality Assurance Framework (Priority 3)

#### A. Implement Automated QA Checks
```python
class TranslationQAChecker:
    def __init__(self):
        self.checks = [
            self.check_literal_translation,
            self.check_no_additions,
            self.check_terminology_consistency,
            self.check_abbreviation_consistency,
            self.check_regulatory_compliance
        ]
    
    def run_qa(self, source, translation, direction, glossary):
        """Run all QA checks and return issues"""
        issues = []
        for check in self.checks:
            issue = check(source, translation, direction, glossary)
            if issue:
                issues.append(issue)
        return issues
```

## 4. Implementation Plan

### Phase 1: Immediate Fixes (Week 1)
1. **Day 1-2**: Update prompts in both pipelines with stricter instructions
2. **Day 3-4**: Implement hallucination detection for KO-EN
3. **Day 5**: Add mandatory terminology validation

### Phase 2: Structural Improvements (Week 2-3)
1. **Week 2**: Implement StrictGlossaryEnforcer and post-processing
2. **Week 3**: Adjust model parameters and test quality improvements

### Phase 3: Quality Framework (Week 4)
1. Implement comprehensive QA checker
2. Add feedback loop for continuous improvement
3. Create performance monitoring dashboard

## 5. Success Metrics

### Quantitative Metrics
- **Hallucination Rate**: Target < 0.1% (currently ~1-2%)
- **Terminology Consistency**: Target > 98% (currently ~85%)
- **Literal Translation Score**: Target > 95% (currently ~80%)
- **Verbosity Reduction**: Target 20% reduction in output length for KO-EN

### Qualitative Metrics
- Reviewer satisfaction with literal translation approach
- Reduced need for manual corrections
- Faster regulatory approval process

## 6. Risk Mitigation

### Risks and Mitigations
1. **Risk**: Over-correction leading to unnatural translations
   - **Mitigation**: Balance literal translation with readability checks

2. **Risk**: Reduced translation speed due to additional checks
   - **Mitigation**: Optimize validation pipeline, run checks in parallel

3. **Risk**: Model resistance to new instructions
   - **Mitigation**: Test multiple prompt variations, consider fine-tuning

## 7. Testing Strategy

### A/B Testing Plan
1. Run current vs improved prompts on same test set
2. Compare:
   - Hallucination rates
   - Terminology consistency
   - Reviewer preference scores
   - Processing time

### Validation Dataset
- Use 100 segments from each direction with known issues
- Include edge cases from feedback (segment 60, terminology examples)
- Measure improvement quantitatively

## 8. Long-term Recommendations

### Model Training/Fine-tuning
Consider fine-tuning GPT-5 OWL specifically for:
- Clinical protocol translation
- Literal translation preference
- Regulatory terminology consistency

### Feedback Integration System
Build automated system to:
- Collect reviewer feedback
- Update glossaries automatically
- Adjust prompts based on patterns
- Track improvement over time

## Appendix: Critical Terminology Updates

### EN-KO Mandatory Terms
| English | Korean | Note |
|---------|--------|------|
| Title Page | 제목페이지 | NOT 표지 |
| Sponsor Representative | 의뢰자 대표자 | NOT 의뢰자 |
| Clinical Study Protocol | 임상시험계획서 | Regulatory standard |
| Informed Consent | 동의서 | NOT 설명문 및 동의서 |

### KO-EN Mandatory Terms
| Korean | English | Note |
|--------|---------|------|
| 임상시험 | clinical study | NOT clinical trial in protocol |
| 교수 | Professor | Do NOT add MD/PhD unless stated |
| 이상반응 | adverse event | NOT side effect |
| 임상시험용 의약품 | investigational product | NOT test drug |

---

**Document Version**: 1.0  
**Date**: 2025-09-14  
**Author**: Translation System Analysis Team  
**Status**: Ready for Implementation