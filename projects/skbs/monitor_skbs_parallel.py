#!/usr/bin/env python3
"""
Monitor SKBS Parallel Translation Processes
Real-time dashboard showing progress of all parallel translation processes
"""

import os
import time
import subprocess
from datetime import datetime


def get_log_progress(log_file: str) -> dict:
    """Extract progress from log file"""
    result = {
        'exists': False,
        'last_progress': 'Waiting...',
        'segments_done': 0,
        'total_segments': 0,
        'percent': 0,
        'status': 'waiting'
    }

    if not os.path.exists(log_file):
        return result

    result['exists'] = True

    try:
        # Read last 50 lines for efficiency
        output = subprocess.run(
            ['tail', '-50', log_file],
            capture_output=True,
            text=True
        )
        lines = output.stdout.strip().split('\n')

        for line in reversed(lines):
            if '✅ Translation pipeline completed' in line:
                result['status'] = 'completed'
                result['percent'] = 100
                result['last_progress'] = 'COMPLETED'
                return result
            elif '❌ Fatal error' in line:
                result['status'] = 'error'
                result['last_progress'] = 'ERROR'
                return result
            elif '✓ [' in line and '%' in line:
                # Parse progress line: "✓ [0-170] 50/170 (29.4%) - ETA: 120s"
                try:
                    parts = line.split(']')[1].strip()
                    progress_part = parts.split('(')[0].strip()
                    done, total = progress_part.split('/')
                    result['segments_done'] = int(done)
                    result['total_segments'] = int(total)

                    pct_part = parts.split('(')[1].split('%')[0]
                    result['percent'] = float(pct_part)

                    eta_part = parts.split('ETA:')[1].strip() if 'ETA:' in parts else ''
                    result['last_progress'] = f"{done}/{total} ({result['percent']:.1f}%) ETA: {eta_part}"
                    result['status'] = 'running'
                    return result
                except:
                    pass
            elif 'Processing range' in line:
                result['status'] = 'running'
                result['last_progress'] = 'Starting...'

    except Exception as e:
        result['last_progress'] = f'Error reading: {e}'

    return result


def monitor_all():
    """Monitor all SKBS parallel processes"""
    log_dir = "/Users/won.suh/Project/translate-ai/phase2/logs"

    # Define processes to monitor
    processes = {
        'Adult 0-170': 'adult_0_170',
        'Adult 170-340': 'adult_170_340',
        'Adult 340-510': 'adult_340_510',
        'Adult 510-673': 'adult_510_673',
        'Child 0-45': 'child_0_45',
        'Child 45-89': 'child_45_89',
    }

    print("\n" + "=" * 80)
    print("🔍 SKBS Parallel Translation Monitor")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Press Ctrl+C to stop monitoring\n")

    try:
        while True:
            os.system('clear' if os.name != 'nt' else 'cls')

            print("=" * 80)
            print(f"🔍 SKBS Parallel Translation Monitor - {datetime.now().strftime('%H:%M:%S')}")
            print("=" * 80)

            all_completed = True
            total_done = 0
            total_segments = 0

            for name, pattern in processes.items():
                # Find matching log file (most recent)
                log_files = sorted([
                    f for f in os.listdir(log_dir)
                    if f.startswith(f'skbs_{pattern}') and f.endswith('.log')
                ], reverse=True)

                if log_files:
                    log_file = os.path.join(log_dir, log_files[0])
                    progress = get_log_progress(log_file)

                    status_emoji = {
                        'waiting': '⏳',
                        'running': '🔄',
                        'completed': '✅',
                        'error': '❌'
                    }.get(progress['status'], '❓')

                    print(f"{status_emoji} {name:15} | {progress['last_progress']}")

                    if progress['status'] != 'completed':
                        all_completed = False

                    total_done += progress['segments_done']
                    total_segments += progress['total_segments']
                else:
                    print(f"⏳ {name:15} | Waiting for log file...")
                    all_completed = False

            print("-" * 80)

            if total_segments > 0:
                overall_pct = (total_done / total_segments) * 100
                print(f"📊 Overall: {total_done}/{total_segments} ({overall_pct:.1f}%)")

            if all_completed:
                print("\n🎉 All processes completed!")
                break

            print(f"\n⏱️  Refreshing in 10 seconds... (Ctrl+C to stop)")
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped by user")


if __name__ == "__main__":
    monitor_all()
