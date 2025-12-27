# Phase 2 Translation System - Implementation Blueprint

## Overview

This document serves as the master implementation guide for the Phase 2 enhanced translation system. It defines the complete 12-step process that transforms Excel input into contextually-aware, consistent translations using document-level context, Translation Memory, glossaries, and intelligent LLM integration.

## System Architecture Principles

1. **Document-Aware Processing**: Every segment understands the overall document context
2. **Context Accumulation**: Each translation builds context for subsequent segments
3. **Memory-Driven Efficiency**: Prioritize TM and glossary over LLM calls
4. **Consistency Enforcement**: Same terms = same translations throughout document
5. **Quality Through Context**: Rich context enables better translation decisions

## Complete 12-Step Implementation Process

### Step 1: Excel Upload & Text Extraction
**Purpose**: Initial data ingestion and preparation

**Input**:
- Excel file with columns: Segment ID, Source Text, Target Text, Comments
- File path and configuration parameters

**Process**:
1. Parse Excel file using pandas/openpyxl
2. Validate required columns exist
3. Extract all source text segments in sequential order
4. Preserve segment metadata (ID, comments, row numbers)
5. Handle empty/null segments gracefully

**Output**:
```python
segments = [
    {
        "id": 1,
        "source_text": "Inclusion Criteria",
        "original_target": "",
        "comments": "section_header",
        "position": 0
    },
    # ... all segments
]
```

**Context Added**: Complete document text corpus, segment sequence order

### Step 2: Document Context Generator
**Purpose**: Establish document-level understanding for all subsequent processing

**Input**:
- Complete list of source text segments from Step 1
- Document metadata (filename, domain hints)

**Process**:
1. Analyze first 10-20 segments to identify key characteristics
2. Detect document type (clinical protocol, IFU, regulatory, etc.)
3. Extract key terms, protocol numbers, drug names, study phases
4. Identify domain (oncology, cardiology, medical device)
5. Determine style requirements (formal regulatory vs patient-facing)
6. Generate document summary in 1-2 sentences

**Output**:
```python
document_context = {
    "type": "clinical_protocol",
    "domain": "oncology", 
    "study_phase": "Phase II",
    "drug_name": "ABC-123",
    "style": "formal_regulatory",
    "summary": "Phase II oncology clinical trial protocol for investigational drug ABC-123 in advanced solid tumors, regulatory submission format",
    "key_entities": ["ABC-123", "ZE46-0134-0002", "Lomond Therapeutics"]
}
```

**Context Added**: Document-level understanding that informs all subsequent decisions

### Step 3: Translation Memory (TM) Matcher
**Purpose**: Find existing professional translations for reuse

**Input**:
- Current segment text
- Document context profile from Step 2
- Pre-built TM database (extracted from protocol pairs)

**Process**:
1. Search TM database for exact text matches
2. Search for fuzzy matches (70%+ similarity) using semantic similarity
3. Filter matches by document domain/type for relevance
4. Score matches based on: similarity, domain match, recency
5. Select best match with confidence score

**Output**:
```python
tm_result = {
    "match_type": "exact|fuzzy|none",
    "confidence": 0.95,
    "source_match": "Inclusion criteria for study enrollment",
    "target_suggestion": "연구 등록을 위한 선정기준",
    "domain_relevance": "high",
    "original_document": "protocol_ABC123"
}
```

**Context Used**: Document domain to prioritize relevant TM entries

### Step 4: Glossary Term Finder
**Purpose**: Identify terms requiring consistent translation

**Input**:
- Current segment text
- Document context (domain, key entities)
- Glossary databases (24 + 2,794 terms)
- Accumulated term usage history for document

**Process**:
1. Scan segment text for known glossary terms
2. Prioritize domain-relevant terms based on document context
3. Check for term variants and synonyms
4. Verify consistency with previous usage in same document
5. Flag new terms not yet translated in current document

**Output**:
```python
glossary_result = {
    "terms_found": [
        {
            "source_term": "Inclusion Criteria",
            "preferred_translation": "선정기준",
            "domain": "clinical_trials",
            "consistency_status": "established|new|conflict",
            "previous_usage_count": 3
        }
    ],
    "new_terms": ["investigational product"],
    "conflicts": []
}
```

