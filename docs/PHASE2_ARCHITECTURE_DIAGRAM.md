# Phase 2 Translation System Architecture

## Complete System Flow: From Test Data to Translation

```mermaid
graph TB
    %% Input Layer
    subgraph "Input Sources"
        TD[Test Data<br/>4,090 segments]
        GL1[EN-KO Glossary<br/>24 terms]
        GL2[KO-EN Glossaries<br/>2,794 terms]
        REF[Reference Docs<br/>Original + Translated]
    end

    %% Pattern Extraction Pipeline
    subgraph "Pattern Extraction Pipeline"
        PE[Pattern Extractor]
        PE --> FP[Formatting Patterns<br/>• Numbers/Codes<br/>• Lists/Bullets<br/>• Headers]
        PE --> TP[Terminology Patterns<br/>• Consistent terms<br/>• Domain vocabulary<br/>• Mixed language]
        PE --> SP[Style Patterns<br/>• Formality level<br/>• Sentence structure<br/>• Regulatory tone]
    end

    %% Guideline Generation
    subgraph "Guideline Generation"
        GG[Guideline Generator]
        GG --> PRG[Prompt Rules<br/>• Consistency requirements<br/>• Formality markers<br/>• Preservation rules]
        GG --> TRG[Term Rules<br/>• Glossary mappings<br/>• Frequency analysis<br/>• Context patterns]
    end

    %% Three-Tier Memory System
    subgraph "Three-Tier Memory Architecture"
        T1[Tier 1: Valkey<br/>Hot Cache]
        T1 --> SC[Session Consistency<br/>• Term tracking<br/>• Recent translations<br/>• Active glossary]
        
        T2[Tier 2: Qdrant<br/>Semantic Search]
        T2 --> VS[Vector Store<br/>• Embedded examples<br/>• Similar segments<br/>• Context retrieval]
        
        T3[Tier 3: Mem0<br/>Adaptive Learning]
        T3 --> AL[Learning Layer<br/>• Style patterns<br/>• Rule evolution<br/>• Quality feedback]
    end

    %% Orchestration Layer
    subgraph "Orchestrated Pipeline"
        ORC[Orchestrator]
        ORC --> CTX[Context Builder<br/>• Select relevant terms<br/>• Retrieve examples<br/>• Build prompt]
        ORC --> TRN[Translation Engine<br/>• Apply guidelines<br/>• Enforce consistency<br/>• Generate output]
        ORC --> VAL[Validator<br/>• Check glossary<br/>• Verify formatting<br/>• Consistency check]
    end

    %% Output Layer
    subgraph "Output"
        TRANS[Final Translation<br/>with consistency tracking]
        META[Metadata<br/>• Terms used<br/>• Confidence scores<br/>• Pattern matches]
    end

    %% Flow connections
    TD --> PE
    GL1 --> PE
    GL2 --> PE
    REF --> PE
    
    FP --> GG
    TP --> GG
    SP --> GG
    
    PRG --> T3
    TRG --> T1
    TRG --> T2
    
    SC --> CTX
    VS --> CTX
    AL --> CTX
    
    CTX --> TRN
    TRN --> VAL
    VAL --> TRANS
    VAL --> META
    
    %% Feedback loop
    TRANS -.-> T3
    META -.-> T3

    %% Styling
    classDef input fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef memory fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef process fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef output fill:#fff3e0,stroke:#e65100,stroke-width:2px
    
    class TD,GL1,GL2,REF input
    class T1,T2,T3,SC,VS,AL memory
    class PE,FP,TP,SP,GG,PRG,TRG,ORC,CTX,TRN,VAL process
    class TRANS,META output
```

## Architecture Components

### 1. Input Processing
- **Test Data**: 4,090 segments serve as both test and reference
- **Glossaries**: Asymmetric (24 vs 2,794 terms) requiring different strategies
- **Reference Docs**: Full documents for context understanding

### 2. Pattern Extraction (Initialization Phase)
- **Formatting Patterns**: How numbers, lists, headers are preserved
- **Terminology Patterns**: Common terms and their consistent translations
- **Style Patterns**: Formality levels, sentence structures, regulatory tone

### 3. Guideline Generation
- **Prompt Rules**: System instructions derived from patterns
- **Term Rules**: Glossary mappings with frequency weights

### 4. Three-Tier Memory System
- **Tier 1 (Valkey)**: Fast lookup for current session consistency
- **Tier 2 (Qdrant)**: Semantic search for similar examples
- **Tier 3 (Mem0)**: Long-term pattern learning and adaptation

### 5. Orchestrated Pipeline
- **Context Builder**: Intelligently selects relevant information
- **Translation Engine**: Applies all rules and guidelines
- **Validator**: Ensures consistency and compliance

### 6. Feedback Loop
- Results feed back into Mem0 for continuous improvement
- Metadata tracks which patterns and terms were used

## Key Design Principles

1. **No TM Available**: Test data becomes the implicit translation memory
2. **Asymmetric Glossaries**: EN-KO (24 terms) vs KO-EN (2,794 terms) need different handling
3. **Pattern-Driven**: Extract and apply patterns rather than loading everything
4. **Consistency First**: Track and enforce term consistency within documents
5. **Regulatory Compliance**: Formal tone and exact terminology required