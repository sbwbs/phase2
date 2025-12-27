# Phase 2 MVP Architecture Diagram

## System Architecture Overview

```mermaid
graph TB
    subgraph "User Interface Layer"
        UI[Streamlit UI]
        UPLOAD[File Upload]
        EVAL[Evaluation Interface]
    end

    subgraph "Data Input Layer"
        TEST[Test Data<br/>KO-EN: 1,400 segments]
        GLOSS[Glossary Data<br/>2,794 terms]
        REF[Reference Docs<br/>Protocol pairs]
    end

    subgraph "Core Processing Pipeline"
        LOADER[Data Loader]
        SEGMENT[Segment Processor]
        SEARCH[Glossary Search Engine]
        CONTEXT[Context Builder]
        TRANS[Translation Service]
    end

    subgraph "Memory & Cache Layer"
        VALKEY[(Valkey/Redis<br/>Term Cache)]
        SESSION[Session Manager]
        CONSIST[Consistency Tracker]
    end

    subgraph "LLM Integration"
        GPT5[GPT-5 API<br/>Owl Model]
        PROMPT[Prompt Formatter]
    end

    subgraph "Output & Evaluation"
        RESULT[Translation Result]
        METRICS[Metrics Collector]
        EXPORT[CSV Export]
    end

    %% Data Flow
    UI --> UPLOAD
    UPLOAD --> TEST
    TEST --> LOADER
    GLOSS --> LOADER
    REF --> LOADER
    
    LOADER --> SEGMENT
    SEGMENT --> SEARCH
    SEGMENT --> SESSION
    
    SEARCH --> CONTEXT
    SESSION --> CONSIST
    CONSIST --> CONTEXT
    
    CONTEXT --> PROMPT
    PROMPT --> GPT5
    GPT5 --> TRANS
    
    TRANS --> RESULT
    TRANS --> CONSIST
    RESULT --> EVAL
    RESULT --> METRICS
    METRICS --> EXPORT
    
    %% Cache interactions
    SEARCH -.-> VALKEY
    CONSIST -.-> VALKEY
    SESSION -.-> VALKEY

    style UI fill:#e1f5fe
    style VALKEY fill:#fff3e0
    style GPT5 fill:#f3e5f5
    style CONTEXT fill:#e8f5e9
```

## Detailed Data Flow Diagram

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Streamlit UI
    participant DL as Data Loader
    participant SP as Segment Processor
    participant GS as Glossary Search
    participant VK as Valkey Cache
    participant CB as Context Builder
    participant TM as Translation Memory
    participant LLM as GPT-5 (Owl)
    participant TC as Consistency Tracker
    participant M as Metrics

    U->>UI: Upload test file & glossary
    UI->>DL: Load data files
    DL->>DL: Parse Excel files
    DL->>SP: Send segments for processing
    
    loop For each segment
        SP->>VK: Check session exists
        alt New session
            VK->>VK: Create doc session
        end
        
        SP->>GS: Search relevant glossary terms
        GS->>GS: Keyword matching & ranking
        GS-->>VK: Cache frequent terms
        
        SP->>TC: Get locked terms for doc
        TC->>VK: Retrieve doc:{id}:terms
        VK-->>TC: Return existing terms
        
        SP->>CB: Build smart context
        CB->>CB: Assemble components
        Note over CB: 1. Source text (33 tokens)<br/>2. Relevant glossary (150 tokens)<br/>3. Locked terms (60 tokens)<br/>4. Previous context (40 tokens)<br/>5. Instructions (50 tokens)
        
        CB->>CB: Optimize token usage
        CB->>LLM: Send context (≤500 tokens)
        LLM->>LLM: Process translation
        LLM-->>CB: Return translation
        
        CB->>TC: Store new term mappings
        TC->>VK: Update doc:{id}:terms
        
        CB->>M: Log metrics
        Note over M: Tokens used<br/>Context size<br/>Cache hits<br/>Response time
    end
    
    SP->>UI: Display results
    UI->>U: Show translation & metrics
    U->>UI: Evaluate quality
    UI->>M: Store evaluation
    M->>UI: Generate report