**Context Added**: Term mapping requirements for consistency enforcement

### Step 5: Context Window Builder
**Purpose**: Provide relevant previous translations for continuity and consistency

**Input**:
- Current segment position
- Previous N translations (typically 3-5)
- Document context profile
- Segment importance weighting

**Process**:
1. Collect last 3-5 successfully translated segments
2. Include document context summary in every request
3. Weight context by recency and semantic relevance
4. Ensure context doesn't exceed token limits
5. Format context for optimal LLM understanding

**Output**:
```python
context_window = {
    "document_summary": "Phase II oncology clinical trial...",
    "previous_translations": [
        {
            "source": "3.1 Study Objectives",
            "translation": "3.1 연구 목표",
            "position": -2
        },
        {
            "source": "The primary objective is to evaluate...",
            "translation": "1차 목표는 ... 평가하는 것입니다",
            "position": -1
        }
    ],
    "total_context_tokens": 245
}
```

**Context Added**: Translation continuity and document flow awareness

### Step 6: Translation Decision Router
**Purpose**: Determine optimal translation method based on available resources

**Input**:
- TM match result from Step 3
- Glossary findings from Step 4
- Context window from Step 5
- Document context profile
- System configuration (cost vs quality preferences)

**Process**:
1. Evaluate TM match quality and domain relevance
2. Assess glossary term coverage in segment
3. Consider document consistency requirements
4. Apply decision logic:
   - Exact TM match (95%+ confidence) + same domain → Use TM directly
   - Fuzzy TM match (70-95%) + domain match → Adapt TM
   - No viable TM match → Route to LLM
   - Special cases: Key terms changed → Always verify with LLM

**Output**:
```python
routing_decision = {
    "method": "tm_direct|tm_adapt|llm_translate",
    "confidence": 0.87,
    "reasoning": "Exact TM match from same protocol type",
    "cost_estimate": 0.02,  # In dollars
    "fallback_method": "llm_translate"
}
```

**Decision Matrix**:
| TM Match | Domain Match | Glossary Coverage | Decision |
|----------|--------------|-------------------|----------|
| Exact (95%+) | Same | High | TM Direct |
| Fuzzy (70-95%) | Same | High | TM Adapt |
| Fuzzy (70-95%) | Different | High | LLM |
| None | N/A | Any | LLM |

### Step 7a: TM Translation Processor (TM Route)
**Purpose**: Use or adapt existing professional translations

**Input**:
- TM match result from Step 3
- Current segment text
- Glossary terms from Step 4
- Document context for style verification

**Process**:
1. **Direct TM Use**: For exact matches, verify glossary term consistency
2. **TM Adaptation**: For fuzzy matches, adapt to current segment:
   - Replace outdated terms with current glossary
   - Adjust for slight context differences
   - Maintain professional translation quality
3. Validate result against document style requirements
4. Ensure integration with surrounding context

**Output**:
```python
tm_translation = {
    "translation": "연구 등록을 위한 선정기준",
    "method": "tm_direct",
    "confidence": 0.95,
    "adaptations_made": ["updated term X to Y"],
    "validation_status": "passed"
}
```

**Context Used**: Document style profile, term consistency requirements

### Step 7b: LLM Prompt Builder (LLM Route)
**Purpose**: Construct comprehensive, context-rich prompts for optimal LLM translation

**Input**:
- Current segment text
- Document context profile from Step 2
- Context window from Step 5
- Glossary terms from Step 4
- Translation guidelines (extracted from protocol pairs)

**Process**:
1. Structure prompt with clear sections:
   - Document context and purpose
   - Current segment to translate
   - Previous translation examples
   - Required glossary terms
   - Style and formatting guidelines
2. Include relevant TM examples even if not exact matches
3. Specify consistency requirements
4. Add domain-specific instructions
5. Optimize prompt length to stay within token limits

