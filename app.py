from flask import Flask, request, render_template_string, send_from_directory, jsonify
import subprocess
import os
import tempfile
import threading
import time
import logging
from typing import Dict, Optional
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
SEGMENT_DURATION = 10  # Duration of each segment in seconds
streaming_active = {"value": True}
current_stream = {
    "base_ts_file": None,
    "duration": None,
    "segments": {},
    "segment_count": 0,
    "processed_videos": set()  # Keep track of processed videos
}

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

def mock_segment_generator(video_url: str) -> Dict:
    """
    Instead of actually processing the video, generate mock segments
    """
    segments_dir = os.path.join(UPLOAD_FOLDER, "segments")
    os.makedirs(segments_dir, exist_ok=True)
    
    # Mock duration (1 minute)
    duration = 60.0
    segment_count = int(duration / SEGMENT_DURATION)
    
    # Create a small mock TS file if it doesn't exist
    mock_segment = os.path.join(segments_dir, "mock_segment.ts")
    if not os.path.exists(mock_segment):
        # Create a minimal valid TS file
        with open(mock_segment, 'wb') as f:
            f.write(b'\x47' * 188 * 100)  # Minimal TS packet
    
    return {
        "duration": duration,
        "segment_count": segment_count,
        "segments_dir": segments_dir,
        "mock_segment": mock_segment
    }

def create_infinite_playlist(duration: float, segment_count: int):
    """
    Create and continuously update the HLS playlist
    """
    base_playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{segment_duration}
#EXT-X-MEDIA-SEQUENCE:{sequence}
#EXT-X-ALLOW-CACHE:NO
"""
    
    sequence = 0
    
    while streaming_active["value"]:
        current_playlist = base_playlist.format(
            segment_duration=SEGMENT_DURATION,
            sequence=sequence
        )
        
        # Add segments to playlist
        for i in range(3):
            segment_index = (sequence + i) % segment_count
            current_playlist += f"#EXTINF:{SEGMENT_DURATION:.3f},\nsegments/mock_segment.ts?seg={segment_index}\n"
        
        with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
            f.write(current_playlist)
        
        sequence = (sequence + 1) % segment_count
        time.sleep(SEGMENT_DURATION / 2)

@app.route("/", methods=["GET", "POST"])
def index():
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        streaming_active["value"] = True

        try:
            # Generate mock segments if not already done
            if video_url not in current_stream["processed_videos"]:
                segment_info = mock_segment_generator(video_url)
                current_stream.update({
                    "duration": segment_info["duration"],
                    "segment_count": segment_info["segment_count"],
                    "mock_segment": segment_info["mock_segment"]
                })
                current_stream["processed_videos"].add(video_url)

            # Start playlist generator in a new thread
            playlist_thread = threading.Thread(
                target=create_infinite_playlist,
                args=(current_stream["duration"], current_stream["segment_count"])
            )
            playlist_thread.daemon = True
            playlist_thread.start()

            stream_url = f"https://{request.host}/stream/stream.m3u8"

        except Exception as e:
            logger.error(f"Error processing video: {e}")
            return render_template_string(TEMPLATE, error=str(e))

    return render_template_string(TEMPLATE, stream_url=stream_url)

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
    streaming_active["value"] = False
    try:
        os.remove(os.path.join(UPLOAD_FOLDER, "stream.m3u8"))
    except Exception as e:
        logger.error(f"Error cleaning up: {e}")
    return jsonify({"status": "stopped"})

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    try:
        if filename.startswith("segments/"):
            # Serve the mock segment
            segments_dir = os.path.join(UPLOAD_FOLDER, "segments")
            base_filename = filename.split('?')[0].split('/')[-1]
            return send_from_directory(segments_dir, "mock_segment.ts")
        else:
            # Serve m3u8 playlist
            response = send_from_directory(UPLOAD_FOLDER, filename)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Cache-Control"] = "no-cache"
            return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
