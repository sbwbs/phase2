# Token Usage Analysis Report

## Executive Summary

Analysis of the EN-KO clinical protocol (2,690 segments) reveals that context accumulation is the primary driver of token usage, with a 17x increase when using a standard context window approach.

## Key Findings

### 1. Baseline Metrics
- **Total segments**: 2,690
- **Average tokens per segment**: 17.6 (very short segments)
- **Total source tokens**: 47,372

### 2. Context Accumulation Impact

| Strategy | Total Tokens | Cost (GPT-4o) | Multiplier |
|----------|-------------|---------------|------------|
| No Context | 47,372 | $0.47 | 1x |
| Context Window=5 | 821,996 | $8.22 | 17x |
| Context Window=10 | 1,058,260 | $10.58 | 22x |
| Full Cumulative | 64,091,426 | $640.91 | 1,353x |
| With 40% TM | 547,334 | $5.47 | 11.5x |

### 3. Per-Segment Analysis

Context accumulation for first 20 segments shows rapid growth:
- Segment 1: 208 tokens (8 source + 0 context + 200 glossary)
- Segment 10: 297 tokens (71 source + 26 context + 200 glossary)
- Segment 20: 253 tokens (9 source + 44 context + 200 glossary)

**Average per segment**:
- Source only: 17.6 tokens
- With context (window=5): 305.6 tokens
- With TM optimization: 203.5 tokens

### 4. Cost Implications

For complete protocol translation:

| Model | Baseline (Context=5) | With TM (40%) | Savings |
|-------|---------------------|---------------|---------|
| GPT-4o ($0.01/1K) | $8.22 | $5.47 | $2.75 (33%) |
| Claude Sonnet ($0.003/1K) | $2.47 | $1.64 | $0.83 (33%) |
| Gemini Flash ($0.00125/1K) | $1.03 | $0.68 | $0.35 (33%) |

## Critical Insights

### 1. Context is the Cost Driver
- Source text: 17.6 tokens average
- Static context (glossary): 200 tokens
- Previous translations: Grows continuously
- **Result**: 94% of tokens are context, not content

### 2. Token Growth Patterns
```
Tokens = Current_Segment + Sum(Previous_N_Segments) + Static_Context

Where:
- Current_Segment ≈ 17.6 tokens
- Previous_N_Segments = N × 17.6 tokens (for window size N)
- Static_Context ≈ 200 tokens (glossary/guidelines)
```

### 3. Optimization Opportunities

**Current State** (No optimization):
- Every segment gets full context
- Redundant glossary loading
- No reuse of previous translations

**Optimized State** (With memory tiers):
1. **40% TM Coverage**: 1,076 segments need no LLM
2. **Smart Context**: Only relevant previous segments
3. **Cached Glossary**: Tier 1 (Valkey) for instant lookup
4. **Semantic Retrieval**: Tier 2 (Qdrant) for similar examples

## Recommendations

### 1. Immediate Actions
- Implement TM matching to eliminate 40% of LLM calls
- Use sliding window (5 segments) not cumulative context
- Cache static context (glossary) in Tier 1

### 2. Advanced Optimizations
- Semantic similarity to select relevant context (not just previous N)
- Batch similar segments together
- Progressive glossary loading (only relevant terms)

### 3. Expected Results
- **Token reduction**: 33-50% with basic optimization
- **Cost savings**: $2.75-4.00 per document
- **Quality improvement**: More consistent translations

## Conclusion

The analysis confirms that the three-tier memory architecture is essential for Phase 2. Without it, token usage grows exponentially with document length. The combination of TM coverage (Tier 1), semantic retrieval (Tier 2), and pattern learning (Tier 3) can reduce token usage by 50% or more while improving translation quality through better context selection.