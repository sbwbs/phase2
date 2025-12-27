#!/usr/bin/env python3
"""
Parallel Production Test - Enhanced Translation Pipelines
Runs both EN-KO and KO-EN pipelines simultaneously for maximum throughput
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

def run_en_ko_pipeline_parallel(num_segments=100):
    """Run EN-KO pipeline in parallel thread"""
    print(f"🚀 [EN-KO THREAD] Starting EN-KO Pipeline ({num_segments} segments)")
    thread_id = threading.get_ident()
    
    from production_pipeline_en_ko_improved import ImprovedENKOPipeline
    
    try:
        # Load test data
        en_ko_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/영한/1_테스트용_Generated_Preview_EN-KO.xlsx"
        df_en_ko = pd.read_excel(en_ko_file)
        
        print(f"📂 [EN-KO-{thread_id}] Loaded {len(df_en_ko)} total segments")
        
        # Initialize production pipeline with unique session
        pipeline = ImprovedENKOPipeline(
            model_name="Owl",
            batch_size=5,
            style_guide_variant="clinical_protocol_strict",
            use_valkey=True
        )
        
        # Update session ID to avoid conflicts
        pipeline.session_id = f"parallel_en_ko_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
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
        
        print(f"🔄 [EN-KO-{thread_id}] Processing {len(test_segments)} segments...")
        
        start_time = time.time()
        
        # Process in batches
        all_results = []
        batch_size = 5
        total_batches = (len(test_segments) + batch_size - 1) // batch_size
        
        for i in range(0, len(test_segments), batch_size):
            batch_num = (i // batch_size) + 1
            batch = test_segments[i:i+batch_size]
            
            if batch_num % 5 == 1 or batch_num == total_batches:
                print(f"⚙️ [EN-KO-{thread_id}] Processing batch {batch_num}/{total_batches}...")
            
            batch_results = pipeline.process_en_ko_batch_strict(batch)
            all_results.extend(batch_results)
        
        # Calculate metrics
        total_time = time.time() - start_time
        total_cost = sum(r.total_cost for r in all_results)
        avg_quality = sum(r.quality_score for r in all_results) / len(all_results)
        total_issues = sum(len(r.qa_issues or []) + len(r.terminology_violations or []) for r in all_results)
        
        result_summary = {
            'pipeline': 'EN-KO',
            'segments_processed': len(all_results),
            'total_time': total_time,
            'avg_time_per_segment': total_time / len(all_results),
            'total_cost': total_cost,
            'cost_per_segment': total_cost / len(all_results),
            'avg_quality': avg_quality,
            'total_issues': total_issues,
            'results': all_results
        }
        
        print(f"✅ [EN-KO-{thread_id}] Completed: {len(all_results)} segments in {total_time/60:.2f}min")
        return result_summary
        
    except Exception as e:
        print(f"❌ [EN-KO-{thread_id}] Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_ko_en_pipeline_parallel(num_segments=50):
    """Run KO-EN pipeline in parallel thread"""
    print(f"🚀 [KO-EN THREAD] Starting KO-EN Pipeline ({num_segments} segments)")
    thread_id = threading.get_ident()
    
    from production_pipeline_ko_en_improved import ImprovedKOENPipeline
    
    try:
        # Load test data
        ko_en_file = "/Users/won.suh/Project/translate-ai/phase2/Phase 2_AI testing kit/한영/1_테스트용_Generated_Preview_KO-EN.xlsx"
        df_ko_en = pd.read_excel(ko_en_file)
        
        print(f"📂 [KO-EN-{thread_id}] Loaded {len(df_ko_en)} total segments")
        
        # Initialize production pipeline with unique session
        pipeline = ImprovedKOENPipeline(
            model_name="Owl",
            use_valkey=True,
            batch_size=5
        )
        
        # Update session ID to avoid conflicts
        pipeline.session_id = f"parallel_ko_en_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
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
        
        print(f"🔄 [KO-EN-{thread_id}] Processing {len(test_segments)} segments (includes Segment 60)...")
        
        start_time = time.time()
        
        # Process segments in batches (NEW OPTIMIZED METHOD)
        all_results = []
        batch_size = pipeline.batch_size
        total_batches = (len(test_segments) + batch_size - 1) // batch_size
        
        for i in range(0, len(test_segments), batch_size):
            batch_num = (i // batch_size) + 1
            batch = test_segments[i:i+batch_size]
            
            # Check if critical Segment 60 is in this batch
            segment_60_in_batch = any(seg.get('segment_id') == 60 for seg in batch)
            if segment_60_in_batch:
                print(f"🚨 [KO-EN-{thread_id}] Processing batch {batch_num}/{total_batches} (includes SEGMENT 60)...")
            elif batch_num % 3 == 1 or batch_num == total_batches:
                print(f"⚙️ [KO-EN-{thread_id}] Processing batch {batch_num}/{total_batches}...")
            
            batch_results = pipeline.process_ko_en_batch_strict(batch)
            all_results.extend(batch_results)
        
        # Calculate metrics
        total_time = time.time() - start_time
        total_cost = sum(r.total_cost for r in all_results)
        avg_quality = sum(r.quality_score for r in all_results) / len(all_results)
        avg_verbosity = sum(r.verbosity_score for r in all_results) / len(all_results)
        total_issues = sum(len(r.qa_issues or []) for r in all_results)
        hallucinations = sum(1 for r in all_results if r.hallucination_detected)
        
        # Check critical Segment 60
        segment_60_result = next((r for r in all_results if r.segment_id == 60), None)
        segment_60_passed = segment_60_result and not segment_60_result.hallucination_detected
        
        result_summary = {
            'pipeline': 'KO-EN',
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
            'results': all_results
        }
        
        print(f"✅ [KO-EN-{thread_id}] Completed: {len(all_results)} segments in {total_time/60:.2f}min")
        return result_summary
        
    except Exception as e:
        print(f"❌ [KO-EN-{thread_id}] Failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Run parallel production tests for both pipelines"""
    print("🚀 PARALLEL PRODUCTION VALIDATION: BOTH PIPELINES SIMULTANEOUSLY")
    print("Maximum throughput with batch processing + parallelization")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Setup logging to be thread-safe
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s [%(threadName)s] %(levelname)s:%(name)s:%(message)s'
    )
    
    # Production test parameters
    EN_KO_SEGMENTS = 100  # Test 100 segments for EN-KO
    KO_EN_SEGMENTS = 50   # Test 50 segments for KO-EN (includes Segment 60)
    
    print(f"📋 PARALLEL TEST PLAN:")
    print(f"   EN-KO Pipeline: {EN_KO_SEGMENTS} segments (batch processing)")
    print(f"   KO-EN Pipeline: {KO_EN_SEGMENTS} segments (batch processing)")
    print(f"   Execution Mode: PARALLEL (simultaneous processing)")
    print(f"   Valkey Memory: Enabled with separate sessions")
    print(f"   QA Framework: Full validation active")
    
    overall_start_time = time.time()
    
    print(f"\n🔥 LAUNCHING PARALLEL PIPELINES...")
    print("=" * 80)
    
    # Use ThreadPoolExecutor for parallel execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="Pipeline") as executor:
        # Submit both pipelines simultaneously
        print(f"🚀 Submitting EN-KO pipeline...")
        en_ko_future = executor.submit(run_en_ko_pipeline_parallel, EN_KO_SEGMENTS)
        
        print(f"🚀 Submitting KO-EN pipeline...")
        ko_en_future = executor.submit(run_ko_en_pipeline_parallel, KO_EN_SEGMENTS)
        
        print(f"⏳ Both pipelines running in parallel...")
        
        # Wait for both to complete and get results
        print(f"⌛ Waiting for results...")
        en_ko_results = en_ko_future.result()
        ko_en_results = ko_en_future.result()
    
    total_parallel_time = time.time() - overall_start_time
    
    # Final assessment
    print(f"\n🏆 PARALLEL PROCESSING RESULTS")
    print("=" * 80)
    
    if en_ko_results and ko_en_results:
        total_segments = en_ko_results['segments_processed'] + ko_en_results['segments_processed']
        total_cost = en_ko_results['total_cost'] + ko_en_results['total_cost']
        
        print(f"📊 OVERALL PARALLEL METRICS:")
        print(f"   Total Segments Processed: {total_segments}")
        print(f"   Total Parallel Processing Time: {total_parallel_time/60:.2f} minutes")
        print(f"   Overall Average Quality: {(en_ko_results['avg_quality'] + ko_en_results['avg_quality'])/2:.3f}")
        print(f"   Total Production Cost: ${total_cost:.2f}")
        print(f"   Cost per Segment: ${total_cost/total_segments:.4f}")
        
        print(f"\n📈 INDIVIDUAL PIPELINE RESULTS:")
        print(f"   EN-KO: {en_ko_results['segments_processed']} segments, {en_ko_results['total_time']/60:.2f}min, Quality: {en_ko_results['avg_quality']:.3f}")
        print(f"   KO-EN: {ko_en_results['segments_processed']} segments, {ko_en_results['total_time']/60:.2f}min, Quality: {ko_en_results['avg_quality']:.3f}")
        
        print(f"\n🎯 CRITICAL SUCCESS METRICS:")
        print(f"   EN-KO Quality: {en_ko_results['avg_quality']:.3f} {'✅ EXCELLENT' if en_ko_results['avg_quality'] >= 0.85 else '✅ GOOD' if en_ko_results['avg_quality'] >= 0.75 else '⚠️ ACCEPTABLE'}")
        print(f"   KO-EN Quality: {ko_en_results['avg_quality']:.3f} {'✅ EXCELLENT' if ko_en_results['avg_quality'] >= 0.8 else '✅ GOOD' if ko_en_results['avg_quality'] >= 0.7 else '⚠️ ACCEPTABLE'}")
        print(f"   Segment 60 Test: {'✅ PASSED' if ko_en_results['segment_60_passed'] else '❌ FAILED'}")
        print(f"   Parallel Processing: ✅ SUCCESSFUL")
        print(f"   Both Pipelines: ✅ COMPLETED SIMULTANEOUSLY")
        
        # Performance comparison
        sequential_time = en_ko_results['total_time'] + ko_en_results['total_time']
        parallel_speedup = ((sequential_time - total_parallel_time) / sequential_time) * 100
        
        print(f"\n⚡ PARALLELIZATION BENEFITS:")
        print(f"   Sequential Time: {sequential_time/60:.2f} minutes")
        print(f"   Parallel Time: {total_parallel_time/60:.2f} minutes") 
        print(f"   Parallel Speedup: {parallel_speedup:.1f}% faster")
        print(f"   Time Saved: {(sequential_time - total_parallel_time)/60:.1f} minutes")
        
        print(f"\n💰 BUSINESS METRICS:")
        print(f"   Production Cost: ${total_cost:.2f} for {total_segments} segments")
        print(f"   Estimated 1000 segments: ${(total_cost/total_segments)*1000:.2f}")
        print(f"   Estimated 4090 segments (full): ${(total_cost/total_segments)*4090:.2f}")
        
        # Extrapolation to full dataset
        print(f"\n🔮 FULL DATASET EXTRAPOLATION (2,690 EN-KO + 1,400 KO-EN):")
        en_ko_full_time = 2690 * en_ko_results['avg_time_per_segment'] / 60  # minutes
        ko_en_full_time = 1400 * ko_en_results['avg_time_per_segment'] / 60  # minutes
        parallel_full_time = max(en_ko_full_time, ko_en_full_time)  # Limited by slower pipeline
        
        print(f"   EN-KO Full: {en_ko_full_time:.1f} minutes ({en_ko_full_time/60:.1f} hours)")
        print(f"   KO-EN Full: {ko_en_full_time:.1f} minutes ({ko_en_full_time/60:.1f} hours)")
        print(f"   Parallel Full: {parallel_full_time:.1f} minutes ({parallel_full_time/60:.1f} hours)")
        
        full_cost = 4090 * (total_cost / total_segments)
        print(f"   Full Dataset Cost: ${full_cost:.2f}")
        
        print(f"\n🚀 PRODUCTION READINESS:")
        if (en_ko_results['avg_quality'] >= 0.8 and 
            ko_en_results['avg_quality'] >= 0.7 and 
            ko_en_results['segment_60_passed']):
            print("   Status: ✅ READY FOR PARALLEL PRODUCTION DEPLOYMENT")
            print("   Recommendation: Maximum throughput achieved with parallel processing")
        else:
            print("   Status: ⚠️ REQUIRES ADDITIONAL TUNING")
            print("   Recommendation: Address quality issues before full deployment")
    
    else:
        print("❌ Parallel processing incomplete - check error logs")
    
    print(f"\n✅ Parallel Production Validation Complete!")
    print(f"   Total Duration: {total_parallel_time/60:.2f} minutes")
    print(f"   Both pipelines processed simultaneously")
    print("=" * 80)

if __name__ == "__main__":
    main()