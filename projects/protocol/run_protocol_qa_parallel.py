#!/usr/bin/env python3
"""
Protocol QA System - Parallel Production Run
Orchestrates 4 parallel processes for validating all 2,178 segments
Similar to greencross_translation_pipeline_range.py

Flow:
1. Extract rules from reference documents (Processor 1)
2. Split 2,178 segments into 4 ranges
3. Launch 4 parallel processes (each validates its range)
4. Monitor all 4 processes
5. Merge results from all 4 processes
6. Generate final Excel report
"""

import json
import logging
import os
import sys
import subprocess
import time
from datetime import datetime
from typing import List, Dict, Tuple

import pandas as pd

# Load environment variables
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

sys.path.insert(0, os.path.dirname(__file__))

from protocol_qa_rule_extractor import ProtocolQARuleExtractor


class ProtocolQAParallelOrchestrator:
    """Orchestrates 4-process parallel QA validation"""

    def __init__(self):
        """Initialize"""
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        self.total_segments = 2178
        self.output_dir = "/tmp/protocol_qa_ranges"

    def setup_logging(self):
        """Setup logging"""
        logging.basicConfig(level=logging.INFO)

    def extract_rules(self) -> str:
        """
        Step 1: Extract rules from reference documents

        Returns:
            Path to rules JSON file
        """
        self.logger.info("")
        self.logger.info("=" * 100)
        self.logger.info("STEP 1: EXTRACT EN-KO RULES FROM REFERENCE DOCUMENTS")
        self.logger.info("=" * 100)

        extractor = ProtocolQARuleExtractor()
        rules_file = extractor.run()

        return rules_file

    def get_process_ranges(self) -> List[Tuple[int, int]]:
        """
        Step 2: Calculate 4 process ranges

        Returns:
            List of (start, end) tuples for each process
        """
        self.logger.info("")
        self.logger.info("=" * 100)
        self.logger.info("STEP 2: CALCULATE PROCESS RANGES")
        self.logger.info("=" * 100)

        # Split 2,178 segments into 4 roughly equal parts
        segment_per_process = self.total_segments // 4
        ranges = [
            (0, segment_per_process),
            (segment_per_process, segment_per_process * 2),
            (segment_per_process * 2, segment_per_process * 3),
            (segment_per_process * 3, self.total_segments)
        ]

        self.logger.info(f"\nSplitting {self.total_segments} segments into 4 processes:")
        for i, (start, end) in enumerate(ranges, 1):
            self.logger.info(f"  Process {i}: Rows {start:4d}-{end:4d} ({end-start:4d} segments)")

        return ranges

    def launch_parallel_processes(self, rules_file: str, ranges: List[Tuple[int, int]]):
        """
        Step 3: Launch 4 parallel processes

        Args:
            rules_file: Path to rules JSON
            ranges: List of (start, end) tuples
        """
        self.logger.info("")
        self.logger.info("=" * 100)
        self.logger.info("STEP 3: LAUNCH 4 PARALLEL PROCESSES")
        self.logger.info("=" * 100)

        os.makedirs(self.output_dir, exist_ok=True)

        processes = []
        for i, (start, end) in enumerate(ranges, 1):
            log_file = f"/tmp/protocol_qa_process_{i}_{start}_{end}.log"

            cmd = [
                "python3",
                "src/protocol_qa_validator_range.py",
                rules_file,
                str(start),
                str(end),
                "--output-dir", self.output_dir
            ]

            self.logger.info(f"\nLaunching Process {i}: {start}-{end}")
            self.logger.info(f"  Command: {' '.join(cmd)}")
            self.logger.info(f"  Log: {log_file}")

            with open(log_file, 'w') as f:
                proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
                processes.append({
                    'id': i,
                    'start': start,
                    'end': end,
                    'process': proc,
                    'log_file': log_file
                })

        return processes

    def monitor_processes(self, processes: List[Dict]) -> bool:
        """
        Step 4: Monitor all 4 processes

        Args:
            processes: List of process info dicts

        Returns:
            True if all succeeded, False otherwise
        """
        self.logger.info("")
        self.logger.info("=" * 100)
        self.logger.info("STEP 4: MONITOR 4 PARALLEL PROCESSES")
        self.logger.info("=" * 100)

        start_time = time.time()
        all_done = False
        iteration = 0

        while not all_done:
            iteration += 1
            all_done = True
            elapsed = int(time.time() - start_time)

            self.logger.info(f"\n[{elapsed}s] Status check - Iteration {iteration}:")

            for proc_info in processes:
                pid = proc_info['process'].pid
                status = "RUNNING" if proc_info['process'].poll() is None else "DONE"
                proc_info['status'] = status

                symbol = "⏳" if status == "RUNNING" else "✅"
                self.logger.info(f"  {symbol} Process {proc_info['id']} ({proc_info['start']}-{proc_info['end']}): {status} (PID: {pid})")

                if status == "RUNNING":
                    all_done = False

            if not all_done:
                time.sleep(10)  # Check every 10 seconds

        elapsed = int(time.time() - start_time)
        self.logger.info(f"\n✅ All processes completed in {elapsed} seconds ({elapsed//60}m {elapsed%60}s)")

        # Check for errors
        all_success = True
        for proc_info in processes:
            if proc_info['process'].returncode != 0:
                self.logger.error(f"❌ Process {proc_info['id']} failed with code {proc_info['process'].returncode}")
                all_success = False
            else:
                self.logger.info(f"✅ Process {proc_info['id']} completed successfully")

        return all_success

    def merge_results(self, processes: List[Dict]) -> str:
        """
        Step 5: Merge results from all 4 processes

        Args:
            processes: List of process info dicts

        Returns:
            Path to merged Excel report
        """
        self.logger.info("")
        self.logger.info("=" * 100)
        self.logger.info("STEP 5: MERGE RESULTS FROM ALL 4 PROCESSES")
        self.logger.info("=" * 100)

        # Collect CSV files from all processes
        csv_files = []
        for proc_info in processes:
            # Find CSV file for this process
            process_id = proc_info['id']
            start = proc_info['start']
            end = proc_info['end']

            # Look for CSV file matching pattern
            import glob
            pattern = f"{self.output_dir}/protocol_qa_range_{start}_{end}_*.csv"
            matching_files = glob.glob(pattern)

            if matching_files:
                csv_file = matching_files[0]  # Take most recent
                self.logger.info(f"  Process {process_id}: {csv_file}")
                csv_files.append((process_id, csv_file))
            else:
                self.logger.warning(f"  ⚠️  No CSV found for Process {process_id}")

        # Merge all CSV files
        all_results = []
        total_pass = 0
        total_fail = 0
        total_error = 0

        for proc_id, csv_file in csv_files:
            df = pd.read_csv(csv_file)
            all_results.append(df)

            # Count results
            pass_count = len(df[df['Status'] == 'PASS'])
            fail_count = len(df[df['Status'] == 'FAIL'])
            error_count = len(df[df['Status'] == 'ERROR'])

            self.logger.info(f"  Process {proc_id}: {len(df)} segments ({pass_count} PASS, {fail_count} FAIL, {error_count} ERROR)")

            total_pass += pass_count
            total_fail += fail_count
            total_error += error_count

        # Combine all dataframes
        merged_df = pd.concat(all_results, ignore_index=True)
        self.logger.info(f"\n✅ Merged {len(merged_df)} total segments")

        # Save merged Excel report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"/Users/won.suh/Downloads/Protocol_QA_Validation_PRODUCTION_{timestamp}.xlsx"
        merged_df.to_excel(output_file, index=False, engine='openpyxl')

        self.logger.info(f"  Saved to: {output_file}")

        # Log summary
        self.logger.info(f"\n📊 FINAL SUMMARY:")
        self.logger.info(f"  ✅ PASS: {total_pass} ({100*total_pass/(total_pass+total_fail+total_error):.1f}%)")
        self.logger.info(f"  ❌ FAIL: {total_fail} ({100*total_fail/(total_pass+total_fail+total_error):.1f}%)")
        self.logger.info(f"  ⚠️  ERROR: {total_error}")
        self.logger.info(f"  TOTAL: {total_pass + total_fail + total_error}")

        return output_file

    def run(self):
        """Execute full parallel QA process"""
        self.logger.info("")
        self.logger.info("╔" + "=" * 98 + "╗")
        self.logger.info("║" + " " * 15 + "PROTOCOL QA SYSTEM - PARALLEL PRODUCTION RUN" + " " * 38 + "║")
        self.logger.info("║" + " " * 15 + "Processing 2,178 segments in 4 parallel processes" + " " * 31 + "║")
        self.logger.info("╚" + "=" * 98 + "╝")

        try:
            start_time = time.time()

            # Step 1: Extract rules
            rules_file = self.extract_rules()

            # Step 2: Calculate ranges
            ranges = self.get_process_ranges()

            # Step 3: Launch processes
            processes = self.launch_parallel_processes(rules_file, ranges)

            # Step 4: Monitor processes
            success = self.monitor_processes(processes)

            if not success:
                self.logger.error("❌ One or more processes failed!")
                return

            # Step 5: Merge results
            final_report = self.merge_results(processes)

            elapsed = int(time.time() - start_time)
            self.logger.info("")
            self.logger.info("=" * 100)
            self.logger.info("✅ PROTOCOL QA PARALLEL PRODUCTION COMPLETE")
            self.logger.info("=" * 100)
            self.logger.info(f"  Total time: {elapsed} seconds ({elapsed//60}m {elapsed%60}s)")
            self.logger.info(f"  Final report: {final_report}")
            self.logger.info("")

        except Exception as e:
            self.logger.error(f"❌ Parallel process failed: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """Main entry point"""
    orchestrator = ProtocolQAParallelOrchestrator()
    orchestrator.run()


if __name__ == '__main__':
    main()