**Output**:
```python
llm_prompt = {
    "prompt": """
    You are translating a Phase II oncology clinical trial protocol from English to Korean.
    
    Document Context: This is a regulatory submission document for drug ABC-123...
    
    Current segment: "Subjects who meet all of the following criteria are eligible for enrollment:"
    
    Previous translations:
    - "3.1 Inclusion Criteria" → "3.1 선정기준"
    - "Study subjects must satisfy..." → "연구 대상자는 다음을 충족해야..."
    
    Required terms:
    - Subject → 대상자
    - Enrollment → 등록
    - Criteria → 기준
    
    Guidelines:
    - Use formal Korean endings (-습니다)
    - Maintain regulatory tone
    - Preserve list formatting
    
    Translation:
    """,
    "token_count": 245,
    "model_target": "sparrow|eagle"
}
```

**Context Used**: Full document awareness + immediate context + consistency requirements

### Step 8: LLM Translation Engine (LLM Route)
**Purpose**: Generate high-quality translations using contextual LLM calls

**Input**:
- Rich prompt from Step 7b
- Model selection (Sparrow/Eagle based on segment complexity)
- API configuration and rate limiting

**Process**:
1. Select appropriate model based on segment complexity and cost constraints
2. Send prompt to LLM API with appropriate parameters
3. Handle API errors and rate limits gracefully
4. Validate response format and content
5. Extract clean translation from LLM response
6. Record metadata (tokens used, cost, response time)

**Output**:
```python
llm_translation = {
    "translation": "다음 기준을 모두 충족하는 대상자는 등록할 수 있습니다:",
    "model_used": "sparrow",
    "tokens_used": 187,
    "cost": 0.00187,
    "confidence": 0.85,
    "response_time": 1.2,
    "api_status": "success"
}
```

**Context Used**: All accumulated context embedded in prompt

### Step 9: Term Consistency Enforcer
**Purpose**: Ensure glossary terms are translated consistently throughout document

**Input**:
- Translation (from Step 7a or 8)
- Glossary terms identified in Step 4
- Document-wide term usage history
- Document context for validation

**Process**:
1. Scan translation for glossary terms that should be consistent
2. Check against established term usage patterns in current document
3. Flag and fix inconsistencies:
   - Replace inconsistent translations with established ones
   - Update term usage database with new occurrences
4. Verify term usage fits document context and style
5. Handle special cases (plurals, grammatical variations)

**Output**:
```python
enforced_translation = {
    "translation": "다음 기준을 모두 충족하는 대상자는 등록할 수 있습니다:",
    "terms_enforced": [
        {"term": "criteria", "translation": "기준", "action": "confirmed"},
        {"term": "subjects", "translation": "대상자", "action": "enforced"}
    ],
    "consistency_score": 0.98,
    "corrections_made": 1
}
```

**Context Used**: Document-specific term usage patterns

### Step 10: Translation Validator
**Purpose**: Final quality check against document requirements and guidelines

**Input**:
- Term-consistent translation from Step 9
- Document context and style requirements
- Previous translations for flow validation
- Quality guidelines (extracted from protocol pairs)

**Process**:
1. **Style Validation**: Check formal tone, appropriate endings, regulatory language
2. **Flow Validation**: Ensure translation connects well with previous segments
3. **Format Validation**: Preserve numbers, punctuation, list structures
4. **Domain Validation**: Verify translation fits clinical protocol context
5. **Completeness Check**: Ensure no content was dropped or added
6. Apply final corrections if needed

**Output**:
```python
validated_translation = {
    "translation": "다음 기준을 모두 충족하는 대상자는 등록 자격이 있습니다:",
    "quality_score": 0.92,
    "validations": {
        "style": "passed",
        "flow": "passed", 
        "format": "passed",
        "domain": "passed",
        "completeness": "passed"
    },
    "final_corrections": ["adjusted formality level"]
}
```

**Context Used**: Document style profile, translation continuity requirements

### Step 11: Context Updater
**Purpose**: Update system state with new translation for future segments

**Input**:
- Final validated translation from Step 10
- Segment metadata (position, terms used)
- Document context (may need refinement)
- System state (context window, term usage database)