```

## Core Module Architecture

```mermaid
graph LR
    subgraph "1. Data Loader Module"
        DL1[Excel Parser]
        DL2[Data Validator]
        DL3[Batch Generator]
        DL1 --> DL2 --> DL3
    end

    subgraph "2. Glossary Search Module"
        GS1[Term Indexer]
        GS2[Keyword Matcher]
        GS3[Relevance Ranker]
        GS4[Cache Manager]
        GS1 --> GS2 --> GS3 --> GS4
    end

    subgraph "3. Context Builder Module"
        CB1[Component Collector]
        CB2[Token Counter]
        CB3[Priority Selector]
        CB4[Context Optimizer]
        CB1 --> CB2 --> CB3 --> CB4
    end

    subgraph "4. Translation Service Module"
        TS1[Request Handler]
        TS2[Prompt Builder]
        TS3[API Client]
        TS4[Response Parser]
        TS1 --> TS2 --> TS3 --> TS4
    end

    subgraph "5. Consistency Tracker Module"
        CT1[Term Extractor]
        CT2[Mapping Store]
        CT3[Conflict Resolver]
        CT4[Lock Manager]
        CT1 --> CT2 --> CT3 --> CT4
    end
```

## Pattern Recognition & Matching Flow

```mermaid
graph TD
    subgraph "Pattern Recognition Pipeline"
        INPUT[Source Segment]
        
        subgraph "Term Detection"
            TD1[Named Entity Recognition]
            TD2[Medical Term Detection]
            TD3[Acronym Identification]
        end
        
        subgraph "Pattern Matching"
            PM1[Exact Match Search]
            PM2[Fuzzy Match Search]
            PM3[Partial Match Search]
        end
        
        subgraph "Translation Patterns"
            TP1[Previously Translated Terms]
            TP2[Glossary Matches]
            TP3[Session Consistency Rules]
        end
        
        OUTPUT[Matched Patterns]
    end
    
    INPUT --> TD1 & TD2 & TD3
    TD1 & TD2 & TD3 --> PM1
    PM1 --> PM2 --> PM3
    PM1 & PM2 & PM3 --> TP1 & TP2 & TP3
    TP1 & TP2 & TP3 --> OUTPUT
```

## Context Assembly Pipeline

```mermaid
flowchart TD
    START([New Segment]) --> EXTRACT[Extract Key Terms]
    
    EXTRACT --> SEARCH{Search Glossary}
    SEARCH -->|Found| RANK[Rank by Relevance]
    SEARCH -->|Not Found| SKIP1[Skip Glossary]
    
    RANK --> FILTER[Filter Top 10 Terms]
    FILTER --> CHECK_CACHE{Check Valkey Cache}
    
    CHECK_CACHE -->|Hit| USE_CACHED[Use Cached Terms]
    CHECK_CACHE -->|Miss| GET_LOCKED[Get Session Terms]
    
    USE_CACHED --> ASSEMBLE
    GET_LOCKED --> ASSEMBLE[Assemble Context]
    SKIP1 --> ASSEMBLE
    
    ASSEMBLE --> COUNT{Count Tokens}
    COUNT -->|< 500| FORMAT[Format Prompt]
    COUNT -->|> 500| REDUCE[Reduce Context]
    
    REDUCE --> PRIORITIZE[Prioritize Terms]
    PRIORITIZE --> COUNT
    
    FORMAT --> SEND[Send to GPT-5]
    SEND --> RESPONSE[Get Translation]
    
    RESPONSE --> EXTRACT_PAIRS[Extract Term Pairs]
    EXTRACT_PAIRS --> STORE[Store in Valkey]
    STORE --> UPDATE[Update Consistency]
    UPDATE --> END([Translation Complete])
```

## Memory Management Architecture

```mermaid
graph TB
    subgraph "Valkey/Redis Cache Structure"
        subgraph "Document Sessions"
            DS1[doc:123:metadata]
            DS2[doc:123:terms]
            DS3[doc:123:segments]
        end
        
        subgraph "Term Consistency"
            TC1[term:source->target]
            TC2[lock:123:term]
            TC3[freq:123:term]
        end
        
        subgraph "Cache Optimization"
            CO1[glossary:cache]
            CO2[pattern:cache]
            CO3[context:cache]
        end
    end
    
    subgraph "Access Patterns"
        AP1[O(1) Term Lookup]
        AP2[Session Scoped]
        AP3[TTL Management]
    end
    
    DS2 --> TC1
    TC1 --> TC2
    TC2 --> TC3
    
    AP1 --> DS2
    AP2 --> DS1
    AP3 --> DS3
