# Step-by-Step Translation Pipeline: Excel to Final Output

## Overview
Starting with an Excel file containing segments to translate, the system processes each segment using TM, Glossary, Guidelines, and maintains document context throughout.

## Detailed Pipeline Flow

```mermaid
graph TB
    %% Input Stage
    subgraph "1. Input Processing"
        EX[Excel File<br/>Segment ID | Source | Target | Comments]
        EX --> DP[Document Parser]
        DP --> DS[Document Structure<br/>• Segments in order<br/>• Section markers<br/>• Metadata]
    end

    %% Initialization Stage
    subgraph "2. Context Initialization"
        DS --> CI[Context Initializer]
        CI --> DC[Document Context<br/>• Document type<br/>• Subject domain<br/>• Style profile]
        CI --> TC[Translation Context<br/>• Previous segments<br/>• Term usage history<br/>• Consistency tracker]
    end

    %% Memory Loading
    subgraph "3. Memory Systems Loading"
        TM[(Translation Memory<br/>40-50% coverage)]
        GL[(Glossary<br/>2,818 terms)]
        SG[(System Guidelines<br/>Patterns & Rules)]
        
        TM --> ML[Memory Loader]
        GL --> ML
        SG --> ML
        ML --> IM[Indexed Memory<br/>Ready for lookup]
    end

    %% Segment Processing Loop
    subgraph "4. Segment-by-Segment Processing"
        DS --> |"For each segment"| SP[Segment Processor]
        
        %% Context Window
        SP --> CW[Context Window<br/>• Current segment<br/>• Previous 3-5 segments<br/>• Next 1-2 segments]
        
        %% TM Matching
        CW --> TMM[TM Matcher]
        TMM --> |"Exact match?"| TM1[Use TM Translation<br/>100% confidence]
        TMM --> |"Fuzzy match?"| TM2[Adapt TM Translation<br/>70-90% confidence]
        TMM --> |"No match?"| LLM[LLM Processing]
        
        %% Glossary Application
        CW --> GLM[Glossary Matcher]
        GLM --> |"Term found"| GLA[Apply Term<br/>Enforce consistency]
        
        %% Guidelines Application
        CW --> GDL[Guideline Engine]
        GDL --> |"Pattern match"| GDA[Apply Rules<br/>• Format preservation<br/>• Style consistency]
    end

    %% LLM Processing
    subgraph "5. LLM Translation (When Needed)"
        LLM --> PC[Prompt Constructor]
        PC --> |"Include:"| PR[Rich Prompt<br/>• Segment to translate<br/>• Previous translations<br/>• Relevant TM examples<br/>• Applicable glossary<br/>• Style guidelines<br/>• Document context]
        PR --> LLME[LLM Engine<br/>Sparrow/Eagle]
        LLME --> RT[Raw Translation]
    end

    %% Post-Processing
    subgraph "6. Post-Processing & Validation"
        TM1 --> PP[Post-Processor]
        TM2 --> PP
        RT --> PP
        GLA --> PP
        GDA --> PP
        
        PP --> CV[Consistency Validator<br/>• Term consistency<br/>• Format compliance<br/>• Style adherence]
        
        CV --> |"Issues found"| CF[Correction & Feedback]
        CF --> PP
        CV --> |"Validated"| FT[Final Translation]
    end

    %% Context Update
    subgraph "7. Context Update"
        FT --> CU[Context Updater]
        CU --> |"Update"| TC2[Translation Context<br/>• Add to history<br/>• Update term usage<br/>• Learn patterns]
        TC2 --> |"Next segment"| SP
    end

    %% Output Stage
    subgraph "8. Output Generation"
        FT --> OC[Output Collector]
        OC --> |"All segments done"| FE[Final Excel<br/>with translations]
        OC --> QR[Quality Report<br/>• TM usage stats<br/>• Consistency scores<br/>• Confidence levels]
    end
```

## Detailed Step Breakdown

### Step 1: Input Processing
```python
# Load Excel file
segments = load_excel("test_segments.xlsx")
# Structure: [
#   {id: 1, source: "Inclusion Criteria", target: "", context: "section_header"},
#   {id: 2, source: "Subjects must be ≥18 years", target: "", context: "bullet_point"}
# ]
```

### Step 2: Context Initialization
```python
document_context = {
    "type": "clinical_protocol",
    "domain": "oncology",
    "style": "formal_regulatory",
    "language_pair": "EN-KO"
}

translation_context = {
    "previous_segments": [],
    "term_usage": {},  # {"Inclusion Criteria": "선정기준"}
    "consistency_rules": []
}
```

