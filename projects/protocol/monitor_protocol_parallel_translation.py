#!/usr/bin/env python3
"""
Monitor Protocol EN-KO Parallel Translation Progress
Tracks 4 concurrent range-based processes similar to GreenCross implementation
"""

import os
import sys
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))


class ParallelTranslationMonitor:
    """Monitor parallel protocol translation processes"""

    def __init__(self, total_segments: int = 910, num_processes: int = 4):
        self.total_segments = total_segments
        self.num_processes = num_processes
        self.segment_per_process = total_segments // num_processes
        self.processes = []
        self.process_outputs = {}

    def calculate_ranges(self) -> list:
        """Calculate segment ranges for parallel processing"""
        ranges = []
        for i in range(self.num_processes):
            start = i * self.segment_per_process
            # Last process gets remaining segments
            end = self.total_segments if i == self.num_processes - 1 else (i + 1) * self.segment_per_process
            ranges.append((start, end))
        return ranges

    def start_processes(self):
        """Start all parallel processes"""
        ranges = self.calculate_ranges()

        print(f"\n{'='*100}")
        print(f"🚀 STARTING PARALLEL PROTOCOL EN-KO TRANSLATION")
        print(f"  Total segments: {self.total_segments}")
        print(f"  Processes: {self.num_processes}")
        print(f"  Segments per process: {self.segment_per_process}")
        print(f"{'='*100}\n")

        for idx, (start, end) in enumerate(ranges, 1):
            log_file = f"/tmp/protocol_range_{start}_{end}.log"
            cmd = f"source /Users/won.suh/Project/translate-ai/phase2/venv_new/bin/activate && python /Users/won.suh/Project/translate-ai/phase2/src/protocol_translation_pipeline_en_ko_range.py {start} {end}"

            print(f"[Process {idx}] Starting range {start:4d}-{end:4d} → {log_file}")

            # Run in background
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=open(log_file, 'w'),
                stderr=subprocess.STDOUT,
                text=True
            )

            self.processes.append({
                'idx': idx,
                'proc': proc,
                'range': (start, end),
                'log_file': log_file,
                'start_time': time.time()
            })

        print(f"\n✅ All {self.num_processes} processes started\n")

    def monitor(self, check_interval: int = 10):
        """Monitor all processes"""
        start_time = time.time()

        try:
            while any(p['proc'].poll() is None for p in self.processes):
                # Print status every check_interval seconds
                elapsed = time.time() - start_time
                active = sum(1 for p in self.processes if p['proc'].poll() is None)

                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] Active: {active}/{self.num_processes} | "
                      f"Elapsed: {elapsed:.0f}s", end='', flush=True)

                time.sleep(check_interval)

            # All processes completed
            elapsed = time.time() - start_time
            print(f"\n\n✅ ALL PROCESSES COMPLETED in {elapsed:.1f}s\n")

            # Print summary
            self.print_summary(elapsed)

        except KeyboardInterrupt:
            print("\n\n⚠️  Terminating all processes...")
            for p in self.processes:
                p['proc'].terminate()
            sys.exit(1)

    def print_summary(self, total_elapsed: float):
        """Print completion summary"""
        print(f"{'='*100}")
        print(f"📊 PARALLEL TRANSLATION SUMMARY")
        print(f"{'='*100}")

        for p in self.processes:
            idx = p['idx']
            start, end = p['range']
            elapsed = time.time() - p['start_time']
            returncode = p['proc'].returncode
            status = "✅ SUCCESS" if returncode == 0 else f"❌ FAILED (code: {returncode})"

            print(f"Process {idx}: Range {start:4d}-{end:4d} | {elapsed:7.1f}s | {status}")

        print(f"{'='*100}")
        print(f"⏱️  Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
        print(f"📁 Output files: /Users/won.suh/Downloads/Protocol_EN_KO_range_*_*.xlsx")
        print(f"📋 Logs: /tmp/protocol_range_*.log")
        print(f"{'='*100}\n")

    def show_logs(self):
        """Show log files for inspection"""
        print("\n" + "="*100)
        print("📋 PROCESS LOGS")
        print("="*100 + "\n")

        for p in self.processes:
            print(f"\n--- Process {p['idx']} (Range {p['range'][0]}-{p['range'][1]}) ---")
            print(f"Log: {p['log_file']}\n")

            try:
                with open(p['log_file'], 'r') as f:
                    lines = f.readlines()
                    # Show last 20 lines
                    for line in lines[-20:]:
                        print(line.rstrip())
            except Exception as e:
                print(f"Could not read log: {e}")


def main():
    monitor = ParallelTranslationMonitor(total_segments=910, num_processes=4)

    # Start all 4 processes
    monitor.start_processes()

    # Monitor until completion
    monitor.monitor(check_interval=5)

    # Show summary and logs
    monitor.print_summary(0)
    # monitor.show_logs()  # Uncomment to view logs


if __name__ == '__main__':
    main()
