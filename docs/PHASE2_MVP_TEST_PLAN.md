# Phase 2 MVP Test Plan: Smart Context Building with Redis/Valkey

## Executive Summary

This MVP test plan focuses on validating the core hypothesis of Phase 2: **Smart context building can achieve 90%+ token reduction while maintaining translation quality**. The MVP will implement a minimal but functional system using Valkey (Redis fork) for term consistency, basic glossary search, and GPT-5 family models for translation.

## MVP Objectives

### Primary Goals
1. **Validate Token Reduction**: Prove 90%+ reduction vs loading all glossary/TM
2. **Test Context Building**: Validate smart context assembly approach
3. **Assess Translation Quality**: Ensure quality matches or exceeds Phase 1
4. **Evaluate Feasibility**: Confirm technical approach is viable for full implementation

### Non-Goals (Out of Scope for MVP)
- Full three-tier memory system (only Tier 1 Valkey)
- Semantic search with Qdrant (manual relevance filtering)
- Adaptive learning with Mem0
- Production-ready performance
- Complete error handling

## Architecture Overview

### MVP System Components

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Streamlit  │────►│Context       │────►│   Valkey    │
│     UI      │     │Builder       │     │   Cache     │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼───────┐
                    │ GPT-5 Family │
                    │   (Owl)      │
                    └──────────────┘
