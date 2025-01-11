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
progress = {"value": 0}
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
        .progress { 
            height: 25px;
            background-color: #e9ecef;
            border-radius: 15px;
            box-shadow: inset 0 1px 2px rgba(0,0,0,.1);
        }
        .progress-bar { 
            transition: width 0.4s ease;
            border-radius: 15px;
            background: linear-gradient(45deg, #2193b0, #6dd5ed);
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
        .alert-danger {
            background: linear-gradient(45deg, #eb3349, #f45c43);
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
        #progress-text {
            margin-top: 8px;
            font-weight: 500;
            color: #1e3c72;
        }
        .icon-spin {
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
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
                                    <i class="fas fa-play me-2"></i>Generate Stream
                                </button>
                                <button type="button" id="stop-stream" class="btn btn-danger">
                                    <i class="fas fa-stop me-2"></i>Stop Stream
                                </button>
                            </div>
                        </form>

                        <div class="mt-4">
                            <div class="progress">
                                <div id="progress-bar" class="progress-bar" role="progressbar" 
                                     style="width: 0%" aria-valuenow="0" aria-valuemin="0" 
                                     aria-valuemax="100"></div>
                            </div>
                            <div id="progress-text" class="text-center">
                                <i class="fas fa-circle-notch icon-spin me-2"></i>
                                Processing...
                            </div>
                        </div>

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

                        {% if error %}
                        <div class="mt-4">
                            <div class="alert alert-danger">
                                <h5 class="mb-2">
                                    <i class="fas fa-exclamation-triangle me-2"></i>
                                    Error
                                </h5>
                                <p class="mb-0">{{ error }}</p>
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
            const stopButton = document.getElementById("stop-stream");

            stopButton.addEventListener("click", () => {
                fetch("/stop-stream", {method: "POST"})
                    .then(response => response.json())
                    .then(data => {
                        progressText.innerHTML = '<i class="fas fa-stop-circle me-2"></i>Stream stopped';
                        progressBar.style.width = "0%";
                    });
            });

            function updateProgress() {
                fetch("/progress")
                    .then(response => response.json())
                    .then(data => {
                        const progress = data.value;
                        progressBar.style.width = progress + "%";
                        if (progress < 100) {
                            progressText.innerHTML = `<i class="fas fa-circle-notch icon-spin me-2"></i>Processing... ${progress}%`;
                            setTimeout(updateProgress, 500);
                        } else {
                            progressText.innerHTML = '<i class="fas fa-check-circle me-2"></i>Stream ready!';
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

def create_infinite_playlist(duration):
    playlist_content = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{duration}
#EXT-X-MEDIA-SEQUENCE:{sequence}
#EXTINF:{duration:.3f},
chunk.ts
"""
    
    sequence = 0
    while streaming_active["value"]:
        current_playlist = playlist_content.format(
            duration=duration,
            sequence=sequence
        )
            
        with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
            f.write(current_playlist)
            
        sequence += 1
        time.sleep(duration)

@app.route("/", methods=["GET", "POST"])
def index():
    global progress, streaming_active
    error = None
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        stream_path = os.path.join(UPLOAD_FOLDER, "stream.m3u8")
        progress["value"] = 0
        streaming_active["value"] = True

        def process_video():
            try:
                logger.info(f"Processing video URL: {video_url}")
                
                duration_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_url
                ]
                
                duration = float(subprocess.check_output(duration_cmd).decode().strip())
                
                ffmpeg_cmd = [
                    "ffmpeg", 
                    "-i", video_url,
                    "-c:v", "copy",
                    "-c:a", "copy",
                    "-f", "mpegts",
                    f"{UPLOAD_FOLDER}/chunk.ts"
                ]

                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
                
                process.wait()
                progress["value"] = 100
                
                playlist_thread = threading.Thread(
                    target=create_infinite_playlist,
                    args=(duration,)
                )
                playlist_thread.daemon = True
                playlist_thread.start()

            except Exception as e:
                logger.error(f"Error during video processing: {e}")
                progress["value"] = 100
                error = str(e)

        video_thread = threading.Thread(target=process_video)
        video_thread.daemon = True
        video_thread.start()

        stream_url = f"https://{request.host}/stream/stream.m3u8"

    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route("/progress")
def get_progress():
    return jsonify(progress)

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
    global streaming_active
    streaming_active["value"] = False
    for file in ["chunk.ts", "stream.m3u8"]:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, file))
        except:
            pass
    return jsonify({"status": "stopped"})

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
