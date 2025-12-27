# Phase 2 Production Pipeline - Detailed Flow Analysis

## Overview
The production pipeline (`production_pipeline_working.py`) processes Korean clinical study protocol text through a sophisticated translation system with memory management, glossary integration, and batch processing.

## 🔄 Complete Pipeline Flow: Input → Output

### 📥 **STAGE 1: INITIALIZATION**

#### 1.1 Pipeline Setup
```python
pipeline = WorkingPhase2Pipeline(use_valkey=True)
```

**What happens:**
1. **Logging Setup**: Creates log file at `/phase2/logs/working_phase2_TIMESTAMP.log`
2. **OpenAI Client**: Initializes GPT-5 OWL client
3. **Glossary Loading**: Loads 2906 terms from Excel files
   - Coding Form: 2527 medical terms
   - Clinical Trials: 379 clinical trial terms
4. **Storage Initialization**:
   - **IF Valkey Available**: 
     - Connects to Valkey server (localhost:6379)
     - Creates session with 24-hour TTL
     - Session ID: `working_phase2_YYYYMMDD_HHMMSS`
   - **ELSE (Fallback)**:
     - Uses Python dict: `self.locked_terms = {}`

**Storage at this stage:**
- **Valkey**: Empty session created, no terms yet
- **Memory**: Glossary terms (2906) loaded in memory, empty locked_terms dict

---

### 📊 **STAGE 2: DATA LOADING**

#### 2.1 Excel Data Import
```python
df = pd.read_excel("1_테스트용_Generated_Preview_KO-EN.xlsx")
```

**What happens:**
1. Reads Korean source text from Excel
2. Extracts reference translations (if available)
3. Creates segment list with IDs

**Example Input Row:**
```
Segment_ID: 1
Korean: "본 임상시험은 의뢰자가 주관하는 다기관, 무작위배정, 공개 임상시험입니다."
Reference_EN: "This clinical trial is a multicenter, randomized, open-label clinical trial sponsored by the sponsor."
```

**Storage at this stage:**
- **Valkey**: Still empty (no processing yet)
- **Memory**: Input data loaded as pandas DataFrame

---

### 🔍 **STAGE 3: GLOSSARY SEARCH** (Per Segment/Batch)

#### 3.1 Term Matching
```python
glossary_terms = self.search_glossary_terms(korean_text)
```

**What happens:**
1. **Exact Match Search**: Scans Korean text for exact glossary matches
2. **Fuzzy Match**: Finds partial matches (>80% similarity)
3. **Returns**: List of found terms with metadata

**Example Glossary Match:**
```python
Input: "본 임상시험은..."
Found Terms: [
    {
        'korean': '임상시험',
        'english': 'clinical trial',
        'source': 'Clinical Trials',
        'match_type': 'exact',
        'score': 1.0
    },
    {
        'korean': '의뢰자',
        'english': 'sponsor',
        'source': 'Clinical Trials',
        'match_type': 'exact',
        'score': 1.0
    }
]
```

**Storage:**
- **Valkey**: No changes yet
- **Memory**: Found glossary terms temporarily stored

---

### 🧠 **STAGE 4: CONTEXT BUILDING**

#### 4.1 Smart Context Generation (Individual)
```python
context = self.build_smart_context(korean_text, glossary_terms, idx)
```

**For Batch Processing:**
```python
context = self.build_batch_smart_context(batch_texts, all_glossary_terms)
```

**Context Components (in order):**

1. **Component 1: Relevant Glossary Terms** (~100-200 tokens)
   ```
   ## Relevant Terminology
   - 임상시험: clinical trial (Clinical Trials)
   - 의뢰자: sponsor (Clinical Trials)
   - 무작위배정: randomized/randomization (Clinical Trials)
   ```

2. **Component 2: Session Memory / Locked Terms** (~50-100 tokens)
   ```
   ## Locked Terms (Maintain Consistency)
   - 시험대상자: subject  [from previous segment]
   - 연구자: investigator  [from previous segment]
   ```
   - **Source**: Retrieved from Valkey or in-memory dict
   - **Purpose**: Ensures consistent translation across document

3. **Component 3: Previous Context** (~100-150 tokens)
   ```
   ## Previous Context
   Segment 14: "시험대상자는 서면 동의서를..." → "The subject must provide written informed consent..."
   ```
   - **Source**: Last 2-3 translations from memory
   - **Purpose**: Maintains narrative flow

**Total Context Size**: ~413 tokens (98% reduction from loading all 2906 terms)

**Storage at this stage:**
- **Valkey**: Locked terms being read (if any exist)
- **Memory**: Context string built and ready

---

### 🤖 **STAGE 5: LLM TRANSLATION**

#### 5.1 Prompt Construction
```python
prompt = self._create_clinical_prompt(korean_text, context)
```

**Full Prompt Structure:**
```
You are a medical translator specializing in clinical study protocols.
Translate this Korean clinical trial text to English following ICH GCP guidelines.

## Context and Terminology
[Smart context from Stage 4]

## Korean Text to Translate
본 임상시험은 의뢰자가 주관하는 다기관, 무작위배정, 공개 임상시험입니다.

## Requirements
1. Use "clinical trial" not "clinical study"
2. Use "subject" not "patient"
3. Maintain regulatory compliance
4. Use provided glossary terms consistently

Translate:
```

