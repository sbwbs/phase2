#!/usr/bin/env python3
"""
Show the complete LLM prompt template with real context
"""

import asyncio
import os
import sys
sys.path.append(os.path.dirname(__file__))

from production_pipeline_working import WorkingPhase2Pipeline
import pandas as pd

async def show_prompt_template():
    print('📝 Complete LLM Prompt Template with Real Context')
    print('=' * 80)
    
    try:
        # Initialize pipeline with Valkey
        pipeline = WorkingPhase2Pipeline(use_valkey=True)
        
        # Add some locked terms for demonstration
        pipeline.add_locked_term("임상시험", "clinical study")
        pipeline.add_locked_term("의뢰자", "sponsor")
        pipeline.add_locked_term("시험대상자", "subject")
        
        # Add some previous translations for context
        pipeline.previous_translations.append({
            'korean': '시험대상자는 서면 동의서를 제공해야 합니다',
            'english': 'The subject must provide written informed consent'
        })
        
        # Sample Korean text
        korean_text = "본 임상시험은 의뢰자가 주관하는 다기관, 무작위배정, 공개 임상시험입니다."
        
        print(f'🔍 Sample Korean Text:')
        print(f'"{korean_text}"')
        print('\n' + '=' * 80)
        
        # 1. INDIVIDUAL SEGMENT PROMPT
        print('\n📋 1. INDIVIDUAL SEGMENT PROMPT TEMPLATE')
        print('=' * 80)
        
        # Get glossary terms
        glossary_terms = pipeline.search_real_glossary(korean_text)
        
        # Build smart context
        smart_context, tokens, metadata = pipeline.build_phase2_smart_context(korean_text, glossary_terms)
        
        # Create final prompt
        final_prompt = pipeline.create_gpt5_owl_prompt(korean_text, smart_context)
        
        print(f'📊 Prompt Stats: {len(final_prompt)} characters, ~{tokens} tokens')
        print('\n🚀 COMPLETE PROMPT SENT TO LLM:')
        print('-' * 80)
        print(final_prompt)
        print('-' * 80)
        
        # 2. BATCH PROMPT
        print('\n\n📋 2. BATCH PROCESSING PROMPT TEMPLATE')
        print('=' * 80)
        
        # Sample batch of Korean sentences
        batch_sentences = [
            "본 임상시험은 의뢰자가 주관하는 다기관 임상시험입니다.",
            "시험대상자는 서면 동의서를 제공해야 합니다.",
            "시험책임자는 모든 절차를 감독해야 합니다."
        ]
        
        # Get batch context
        smart_context_batch, tokens_batch, metadata_batch, all_terms = pipeline.build_batch_smart_context(
            batch_sentences, 
            [pipeline.search_real_glossary(sent) for sent in batch_sentences]
        )
        
        # Create batch prompt
        batch_prompt = pipeline._create_batch_clinical_prompt(batch_sentences, smart_context_batch)
        
        print(f'📊 Batch Prompt Stats: {len(batch_prompt)} characters, ~{tokens_batch} tokens')
        print(f'🔢 Processing: {len(batch_sentences)} sentences in 1 API call')
        print('\n🚀 COMPLETE BATCH PROMPT SENT TO LLM:')
        print('-' * 80)
        print(batch_prompt)
        print('-' * 80)
        
        # 3. CONTEXT BREAKDOWN
        print('\n\n🔬 3. CONTEXT COMPONENT BREAKDOWN')
        print('=' * 80)
        
        print('📚 Glossary Terms Found:')
        for i, term in enumerate(glossary_terms[:5], 1):
            print(f'   {i}. {term["korean"]} → {term["english"]} ({term["source"]})')
        
        print(f'\n🔒 Locked Terms in Valkey:')
        for i, (ko, en) in enumerate(pipeline.get_locked_terms_items(5), 1):
            print(f'   {i}. {ko} → {en}')
        
        print(f'\n📖 Previous Context:')
        for i, prev in enumerate(pipeline.previous_translations, 1):
            print(f'   {i}. {prev["korean"][:50]}... → {prev["english"][:50]}...')
        
        # 4. API CALL STRUCTURE
        print('\n\n🔌 4. ACTUAL API CALL STRUCTURE')
        print('=' * 80)
        
        print('📡 GPT-5 OWL API Call:')
        print('```python')
        print('response = client.responses.create(')
        print('    model="gpt-5",')
        print('    input=[{"role": "user", "content": final_prompt}],')
        print('    text={"verbosity": "medium"},')
        print('    reasoning={"effort": "minimal"}')
        print(')')
        print('```')
        
        print('\n📡 GPT-4o Fallback API Call:')
        print('```python') 
        print('response = client.chat.completions.create(')
        print('    model="gpt-4o",')
        print('    messages=[{"role": "user", "content": final_prompt}],')
        print('    max_tokens=500,')
        print('    temperature=0.3')
        print(')')
        print('```')
        
        # 5. PRIORITY DEMONSTRATION
        print('\n\n⚡ 5. PRIORITY SYSTEM DEMONSTRATION')
        print('=' * 80)
        
        if '**PRIORITY 1**' in smart_context:
            print('✅ PRIORITY 1: Locked terms override glossary')
            print('✅ PRIORITY 2: Glossary terms for non-locked terms')
            print('✅ Clear priority hierarchy established')
        else:
            print('❌ Priority system not found in context')
        
        # Check for conflicts
        conflicts = []
        locked_terms = pipeline.get_locked_terms()
        for term in glossary_terms:
            if term['korean'] in locked_terms:
                if locked_terms[term['korean']] != term['english']:
                    conflicts.append({
                        'korean': term['korean'],
                        'glossary': term['english'],
                        'locked': locked_terms[term['korean']]
                    })
        
        if conflicts:
            print(f'\n⚔️  CONFLICTS DETECTED ({len(conflicts)} terms):')
            for conflict in conflicts:
                print(f'   📖 Glossary: {conflict["korean"]} → {conflict["glossary"]}')
                print(f'   🔒 Locked: {conflict["korean"]} → {conflict["locked"]} ✅ WINS')
                print()
        else:
            print('\n✅ No conflicts between locked terms and glossary')
        
        # Cleanup
        pipeline.cleanup()
        
        print('\n' + '=' * 80)
        print('✅ Complete prompt template demonstration finished!')
        
    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(show_prompt_template())