### Step 3: Memory Loading
```python
# Load pre-extracted TM from protocol pairs
tm_database = load_tm("protocol_tm.db")  # 40-50% coverage

# Load glossaries
glossary = load_glossary([
    "clinical_terms.xlsx",     # 2,818 terms
    "regulatory_terms.xlsx"    # Additional domain terms
])

# Load guidelines extracted from paired protocols
guidelines = load_guidelines("clinical_protocol_rules.yaml")
# Rules like:
# - Keep protocol numbers unchanged
# - Use -습니다 endings
# - Preserve table structures
```

### Step 4: Segment Processing (Core Loop)
```python
for segment in segments:
    # A. Build context window
    context_window = {
        "current": segment,
        "previous": get_previous_segments(3-5),
        "next": get_next_segments(1-2)
    }
    
    # B. Try TM matching first (cheapest)
    tm_match = search_tm(segment.source, context_window)
    if tm_match.exact:
        translation = tm_match.translation
        confidence = 1.0
    elif tm_match.fuzzy:
        translation = adapt_fuzzy_match(tm_match, context_window)
        confidence = tm_match.score
    else:
        # C. Build LLM prompt with all context
        prompt = build_prompt(
            segment=segment,
            previous_translations=get_recent_translations(5),
            similar_tm_examples=get_similar_tm(3),
            relevant_glossary=extract_relevant_terms(segment),
            guidelines=get_applicable_rules(segment),
            document_context=document_context
        )
        translation = llm_translate(prompt)
        confidence = 0.8
    
    # D. Apply glossary enforcement
    translation = enforce_glossary_terms(translation, glossary)
    
    # E. Validate consistency
    translation = validate_consistency(translation, translation_context)
    
    # F. Update context for next segment
    translation_context["previous_segments"].append({
        "source": segment.source,
        "translation": translation
    })
    update_term_usage(translation_context, segment, translation)
```

### Step 5: Context-Aware Prompt Example
```
Translate this clinical protocol segment from English to Korean.

Current segment: "Subjects who meet all of the following criteria are eligible for enrollment:"

Previous context:
- "3.1 Inclusion Criteria" → "3.1 선정기준"
- "The following criteria must be met for subject enrollment" → "대상자 등록을 위해 다음 기준을 충족해야 합니다"

Similar TM examples:
- "Patients who meet the following criteria" → "다음 기준을 충족하는 환자"
- "Subjects meeting all criteria below" → "아래 모든 기준을 충족하는 대상자"

Relevant glossary:
- Subject → 대상자
- Enrollment → 등록
- Criteria → 기준

Guidelines:
- Use formal endings (-습니다)
- Maintain consistent terminology throughout
- This appears to be introducing a list - preserve the colon

Translation:
```

### Step 6: Consistency Validation
```python
def validate_consistency(translation, context):
    # Check term consistency
    for term, standard_translation in context["term_usage"].items():
        if term in segment.source:
            if standard_translation not in translation:
                # Flag: Same term translated differently
                translation = apply_consistency_fix(translation, term, standard_translation)
    
    # Check style consistency
    if not matches_style_pattern(translation, context["style"]):
        translation = adjust_style(translation)
    
    return translation
```

### Step 7: Output Generation
```python
# Final Excel includes:
output_excel = {
    "Segment ID": segment.id,
    "Source text": segment.source,
    "Target text": translation,
    "Confidence": confidence,
    "TM Match": tm_match_type,  # "exact", "fuzzy", "none"
    "Glossary terms": used_glossary_terms,
    "Context used": previous_segments_referenced
}

# Quality metrics
quality_report = {
    "tm_coverage": "45%",
    "exact_matches": 156,
    "fuzzy_matches": 89,
    "llm_translations": 45,
    "consistency_score": 0.98,
    "glossary_compliance": 0.99
}
```

## Key Principles

1. **Never Translate in Isolation**: Every segment sees previous/next context
2. **TM First**: Always check TM before expensive LLM calls
3. **Consistency Enforcement**: Same term = same translation throughout
4. **Progressive Context**: Each translation enriches context for next segment
5. **Validation Loop**: Catch and fix inconsistencies immediately

## Expected Performance

For a 100-segment clinical protocol:
- **TM exact matches**: 40-45 segments (0 LLM cost)
- **TM fuzzy matches**: 20-25 segments (minimal LLM cost)
- **Glossary/Guidelines**: 25-30 segments (reduced LLM cost)
- **Full LLM translation**: 5-10 segments only

**Result**: 90-95% cost reduction while maintaining higher quality through consistency!