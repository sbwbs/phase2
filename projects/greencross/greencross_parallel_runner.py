#!/usr/bin/env python3
"""
GreenCross Parallel Translation Runner
Runs 4 concurrent processes to translate 1,997 segments in ~2 hours instead of 8

Usage:
    python greencross_parallel_runner.py              # Run all 4 processes
    python greencross_parallel_runner.py --monitor    # Monitor existing processes
"""

import os
import sys
import subprocess
import time
import logging
from datetime import datetime
import pandas as pd
import glob

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ParallelTranslationRunner:
    """Run translation in parallel chunks"""

    def __init__(self):
        self.total_segments = 1997
        self.num_processes = 4
        self.segment_chunk_size = (self.total_segments + self.num_processes - 1) // self.num_processes
        self.processes = []
        self.output_files = []

    def calculate_ranges(self):
        """Calculate segment ranges for each process"""
        ranges = []
        for i in range(self.num_processes):
            start_idx = i * self.segment_chunk_size
            end_idx = min((i + 1) * self.segment_chunk_size, self.total_segments)
            if start_idx < self.total_segments:
                ranges.append((i + 1, start_idx, end_idx))
        return ranges

    def run_parallel(self):
        """Launch 4 parallel translation processes"""
        ranges = self.calculate_ranges()

        print("\n" + "=" * 100)
        print("🚀 GREENCROSS PARALLEL TRANSLATION - 4 CONCURRENT PROCESSES")
        print("=" * 100)
        print(f"\nStarting translation of {self.total_segments} segments across {len(ranges)} processes")
        print(f"Expected completion time: ~2 hours (vs 8 hours sequential)\n")

        for process_num, start_idx, end_idx in ranges:
            num_segs = end_idx - start_idx
            cmd = f"source venv_new/bin/activate && python src/greencross_translation_pipeline_range.py {start_idx} {end_idx}"

            print(f"\n📍 Process {process_num}/4:")
            print(f"   Segments: {start_idx:4d} - {end_idx:4d} ({num_segs:4d} segments)")
            print(f"   Estimated time: ~{num_segs * 15.05 / 60:.0f} minutes")
            print(f"   Command: {cmd}")

            # Launch in background
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd="/Users/won.suh/Project/translate-ai/phase2"
            )
            self.processes.append((process_num, start_idx, end_idx, proc))

        print("\n" + "=" * 100)
        print("⏱️  MONITORING PROGRESS")
        print("=" * 100)

        # Monitor all processes
        self._monitor_processes()

    def _monitor_processes(self):
        """Monitor progress of all running processes"""
        start_time = time.time()

        while any(p[3].poll() is None for p in self.processes):
            elapsed = int(time.time() - start_time)
            print(f"\n[{elapsed:5d}s elapsed] Status:")

            for process_num, start_idx, end_idx, proc in self.processes:
                status = "🟢 Running" if proc.poll() is None else "🟡 Completed"
                print(f"  Process {process_num}/4: {status}")

            time.sleep(30)

        elapsed = int(time.time() - start_time)
        print(f"\n✅ All processes completed in {elapsed}s ({elapsed/60:.1f} minutes)")

        # Collect results
        self._collect_results()

    def _collect_results(self):
        """Collect and merge results from all processes"""
        print("\n" + "=" * 100)
        print("📊 RESULTS")
        print("=" * 100)

        all_results = []

        for process_num, start_idx, end_idx, proc in self.processes:
            stdout, stderr = proc.communicate()
            returncode = proc.returncode

            print(f"\nProcess {process_num}/4 (segments {start_idx}-{end_idx}):")
            print(f"  Return code: {returncode}")

            if returncode == 0:
                print(f"  ✅ Completed successfully")
                # Find output file for this range
                files = glob.glob("/Users/won.suh/Downloads/Bilingual files/*translated*.xlsx")
                if files:
                    latest = max(files, key=os.path.getctime)
                    df = pd.read_excel(latest)
                    translated_count = df['Target segment'].notna().sum()
                    print(f"  📄 Output: {os.path.basename(latest)}")
                    print(f"  Segments translated: {translated_count}")
            else:
                print(f"  ❌ Failed with return code {returncode}")
                if stderr:
                    print(f"  Error: {stderr[:200]}")

        print("\n" + "=" * 100)
        print("✅ PARALLEL TRANSLATION COMPLETE")
        print("=" * 100)


def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == '--monitor':
        print("Monitor mode not yet implemented")
        return

    runner = ParallelTranslationRunner()
    runner.run_parallel()


if __name__ == "__main__":
    main()