**Process**:
1. Add translation to context window (removing oldest if at limit)
2. Update term usage database with new term occurrences
3. Refine document context understanding if new information learned
4. Update translation statistics and quality metrics
5. Prepare state for next segment processing
6. Log translation metadata for reporting

**Output**:
```python
updated_state = {
    "context_window": [...],  # Updated with new translation
    "term_database": {...},   # Updated with new term usage
    "document_context": {...}, # Refined understanding
    "statistics": {
        "segments_completed": 157,
        "tm_usage": 0.43,
        "avg_confidence": 0.89
    }
}
```

**Context Added**: New translation becomes context for subsequent processing

### Step 12: Output Collector & Excel Generator
**Purpose**: Compile final results with comprehensive quality reporting

**Input**:
- All completed translations with metadata
- Document context and summary
- Quality metrics and statistics
- Original Excel structure

**Process**:
1. Compile all translations maintaining original segment order
2. Generate comprehensive quality report:
   - TM coverage statistics
   - Glossary compliance metrics
   - Consistency scores
   - Cost analysis
   - Processing time breakdown
3. Create final Excel with enhanced columns:
   - Original columns preserved
   - Translation results
   - Confidence scores
   - Method used (TM/LLM)
   - Quality indicators
4. Generate separate detailed report

**Output**:
```excel
Final Excel Columns:
- Segment ID (original)
- Source Text (original)
- Target Text (new - our translation)
- Comments (original)
- Translation Method (TM Direct/TM Adapt/LLM)
- Confidence Score (0.0-1.0)
- Terms Used (glossary terms found)
- Quality Score (0.0-1.0)
```

**Quality Report**:
```python
quality_report = {
    "document_summary": "Phase II oncology clinical trial...",
    "segments_processed": 2690,
    "tm_coverage": {
        "exact_matches": 1156, "percentage": 43.0
    },
    "glossary_compliance": 0.99,
    "consistency_score": 0.98,
    "cost_analysis": {
        "total_cost": 12.47,
        "cost_per_segment": 0.0046,
        "savings_from_tm": 8.23
    },
    "processing_time": "47 minutes",
    "quality_score": 0.94
}
```

## Context Flow Architecture

### Document-Level Context (Persistent Throughout)
```
Document Context = {
    type, domain, style, summary, key_entities
}
↓
Applied to every segment decision
```

### Segment-Level Context (Accumulating)
```
Segment N Processing:
- Current segment text
- Previous 3-5 translations
- Document context
- Term usage history (segments 1 to N-1)
- Applicable TM examples
↓
Rich, contextual translation
↓
Update context for Segment N+1
```

### Memory System Integration Points

**Tier 1 (Valkey - Hot Cache)**:
- Step 4: Cache glossary term lookups
- Step 9: Cache term consistency rules
- Step 11: Cache context window updates

**Tier 2 (Qdrant - Semantic Search)**:
- Step 3: Vector search for TM matches
- Step 7b: Retrieve similar examples for prompts
- Step 10: Validate against quality patterns

**Tier 3 (Mem0 - Adaptive Learning)**:
- Step 2: Learn document type patterns
- Step 10: Learn quality patterns from validation
- Step 12: Store successful patterns for future documents

## Implementation Priority

### Phase 1 (Weeks 1-2): Core Pipeline
1. Steps 1-2: Excel processing + document context
2. Steps 3-6: Basic TM matching + routing
3. Step 12: Basic output generation

### Phase 2 (Weeks 3-4): LLM Integration
1. Steps 7b-8: LLM prompt building + translation
2. Steps 9-10: Consistency + validation
3. Step 11: Context updating

### Phase 3 (Weeks 5-6): Memory Integration
1. Integrate Tier 1 (Valkey) caching
2. Integrate Tier 2 (Qdrant) semantic search
3. Integrate Tier 3 (Mem0) learning

### Phase 4 (Weeks 7-8): Optimization & Testing
1. Performance optimization
2. Quality validation against test data
3. Cost optimization and reporting

This blueprint provides the complete implementation roadmap for building the Phase 2 translation system with document-aware, context-rich processing.