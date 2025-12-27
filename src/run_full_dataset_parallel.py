#!/usr/bin/env python3
"""
Full Dataset Parallel Processing - Complete Production Run
Processes entire EN-KO (2,690) and KO-EN (1,400) datasets simultaneously
"""

import os
import sys
import pandas as pd
import logging
import threading
import time
import concurrent.futures
from datetime import datetime

# Add current directory to path for imports
sys.path.append(os.path.dirname(__file__))

def run_en_ko_full_dataset():
    """Run EN-KO pipeline on complete dataset (2,690 segments)"""
    print(f"🚀 [EN-KO FULL] Starting Complete EN-KO Dataset Processing")
    thread_id = threading.get_ident()
    
    from production_pipeline_en_ko_improved import ImprovedENKOPipeline
    
    try:
        # Load complete test data
        en_ko_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/영한/1_테스트용_Generated_Preview_EN-KO.xlsx"
        df_en_ko = pd.read_excel(en_ko_file)
        
        print(f"📂 [EN-KO-{thread_id}] Processing COMPLETE dataset: {len(df_en_ko)} segments")
        
        # Initialize production pipeline with unique session
        pipeline = ImprovedENKOPipeline(
            model_name="Owl",
            batch_size=5,
            style_guide_variant="clinical_protocol_strict",
            use_valkey=True
        )
        
        # Update session ID to avoid conflicts
        pipeline.session_id = f"full_en_ko_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Prepare ALL segments for processing
        test_segments = []
        for idx, row in df_en_ko.iterrows():
            source_col = next((col for col in row.index if 'source' in col.lower() or 'Source' in col), None)
            target_col = next((col for col in row.index if 'target' in col.lower() or 'Target' in col), None)
            
            if source_col and not pd.isna(row[source_col]):
                test_segments.append({
                    'segment_id': idx + 1,
                    'source_en': str(row[source_col]),
                    'reference_ko': str(row[target_col]) if target_col and not pd.isna(row[target_col]) else ''
                })
        
        print(f"🔄 [EN-KO-{thread_id}] Processing {len(test_segments)} segments in FULL PRODUCTION mode...")
        print(f"📊 [EN-KO-{thread_id}] Glossary: {pipeline.glossary_stats.get('total_terms', 0)} terms loaded")
        
        start_time = time.time()
        
        # Process in batches
        all_results = []
        batch_size = 5
        total_batches = (len(test_segments) + batch_size - 1) // batch_size
        
        print(f"📊 [EN-KO-{thread_id}] Processing {total_batches} batches of {batch_size} segments each...")
        
        for i in range(0, len(test_segments), batch_size):
            batch_num = (i // batch_size) + 1
            batch = test_segments[i:i+batch_size]
            
            if batch_num % 50 == 1 or batch_num == total_batches:
                print(f"⚙️ [EN-KO-{thread_id}] Processing batch {batch_num}/{total_batches}...")
            
            batch_results = pipeline.process_en_ko_batch_strict(batch)
            all_results.extend(batch_results)
            
            # Progress updates every 100 batches
            if batch_num % 100 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / (batch_num * batch_size)
                remaining = (total_batches - batch_num) * batch_size * avg_time
                print(f"   [EN-KO-{thread_id}] Progress: {batch_num}/{total_batches} batches | Avg: {avg_time:.2f}s/segment | ETA: {remaining/60:.1f}min")
        
        # Calculate final metrics
        total_time = time.time() - start_time
        total_cost = sum(r.total_cost for r in all_results)
        avg_quality = sum(r.quality_score for r in all_results) / len(all_results)
        total_issues = sum(len(r.qa_issues or []) + len(r.terminology_violations or []) for r in all_results)
        glossary_usage = sum(r.glossary_terms_found for r in all_results)
        
        # Export results to Excel
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_file = f"full_en_ko_results_{timestamp}.xlsx"
        
        # Convert to DataFrame and export
        data = []
        for result in all_results:
            data.append({
                'Segment_ID': result.segment_id,
                'Source_EN': result.source_text_en,
                'Reference_KO': result.reference_ko,
                'Translated_KO': result.translated_text_ko,
                'Quality_Score': result.quality_score,
                'Processing_Time': result.processing_time,
                'Total_Cost': result.total_cost,
                'QA_Issues': '; '.join(result.qa_issues or []),
                'Terminology_Violations': '; '.join(result.terminology_violations or []),
                'Status': result.status
            })
        
        df_results = pd.DataFrame(data)
        df_results.to_excel(excel_file, index=False)
        
        result_summary = {
            'pipeline': 'EN-KO-FULL',
            'segments_processed': len(all_results),
            'total_time': total_time,
            'avg_time_per_segment': total_time / len(all_results),
            'total_cost': total_cost,
            'cost_per_segment': total_cost / len(all_results),
            'avg_quality': avg_quality,
            'total_issues': total_issues,
            'glossary_usage': glossary_usage,
            'excel_file': excel_file,
            'results': all_results
        }
        
        print(f"✅ [EN-KO-{thread_id}] COMPLETE DATASET PROCESSED!")
        print(f"   Segments: {len(all_results)}")
        print(f"   Time: {total_time/60:.1f} minutes ({total_time/3600:.1f} hours)")
        print(f"   Quality: {avg_quality:.3f}")
        print(f"   Cost: ${total_cost:.2f}")
        print(f"   Excel: {excel_file}")
        
        return result_summary
        
    except Exception as e:
        print(f"❌ [EN-KO-{thread_id}] Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_ko_en_full_dataset():
    """Run KO-EN pipeline on complete dataset (1,400 segments)"""
    print(f"🚀 [KO-EN FULL] Starting Complete KO-EN Dataset Processing")
    thread_id = threading.get_ident()
    
    from production_pipeline_ko_en_improved import ImprovedKOENPipeline
    
    try:
        # Load complete test data
        ko_en_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/1_테스트용_Generated_Preview_KO-EN.xlsx"
        df_ko_en = pd.read_excel(ko_en_file)
        
        print(f"📂 [KO-EN-{thread_id}] Processing COMPLETE dataset: {len(df_ko_en)} segments")
        
        # Initialize production pipeline with unique session
        pipeline = ImprovedKOENPipeline(
            model_name="Owl",
            use_valkey=True,
            batch_size=5
        )
        
        # Update session ID to avoid conflicts
        pipeline.session_id = f"full_ko_en_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Add critical Segment 60 test case first
        test_segments = [{
            'segment_id': 60,
            'source_ko': '원광대학교병원 소화기내과 최석채 교수',
            'reference_en': 'Professor Choi Seok-chae, Division of Gastroenterology, Wonkwang University Hospital'
        }]
        
        # Prepare ALL segments for processing
        for idx, row in df_ko_en.iterrows():
            source_col = next((col for col in row.index if 'source' in col.lower() or 'Source' in col), None)
            target_col = next((col for col in row.index if 'target' in col.lower() or 'Target' in col), None)
            
            if source_col and not pd.isna(row[source_col]):
                test_segments.append({
                    'segment_id': idx + 1,
                    'source_ko': str(row[source_col]),
                    'reference_en': str(row[target_col]) if target_col and not pd.isna(row[target_col]) else ''
                })
        
        print(f"🔄 [KO-EN-{thread_id}] Processing {len(test_segments)} segments (includes critical Segment 60)...")
        
        start_time = time.time()
        
        # Process segments in batches (OPTIMIZED METHOD)
        all_results = []
        batch_size = pipeline.batch_size
        total_batches = (len(test_segments) + batch_size - 1) // batch_size
        
        print(f"📊 [KO-EN-{thread_id}] Processing {total_batches} batches of {batch_size} segments each...")
        
        for i in range(0, len(test_segments), batch_size):
            batch_num = (i // batch_size) + 1
            batch = test_segments[i:i+batch_size]
            
            # Check if critical Segment 60 is in this batch
            segment_60_in_batch = any(seg.get('segment_id') == 60 for seg in batch)
            if segment_60_in_batch:
                print(f"🚨 [KO-EN-{thread_id}] Processing batch {batch_num}/{total_batches} (includes CRITICAL SEGMENT 60)...")
            elif batch_num % 30 == 1 or batch_num == total_batches:
                print(f"⚙️ [KO-EN-{thread_id}] Processing batch {batch_num}/{total_batches}...")
            
            batch_results = pipeline.process_ko_en_batch_strict(batch)
            all_results.extend(batch_results)
            
            # Progress updates every 50 batches
            if batch_num % 50 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / len(all_results)
                remaining_segments = len(test_segments) - len(all_results)
                remaining_time = remaining_segments * avg_time
                print(f"   [KO-EN-{thread_id}] Progress: {batch_num}/{total_batches} batches | Avg: {avg_time:.2f}s/segment | ETA: {remaining_time/60:.1f}min")
        
        # Calculate final metrics
        total_time = time.time() - start_time
        total_cost = sum(r.total_cost for r in all_results)
        avg_quality = sum(r.quality_score for r in all_results) / len(all_results)
        avg_verbosity = sum(r.verbosity_score for r in all_results) / len(all_results)
        total_issues = sum(len(r.qa_issues or []) for r in all_results)
        hallucinations = sum(1 for r in all_results if r.hallucination_detected)
        
        # Check critical Segment 60
        segment_60_result = next((r for r in all_results if r.segment_id == 60), None)
        segment_60_passed = segment_60_result and not segment_60_result.hallucination_detected
        
        # Export results to Excel
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_file = f"full_ko_en_results_{timestamp}.xlsx"
        
        # Convert to DataFrame and export
        data = []
        for result in all_results:
            data.append({
                'Segment_ID': result.segment_id,
                'Source_KO': result.source_text_ko,
                'Reference_EN': result.reference_en,
                'Translated_EN': result.translated_text_en,
                'Quality_Score': result.quality_score,
                'Verbosity_Score': result.verbosity_score,
                'Processing_Time': result.processing_time,
                'Total_Cost': result.total_cost,
                'QA_Issues': '; '.join(result.qa_issues or []),
                'Hallucination_Detected': result.hallucination_detected,
                'Status': result.status
            })
        
        df_results = pd.DataFrame(data)
        df_results.to_excel(excel_file, index=False)
        
        result_summary = {
            'pipeline': 'KO-EN-FULL',
            'segments_processed': len(all_results),
            'total_time': total_time,
            'avg_time_per_segment': total_time / len(all_results),
            'total_cost': total_cost,
            'cost_per_segment': total_cost / len(all_results),
            'avg_quality': avg_quality,
            'avg_verbosity': avg_verbosity,
            'total_issues': total_issues,
            'hallucinations': hallucinations,
            'segment_60_passed': segment_60_passed,
            'segment_60_result': segment_60_result,
            'excel_file': excel_file,
            'results': all_results
        }
        
        print(f"✅ [KO-EN-{thread_id}] COMPLETE DATASET PROCESSED!")
        print(f"   Segments: {len(all_results)}")
        print(f"   Time: {total_time/60:.1f} minutes ({total_time/3600:.1f} hours)")
        print(f"   Quality: {avg_quality:.3f}")
        print(f"   Cost: ${total_cost:.2f}")
        print(f"   Segment 60: {'✅ PASSED' if segment_60_passed else '❌ FAILED'}")
        print(f"   Excel: {excel_file}")
        
        return result_summary
        
    except Exception as e:
        print(f"❌ [KO-EN-{thread_id}] Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run complete dataset processing for both pipelines in parallel"""
    print("🌍 FULL DATASET PARALLEL PROCESSING: COMPLETE PRODUCTION RUN")
    print("Processing entire datasets simultaneously for maximum throughput")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Setup thread-safe logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(threadName)s] %(levelname)s:%(name)s:%(message)s'
    )
    
    # Production dataset parameters
    print(f"📋 FULL DATASET PROCESSING PLAN:")
    print(f"   EN-KO Dataset: ~2,690 segments (complete dataset)")
    print(f"   KO-EN Dataset: ~1,400 segments (complete dataset)")
    print(f"   Total Expected: ~4,090 segments")
    print(f"   Execution Mode: PARALLEL (simultaneous processing)")
    print(f"   Expected Time: ~3.4 hours")
    print(f"   Expected Cost: ~$71")
    print(f"   Valkey Memory: Enabled with separate sessions")
    print(f"   QA Framework: Full validation active")
    
    overall_start_time = time.time()
    
    print(f"\n🚀 LAUNCHING FULL DATASET PARALLEL PROCESSING...")
    print("=" * 80)
    
    # Use ThreadPoolExecutor for parallel execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="FullDataset") as executor:
        # Submit both pipelines simultaneously
        print(f"🚀 Submitting EN-KO complete dataset processing...")
        en_ko_future = executor.submit(run_en_ko_full_dataset)
        
        print(f"🚀 Submitting KO-EN complete dataset processing...")
        ko_en_future = executor.submit(run_ko_en_full_dataset)
        
        print(f"⏳ Both complete datasets processing in parallel...")
        print(f"📊 This will take approximately 3-4 hours to complete...")
        
        # Wait for both to complete and get results
        print(f"⌛ Waiting for complete results...")
        en_ko_results = en_ko_future.result()
        ko_en_results = ko_en_future.result()
    
    total_parallel_time = time.time() - overall_start_time
    
    # Final comprehensive assessment
    print(f"\n🏆 COMPLETE DATASET PROCESSING RESULTS")
    print("=" * 80)
    
    if en_ko_results and ko_en_results:
        total_segments = en_ko_results['segments_processed'] + ko_en_results['segments_processed']
        total_cost = en_ko_results['total_cost'] + ko_en_results['total_cost']
        
        print(f"📊 FINAL PRODUCTION METRICS:")
        print(f"   Total Segments Processed: {total_segments:,}")
        print(f"   Total Parallel Processing Time: {total_parallel_time/60:.1f} minutes ({total_parallel_time/3600:.1f} hours)")
        print(f"   Overall Average Quality: {(en_ko_results['avg_quality'] + ko_en_results['avg_quality'])/2:.3f}")
        print(f"   Total Production Cost: ${total_cost:.2f}")
        print(f"   Cost per Segment: ${total_cost/total_segments:.4f}")
        
        print(f"\n📈 INDIVIDUAL DATASET RESULTS:")
        print(f"   EN-KO: {en_ko_results['segments_processed']:,} segments, {en_ko_results['total_time']/3600:.1f}h, Quality: {en_ko_results['avg_quality']:.3f}, Cost: ${en_ko_results['total_cost']:.2f}")
        print(f"   KO-EN: {ko_en_results['segments_processed']:,} segments, {ko_en_results['total_time']/3600:.1f}h, Quality: {ko_en_results['avg_quality']:.3f}, Cost: ${ko_en_results['total_cost']:.2f}")
        
        print(f"\n🎯 CRITICAL SUCCESS METRICS:")
        print(f"   EN-KO Quality: {en_ko_results['avg_quality']:.3f} {'✅ EXCELLENT' if en_ko_results['avg_quality'] >= 0.85 else '✅ GOOD' if en_ko_results['avg_quality'] >= 0.75 else '⚠️ ACCEPTABLE'}")
        print(f"   KO-EN Quality: {ko_en_results['avg_quality']:.3f} {'✅ EXCELLENT' if ko_en_results['avg_quality'] >= 0.8 else '✅ GOOD' if ko_en_results['avg_quality'] >= 0.7 else '⚠️ ACCEPTABLE'}")
        print(f"   Segment 60 Test: {'✅ PASSED' if ko_en_results['segment_60_passed'] else '❌ FAILED'}")
        print(f"   Parallel Processing: ✅ SUCCESSFUL")
        print(f"   Complete Datasets: ✅ FULLY PROCESSED")
        
        print(f"\n📁 RESULTS FILES:")
        print(f"   EN-KO Results: {en_ko_results['excel_file']}")
        print(f"   KO-EN Results: {ko_en_results['excel_file']}")
        
        print(f"\n🚀 PRODUCTION DEPLOYMENT STATUS:")
        if (en_ko_results['avg_quality'] >= 0.8 and 
            ko_en_results['avg_quality'] >= 0.7 and 
            ko_en_results['segment_60_passed']):
            print("   Status: ✅ PRODUCTION VALIDATED WITH COMPLETE DATASETS")
            print("   Recommendation: System ready for full-scale deployment")
        else:
            print("   Status: ⚠️ REQUIRES REVIEW")
            print("   Recommendation: Address quality issues before deployment")
    
    else:
        print("❌ Complete dataset processing incomplete - check error logs")
    
    print(f"\n✅ Complete Dataset Processing Finished!")
    print(f"   Total Duration: {total_parallel_time/60:.1f} minutes ({total_parallel_time/3600:.1f} hours)")
    print(f"   Complete datasets processed simultaneously")
    print("=" * 80)

if __name__ == "__main__":
    main()