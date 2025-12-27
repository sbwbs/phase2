# Translation Patterns & Guidelines for System Prompt

## Core Insights from Phase 2 Test Data Analysis

### 1. **Document Type Context**
- **Clinical Trial Protocols**: Formal regulatory documents requiring precise, consistent terminology
- **NOT medical device manuals**: Different style and terminology from Phase 1

### 2. **Key Translation Rules to Enforce**

#### A. Preserve Original Formatting
- **Protocol numbers**: Keep unchanged (e.g., "ZE46-0134-0002-US")
- **Company names**: Maintain in English (e.g., "Lomond Therapeutics, LLC")
- **List structures**: Preserve numbering, bullets, and indentation
- **Headers/Titles**: Maintain capitalization patterns

#### B. Terminology Consistency (Critical without TM)
- **"Protocol"** → "임상시험계획서" (EN→KO)
- **"Study"** → "임상시험" (EN→KO)
- **"Investigator"** → "시험자" (EN→KO)
- **"Subject"** → "대상자" (EN→KO)
- Mixed terminology: English terms often retained in Korean text (e.g., "Protocol No.")

#### C. Style Guidelines
- **Formality**: Use formal Korean endings (-습니다, -입니다) for regulatory documents
- **Passive voice**: Common in clinical protocols
- **Technical precision**: No paraphrasing or simplification
- **Regulatory compliance**: Exact translation required, no creative interpretation

### 3. **System Prompt Additions**

```
You are translating clinical trial protocol documents. These are formal regulatory documents requiring:

1. CONSISTENCY: Use the exact same translation for repeated terms throughout the document
2. FORMALITY: Use formal language appropriate for regulatory submission
3. PRESERVATION: Keep all numbers, codes, company names, and formatting exactly as in source
4. PRECISION: Do not paraphrase or simplify technical/medical terms
5. GLOSSARY ADHERENCE: When provided glossary terms exist, use them exactly

For EN→KO: Use formal endings (-습니다, -입니다), preserve English proper nouns
For KO→EN: Maintain clinical trial terminology standards, preserve Korean regulatory terms when no English equivalent exists
```

### 4. **Memory System Requirements**

Since we have no TM, the memory system must:

1. **Learn from examples**: Extract patterns from the 4,090 test segments
2. **Track consistency**: Remember translations within document session
3. **Build dynamic TM**: Create TM-like memory from the test data itself
4. **Apply style rules**: Enforce formal tone and regulatory compliance

### 5. **Critical Difference from Phase 1**

Phase 1 had:
- Small dataset (49 segments)
- Existing TM (304 entries)
- Medical device domain

Phase 2 has:
- Large dataset (4,090 segments) that IS the reference
- No TM - must infer from examples
- Clinical trial domain with stricter regulatory requirements

## Recommendation

The test data itself becomes our "implicit TM" - we should:
1. Pre-process all 4,090 segments to extract common patterns
2. Build a consistency database during initialization
3. Use Tier 3 (Mem0) to learn style patterns from the examples
4. Apply these learned patterns during translation

This approach turns the challenge of "no TM" into an opportunity for adaptive learning.