```

## Translation Consolidation Flow

```mermaid
flowchart LR
    subgraph "Input Processing"
        S1[Segment 1]
        S2[Segment 2]
        S3[Segment N]
    end
    
    subgraph "Translation Pipeline"
        T1[Translate]
        T2[Validate]
        T3[Consolidate]
    end
    
    subgraph "Consistency Layer"
        C1[Term Tracking]
        C2[Pattern Learning]
        C3[Conflict Resolution]
    end
    
    subgraph "Final Output"
        O1[Translated Segments]
        O2[Consistency Report]
        O3[Quality Metrics]
    end
    
    S1 & S2 & S3 --> T1
    T1 --> C1
    C1 --> T2
    T2 --> C2
    C2 --> T3
    T3 --> C3
    C3 --> O1 & O2 & O3
```

## Performance Metrics Flow

```mermaid
graph TD
    subgraph "Metrics Collection Points"
        M1[Context Building Time]
        M2[Token Usage]
        M3[Cache Hit Rate]
        M4[Translation Time]
        M5[Total Pipeline Time]
    end
    
    subgraph "Aggregation"
        A1[Per Segment Metrics]
        A2[Per Document Metrics]
        A3[Session Metrics]
    end
    
    subgraph "Reporting"
        R1[Real-time Dashboard]
        R2[Batch Report]
        R3[Comparison Analysis]
    end
    
    M1 & M2 & M3 & M4 & M5 --> A1
    A1 --> A2 --> A3
    A3 --> R1 & R2 & R3
```

## Error Handling & Recovery

```mermaid
stateDiagram-v2
    [*] --> LoadData
    LoadData --> ProcessSegment
    ProcessSegment --> SearchGlossary
    
    SearchGlossary --> BuildContext: Terms Found
    SearchGlossary --> MinimalContext: No Terms
    
    BuildContext --> CheckTokens
    CheckTokens --> Translate: ≤500 tokens
    CheckTokens --> ReduceContext: >500 tokens
    ReduceContext --> CheckTokens
    
    Translate --> StoreResults: Success
    Translate --> Retry: API Error
    Retry --> Translate: Attempt < 3
    Retry --> Fallback: Attempt ≥ 3
    
    Fallback --> ManualReview
    MinimalContext --> Translate
    StoreResults --> [*]
    ManualReview --> [*]
```

## Component Interaction Matrix

| Component | Data Loader | Glossary Search | Context Builder | Translation | Valkey | Metrics |
|-----------|------------|-----------------|-----------------|-------------|---------|---------|
| **Data Loader** | - | Provides glossary | Sends segments | - | - | Log load time |
| **Glossary Search** | Receives glossary | - | Returns matches | - | Cache results | Hit/miss rate |
| **Context Builder** | Receives segments | Requests terms | - | Sends context | Get cached terms | Context size |
| **Translation** | - | - | Receives context | - | Store translations | Token usage |
| **Valkey** | - | Provides cache | Provides terms | Stores results | - | Cache metrics |
| **Metrics** | Track performance | Track efficiency | Track optimization | Track quality | Track cache | - |

## Key Design Decisions

### 1. Modular Architecture
- Each module has single responsibility
- Clear interfaces between components
- Easy to test and debug individually
- Can swap implementations (e.g., different search algorithms)

### 2. Cache-First Design
- Check Valkey before expensive operations
- Cache glossary searches
- Store term mappings for consistency
- Session-based isolation

### 3. Token Optimization Priority
- Count tokens at each step
- Prioritize high-value terms
- Dynamic context adjustment
- Fallback strategies for edge cases

### 4. Stream Processing
- Process segments sequentially
- Build consistency incrementally
- Learn patterns during translation
- Real-time metrics collection

### 5. Fail-Safe Mechanisms
- Graceful degradation on cache miss
- API retry with exponential backoff
- Fallback to minimal context
- Manual review queue for failures