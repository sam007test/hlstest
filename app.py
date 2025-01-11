from flask import Flask, request, render_template_string, send_from_directory, jsonify
import subprocess
import os
import tempfile
import threading
import time
import logging
from collections import OrderedDict
import shutil
from typing import Dict, Optional
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
SEGMENT_DURATION = 10  # Duration of each segment in seconds
MAX_SEGMENTS = 3  # Maximum number of segments to keep in memory
SEGMENT_CACHE_SIZE = 5  # Number of segments to cache
streaming_active = {"value": True}

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Infinite Stream Generator</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.1);
        }
        .card-header {
            background: linear-gradient(45deg, #1e3c72, #2a5298);
            border-radius: 15px 15px 0 0 !important;
            padding: 1.5rem;
        }
        .form-control {
            border-radius: 10px;
            padding: 12px;
            border: 2px solid #e9ecef;
        }
        .form-control:focus {
            border-color: #2193b0;
            box-shadow: 0 0 0 0.2rem rgba(33, 147, 176, 0.25);
        }
        .btn {
            padding: 12px 25px;
            border-radius: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .btn-primary {
            background: linear-gradient(45deg, #1e3c72, #2a5298);
            border: none;
        }
        .btn-danger {
            background: linear-gradient(45deg, #cb2d3e, #ef473a);
            border: none;
        }
        .alert {
            border-radius: 10px;
            padding: 1.2rem;
        }
        .alert-success {
            background: linear-gradient(45deg, #43cea2, #185a9d);
            color: white;
            border: none;
        }
        .stream-url {
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 8px;
            word-break: break-all;
            margin-top: 10px;
        }
        .status-badge {
            position: absolute;
            top: 10px;
            right: 10px;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 0.8em;
        }
    </style>
</head>
<body class="d-flex align-items-center py-4">
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header position-relative">
                        <h3 class="text-white mb-0">
                            <i class="fas fa-broadcast-tower me-2"></i>
                            Infinite Stream Generator
                        </h3>
                        <span id="stream-status" class="status-badge bg-secondary text-white">
                            <i class="fas fa-circle me-1"></i>Idle
                        </span>
                    </div>
                    <div class="card-body p-4">
                        <form method="post" class="mb-4">
                            <div class="mb-4">
                                <label for="video_url" class="form-label h6">
                                    <i class="fas fa-link me-2"></i>Video URL
                                </label>
                                <input type="url" class="form-control form-control-lg" 
                                       id="video_url" name="video_url" 
                                       placeholder="Enter video URL (MP4)" required>
                            </div>
                            <div class="d-flex gap-2">
                                <button type="submit" class="btn btn-primary">
                                    <i class="fas fa-play me-2"></i>Generate Stream
                                </button>
                                <button type="button" id="stop-stream" class="btn btn-danger">
                                    <i class="fas fa-stop me-2"></i>Stop Stream
                                </button>
                            </div>
                        </form>

                        {% if stream_url %}
                        <div class="mt-4">
                            <div class="alert alert-success">
                                <h5 class="mb-3">
                                    <i class="fas fa-check-circle me-2"></i>
                                    Your Stream URL
                                </h5>
                                <div class="stream-url">{{ stream_url }}</div>
                                <small class="d-block mt-3">
                                    <i class="fas fa-info-circle me-2"></i>
                                    Use this URL in your media player
                                </small>
                            </div>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.addEventListener("DOMContentLoaded", () => {
            const stopButton = document.getElementById("stop-stream");
            const statusBadge = document.getElementById("stream-status");

            if ("{{ stream_url }}") {
                statusBadge.className = "status-badge bg-success text-white";
                statusBadge.innerHTML = '<i class="fas fa-circle me-1"></i>Streaming';
            }

            stopButton.addEventListener("click", () => {
                fetch("/stop-stream", {method: "POST"})
                    .then(response => response.json())
                    .then(data => {
                        statusBadge.className = "status-badge bg-secondary text-white";
                        statusBadge.innerHTML = '<i class="fas fa-circle me-1"></i>Stopped';
                    });
            });
        });
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

class StreamManager:
    def __init__(self):
        self.base_ts_file: Optional[str] = None
        self.duration: Optional[float] = None
        self.segment_cache = OrderedDict()  # LRU cache for segments
        self.cache_lock = threading.Lock()
        
    def clear(self):
        with self.cache_lock:
            self.segment_cache.clear()
            self.base_ts_file = None
            self.duration = None

stream_manager = StreamManager()

def process_video(video_url: str) -> Dict:
    """Process video and create base TS file with minimal memory usage"""
    segments_dir = os.path.join(UPLOAD_FOLDER, "segments")
    os.makedirs(segments_dir, exist_ok=True)

    # Clean up existing files
    shutil.rmtree(segments_dir)
    os.makedirs(segments_dir)
    
    # Get video duration using minimal resources
    duration_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_url
    ]
    
    try:
        duration = float(subprocess.check_output(duration_cmd).decode().strip())
    except subprocess.CalledProcessError as e:
        logger.error(f"Error getting duration: {e}")
        raise RuntimeError("Failed to process video duration")

    # Convert to low-bitrate TS format to save memory
    output_file = os.path.join(segments_dir, "base.ts")
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", video_url,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-b:v", "800k",  # Lower bitrate
        "-c:a", "aac",
        "-b:a", "128k",
        "-f", "mpegts",
        output_file
    ]
    
    try:
        subprocess.run(ffmpeg_cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error converting video: {e}")
        raise RuntimeError("Failed to convert video")

    return {
        "duration": duration,
        "base_ts_file": output_file
    }

def get_segment(timestamp: float, duration: float, base_file: str) -> bytes:
    """Get video segment with caching"""
    cache_key = f"{timestamp:.1f}"
    
    with stream_manager.cache_lock:
        if cache_key in stream_manager.segment_cache:
            return stream_manager.segment_cache[cache_key]
    
    try:
        offset = timestamp % duration if duration else 0
        
        process = subprocess.run([
            'ffmpeg',
            '-ss', str(offset),
            '-i', base_file,
            '-c', 'copy',
            '-t', str(SEGMENT_DURATION),
            '-f', 'mpegts',
            'pipe:1'
        ], capture_output=True, check=True)

        segment_data = process.stdout
        
        # Cache segment
        with stream_manager.cache_lock:
            stream_manager.segment_cache[cache_key] = segment_data
            if len(stream_manager.segment_cache) > SEGMENT_CACHE_SIZE:
                stream_manager.segment_cache.popitem(last=False)
        
        return segment_data
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Error generating segment: {e}")
        raise RuntimeError("Failed to generate segment")

def create_playlist(duration: float) -> str:
    """Create HLS playlist with minimal updates"""
    current_time = time.time()
    sequence = int(current_time / SEGMENT_DURATION)
    
    playlist = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{SEGMENT_DURATION}",
        f"#EXT-X-MEDIA-SEQUENCE:{sequence}",
        "#EXT-X-ALLOW-CACHE:NO"
    ]
    
    for i in range(MAX_SEGMENTS):
        timestamp = current_time + (i * SEGMENT_DURATION)
        playlist.extend([
            f"#EXTINF:{SEGMENT_DURATION:.3f},",
            f"segments/chunk.ts?t={timestamp:.3f}"
        ])
    
    return "\n".join(playlist)

@app.route("/", methods=["GET", "POST"])
def index():
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        streaming_active["value"] = True

        try:
            video_info = process_video(video_url)
            stream_manager.base_ts_file = video_info["base_ts_file"]
            stream_manager.duration = video_info["duration"]
            stream_url = f"https://{request.host}/stream/stream.m3u8"

        except Exception as e:
            logger.error(f"Error processing video: {e}")
            return render_template_string(TEMPLATE, error=str(e))

    return render_template_string(TEMPLATE, stream_url=stream_url)

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
    streaming_active["value"] = False
    stream_manager.clear()
    try:
        segments_dir = os.path.join(UPLOAD_FOLDER, "segments")
        if os.path.exists(segments_dir):
            shutil.rmtree(segments_dir)
    except Exception as e:
        logger.error(f"Error cleaning up: {e}")
    return jsonify({"status": "stopped"})

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    try:
        if filename.startswith("segments/"):
            timestamp = float(request.args.get('t', 0))
            
            if not stream_manager.base_ts_file or not stream_manager.duration:
                return "Stream not initialized", 500
                
            segment_data = get_segment(
                timestamp,
                stream_manager.duration,
                stream_manager.base_ts_file
            )
            
            response = app.response_class(
                segment_data,
                mimetype='video/MP2T'
            )
            response.headers.update({
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=60"
            })
            return response
            
        else:
            playlist_content = create_playlist(stream_manager.duration)
            response = app.response_class(
                playlist_content,
                mimetype='application/vnd.apple.mpegurl'
            )
            response.headers.update({
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache"
            })
            return response
            
    except Exception as e:
        logger.error(f"Error serving {filename}: {e}")
        return str(e), 500

@app.before_request
def check_memory():
    """Monitor memory usage and clean cache if necessary"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_percent = process.memory_percent()
        
        if memory_percent > 80:  # If using more than 80% of available memory
            stream_manager.clear()
            logger.warning("Memory usage high - cleared cache")
    except ImportError:
        pass  # psutil not available

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
