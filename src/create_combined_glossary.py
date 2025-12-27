#!/usr/bin/env python3
"""
Create Combined Glossary for EN-KO Translation
Combines glossaries from all available sources into a single standardized file
"""

import pandas as pd
import os
from datetime import datetime

def create_combined_glossary():
    """Create combined glossary from all available sources"""
    
    combined_terms = []
    total_processed = 0
    
    print("🔄 Creating Combined EN-KO Glossary...")
    print("=" * 60)
    
    # Source 1: Avance Clinical Glossary (EN→KO)
    print("\n📚 Processing Avance Clinical Glossary...")
    try:
        avance_file = "../Phase 2_AI testing kit/영한/2_용어집_Avance Clinical Glossary.xlsx"
        df_avance = pd.read_excel(avance_file)
        
        avance_added = 0
        for _, row in df_avance.iterrows():
            english = str(row.get('English', '')).strip()
            korean = str(row.get('Korean', '')).strip()
            
            if english and korean:
                combined_terms.append({
                    'English': english,
                    'Korean': korean,
                    'Source': 'Avance Clinical',
                    'Priority': 1  # High priority - specific to current dataset
                })
                avance_added += 1
        
        print(f"✅ Added {avance_added} terms from Avance Clinical")
        total_processed += avance_added
        
    except Exception as e:
        print(f"❌ Error processing Avance Clinical: {e}")
    
    # Source 2: Coding Form Glossary (KO→EN reversed to EN→KO)
    print("\n📚 Processing Coding Form Glossary...")
    try:
        coding_file = "../Phase 2_AI testing kit/한영/2_용어집_Coding Form.xlsx"
        df_coding = pd.read_excel(coding_file)
        
        coding_added = 0
        for _, row in df_coding.iterrows():
            korean = str(row.get('KR_SOC_27.0', '')).strip()
            english = str(row.get('SOC_27.0', '')).strip()
            
            # Filter for medical terms (remove common words, numbers)
            if (english and korean and 
                len(english) > 3 and len(korean) > 1 and
                not english.replace(' ', '').isdigit() and 
                not korean.replace(' ', '').isdigit() and
                english.lower() not in ['and', 'the', 'of', 'to', 'in', 'a', 'an', 'for', 'with', 'or', 'by'] and
                # Medical/clinical terms
                any(word in english.lower() for word in ['disorder', 'disease', 'syndrome', 'condition', 'adverse', 'event', 'reaction', 'medical', 'clinical', 'therapeutic', 'drug', 'treatment', 'diagnosis', 'symptom'])):
                
                # Check if not already exists (avoid duplicates)
                existing = [t for t in combined_terms if t['English'].lower() == english.lower()]
                if not existing:
                    combined_terms.append({
                        'English': english,
                        'Korean': korean,
                        'Source': 'Coding Form (Medical)',
                        'Priority': 2  # Medium priority - broader medical terms
                    })
                    coding_added += 1
        
        print(f"✅ Added {coding_added} relevant medical terms from Coding Form")
        total_processed += coding_added
        
    except Exception as e:
        print(f"❌ Error processing Coding Form: {e}")
    
    # Source 3: Clinical Trials Glossary (KO→EN reversed to EN→KO)  
    print("\n📚 Processing Clinical Trials Glossary...")
    try:
        trials_file = "../Phase 2_AI testing kit/한영/2_용어집_LDE KO-EN Clinical Trials TB_20250421.xlsx"
        df_trials = pd.read_excel(trials_file)
        
        trials_added = 0
        for _, row in df_trials.iterrows():
            korean_raw = str(row.get('KO', '')).strip()
            english_raw = str(row.get('EN', '')).strip()
            
            # Handle multiple terms separated by |
            korean_terms = [k.strip() for k in korean_raw.split('|') if k.strip()]
            english_terms = [e.strip() for e in english_raw.split('|') if e.strip()]
            
            # Use the first/primary term from each
            if korean_terms and english_terms:
                korean = korean_terms[0]
                english = english_terms[0]
                
                # Clean up Korean text (remove parenthetical English if present)
                if '(' in korean and ')' in korean:
                    korean = korean.split('(')[0].strip()
                
                if (english and korean and len(english) > 2 and len(korean) > 1 and
                    not english.replace(' ', '').isdigit()):
                    
                    # Check if not already exists
                    existing = [t for t in combined_terms if t['English'].lower() == english.lower()]
                    if not existing:
                        combined_terms.append({
                            'English': english,
                            'Korean': korean,  
                            'Source': 'Clinical Trials',
                            'Priority': 1  # High priority - clinical trials specific
                        })
                        trials_added += 1
        
        print(f"✅ Added {trials_added} terms from Clinical Trials")
        total_processed += trials_added
        
    except Exception as e:
        print(f"❌ Error processing Clinical Trials: {e}")
    
    # Create combined DataFrame
    if combined_terms:
        df_combined = pd.DataFrame(combined_terms)
        
        # Sort by priority (higher first), then by source, then alphabetically
        df_combined = df_combined.sort_values(['Priority', 'Source', 'English'])
        
        # Save to Excel
        output_file = "../data/combined_en_ko_glossary.xlsx"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        df_combined.to_excel(output_file, index=False)
        
        print(f"\n🎉 Combined Glossary Created Successfully!")
        print(f"📁 File: {output_file}")
        print(f"📊 Total unique terms: {len(df_combined)}")
        
        # Statistics by source
        print(f"\n📈 Terms by source:")
        source_stats = df_combined['Source'].value_counts()
        for source, count in source_stats.items():
            print(f"   • {source}: {count} terms")
        
        # Show samples
        print(f"\n📝 Sample terms from combined glossary:")
        for source in df_combined['Source'].unique():
            sample = df_combined[df_combined['Source'] == source].head(3)
            print(f"\n{source}:")
            for _, row in sample.iterrows():
                print(f"   • {row['English']} → {row['Korean']}")
        
        return output_file, len(df_combined)
    
    else:
        print(f"❌ No terms could be processed from any source!")
        return None, 0

if __name__ == "__main__":
    output_file, term_count = create_combined_glossary()
    
    if output_file:
        print(f"\n✅ Success! Created combined glossary with {term_count} terms")
        print(f"📁 Location: {output_file}")
        print(f"🚀 Ready to use in EN-KO translation pipeline")
    else:
        print(f"❌ Failed to create combined glossary")