#### 5.2 API Call (Batch Mode)
```python
# Batch of 5 segments sent together
response = self.client.responses.create(
    model="gpt-5",
    input=[{"role": "user", "content": batch_prompt}],
    text={"verbosity": "medium"},
    reasoning={"effort": "minimal"}
)
```

**API Response Processing:**
1. Extract text from GPT-5 Responses API format
2. Parse batch response into individual translations
3. Handle any errors with fallback to GPT-4o

---

### 💾 **STAGE 6: SESSION MEMORY UPDATE**

#### 6.1 Term Locking
```python
self.update_session_memory(korean_text, translation, glossary_terms)
```

**What gets stored:**

**In Valkey (Persistent):**
```python
# Term mappings stored as hash
"doc_terms:working_phase2_20250816_163046": {
    "임상시험": {"target": "clinical trial", "confidence": 1.0},
    "의뢰자": {"target": "sponsor", "confidence": 1.0},
    "시험대상자": {"target": "subject", "confidence": 1.0}
}

# Session metadata
"session:working_phase2_20250816_163046": {
    "processed_segments": 280,
    "term_count": 137,
    "status": "active"
}
```

**In Memory (Temporary):**
```python
self.previous_translations = [
    {"korean": "본 임상시험은...", "english": "This clinical trial is..."},
    # Last 5 translations kept
]

self.session_context = [
    # Processing metadata
]
```

**Persistence Frequency:**
- Every 10 segments: Full session state saved to Valkey
- On completion: Final state saved and connection closed

---

### 📊 **STAGE 7: RESULTS COMPILATION**

#### 7.1 Result Object Creation
```python
WorkingTranslationResult(
    segment_id=1,
    source_text="본 임상시험은...",
    translated_text="This clinical trial is...",
    glossary_terms_found=4,
    glossary_terms_used=[...],
    total_tokens=523,
    total_cost=0.0367,
    processing_time=1.2
)
```

---

### 💾 **STAGE 8: EXCEL OUTPUT GENERATION**

#### 8.1 Multi-Sheet Excel Creation
```python
self.save_results_to_excel(results, output_file)
```

**Sheet 1: Translation_Results**
```
| Segment_ID | Korean_Source | English_Translation | Glossary_Terms | Cost |
|------------|---------------|-------------------|----------------|------|
| 1          | 본 임상시험은... | This clinical... | 4              | 0.037|
```

**Sheet 2: Glossary_Terms_Used**
```
| Segment_ID | Term_Korean | Term_English | Source | Match_Type |
|------------|-------------|--------------|--------|------------|
| 1          | 임상시험     | clinical trial| Clinical Trials | exact |
```

**Sheet 3: Pipeline_Details**
```
| Segment | Step | Input | Output | Tokens | Time |
|---------|------|-------|--------|--------|------|
| 1       | Glossary Search | 본 임상... | 4 terms found | 0 | 0.05s |
```

**Sheet 4: Working_Phase2_Summary**
```
Total Segments: 1400
Successful: 1395
Average Glossary Terms: 5.3
Session Terms Learned: 137
Total Cost: $51.20
```

---

## 📈 **Storage Summary by Component**

### **Valkey (Persistent - 24hr TTL)**
- ✅ Locked term mappings (Korean → English)
- ✅ Session metadata (counts, status)
- ✅ Term confidence scores
- ✅ Processing timestamps

### **In-Memory (Session Only)**
- ✅ Full glossary (2906 terms)
- ✅ Previous translations (last 5)
- ✅ Current batch data
- ✅ Pipeline configuration
- ✅ Temporary processing buffers

### **Not Stored (Computed Each Time)**
- ❌ Smart context (rebuilt per segment)
- ❌ Prompts (generated dynamically)
- ❌ Intermediate search results

---

## 🚀 **Performance Optimizations**

1. **Batch Processing**: 5 segments → 1 API call (80% reduction)
2. **Smart Context**: 413 tokens vs 20,473 (98% reduction)
3. **Valkey Caching**: O(1) term lookups vs O(n) search
4. **Session Persistence**: Terms survive across runs
5. **Lazy Loading**: Context built only with relevant terms

---

## 🔄 **Failure Handling**

### **Valkey Unavailable**
- Automatic fallback to in-memory dict
- No data loss during session
- Warning logged, processing continues

### **API Errors**
- GPT-5 failure → GPT-4o fallback
- Rate limiting → Exponential backoff
- Batch failure → Individual processing

### **Data Issues**
- Missing glossary → Continue with empty
- Malformed input → Skip segment, log error
- Excel issues → Validate and report

---

## 📊 **Metrics for 1400 Segments**

| Metric | Value |
|--------|-------|
| Total Processing Time | 15.5 minutes |
| API Calls | 280 (vs 1400) |
| Tokens Used | 170,905 |
| Total Cost | $51.20 |
| Average Cost/Segment | $0.0367 |
| Glossary Terms Found | 5.3 per segment |
| Locked Terms in Valkey | 137 unique |
| Success Rate | 99.6% |

---

## 🎯 **Key Insights**

1. **Valkey's Role**: Maintains translation consistency across entire document by storing verified term pairs
2. **Context Window**: Only ~2% of available context used, highly optimized
3. **Batch Efficiency**: 80% fewer API calls while maintaining quality
4. **Memory Hierarchy**: Hot data in memory, persistent terms in Valkey
5. **Clinical Compliance**: ICH GCP terminology enforced throughout