import subprocess
import time
import re

def run_ffmpeg_with_progress(ffmpeg_cmd, progress_callback):
    """
    Runs the given ffmpeg command while parsing the '-progress pipe:1' output
    to provide real-time updates to 'progress_callback'.
    """
    # Insert the '-progress pipe:1' and '-nostats' options to the command,
    # so FFmpeg sends progress info to stdout where we can parse it
    cmd = ffmpeg_cmd + ["-progress", "pipe:1", "-nostats"]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    for line in process.stdout:
        # Example lines that FFmpeg prints when '-progress pipe:1' is used:
        # out_time_ms=1290000
        # progress=continue
        line = line.strip()
        if line.startswith("out_time_ms="):
            ms_value = int(line.split("=")[1])
            # Convert to seconds or a fraction of total to get progress
            seconds = ms_value / 1000000.0
            # Example: call progress_callback with seconds or a percentage
            progress_callback(seconds)
        elif line.startswith("progress=") and "end" in line:
            break

    process.wait()
    return process.returncode