```

### Key Differences from Phase 1

| Component | Phase 1 | Phase 2 MVP |
|-----------|---------|-------------|
| **Context Loading** | All TM + All Glossary | Smart selection only |
| **Memory** | None (stateless) | Valkey for session consistency |
| **Context Size** | ~20,000 tokens | Target: <500 tokens |
| **Glossary Search** | Load everything | Keyword matching + relevance |
| **Term Consistency** | None | Document-session tracking |

## Test Data Strategy

### Dataset Selection
- **Primary**: KO→EN test set (1,400 segments)
  - Smaller dataset for faster iteration
  - 2,794 glossary terms to test selection algorithms
- **Secondary**: EN→KO subset (100 segments for validation)
  - Minimal glossary (24 terms) for baseline comparison

### Test Scenarios

#### Scenario 1: Baseline Measurement
```python
# Phase 1 approach (for comparison)
context = {
    "all_glossary": load_all_2794_terms(),  # ~15,000 tokens
    "instructions": standard_prompt()        # ~400 tokens
}
# Total: ~15,400 tokens per request
```

#### Scenario 2: Smart Context (MVP Target)
```python
# Phase 2 MVP approach
context = {
    "relevant_glossary": search_relevant_terms(segment),  # ~150 tokens
    "locked_terms": get_session_terms(doc_id),           # ~60 tokens
    "previous_translation": get_previous(segment_id-1),   # ~40 tokens
    "instructions": minimal_prompt()                      # ~50 tokens
}
# Total: ~300 tokens per request (98% reduction)
```

## Implementation Plan

### Week 1: Infrastructure Setup

#### Day 1-2: Environment Setup
- [ ] Install Valkey locally (Redis fork)
- [ ] Set up Python virtual environment
- [ ] Install core dependencies:
  ```bash
  pip install redis streamlit pandas openai python-dotenv
  ```
- [ ] Create project structure:
  ```
  phase2_mvp/
  ├── src/
  │   ├── context_builder.py
  │   ├── valkey_manager.py
  │   ├── glossary_search.py
  │   └── translation_api.py
  ├── ui/
  │   └── mvp_app.py
  ├── data/
  │   └── (test files)
  └── tests/
  ```

#### Day 3-4: Valkey Integration
- [ ] Implement basic Valkey connection manager
- [ ] Create document session management:
  - Session initialization
  - Term storage (source→target mapping)
  - TTL management (1-hour sessions)
- [ ] Build term consistency tracker:
  ```python
  class TermConsistencyTracker:
      def store_term(self, doc_id, source, target):
          # Store in Valkey: doc:{doc_id}:terms
      def get_term(self, doc_id, source):
          # Retrieve consistent translation
      def get_all_terms(self, doc_id):
          # Get all locked terms for context
  ```

#### Day 5: Data Loading
- [ ] Load KO-EN test data (1,400 segments)
- [ ] Parse glossary files (2,794 terms total)
- [ ] Create data structures for efficient search
- [ ] Implement basic statistics reporting

### Week 2: Context Building

#### Day 6-7: Glossary Search
- [ ] Implement keyword-based glossary search:
  ```python
  class GlossarySearcher:
      def search(self, segment_text, limit=10):
          # Find glossary terms present in segment
          # Rank by relevance (exact match > partial)
          # Return top N terms only
  ```
- [ ] Add fuzzy matching for variations
- [ ] Implement relevance scoring
- [ ] Create filtering by frequency/importance

#### Day 8-9: Context Builder
- [ ] Design context assembly pipeline:
  ```python
  class SmartContextBuilder:
      def build(self, segment, doc_id, segment_id):
          context = {
              "source": segment,
              "locked_terms": self.get_locked_terms(doc_id),
              "glossary": self.search_glossary(segment),
              "previous": self.get_previous_context(doc_id, segment_id),
              "instructions": self.get_minimal_prompt()
          }
          return self.optimize_tokens(context)
  ```
- [ ] Implement token counting and optimization
- [ ] Add context size limits (max 500 tokens)
- [ ] Create priority-based inclusion

#### Day 10: GPT-5 Integration
- [ ] Adapt Phase 1 translation service for GPT-5:
  ```python
  def translate_with_gpt5(self, context):
      response = client.responses.create(
          model="gpt-5",  # Owl
          input=[{
              "role": "user",
              "content": self.format_context(context)
          }],
          text={"verbosity": "medium"},
          reasoning={"effort": "minimal"}
      )
      return response.output
  ```
- [ ] Handle new response format
- [ ] Add error handling for API calls
- [ ] Implement retry logic

### Week 3: Streamlit Interface

#### Day 11-12: Basic UI
- [ ] Create Streamlit interface with:
  - File upload for test data
  - Model selection (Owl/Kestrel/Wren)
  - Translation mode (single/batch)
  - Progress tracking
- [ ] Display interface:
  ```python
  # Main components
  - Source text display
  - Context preview (show what's being sent)
  - Translation result
  - Token usage metrics
  - Consistency tracking
  ```

#### Day 13: Evaluation Features
- [ ] Add comparison mode:
  - Side-by-side: Phase 1 vs Phase 2 context
  - Token usage comparison
  - Translation quality assessment
- [ ] Implement metrics dashboard:
  - Total tokens saved
  - Average context size
  - Cache hit rate
  - Translation speed

#### Day 14: Testing Interface
- [ ] Create test workflow:
  1. Load test segment
  2. Build smart context
  3. Display context (for inspection)
  4. Translate with GPT-5
  5. Store term mappings
  6. Show results and metrics
- [ ] Add manual evaluation options:
  - Pass/Fail rating
  - Comments field
  - Export results to CSV

### Week 4: Testing & Evaluation

#### Day 15-16: Baseline Testing
- [ ] Run Phase 1 approach on test subset:
  - Measure token usage with full glossary
  - Record translation times
  - Establish quality baseline
- [ ] Document baseline metrics:
  ```
  Phase 1 Baseline (100 segments):
  - Average tokens per request: 15,400
  - Total tokens used: 1,540,000
  - Average response time: 2.5s
  - Translation quality score: X/100
  ```

#### Day 17-18: MVP Testing
- [ ] Run Phase 2 MVP on same subset:
  - Measure token reduction
  - Track consistency improvements
  - Evaluate translation quality
- [ ] Document MVP metrics:
  ```
  Phase 2 MVP (100 segments):
  - Average tokens per request: 450 (97% reduction)
  - Total tokens used: 45,000
  - Average response time: 1.2s
  - Translation quality score: Y/100
  - Term consistency: 100%
  ```

#### Day 19: Comparative Analysis
- [ ] Create comparison report:
  - Token usage charts
  - Quality metrics
  - Consistency analysis
  - Cost projections
- [ ] Identify issues and improvements

#### Day 20: Documentation
- [ ] Write findings report
- [ ] Document architectural decisions
- [ ] Create recommendations for full implementation
- [ ] Prepare demo presentation

## Success Criteria

### Quantitative Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **Token Reduction** | >90% vs baseline | Compare average tokens/request |
| **Translation Quality** | ≥Phase 1 baseline | Manual evaluation (Pass/Fail) |
| **Term Consistency** | 100% within document | Track term reuse accuracy |
| **Context Size** | <500 tokens average | Measure actual context sizes |
| **Cache Hit Rate** | >60% for repeated terms | Valkey statistics |
| **Response Time** | <2s per segment | End-to-end timing |

### Qualitative Assessments

1. **Context Relevance**
   - Are selected glossary terms actually used?
   - Is context sufficient for accurate translation?
   - Are important terms being missed?

2. **Translation Consistency**
   - Do repeated terms translate the same way?
   - Is document-level consistency maintained?
   - Are locked terms properly enforced?

3. **System Usability**
   - Is the Streamlit interface intuitive?
   - Can users understand the context building?
   - Is the evaluation workflow efficient?

## Risk Mitigation

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Insufficient Context** | Poor translation quality | Implement fallback to load more terms |
| **Valkey Performance** | Slow response times | Use connection pooling, optimize queries |
| **GPT-5 API Issues** | Testing blocked | Have GPT-4o as fallback option |
| **Large Glossary Search** | High latency | Pre-index terms, use efficient algorithms |

### Quality Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Missing Critical Terms** | Translation errors | Implement importance scoring |
| **Context Too Small** | Ambiguous translations | Dynamic context expansion |
| **Consistency Drift** | Term variations | Strict locking mechanism |

## Implementation Guidelines

### Code Quality Standards
- Type hints for all functions
- Comprehensive docstrings
- Error handling for all external calls
- Logging for debugging
- Unit tests for core functions

### Performance Considerations
```python
# Efficient glossary search
class OptimizedGlossarySearch:
    def __init__(self, glossary_df):
        # Pre-process glossary for fast lookup
        self.term_index = self._build_index(glossary_df)
        self.term_cache = {}  # LRU cache
    
    def search(self, text, limit=10):
        # Check cache first
        if text in self.term_cache:
            return self.term_cache[text]
        
        # Efficient search algorithm
        matches = self._find_matches(text)
        ranked = self._rank_by_relevance(matches)
        result = ranked[:limit]
        
        # Cache result
        self.term_cache[text] = result
        return result
```

### Monitoring & Logging
```python
# Comprehensive metrics tracking
class MetricsCollector:
    def track_translation(self, segment_id, metrics):
        self.log({
            "segment_id": segment_id,
            "tokens_used": metrics["tokens"],
            "context_size": metrics["context_size"],
            "glossary_terms": metrics["glossary_count"],
            "cache_hits": metrics["cache_hits"],
            "response_time": metrics["time"],
            "timestamp": datetime.now()
        })
```

## Next Steps After MVP

### If Successful (>90% token reduction, quality maintained):
1. **Proceed to Phase 2A**: Full Valkey implementation
2. **Begin Qdrant Integration**: Semantic search for glossary
3. **Scale Testing**: Run on full 4,090 segments
4. **Production Planning**: Architecture for enterprise deployment

### If Partially Successful (50-90% reduction):
1. **Analyze Gaps**: Identify why reduction is limited
2. **Enhance Algorithm**: Improve context selection
3. **Consider Hybrid**: Mix smart and full context approaches
4. **Iterate MVP**: Address specific issues

### If Unsuccessful (<50% reduction):
1. **Root Cause Analysis**: Understand failure points
2. **Revisit Architecture**: Consider alternative approaches
3. **Adjust Expectations**: Redefine success metrics
4. **Pivot Strategy**: Explore different optimization methods

## Deliverables

### Week 4 Outputs
1. **Working MVP System**
   - Streamlit application
   - Valkey-based term consistency
   - Smart context builder
   - GPT-5 integration

2. **Test Results Document**
   - Baseline metrics
   - MVP performance data
   - Comparison analysis
   - Quality evaluation

3. **Technical Documentation**
   - Architecture diagram
   - API documentation
   - Deployment guide
   - Configuration instructions

4. **Recommendations Report**
   - Feasibility assessment
   - Scaling considerations
   - Cost projections
   - Implementation roadmap

## Conclusion

This MVP test plan provides a structured approach to validating Phase 2's core hypothesis: smart context building can dramatically reduce token usage while maintaining translation quality. By focusing on the essential components (Valkey cache, glossary search, context assembly), we can quickly assess feasibility before committing to the full three-tier architecture.

The 4-week timeline balances thoroughness with speed, allowing for comprehensive testing while maintaining momentum. Success will be measured not just by token reduction, but by translation quality, consistency, and system usability.

Key success factors:
- **Focus on core functionality** (not production polish)
- **Iterative development** with daily validation
- **Clear metrics** for objective evaluation
- **Fallback options** for risk mitigation
- **Documentation** for knowledge transfer

This MVP will provide the confidence and insights needed to proceed with full Phase 2 implementation or identify necessary pivots early in the process.