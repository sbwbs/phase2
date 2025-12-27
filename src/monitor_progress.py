#!/usr/bin/env python3
"""
Monitor progress of full production translation run
"""

import glob
import os
import time
import subprocess
import sys
from pathlib import Path

def get_progress_info():
    """Get current progress from translated files"""
    translated_files = glob.glob("/Users/won.suh/Downloads/Bilingual files/*translated*.xlsx")

    if not translated_files:
        return None

    latest_file = max(translated_files, key=os.path.getctime)
    file_size = os.path.getsize(latest_file)
    mod_time = os.path.getmtime(latest_file)

    # Try to read segment count from file
    try:
        import pandas as pd
        df = pd.read_excel(latest_file, nrows=1)
        total_in_file = len(pd.read_excel(latest_file))
        return {
            'file': os.path.basename(latest_file),
            'size': file_size,
            'segments': total_in_file,
            'mod_time': mod_time
        }
    except:
        return {
            'file': os.path.basename(latest_file),
            'size': file_size,
            'mod_time': mod_time
        }

def format_size(size_bytes):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"

def monitor():
    """Monitor progress"""
    print("\n" + "="*100)
    print("📊 GreenCross Translation - Production Run Monitor")
    print("="*100)

    start_time = time.time()
    last_size = 0
    last_check = start_time

    while True:
        info = get_progress_info()

        if info:
            elapsed = int(time.time() - start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60

            size_diff = info['size'] - last_size
            time_diff = time.time() - last_check
            speed = (size_diff / time_diff / 1024 / 1024) if time_diff > 0 else 0  # MB/s

            print(f"\n⏱️  Elapsed: {minutes}m {seconds}s")
            print(f"📄 File: {info['file']}")
            print(f"💾 Size: {format_size(info['size'])}")
            if 'segments' in info:
                print(f"📋 Segments: {info['segments']}")
            if speed > 0:
                print(f"⚡ Write speed: {speed:.2f} MB/s")

            last_size = info['size']
            last_check = time.time()

        # Check if process is still running
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        if 'greencross_translation_pipeline.py' not in result.stdout:
            print("\n✅ Translation process completed!")
            return info

        time.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    try:
        final_info = monitor()
        print("\n" + "="*100)
        print("✅ Full production run complete")
        print("="*100)
    except KeyboardInterrupt:
        print("\n\n⛔ Monitoring stopped by user")
