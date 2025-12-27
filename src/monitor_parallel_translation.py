#!/usr/bin/env python3
"""
Real-Time Monitoring Dashboard for Parallel Translation Processes
Monitors all 4 processes and displays unified statistics

Usage:
    python monitor_parallel_translation.py

    Then in another terminal:
    python greencross_translation_pipeline_range.py 0 500 &
    python greencross_translation_pipeline_range.py 500 1000 &
    python greencross_translation_pipeline_range.py 1000 1500 &
    python greencross_translation_pipeline_range.py 1500 1997 &
"""

import os
import sys
import time
import glob
from pathlib import Path
from datetime import datetime
import re


class ParallelTranslationMonitor:
    """Monitor all 4 parallel translation processes"""

    def __init__(self, log_dir="/Users/won.suh/Project/translate-ai/phase2/logs"):
        self.log_dir = log_dir
        self.ranges = [(0, 500), (500, 1000), (1000, 1500), (1500, 1997)]
        self.process_stats = {
            f"{start}-{end}": {
                'segments_processed': 0,
                'total_segments': end - start,
                'glossary_matches': 0,
                'tm_matches': 0,
                'qa_issues': 0,
                'api_calls': 0,
                'status': 'waiting',
                'last_log_line': ''
            }
            for start, end in self.ranges
        }

    def find_log_files(self):
        """Find the latest log files for each range"""
        log_files = {}
        for start, end in self.ranges:
            pattern = f"{self.log_dir}/greencross_range_{start}_{end}_*.log"
            files = glob.glob(pattern)
            if files:
                # Get most recent
                log_files[f"{start}-{end}"] = max(files, key=os.path.getctime)
        return log_files

    def parse_log_file(self, log_file: str, key: str):
        """Parse log file for statistics"""
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            if not lines:
                return

            # Get last line for status
            for line in reversed(lines):
                if line.strip():
                    self.process_stats[key]['last_log_line'] = line.strip()
                    break

            # Parse progress
            for line in lines:
                if 'Progress:' in line and 'segments' in line:
                    # Extract "✓ Progress: 50/500 segments (10%)"
                    match = re.search(r'(\d+)/(\d+)', line)
                    if match:
                        processed = int(match.group(1))
                        total = int(match.group(2))
                        self.process_stats[key]['segments_processed'] = processed

                if 'Glossary matches:' in line:
                    match = re.search(r'Glossary matches: (\d+)', line)
                    if match:
                        self.process_stats[key]['glossary_matches'] = int(match.group(1))

                if 'TM matches:' in line:
                    match = re.search(r'TM matches: (\d+)', line)
                    if match:
                        self.process_stats[key]['tm_matches'] = int(match.group(1))

                if 'QA issues:' in line:
                    match = re.search(r'QA issues: (\d+)', line)
                    if match:
                        self.process_stats[key]['qa_issues'] = int(match.group(1))

                if 'API calls:' in line:
                    match = re.search(r'API calls: (\d+)', line)
                    if match:
                        self.process_stats[key]['api_calls'] = int(match.group(1))

                # Status detection
                if 'Starting translation' in line:
                    self.process_stats[key]['status'] = '🟡 Processing'
                elif 'completed successfully' in line:
                    self.process_stats[key]['status'] = '🟢 Completed'
                elif 'Error' in line or 'error' in line:
                    self.process_stats[key]['status'] = '🔴 Error'

        except Exception as e:
            self.process_stats[key]['status'] = f'❌ Read Error: {str(e)[:30]}'

    def display_dashboard(self):
        """Display unified dashboard"""
        os.system('clear' if os.name == 'posix' else 'cls')

        print("=" * 130)
        print(f"🔄 GREENCROSS PARALLEL TRANSLATION MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 130)
        print()

        log_files = self.find_log_files()

        # Parse all log files
        for key in self.process_stats:
            if key in log_files:
                self.parse_log_file(log_files[key], key)

        # Display status for each process
        total_processed = 0
        total_segments = 0
        total_glossary = 0
        total_tm = 0
        total_qa = 0
        total_api = 0

        for start, end in self.ranges:
            key = f"{start}-{end}"
            stats = self.process_stats[key]

            processed = stats['segments_processed']
            total = stats['total_segments']
            pct = (processed * 100 // total) if total > 0 else 0

            progress_bar = self._create_progress_bar(processed, total)

            print(f"📍 Process {key} (segments {start:4d}-{end:4d})")
            print(f"   Status: {stats['status']}")
            print(f"   Progress: {progress_bar} {processed:4d}/{total:4d} ({pct:3d}%)")
            print(f"   📚 Glossary: {stats['glossary_matches']:4d} | 📖 TM: {stats['tm_matches']:4d} | ⚠️  QA: {stats['qa_issues']:4d} | 🔌 API: {stats['api_calls']:4d}")
            print(f"   Last: {stats['last_log_line'][:100]}")
            print()

            total_processed += processed
            total_segments += total
            total_glossary += stats['glossary_matches']
            total_tm += stats['tm_matches']
            total_qa += stats['qa_issues']
            total_api += stats['api_calls']

        # Display totals
        print("=" * 130)
        print("📊 TOTAL STATISTICS")
        print("=" * 130)
        total_pct = (total_processed * 100 // total_segments) if total_segments > 0 else 0
        total_progress = self._create_progress_bar(total_processed, total_segments)
        print(f"Overall Progress: {total_progress} {total_processed}/{total_segments} ({total_pct}%)")
        print(f"   📚 Total Glossary Matches: {total_glossary}")
        print(f"   📖 Total TM Matches: {total_tm}")
        print(f"   ⚠️  Total QA Issues: {total_qa}")
        print(f"   🔌 Total API Calls: {total_api}")
        print()

        # Log file locations
        print("=" * 130)
        print("📁 LOG FILES")
        print("=" * 130)
        for key, log_file in log_files.items():
            print(f"   {key}: {log_file}")
        print()

        # Commands
        print("=" * 130)
        print("💡 USEFUL COMMANDS")
        print("=" * 130)
        print(f"   tail -f {self.log_dir}/greencross_range_0_500_*.log")
        print(f"   tail -f {self.log_dir}/greencross_range_500_1000_*.log")
        print(f"   tail -f {self.log_dir}/greencross_range_1000_1500_*.log")
        print(f"   tail -f {self.log_dir}/greencross_range_1500_1997_*.log")
        print(f"   ps aux | grep greencross_translation_pipeline_range")
        print()
        print("   Press Ctrl+C to stop monitoring")
        print("=" * 130)

    def _create_progress_bar(self, current: int, total: int, width: int = 40) -> str:
        """Create visual progress bar"""
        if total == 0:
            filled = 0
        else:
            filled = int((current * width) // total)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}]"

    def start_monitoring(self, interval: int = 5):
        """Start continuous monitoring"""
        print(f"Starting monitoring (update every {interval}s)...")
        time.sleep(2)

        try:
            while True:
                self.display_dashboard()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\n✅ Monitoring stopped")
            sys.exit(0)


def main():
    """Main entry point"""
    monitor = ParallelTranslationMonitor()
    monitor.start_monitoring(interval=10)  # Update every 10 seconds


if __name__ == "__main__":
    main()
