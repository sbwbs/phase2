#!/usr/bin/env python3
"""
Glossary Loader for Phase 2 Production Pipeline
Load and process the two glossary files for integration
"""

import pandas as pd
import os
from typing import List, Dict, Tuple
import logging

class GlossaryLoader:
    """Load and process Phase 2 glossary files"""
    
    def __init__(self):
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def load_coding_form_glossary(self, file_path: str) -> List[Dict]:
        """Load Coding Form glossary"""
        self.logger.info(f"📚 Loading Coding Form glossary: {file_path}")
        
        try:
            # Read Excel file and examine structure
            xl_file = pd.ExcelFile(file_path)
            self.logger.info(f"Sheets in Coding Form: {xl_file.sheet_names}")
            
            glossary_terms = []
            
            for sheet_name in xl_file.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                self.logger.info(f"Sheet '{sheet_name}': {len(df)} rows, columns: {list(df.columns)}")
                
                # Show sample data
                if len(df) > 0:
                    self.logger.info(f"Sample data from '{sheet_name}':")
                    self.logger.info(df.head(3).to_string())
                    
                    # Try to identify Korean and English columns
                    for col in df.columns:
                        sample_text = str(df[col].iloc[0]) if len(df) > 0 else ""
                        # Check if contains Korean characters
                        has_korean = any('\u3131' <= char <= '\uD79D' for char in sample_text)
                        self.logger.info(f"Column '{col}': Korean detected: {has_korean}")
                
                # Extract terms based on identified structure
                if 'KR_SOC_27.0' in df.columns and 'SOC_27.0' in df.columns:
                    for idx, row in df.iterrows():
                        if pd.notna(row['KR_SOC_27.0']) and pd.notna(row['SOC_27.0']):
                            glossary_terms.append({
                                'korean': str(row['KR_SOC_27.0']).strip(),
                                'english': str(row['SOC_27.0']).strip(),
                                'source': f"Coding_Form_{sheet_name}",
                                'score': 0.9  # High confidence for medical terms
                            })
            
            self.logger.info(f"✅ Loaded {len(glossary_terms)} terms from Coding Form")
            return glossary_terms
            
        except Exception as e:
            self.logger.error(f"❌ Error loading Coding Form glossary: {e}")
            return []
    
    def load_clinical_trials_glossary(self, file_path: str) -> List[Dict]:
        """Load Clinical Trials glossary"""
        self.logger.info(f"📚 Loading Clinical Trials glossary: {file_path}")
        
        try:
            # Read Excel file and examine structure
            xl_file = pd.ExcelFile(file_path)
            self.logger.info(f"Sheets in Clinical Trials: {xl_file.sheet_names}")
            
            glossary_terms = []
            
            for sheet_name in xl_file.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                self.logger.info(f"Sheet '{sheet_name}': {len(df)} rows, columns: {list(df.columns)}")
                
                # Show sample data
                if len(df) > 0:
                    self.logger.info(f"Sample data from '{sheet_name}':")
                    self.logger.info(df.head(3).to_string())
                    
                    # Try to identify Korean and English columns
                    for col in df.columns:
                        sample_text = str(df[col].iloc[0]) if len(df) > 0 else ""
                        # Check if contains Korean characters
                        has_korean = any('\u3131' <= char <= '\uD79D' for char in sample_text)
                        self.logger.info(f"Column '{col}': Korean detected: {has_korean}")
                
                # Extract terms based on identified structure  
                if 'KO' in df.columns and 'EN' in df.columns:
                    for idx, row in df.iterrows():
                        if pd.notna(row['KO']) and pd.notna(row['EN']):
                            # Handle multiple terms separated by |
                            ko_terms = str(row['KO']).split('|')
                            en_terms = str(row['EN']).split('|')
                            
                            # Use first term as primary, others as alternatives
                            main_ko = ko_terms[0].strip()
                            main_en = en_terms[0].strip()
                            
                            if main_ko and main_en:
                                glossary_terms.append({
                                    'korean': main_ko,
                                    'english': main_en,
                                    'source': f"Clinical_Trials_{sheet_name}",
                                    'score': 0.95,  # Very high confidence for clinical terms
                                    'alternatives': {
                                        'korean': [t.strip() for t in ko_terms[1:] if t.strip()],
                                        'english': [t.strip() for t in en_terms[1:] if t.strip()]
                                    }
                                })
            
            self.logger.info(f"✅ Loaded {len(glossary_terms)} terms from Clinical Trials")
            return glossary_terms
            
        except Exception as e:
            self.logger.error(f"❌ Error loading Clinical Trials glossary: {e}")
            return []
    
    def load_all_glossaries(self) -> Tuple[List[Dict], Dict]:
        """Load both glossary files and return combined terms"""
        self.logger.info("🔍 Loading all Phase 2 glossary files...")
        
        # File paths
        coding_form_path = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/2_용어집_Coding Form.xlsx"
        clinical_trials_path = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/2_용어집_LDE KO-EN Clinical Trials TB_20250421.xlsx"
        
        # Load individual glossaries
        coding_terms = self.load_coding_form_glossary(coding_form_path)
        clinical_terms = self.load_clinical_trials_glossary(clinical_trials_path)
        
        # Combine and deduplicate
        all_terms = coding_terms + clinical_terms
        
        # Create statistics
        stats = {
            "coding_form_terms": len(coding_terms),
            "clinical_trials_terms": len(clinical_terms),
            "total_terms": len(all_terms),
            "files_loaded": 2
        }
        
        self.logger.info(f"📊 Glossary loading summary:")
        self.logger.info(f"   Coding Form: {stats['coding_form_terms']} terms")
        self.logger.info(f"   Clinical Trials: {stats['clinical_trials_terms']} terms")
        self.logger.info(f"   Total: {stats['total_terms']} terms")
        
        return all_terms, stats
    
    def save_production_glossary(self, terms: List[Dict], output_file: str):
        """Save combined glossary in production-ready format"""
        self.logger.info(f"💾 Saving production glossary to {output_file}")
        
        try:
            # Create DataFrame for easy processing
            df_terms = pd.DataFrame(terms)
            
            # Save as Excel with multiple sheets
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # Main glossary sheet
                df_terms.to_excel(writer, sheet_name='Combined_Glossary', index=False)
                
                # Separate sheets by source
                coding_terms = df_terms[df_terms['source'].str.contains('Coding_Form')]
                clinical_terms = df_terms[df_terms['source'].str.contains('Clinical_Trials')]
                
                if len(coding_terms) > 0:
                    coding_terms.to_excel(writer, sheet_name='Coding_Form_Terms', index=False)
                
                if len(clinical_terms) > 0:
                    clinical_terms.to_excel(writer, sheet_name='Clinical_Trials_Terms', index=False)
            
            # Also save as JSON for easy loading
            import json
            json_file = output_file.replace('.xlsx', '.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(terms, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"✅ Production glossary saved:")
            self.logger.info(f"   Excel: {output_file}")
            self.logger.info(f"   JSON: {json_file}")
            
        except Exception as e:
            self.logger.error(f"❌ Error saving production glossary: {e}")
            raise

def main():
    """Main function to examine and prepare glossary files"""
    print("📚 Phase 2 Glossary File Analysis & Production Preparation")
    print("=" * 70)
    
    loader = GlossaryLoader()
    all_terms, stats = loader.load_all_glossaries()
    
    # Save production-ready glossary
    output_file = "/Users/won.suh/Project/translate-ai/phase2/data/production_glossary.xlsx"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    loader.save_production_glossary(all_terms, output_file)
    
    # Show sample terms
    print(f"\n📝 Sample Terms:")
    for i, term in enumerate(all_terms[:5]):
        print(f"   {i+1}. {term['korean']} → {term['english']} ({term['source']})")
    
    print(f"\n✨ Glossary analysis and production preparation completed!")
    print(f"📊 Total terms loaded: {stats['total_terms']}")
    print(f"💾 Production files created in: /Users/won.suh/Project/translate-ai/phase2/data/")

if __name__ == "__main__":
    main()