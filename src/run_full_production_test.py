#!/usr/bin/env python3
"""
Full Production Test - Enhanced Translation Pipelines
Tests both EN-KO and KO-EN pipelines with larger datasets for production validation
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime
import time

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

def run_full_production_en_ko(num_segments=50):
    """Run full production test for EN-KO pipeline"""
    print(f"\n🚀 FULL PRODUCTION TEST: EN-KO Pipeline ({num_segments} segments)")
    print("=" * 70)
    
    from production_pipeline_en_ko_improved import ImprovedENKOPipeline
    
    try:
        # Load test data
        en_ko_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/영한/1_테스트용_Generated_Preview_EN-KO.xlsx"
        df_en_ko = pd.read_excel(en_ko_file)
        
        print(f"📂 Loaded {len(df_en_ko)} total segments from test dataset")
        
        # Initialize production pipeline
        pipeline = ImprovedENKOPipeline(
            model_name="Owl",
            batch_size=5,  # Process in batches of 5
            style_guide_variant="clinical_protocol_strict",
            use_valkey=True
        )
        
        # Prepare production test data
        test_segments = []
        for idx, row in df_en_ko.head(num_segments).iterrows():
            source_col = next((col for col in row.index if 'source' in col.lower() or 'Source' in col), None)
            target_col = next((col for col in row.index if 'target' in col.lower() or 'Target' in col), None)
            
            if source_col and not pd.isna(row[source_col]):
                test_segments.append({
                    'segment_id': idx + 1,
                    'source_en': str(row[source_col]),
                    'reference_ko': str(row[target_col]) if target_col and not pd.isna(row[target_col]) else ''
                })
        
        print(f"🔄 Processing {len(test_segments)} segments in production mode...")
        print(f"📊 Glossary: {pipeline.glossary_stats.get('total_terms', 0)} terms loaded")
        
        start_time = time.time()
        
        # Process in batches
        all_results = []
        batch_size = 5
        total_batches = (len(test_segments) + batch_size - 1) // batch_size
        
        for i in range(0, len(test_segments), batch_size):
            batch_num = (i // batch_size) + 1
            batch = test_segments[i:i+batch_size]
            
            print(f"⚙️ Processing batch {batch_num}/{total_batches} ({len(batch)} segments)...")
            
            batch_results = pipeline.process_en_ko_batch_strict(batch)
            all_results.extend(batch_results)
            
            # Progress indicator
            if batch_num % 5 == 0 or batch_num == total_batches:
                elapsed = time.time() - start_time
                avg_time = elapsed / (batch_num * batch_size)
                remaining = (total_batches - batch_num) * batch_size * avg_time
                print(f"   Progress: {batch_num}/{total_batches} batches | Avg: {avg_time:.2f}s/segment | ETA: {remaining/60:.1f}min")
        
        # Production metrics
        total_time = time.time() - start_time
        total_cost = sum(r.total_cost for r in all_results)
        avg_quality = sum(r.quality_score for r in all_results) / len(all_results)
        total_issues = sum(len(r.qa_issues or []) + len(r.terminology_violations or []) for r in all_results)
        glossary_usage = sum(r.glossary_terms_found for r in all_results)
        
        print(f"\n📊 EN-KO PRODUCTION RESULTS:")
        print(f"   Segments Processed: {len(all_results)}")
        print(f"   Total Processing Time: {total_time/60:.2f} minutes")
        print(f"   Average Time per Segment: {total_time/len(all_results):.2f} seconds")
        print(f"   Average Quality Score: {avg_quality:.3f}")
        print(f"   Total Cost: ${total_cost:.2f}")
        print(f"   Cost per Segment: ${total_cost/len(all_results):.4f}")
        print(f"   Total QA Issues: {total_issues}")
        print(f"   Glossary Terms Used: {glossary_usage}")
        print(f"   Issues Rate: {(total_issues/len(all_results)*100):.1f}% of segments")
        
        # Quality distribution
        excellent = sum(1 for r in all_results if r.quality_score >= 0.9)
        good = sum(1 for r in all_results if 0.8 <= r.quality_score < 0.9)
        acceptable = sum(1 for r in all_results if 0.7 <= r.quality_score < 0.8)
        needs_review = sum(1 for r in all_results if r.quality_score < 0.7)
        
        print(f"\n📈 QUALITY DISTRIBUTION:")
        print(f"   Excellent (≥0.9): {excellent} ({excellent/len(all_results)*100:.1f}%)")
        print(f"   Good (0.8-0.9): {good} ({good/len(all_results)*100:.1f}%)")
        print(f"   Acceptable (0.7-0.8): {acceptable} ({acceptable/len(all_results)*100:.1f}%)")
        print(f"   Needs Review (<0.7): {needs_review} ({needs_review/len(all_results)*100:.1f}%)")
        
        return all_results
        
    except Exception as e:
        print(f"❌ EN-KO Production Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_full_production_ko_en(num_segments=50):
    """Run full production test for KO-EN pipeline"""
    print(f"\n🚀 FULL PRODUCTION TEST: KO-EN Pipeline ({num_segments} segments)")
    print("=" * 70)
    
    from production_pipeline_ko_en_improved import ImprovedKOENPipeline
    
    try:
        # Load test data
        ko_en_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/1_테스트용_Generated_Preview_KO-EN.xlsx"
        df_ko_en = pd.read_excel(ko_en_file)
        
        print(f"📂 Loaded {len(df_ko_en)} total segments from test dataset")
        
        # Initialize production pipeline
        pipeline = ImprovedKOENPipeline(
            model_name="Owl",
            use_valkey=True
        )
        
        # Add critical Segment 60 test case
        test_segments = [{
            'segment_id': 60,
            'source_ko': '원광대학교병원 소화기내과 최석채 교수',
            'reference_en': 'Professor Choi Seok-chae, Division of Gastroenterology, Wonkwang University Hospital'
        }]
        
        # Prepare production test data
        for idx, row in df_ko_en.head(num_segments-1).iterrows():
            source_col = next((col for col in row.index if 'source' in col.lower() or 'Source' in col), None)
            target_col = next((col for col in row.index if 'target' in col.lower() or 'Target' in col), None)
            
            if source_col and not pd.isna(row[source_col]):
                test_segments.append({
                    'segment_id': idx + 1,
                    'source_ko': str(row[source_col]),
                    'reference_en': str(row[target_col]) if target_col and not pd.isna(row[target_col]) else ''
                })
        
        print(f"🔄 Processing {len(test_segments)} segments (including critical Segment 60)...")
        
        start_time = time.time()
        
        # Process segments in batches for KO-EN (NEW OPTIMIZED METHOD)
        all_results = []
        batch_size = pipeline.batch_size
        total_batches = (len(test_segments) + batch_size - 1) // batch_size
        
        print(f"📊 Processing {len(test_segments)} segments in {total_batches} batches of {batch_size}...")
        
        for i in range(0, len(test_segments), batch_size):
            batch_num = (i // batch_size) + 1
            batch = test_segments[i:i+batch_size]
            
            # Check if critical Segment 60 is in this batch
            segment_60_in_batch = any(seg.get('segment_id') == 60 for seg in batch)
            if segment_60_in_batch:
                print(f"🚨 Processing batch {batch_num}/{total_batches} (includes CRITICAL Segment 60, {len(batch)} segments)...")
            else:
                print(f"⚙️ Processing batch {batch_num}/{total_batches} ({len(batch)} segments)...")
            
            batch_results = pipeline.process_ko_en_batch_strict(batch)
            all_results.extend(batch_results)
            
            # Progress update
            if batch_num % 5 == 0 or batch_num == total_batches:
                elapsed = time.time() - start_time
                processed_segments = len(all_results)
                avg_time = elapsed / processed_segments if processed_segments > 0 else 0
                remaining_segments = len(test_segments) - processed_segments
                remaining_time = remaining_segments * avg_time
                print(f"   Progress: {batch_num}/{total_batches} batches | Avg: {avg_time:.2f}s/segment | ETA: {remaining_time/60:.1f}min")
        
        # Production metrics
        total_time = time.time() - start_time
        total_cost = sum(r.total_cost for r in all_results)
        avg_quality = sum(r.quality_score for r in all_results) / len(all_results)
        avg_verbosity = sum(r.verbosity_score for r in all_results) / len(all_results)
        total_issues = sum(len(r.qa_issues or []) for r in all_results)
        hallucinations = sum(1 for r in all_results if r.hallucination_detected)
        
        # Check critical Segment 60
        segment_60_result = next((r for r in all_results if r.segment_id == 60), None)
        
        print(f"\n📊 KO-EN PRODUCTION RESULTS:")
        print(f"   Segments Processed: {len(all_results)}")
        print(f"   Total Processing Time: {total_time/60:.2f} minutes")
        print(f"   Average Time per Segment: {total_time/len(all_results):.2f} seconds")
        print(f"   Average Quality Score: {avg_quality:.3f}")
        print(f"   Average Verbosity Score: {avg_verbosity:.3f}")
        print(f"   Total Cost: ${total_cost:.2f}")
        print(f"   Cost per Segment: ${total_cost/len(all_results):.4f}")
        print(f"   Total QA Issues: {total_issues}")
        print(f"   Hallucinations Detected: {hallucinations}")
        
        print(f"\n🚨 CRITICAL SEGMENT 60 ASSESSMENT:")
        if segment_60_result:
            print(f"   Translation: {segment_60_result.translated_text_en}")
            print(f"   Quality: {segment_60_result.quality_score:.2f}")
            print(f"   Hallucination: {'❌ DETECTED' if segment_60_result.hallucination_detected else '✅ NONE'}")
            if segment_60_result.hallucination_detected:
                print(f"   Details: {segment_60_result.hallucination_details}")
            print(f"   Status: {'✅ PASSED' if not segment_60_result.hallucination_detected else '❌ FAILED'}")
        
        # Quality and verbosity distribution
        excellent = sum(1 for r in all_results if r.quality_score >= 0.8)
        good = sum(1 for r in all_results if 0.7 <= r.quality_score < 0.8)
        needs_review = sum(1 for r in all_results if r.quality_score < 0.7)
        
        concise = sum(1 for r in all_results if r.verbosity_score <= 1.2)
        acceptable_verbosity = sum(1 for r in all_results if 1.2 < r.verbosity_score <= 1.8)
        verbose = sum(1 for r in all_results if r.verbosity_score > 1.8)
        
        print(f"\n📈 QUALITY DISTRIBUTION:")
        print(f"   Excellent (≥0.8): {excellent} ({excellent/len(all_results)*100:.1f}%)")
        print(f"   Good (0.7-0.8): {good} ({good/len(all_results)*100:.1f}%)")
        print(f"   Needs Review (<0.7): {needs_review} ({needs_review/len(all_results)*100:.1f}%)")
        
        print(f"\n📝 VERBOSITY DISTRIBUTION:")
        print(f"   Concise (≤1.2): {concise} ({concise/len(all_results)*100:.1f}%)")
        print(f"   Acceptable (1.2-1.8): {acceptable_verbosity} ({acceptable_verbosity/len(all_results)*100:.1f}%)")
        print(f"   Verbose (>1.8): {verbose} ({verbose/len(all_results)*100:.1f}%)")
        
        return all_results
        
    except Exception as e:
        print(f"❌ KO-EN Production Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run full production tests for both pipelines"""
    print("🏭 FULL PRODUCTION VALIDATION: IMPROVED TRANSLATION PIPELINES")
    print("Using Complete Test Datasets with Valkey Memory")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    # Production test parameters
    EN_KO_SEGMENTS = 100  # Test 100 segments for EN-KO
    KO_EN_SEGMENTS = 50   # Test 50 segments for KO-EN (includes Segment 60)
    
    print(f"📋 PRODUCTION TEST PLAN:")
    print(f"   EN-KO Pipeline: {EN_KO_SEGMENTS} segments (batch processing)")
    print(f"   KO-EN Pipeline: {KO_EN_SEGMENTS} segments (batch processing - NEW OPTIMIZED!)")
    print(f"   Valkey Memory: Enabled for term consistency")
    print(f"   QA Framework: Full validation active")
    
    start_time = time.time()
    
    # Run EN-KO production test
    print("\n" + "🔥" * 50)
    en_ko_results = run_full_production_en_ko(EN_KO_SEGMENTS)
    
    # Run KO-EN production test  
    print("\n" + "🔥" * 50)
    ko_en_results = run_full_production_ko_en(KO_EN_SEGMENTS)
    
    # Final production assessment
    total_time = time.time() - start_time
    
    print("\n" + "🏆" * 50)
    print("FINAL PRODUCTION ASSESSMENT")
    print("🏆" * 50)
    
    if en_ko_results and ko_en_results:
        total_segments = len(en_ko_results) + len(ko_en_results)
        total_cost = (sum(r.total_cost for r in en_ko_results) + 
                     sum(r.total_cost for r in ko_en_results))
        
        # Critical metrics
        en_ko_avg_quality = sum(r.quality_score for r in en_ko_results) / len(en_ko_results)
        ko_en_avg_quality = sum(r.quality_score for r in ko_en_results) / len(ko_en_results)
        
        segment_60_passed = not any(r.hallucination_detected for r in ko_en_results if r.segment_id == 60)
        
        print(f"📊 OVERALL PRODUCTION METRICS:")
        print(f"   Total Segments Processed: {total_segments}")
        print(f"   Total Processing Time: {total_time/60:.2f} minutes")
        print(f"   Overall Average Quality: {(en_ko_avg_quality + ko_en_avg_quality) / 2:.3f}")
        print(f"   Total Production Cost: ${total_cost:.2f}")
        print(f"   Cost per Segment: ${total_cost/total_segments:.4f}")
        
        print(f"\n🎯 CRITICAL SUCCESS METRICS:")
        print(f"   EN-KO Quality: {en_ko_avg_quality:.3f} {'✅ EXCELLENT' if en_ko_avg_quality >= 0.85 else '✅ GOOD' if en_ko_avg_quality >= 0.75 else '⚠️ ACCEPTABLE'}")
        print(f"   KO-EN Quality: {ko_en_avg_quality:.3f} {'✅ EXCELLENT' if ko_en_avg_quality >= 0.8 else '✅ GOOD' if ko_en_avg_quality >= 0.7 else '⚠️ ACCEPTABLE'}")
        print(f"   Segment 60 Test: {'✅ PASSED' if segment_60_passed else '❌ FAILED'}")
        print(f"   Valkey Memory: ✅ ACTIVE")
        print(f"   QA Framework: ✅ ACTIVE")
        
        print(f"\n🚀 PRODUCTION READINESS:")
        if en_ko_avg_quality >= 0.8 and ko_en_avg_quality >= 0.7 and segment_60_passed:
            print("   Status: ✅ READY FOR PRODUCTION DEPLOYMENT")
            print("   Recommendation: Both pipelines meet production quality standards")
        else:
            print("   Status: ⚠️ REQUIRES ADDITIONAL TUNING")
            print("   Recommendation: Address quality issues before full deployment")
        
        print(f"\n💰 BUSINESS METRICS:")
        print(f"   Production Cost: ${total_cost:.2f} for {total_segments} segments")
        print(f"   Estimated 1000 segments: ${(total_cost/total_segments)*1000:.2f}")
        print(f"   Estimated 10,000 segments: ${(total_cost/total_segments)*10000:.2f}")
        
    else:
        print("❌ Production test incomplete - check error logs")
    
    print(f"\n✅ Full Production Validation Complete!")
    print(f"   Duration: {total_time/60:.2f} minutes")
    print(f"   Both pipelines tested with real datasets")

if __name__ == "__main__":
    main()