import pandas as pd
import tiktoken

# Initialize tokenizer
enc = tiktoken.get_encoding('cl100k_base')

# Load sample data
df = pd.read_excel('../shared/data/Phase2_Test/영한/1_테스트용_Generated_Preview_EN-KO.xlsx')

print('TOKEN USAGE ANALYSIS FOR PROTOCOL TRANSLATION')
print('='*60)

# Basic stats
total_segments = len(df)
print(f'Total segments in protocol: {total_segments}')

# Calculate tokens for all segments
source_tokens = []
for text in df['Source text']:
    if pd.notna(text):
        tokens = len(enc.encode(str(text)))
        source_tokens.append(tokens)

avg_tokens = sum(source_tokens) / len(source_tokens) if source_tokens else 0
total_source_tokens = sum(source_tokens)

print(f'Average tokens per segment: {avg_tokens:.1f}')
print(f'Total source tokens: {total_source_tokens:,}')

# Context accumulation analysis
print('\nCONTEXT ACCUMULATION SIMULATION:')
print('-'*40)

# Show how context grows for first 20 segments
print('\nSegment | Current | Context | Glossary | Total')
print('-'*60)
running_context = []
context_window = 5

for i in range(min(20, len(df))):
    text = df.iloc[i]['Source text']
    if pd.notna(text):
        current = len(enc.encode(str(text)))
        context = sum(len(enc.encode(str(ctx))) for ctx in running_context[-context_window:])
        glossary = 200  # Estimated static context
        total = current + context + glossary
        
        print(f'{i+1:7} | {current:7} | {context:7} | {glossary:8} | {total:7}')
        running_context.append(text)

# Simulate full document with different strategies
def calculate_tokens_with_context(segments, context_window=5, include_glossary=True):
    total_tokens = 0
    running_context = []
    
    for i, text in enumerate(segments):
        if pd.notna(text):
            # Current segment
            current = len(enc.encode(str(text)))
            
            # Previous context
            context = sum(len(enc.encode(str(ctx))) for ctx in running_context[-context_window:])
            
            # Glossary/TM context
            static_context = 200 if include_glossary else 0
            
            total_tokens += (current + context + static_context)
            running_context.append(text)
    
    return total_tokens

# Different scenarios
print('\n\nFULL DOCUMENT TOKEN PROJECTIONS:')
print('='*60)

scenarios = {
    'No Context (baseline)': total_source_tokens,
    'Context Window=5': calculate_tokens_with_context(df['Source text'], 5),
    'Context Window=10': calculate_tokens_with_context(df['Source text'], 10),
    'Full Context (cumulative)': calculate_tokens_with_context(df['Source text'], 9999),
}

# With TM reduction
tm_coverage = 0.4  # 40% TM coverage
tm_segments = int(total_segments * tm_coverage)
non_tm_segments = total_segments - tm_segments

# For TM matches, we only need minimal tokens (just for validation)
tm_tokens = tm_segments * 50  # Minimal prompt for TM validation
llm_tokens = calculate_tokens_with_context(df['Source text'][tm_segments:], 5)
scenarios['With 40% TM Coverage'] = tm_tokens + llm_tokens

for scenario, tokens in scenarios.items():
    print(f'{scenario:<25}: {tokens:>12,} tokens')

# Cost estimates
print('\n\nCOST ESTIMATES BY MODEL:')
print('='*60)

models = {
    'GPT-4o': 0.01,      # $0.01 per 1K tokens
    'Claude Sonnet': 0.003,  # $0.003 per 1K tokens  
    'Gemini Flash': 0.00125, # $0.00125 per 1K tokens
}

print(f'{"Scenario":<25} | {"GPT-4o":>10} | {"Claude":>10} | {"Gemini":>10}')
print('-'*60)

for scenario, tokens in scenarios.items():
    costs = []
    for model, price in models.items():
        cost = (tokens / 1000) * price
        costs.append(f'${cost:.2f}')
    print(f'{scenario:<25} | {costs[0]:>10} | {costs[1]:>10} | {costs[2]:>10}')

# Show impact of optimization
print('\n\nOPTIMIZATION IMPACT:')
print('='*60)

baseline = scenarios['Context Window=5']
optimized = scenarios['With 40% TM Coverage']
savings = baseline - optimized
savings_pct = (savings / baseline) * 100

print(f'Baseline (Context=5): {baseline:,} tokens')
print(f'With TM Optimization: {optimized:,} tokens')
print(f'Token Reduction: {savings:,} tokens ({savings_pct:.1f}%)')
print(f'Cost Savings (GPT-4o): ${(savings/1000)*0.01:.2f}')

# Per-segment analysis
print('\n\nPER-SEGMENT ANALYSIS:')
print('='*60)
print(f'Average tokens per segment (source only): {avg_tokens:.1f}')
print(f'Average with context (window=5): {baseline/total_segments:.1f}')
print(f'Average with TM optimization: {optimized/total_segments:.1f}')