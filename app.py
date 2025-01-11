from flask import Flask, request, render_template_string, send_from_directory, jsonify
import subprocess
import os
import tempfile
import logging
import shutil
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
SEGMENT_DURATION = 5  # Reduced for faster loading
streaming_active = {"value": True}

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stream Generator</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding: 20px; }
        .stream-url { word-break: break-all; }
    </style>
</head>
<body>
    <div class="container">
        <div class="row">
            <div class="col-md-8 offset-md-2">
                <div class="card">
                    <div class="card-header">
                        <h3>Stream Generator</h3>
                    </div>
                    <div class="card-body">
                        <form method="post">
                            <div class="mb-3">
                                <label for="video_url" class="form-label">Video URL (MP4)</label>
                                <input type="url" class="form-control" id="video_url" name="video_url" required>
                            </div>
                            <button type="submit" class="btn btn-primary">Generate Stream</button>
                            <button type="button" id="stop-stream" class="btn btn-danger">Stop Stream</button>
                        </form>
                        
                        {% if stream_url %}
                        <div class="mt-4 alert alert-success">
                            <h5>Stream URL:</h5>
                            <div class="stream-url">{{ stream_url }}</div>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('stop-stream').addEventListener('click', () => {
            fetch('/stop-stream', {method: 'POST'})
                .then(response => response.json())
                .then(data => alert('Stream stopped'));
        });
    </script>
</body>
</html>
"""

def process_video(video_url: str) -> Dict:
    """Simplified video processing"""
    try:
        segments_dir = os.path.join(UPLOAD_FOLDER, "segments")
        os.makedirs(segments_dir, exist_ok=True)
        
        output_file = os.path.join(segments_dir, "output.ts")
        
        # Convert directly to low-quality TS
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_url,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "30",
            "-c:a", "aac",
            "-b:a", "64k",
            "-f", "mpegts",
            output_file
        ]
        
        subprocess.run(ffmpeg_cmd, check=True)
        
        # Get duration
        duration_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            output_file
        ]
        
        duration = float(subprocess.check_output(duration_cmd).decode().strip())
        
        return {
            "duration": duration,
            "base_file": output_file
        }
    
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        raise

def create_playlist(duration: float) -> str:
    """Create simple HLS playlist"""
    return f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{SEGMENT_DURATION}
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:{SEGMENT_DURATION},
segments/output.ts
#EXT-X-ENDLIST"""

@app.route("/", methods=["GET", "POST"])
def index():
    stream_url = None
    if request.method == "POST":
        video_url = request.form["video_url"]
        try:
            process_video(video_url)
            stream_url = f"https://{request.host}/stream/playlist.m3u8"
        except Exception as e:
            return render_template_string(TEMPLATE, error=str(e))
    
    return render_template_string(TEMPLATE, stream_url=stream_url)

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
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
        if filename == "playlist.m3u8":
            playlist = create_playlist(0)
            response = app.response_class(
                playlist,
                mimetype='application/vnd.apple.mpegurl'
            )
        else:
            segments_dir = os.path.join(UPLOAD_FOLDER, "segments")
            response = send_from_directory(segments_dir, "output.ts")
            response.headers["Content-Type"] = "video/MP2T"
        
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response
        
    except Exception as e:
        logger.error(f"Error serving {filename}: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
