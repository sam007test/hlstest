from flask import Flask, request, render_template_string, send_from_directory, jsonify
import subprocess
import os
import tempfile
import threading
import time
import logging
import glob
import shutil
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
PROCESSED_FOLDER = os.path.join(UPLOAD_FOLDER, "processed")
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

progress = {
    "value": 0,
    "status": "Waiting",
    "processed": False
}

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stream Generator</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .progress { height: 30px; }
        .progress-bar { transition: width 0.4s; }
    </style>
</head>
<body class="bg-light">
    <div class="container py-4">
        <div class="row justify-content-center">
            <div class="col-md-8">
                <div class="card shadow">
                    <div class="card-header bg-primary text-white">
                        <h3 class="mb-0">Stream Generator</h3>
                    </div>
                    <div class="card-body">
                        <form method="post">
                            <div class="mb-3">
                                <label for="video_url" class="form-label">Video URL</label>
                                <input type="url" class="form-control" id="video_url" name="video_url" 
                                       placeholder="Enter video URL (MP4)" required>
                            </div>
                            <button type="submit" class="btn btn-primary">Generate Stream</button>
                        </form>

                        <div class="mt-3">
                            <div class="progress">
                                <div id="progress-bar" class="progress-bar bg-success" role="progressbar" style="width: 0%"></div>
                            </div>
                            <small class="text-muted" id="progress-text">Waiting to start...</small>
                        </div>

                        {% if stream_url %}
                        <div class="mt-4">
                            <div class="alert alert-success">
                                <h5>Your Stream URL:</h5>
                                <p class="mb-2">{{ stream_url }}</p>
                                <small class="text-muted">Use this URL in your media player</small>
                            </div>
                        </div>
                        {% endif %}

                        {% if error %}
                        <div class="mt-4">
                            <div class="alert alert-danger">
                                <h5>Error:</h5>
                                <p>{{ error }}</p>
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
            const progressBar = document.getElementById("progress-bar");
            const progressText = document.getElementById("progress-text");

            function updateProgress() {
                fetch("/progress")
                    .then(response => response.json())
                    .then(data => {
                        const progress = data.value;
                        const status = data.status;
                        progressBar.style.width = progress + "%";
                        progressText.textContent = status;
                        if (!data.processed) {
                            setTimeout(updateProgress, 500);
                        }
                    });
            }
            updateProgress();
        });
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

def process_video_once(video_url, output_path):
    """Process video once and save segments"""
    try:
        logger.info("Initial video processing started")
        progress["status"] = "Processing video..."
        
        ffmpeg_cmd = [
            "ffmpeg", "-i", video_url,
            "-c:v", "copy",
            "-c:a", "copy",
            "-hls_time", "2",
            "-hls_list_size", "0",
            "-hls_segment_type", "mpegts",
            "-hls_flags", "independent_segments",
            "-hls_segment_filename", f"{output_path}/segment%03d.ts",
            "-f", "hls",
            f"{output_path}/playlist.m3u8"
        ]
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        while process.poll() is None:
            progress["value"] = min(progress["value"] + 2, 90)
            time.sleep(0.5)
        
        progress["value"] = 100
        progress["status"] = "Processing complete! Stream is ready."
        logger.info("Video processing completed")
        return True
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        progress["status"] = f"Error: {str(e)}"
        return False

def create_live_stream(processed_path, stream_path):
    """Create continuous live stream from processed segments"""
    try:
        while True:
            # Create live playlist
            with open(f"{processed_path}/playlist.m3u8", 'r') as source:
                with open(stream_path, 'w') as target:
                    content = source.read()
                    target.write("#EXT-X-VERSION:3\n")
                    target.write("#EXT-X-TARGETDURATION:2\n")
                    target.write("#EXT-X-MEDIA-SEQUENCE:0\n")
                    target.write(content)
            
            # Copy segments if needed
            segments = glob.glob(f"{processed_path}/segment*.ts")
            for segment in segments:
                target_segment = os.path.join(os.path.dirname(stream_path), os.path.basename(segment))
                if not os.path.exists(target_segment):
                    shutil.copy2(segment, target_segment)
            
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"Error in live stream: {e}")

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        stream_path = os.path.join(UPLOAD_FOLDER, "stream.m3u8")
        processed_path = os.path.join(PROCESSED_FOLDER, "video")
        os.makedirs(processed_path, exist_ok=True)
        
        progress["value"] = 0
        progress["status"] = "Starting..."
        progress["processed"] = False

        def setup_stream():
            # Process video once
            if process_video_once(video_url, processed_path):
                progress["processed"] = True
                # Start continuous live stream
                create_live_stream(processed_path, stream_path)

        stream_thread = threading.Thread(target=setup_stream)
        stream_thread.daemon = True
        stream_thread.start()

        stream_url = f"https://{request.host}/stream/stream.m3u8"

    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route("/progress")
def get_progress():
    return jsonify(progress)

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    try:
        response = send_from_directory(UPLOAD_FOLDER, filename)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = "no-cache"
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
