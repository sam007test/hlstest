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
streaming_active = {"value": False}

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
        body { background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); min-height: 100vh; }
        .card { border: none; border-radius: 15px; box-shadow: 0 10px 20px rgba(0,0,0,0.1); }
        .card-header { 
            background: linear-gradient(45deg, #1e3c72, #2a5298); 
            border-radius: 15px 15px 0 0 !important; 
            padding: 1.5rem; 
        }
        .btn-primary { background: linear-gradient(45deg, #1e3c72, #2a5298); border: none; }
        .btn-danger { background: linear-gradient(45deg, #cb2d3e, #ef473a); border: none; }
        .stream-url { 
            background: rgba(255,255,255,0.2); 
            padding: 15px; 
            border-radius: 8px; 
            word-break: break-all; 
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
                            Infinite Stream Generator
                        </h3>
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
                                    <i class="fas fa-play me-2"></i>Start Stream
                                </button>
                                <button type="button" id="stop-stream" class="btn btn-danger">
                                    <i class="fas fa-stop me-2"></i>Stop Stream
                                </button>
                            </div>
                        </form>

                        {% if stream_url %}
                        <div class="alert alert-success mt-4">
                            <h5 class="mb-2">Stream URL:</h5>
                            <div class="stream-url">{{ stream_url }}</div>
                        </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById("stop-stream").addEventListener("click", () => {
            fetch("/stop-stream", {method: "POST"})
                .then(response => response.json())
                .then(data => {
                    if(data.status === "stopped") {
                        window.location.href = "/";
                    }
                });
        });
    </script>
</body>
</html>
"""

def generate_playlist():
    while streaming_active["value"]:
        playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10,
stream.ts
"""
        with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
            f.write(playlist)
        time.sleep(1)

@app.route("/", methods=["GET", "POST"])
def index():
    global streaming_active
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        streaming_active["value"] = True

        try:
            # Direct stream copy to TS format
            ffmpeg_cmd = [
                "ffmpeg", "-i", video_url,
                "-c", "copy",
                "-f", "mpegts",
                "-loop", "1",
                f"{UPLOAD_FOLDER}/stream.ts"
            ]
            
            subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Start playlist generator
            playlist_thread = threading.Thread(target=generate_playlist)
            playlist_thread.daemon = True
            playlist_thread.start()

            stream_url = f"http://{request.host}/stream/stream.m3u8"
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return render_template_string(TEMPLATE, error=str(e))

    return render_template_string(TEMPLATE, stream_url=stream_url)

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
    global streaming_active
    streaming_active["value"] = False
    
    # Kill ffmpeg process
    subprocess.run(["pkill", "ffmpeg"])
    
    # Cleanup files
    for file in ["stream.m3u8", "stream.ts"]:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, file))
        except:
            pass
            
    return jsonify({"status": "stopped"})

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    response = send_from_directory(UPLOAD_FOLDER, filename)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
