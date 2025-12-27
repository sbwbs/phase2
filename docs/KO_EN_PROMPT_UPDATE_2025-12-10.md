# KO-EN Prompt Update Summary (2025-12-10)

## Overview

Updated KO-EN (Korean→English) translation prompts based on real customer feedback from the **Yuhan AD-223P3 clinical protocol/SAP translation project**.

## Source Documents Analyzed

| File | Issues | Content |
|------|--------|---------|
| `2025-11-17_선영_Debriefing.xlsx` | 43 | Sentence structure, consistency issues |
| `2025-11-17_주연_Debriefing(유한).xlsx` | 16 | Specific segment corrections with IDs |
| `2025-11-18_주연_조동사 사용.xlsx` | 6 | Modal verb hierarchy guidelines |

---

## Files Modified

### 1. `phase2/src/style_guide_config.py`

#### Method: `_get_ko_en_regulatory_compliance_style_guide()` (lines 401-455)
**Change**: Replaced baseline KO-EN style guide (~300 tokens → ~500 tokens)

**New Rules Added:**
- Modal verb hierarchy (must > shall > should > will)
- Subject terminology consistency ("Subjects" only)
- Critical term corrections (rate/ratio, height/renal)
- Formatting rules (Korean names, symbols to words)
- Sentence structure rules (passive voice, past tense)
- Split segment handling
- Content integrity rules

#### Method: `_get_ko_en_enhanced_with_examples()` (lines 457-566)
**Change**: Replaced enhanced KO-EN style guide (~900 tokens → ~1100 tokens)

**New Examples Added (11 total):**
1. Modal verb - must (legal requirement)
2. Modal verb - shall (protocol prohibition)
3. Modal verb - should (recommendation)
4. Modal verb - will (factual statement)
5. Subject consistency ("Subjects who...")
6. Rate vs Ratio distinction
7. Height vs Renal function
8. Korean name formatting
9. Symbol to words conversion
10. Passive procedure form
11. No content addition

---

### 2. `phase2/src/production_pipeline_ko_en_improved.py`

#### Method: `_extract_mandatory_ko_en_terms()` (lines 204-242)
**Change**: Added customer feedback term corrections

**New/Updated Terms:**
| Korean | English | Note |
|--------|---------|------|
| 시험대상자 | Subjects | Changed from "study subject" |
| 대상자 | Subjects | Added for consistency |
| 비율 | rate | Added (not "ratio") |
| 신장 | height | Added (not "renal function") |
| 대체 날짜 | Imputed date | Added (not "Alternate date") |

---

## Key Rules Implemented

### Modal Verb Hierarchy (MANDATORY)

| Modal | Obligation Level | Korean Indicators | Example |
|-------|-----------------|-------------------|---------|
| **must** | Legal/regulatory requirement | 반드시, 필수, 법적 의무 | "consent must be documented" |
| **shall** | Protocol-defined procedure | 규정됨, ~수 없다 | "shall not be disclosed" |
| **should** | Recommendation | 권고, 주의 | "should be administered with caution" |
| **will** | Factual statement | ~한다, 예정 | "will be conducted using" |

### Subject Terminology (MANDATORY)

- Always use **"Subjects"** (not "study subjects", "individual", "person")
- Eligibility format: **"Subjects who..."** (not "Participation in..." / "Any person...")

### Critical Term Corrections

| Korean | CORRECT | INCORRECT |
|--------|---------|-----------|
| 비율 (achievement context) | rate | ratio |
| 신장 (body measurement) | height | renal function |
| 대체 날짜 (statistics) | Imputed date | Alternate date |

### Formatting Rules (MANDATORY)

| Rule | Format | Example |
|------|--------|---------|
| Korean names | "Last, First" | 조현지 → "Jo, Hyun Ji" |
| Symbols | Words | ≥20 mmHg → "20 mmHg or greater" |
| Timepoints | Capitalize | Week 4, Visit 1, Screening |
| Treatment groups | Capitalize | Study Group, Control Group |
| Drug names | Lowercase | isosorbide mononitrate |

### Sentence Structure Rules

| Context | Rule | Example |
|---------|------|---------|
| Revision history | Past tense | "Added", "Changed", "Clarified" |
| Procedures | Passive form | "will be collected", "will be measured" |
| Prepositions | Consistent | "from baseline at Week X" |

### Content Integrity (CRITICAL)

- **NO content addition**: Never add information not in Korean source
- **NO content omission**: Preserve all source content
- **Typo verification**: Check English terms in source match output

---

## Token Impact

| Style Guide | Before | After | Change |
|-------------|--------|-------|--------|
| Baseline (REGULATORY_COMPLIANCE) | ~300 | ~500 | +67% |
| Enhanced (REGULATORY_COMPLIANCE_ENHANCED) | ~900 | ~1100 | +22% |

---

## Expected Improvements

1. **Modal verb consistency** across all translations
2. **Subject terminology** uniformity ("Subjects who...")
3. **Rate/ratio distinction** for statistical metrics
4. **Height/renal** disambiguation for 신장
5. **Korean name formatting** compliance
6. **Symbol-to-word conversion** for regulatory documents
7. **No content addition/omission** enforcement
8. **Split segment handling** for multi-segment sentences

---

## Usage

```python
# Baseline prompts (routine documents)
from phase2.src.style_guide_config import StyleGuideManager, StyleGuideVariant
manager = StyleGuideManager()
style_guide = manager.get_style_guide(StyleGuideVariant.REGULATORY_COMPLIANCE)

# Enhanced prompts (critical regulatory documents)
style_guide = manager.get_style_guide(StyleGuideVariant.REGULATORY_COMPLIANCE_ENHANCED)
```

---

## Customer Feedback Source

- **Project**: Yuhan AD-223P3
- **Documents**: Clinical Protocol, Statistical Analysis Plan (SAP)
- **Reviewers**: 선영, 주연
- **Date**: November 2025
- **Location**: `/Users/won.suh/Downloads/DU-00001_유한_Debriefing_2025-11-22/`
