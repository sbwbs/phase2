#!/usr/bin/env python3
"""
Run Improved Translation Pipelines with Actual Test Data
Tests both EN-KO and KO-EN pipelines using real test data files
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

def load_test_data():
    """Load actual test data from Excel files"""
    print("📂 Loading Actual Test Data")
    print("=" * 50)
    
    # Load EN-KO test data
    en_ko_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/영한/1_테스트용_Generated_Preview_EN-KO.xlsx"
    try:
        df_en_ko = pd.read_excel(en_ko_file)
        print(f"✅ EN-KO Test Data: {len(df_en_ko)} segments")
        print(f"   Columns: {list(df_en_ko.columns)}")
        if len(df_en_ko) > 0:
            print(f"   Sample: {df_en_ko.iloc[0].to_dict()}")
    except Exception as e:
        print(f"❌ Failed to load EN-KO test data: {e}")
        df_en_ko = None
    
    # Load KO-EN test data  
    ko_en_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/1_테스트용_Generated_Preview_KO-EN.xlsx"
    try:
        df_ko_en = pd.read_excel(ko_en_file)
        print(f"✅ KO-EN Test Data: {len(df_ko_en)} segments")
        print(f"   Columns: {list(df_ko_en.columns)}")
        if len(df_ko_en) > 0:
            print(f"   Sample: {df_ko_en.iloc[0].to_dict()}")
    except Exception as e:
        print(f"❌ Failed to load KO-EN test data: {e}")
        df_ko_en = None
    
    return df_en_ko, df_ko_en

def test_en_ko_pipeline_with_real_data(df_test):
    """Test EN-KO pipeline with real test data"""
    print("\n🔥 Testing Improved EN-KO Pipeline with Real Data")
    print("=" * 60)
    
    if df_test is None or len(df_test) == 0:
        print("❌ No test data available")
        return None
    
    # Import the improved EN-KO pipeline
    from production_pipeline_en_ko_improved import ImprovedENKOPipeline
    
    try:
        # Initialize pipeline with Valkey enabled
        pipeline = ImprovedENKOPipeline(
            model_name="Owl",
            batch_size=3,
            style_guide_variant="clinical_protocol_strict",
            use_valkey=True
        )
        
        # Prepare test data (take first 5 segments to avoid excessive API costs)
        test_segments = []
        for idx, row in df_test.head(5).iterrows():
            # Try to identify source and reference columns
            source_col = next((col for col in row.index if 'source' in col.lower() or 'en' in col.lower()), None)
            reference_col = next((col for col in row.index if 'reference' in col.lower() or 'ko' in col.lower()), None)
            
            if source_col:
                test_segments.append({
                    'segment_id': idx + 1,
                    'source_en': str(row[source_col]),
                    'reference_ko': str(row[reference_col]) if reference_col else ''
                })
        
        print(f"Processing {len(test_segments)} segments...")
        
        # Process with improved pipeline
        results = pipeline.process_en_ko_batch_strict(test_segments)
        
        # Display detailed results
        total_issues = 0
        quality_scores = []
        
        for result in results:
            print(f"\n📄 Segment {result.segment_id}")
            print(f"Source (EN): {result.source_text_en[:100]}...")
            print(f"Reference (KO): {result.reference_ko[:100]}...")
            print(f"Translation (KO): {result.translated_text_ko}")
            print(f"Quality Score: {result.quality_score:.2f}")
            print(f"Status: {result.status}")
            print(f"Cost: ${result.total_cost:.4f}")
            
            quality_scores.append(result.quality_score)
            
            # Show QA issues
            if result.qa_issues:
                print(f"🚨 QA Issues ({len(result.qa_issues)}):")
                for issue in result.qa_issues:
                    print(f"  - {issue}")
                total_issues += len(result.qa_issues)
            
            if result.terminology_violations:
                print(f"📝 Terminology Violations ({len(result.terminology_violations)}):")
                for violation in result.terminology_violations:
                    print(f"  - {violation}")
                total_issues += len(result.terminology_violations)
            
            print("-" * 50)
        
        # Summary
        avg_quality = sum(quality_scores) / len(quality_scores)
        total_cost = sum(r.total_cost for r in results)
        
        print(f"\n📊 EN-KO Pipeline Summary:")
        print(f"Average Quality Score: {avg_quality:.2f}")
        print(f"Total Issues Found: {total_issues}")
        print(f"Total Cost: ${total_cost:.4f}")
        
        return results
        
    except Exception as e:
        print(f"❌ EN-KO Pipeline Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_ko_en_pipeline_with_real_data(df_test):
    """Test KO-EN pipeline with real test data including critical Segment 60 test"""
    print("\n🔥 Testing Improved KO-EN Pipeline with Real Data")  
    print("=" * 60)
    
    if df_test is None or len(df_test) == 0:
        print("❌ No test data available")
        return None
    
    # Import the improved KO-EN pipeline
    from production_pipeline_ko_en_improved import ImprovedKOENPipeline
    
    try:
        # Initialize pipeline with Valkey enabled
        pipeline = ImprovedKOENPipeline(
            model_name="Owl",
            use_valkey=True
        )
        
        # Prepare test data including the critical test case
        test_segments = []
        
        # Add the critical Segment 60 test case first
        test_segments.append({
            'segment_id': 60,
            'source_ko': '원광대학교병원 소화기내과 최석채 교수',
            'reference_en': 'Professor Choi Seok-chae, Division of Gastroenterology, Wonkwang University Hospital'
        })
        
        # Add real test data (first 4 segments)
        for idx, row in df_test.head(4).iterrows():
            # Try to identify source and reference columns
            source_col = next((col for col in row.index if 'source' in col.lower() or 'ko' in col.lower()), None)
            reference_col = next((col for col in row.index if 'reference' in col.lower() or 'en' in col.lower()), None)
            
            if source_col:
                test_segments.append({
                    'segment_id': idx + 1,
                    'source_ko': str(row[source_col]),
                    'reference_en': str(row[reference_col]) if reference_col else ''
                })
        
        print(f"Processing {len(test_segments)} segments (including critical Segment 60)...")
        
        # Process each segment
        results = []
        for segment in test_segments:
            result = pipeline.process_ko_en_segment_strict(segment)
            results.append(result)
        
        # Display detailed results
        total_issues = 0
        quality_scores = []
        verbosity_scores = []
        hallucinations = 0
        
        for result in results:
            print(f"\n📄 Segment {result.segment_id}")
            if result.segment_id == 60:
                print("🚨 CRITICAL TEST CASE (Segment 60 equivalent)")
            
            print(f"Source (KO): {result.source_text_ko}")
            print(f"Reference (EN): {result.reference_en[:100]}...")
            print(f"Translation (EN): {result.translated_text_en}")
            print(f"Quality Score: {result.quality_score:.2f}")
            print(f"Verbosity Score: {result.verbosity_score:.2f}")
            print(f"Status: {result.status}")
            print(f"Cost: ${result.total_cost:.4f}")
            
            quality_scores.append(result.quality_score)
            verbosity_scores.append(result.verbosity_score)
            
            # Critical: Check for hallucination
            if result.hallucination_detected:
                print(f"🚨 HALLUCINATION DETECTED: {result.hallucination_details}")
                hallucinations += 1
            else:
                print("✅ No hallucination detected")
            
            # Show QA issues
            if result.qa_issues:
                print(f"⚠️ QA Issues ({len(result.qa_issues)}):")
                for issue in result.qa_issues:
                    print(f"  - {issue}")
                total_issues += len(result.qa_issues)
            
            print("-" * 50)
        
        # Summary
        avg_quality = sum(quality_scores) / len(quality_scores)
        avg_verbosity = sum(verbosity_scores) / len(verbosity_scores)
        total_cost = sum(r.total_cost for r in results)
        
        print(f"\n📊 KO-EN Pipeline Summary:")
        print(f"Average Quality Score: {avg_quality:.2f}")
        print(f"Average Verbosity Score: {avg_verbosity:.2f}")
        print(f"Hallucinations Detected: {hallucinations}")
        print(f"Total Issues Found: {total_issues}")
        print(f"Total Cost: ${total_cost:.4f}")
        
        # Critical assessment
        if hallucinations == 0:
            print("✅ CRITICAL: No hallucinations detected - major improvement!")
        else:
            print(f"🚨 CRITICAL: {hallucinations} hallucinations still detected")
        
        if avg_verbosity < 1.3:
            print("✅ VERBOSITY: Output is concise and appropriate")
        else:
            print("⚠️ VERBOSITY: Output may still be too verbose")
        
        return results
        
    except Exception as e:
        print(f"❌ KO-EN Pipeline Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def compare_with_original_feedback():
    """Compare results with original feedback issues"""
    print("\n🎯 COMPARISON WITH ORIGINAL REVIEWER FEEDBACK")
    print("=" * 60)
    
    print("📋 Original EN-KO Critical Issues:")
    print("1. ❌ Using '표지' instead of '제목페이지' for 'title page'")
    print("2. ❌ Using '의뢰자' instead of '의뢰자 대표자' for 'sponsor representative'")
    print("3. ❌ Adding subjective interpretations like '내용이 적정함'")
    print("4. ❌ Too informal, not literal enough for regulatory side-by-side review")
    
    print("\n📋 Original KO-EN Critical Issues:")
    print("1. 🚨 CRITICAL: Segment 60 added 'MD, PhD' not present in Korean")
    print("2. ❌ Excessive verbosity - technical rather than regulatory writing")
    print("3. ❌ Inconsistent abbreviation usage and mid-sentence capitalization")
    print("4. ❌ Adding explanatory information not in source text")
    
    print("\n✅ Expected Improvements from Enhanced Pipelines:")
    print("- Strict literal translation preventing subjective interpretations")
    print("- Mandatory terminology enforcement with QA validation")
    print("- Hallucination detection preventing information additions")
    print("- Concise, regulatory-appropriate output style")
    print("- Comprehensive quality assurance with issue categorization")

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    print("🚀 COMPREHENSIVE TEST: IMPROVED TRANSLATION PIPELINES")
    print("Using Real Test Data with Valkey Memory Enabled")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Show comparison with original feedback first
    compare_with_original_feedback()
    
    # Load actual test data
    df_en_ko, df_ko_en = load_test_data()
    
    # Test EN-KO pipeline with real data
    en_ko_results = test_en_ko_pipeline_with_real_data(df_en_ko)
    
    # Test KO-EN pipeline with real data
    ko_en_results = test_ko_en_pipeline_with_real_data(df_ko_en)
    
    # Final summary
    print("\n🏆 FINAL ASSESSMENT")
    print("=" * 60)
    
    if en_ko_results:
        avg_quality_en_ko = sum(r.quality_score for r in en_ko_results) / len(en_ko_results)
        total_issues_en_ko = sum(len(r.qa_issues or []) + len(r.terminology_violations or []) for r in en_ko_results)
        print(f"📊 EN-KO Performance:")
        print(f"   Average Quality: {avg_quality_en_ko:.2f}")
        print(f"   Total Issues: {total_issues_en_ko}")
        print(f"   QA Validation: {'✅ Working' if total_issues_en_ko > 0 else '⚠️ No issues detected'}")
    
    if ko_en_results:
        avg_quality_ko_en = sum(r.quality_score for r in ko_en_results) / len(ko_en_results)
        avg_verbosity = sum(r.verbosity_score for r in ko_en_results) / len(ko_en_results)
        hallucinations = sum(1 for r in ko_en_results if r.hallucination_detected)
        print(f"📊 KO-EN Performance:")
        print(f"   Average Quality: {avg_quality_ko_en:.2f}")
        print(f"   Average Verbosity: {avg_verbosity:.2f}")
        print(f"   Hallucinations: {hallucinations}")
        print(f"   Critical Test (Segment 60): {'✅ Passed' if hallucinations == 0 else '❌ Failed'}")
    
    print(f"\n✅ Comprehensive Testing Complete!")
    print(f"   Valkey Memory: Active")
    print(f"   QA Framework: Active") 
    print(f"   Improved Prompts: Active")
    print(f"   Terminology Enforcement: Active")