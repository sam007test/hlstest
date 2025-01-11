from flask import Flask, request, render_template_string, send_from_directory, jsonify 
import subprocess
import os
import tempfile
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
streaming_active = {"value": True}
current_stream = {"ts_file": None, "duration": None, "video_url": None, "repeats": 1}

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Video Stream Generator</title>
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
        .stream-info {
            background: rgba(255,255,255,0.2);
            padding: 15px;
            border-radius: 8px;
            word-break: break-all;
            margin-top: 10px;
        }
    </style>
</head>
<body class="d-flex align-items-center py-4">
    <div class="container">
        <div class="row justify-content-center">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header">
                        <h3 class="text-white mb-0">
                            <i class="fas fa-broadcast-tower me-2"></i>
                            Video Stream Generator
                        </h3>
                    </div>
                    <div class="card-body p-4">
                        <form method="post" class="mb-4">
                            <div class="mb-3">
                                <label for="video_url" class="form-label h6">
                                    <i class="fas fa-link me-2"></i>Video URL
                                </label>
                                <input type="url" class="form-control form-control-lg" 
                                       id="video_url" name="video_url" 
                                       placeholder="Enter video URL (MP4)" required>
                            </div>
                            <div class="mb-4">
                                <label for="repeats" class="form-label h6">
                                    <i class="fas fa-redo me-2"></i>Number of Repeats
                                </label>
                                <input type="number" class="form-control form-control-lg" 
                                       id="repeats" name="repeats" 
                                       min="1" max="100" value="1" required>
                            </div>
                            <button type="submit" class="btn btn-primary">
                                <i class="fas fa-play me-2"></i>Generate Stream
                            </button>
                        </form>

                        {% if stream_url %}
                        <div class="mt-4">
                            <div class="alert alert-success">
                                <h5 class="mb-3">
                                    <i class="fas fa-check-circle me-2"></i>
                                    Stream Information
                                </h5>
                                <div class="stream-info">
                                    <p><strong>Source:</strong> {{ current_video_url }}</p>
                                    <p><strong>Repeats:</strong> {{ repeats }} times</p>
                                    <p><strong>Stream URL:</strong> {{ stream_url }}</p>
                                </div>
                            </div>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

def create_playlist(duration, repeats):
    base_playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{duration}
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
"""
    
    playlist = base_playlist.format(duration=int(duration))
    
    # Add repeated segments
    for i in range(repeats):
        playlist += f"#EXTINF:{duration:.3f},\nchunk.ts\n"
    
    # Add end marker
    playlist += "#EXT-X-ENDLIST\n"
    
    with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
        f.write(playlist)

@app.route("/", methods=["GET", "POST"])
def index():
    global current_stream
    stream_url = None
    current_video_url = None
    repeats = 1

    if request.method == "POST":
        video_url = request.form["video_url"]
        repeats = int(request.form["repeats"])
        current_video_url = video_url
        
        try:
            # Get video duration
            duration_cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_url
            ]
            
            duration = float(subprocess.check_output(duration_cmd).decode().strip())
            
            # Convert video to TS format with reduced quality
            ffmpeg_cmd = [
                "ffmpeg", 
                "-i", video_url,
                "-vf", "scale=640:-1",  # Scale video to 640px width
                "-b:v", "500k",         # Lower video bitrate
                "-b:a", "64k",          # Lower audio bitrate
                "-c:v", "libx264",      # H.264 codec
                "-preset", "veryfast",  # Faster preset
                "-c:a", "aac",          # AAC codec for audio
                "-f", "mpegts",
                f"{UPLOAD_FOLDER}/chunk.ts"
            ]

            subprocess.run(ffmpeg_cmd, check=True)
            
            current_stream = {
                "ts_file": "chunk.ts",
                "duration": duration,
                "video_url": video_url,
                "repeats": repeats
            }
            
            # Create the playlist
            create_playlist(duration, repeats)
            
            stream_url = f"http://{request.host}/stream/stream.m3u8"
            
        except Exception as e:
            logger.error(f"Error processing video: {e}")
            return render_template_string(TEMPLATE, error=str(e))

    return render_template_string(
        TEMPLATE, 
        stream_url=stream_url,
        current_video_url=current_video_url,
        repeats=repeats
    )

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    try:
        response = send_from_directory(UPLOAD_FOLDER, filename.split('?')[0])
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = "no-cache"
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
