from flask import Flask, request, render_template_string, send_from_directory, jsonify 
import subprocess
import os
import tempfile
import threading
import time
import logging
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
streaming_active = {"value": True}
current_stream = {"ts_file": None, "duration": None, "video_url": None}

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
                            <div class="mb-4">
                                <label for="repeat_count" class="form-label h6">
                                    <i class="fas fa-redo me-2"></i>Number of Times to Play
                                </label>
                                <input type="number" class="form-control form-control-lg" 
                                       id="repeat_count" name="repeat_count" 
                                       placeholder="Enter number of times to play" 
                                       value="1" min="1" required>
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
                                <small class="d-block mt-2">
                                    <i class="fas fa-video me-2"></i>
                                    Currently playing: {{ current_video_url }}
                                </small>
                                <small class="d-block mt-2">
                                    <i class="fas fa-redo me-2"></i>
                                    Playing {{ repeat_count }} times
                                </small>
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

def concatenate_video(video_url, repeat_count):
    """
    Downloads and concatenates the video file specified number of times
    """
    try:
        # Create a temporary file for the original MP4
        temp_mp4 = os.path.join(UPLOAD_FOLDER, "temp_original.mp4")
        
        # Download original video
        download_cmd = [
            "ffmpeg",
            "-i", video_url,
            "-c", "copy",
            temp_mp4
        ]
        subprocess.run(download_cmd, check=True)

        # Create output file for concatenated video
        output_mp4 = os.path.join(UPLOAD_FOLDER, "concatenated.mp4")
        
        # Read the original file
        with open(temp_mp4, 'rb') as f:
            original_data = f.read()

        # Write the data repeated times
        with open(output_mp4, 'wb') as f:
            for _ in range(repeat_count):
                f.write(original_data)

        # Clean up original temp file
        os.remove(temp_mp4)
        
        return output_mp4
    except Exception as e:
        logger.error(f"Error in concatenation: {e}")
        raise e

def create_infinite_playlist(duration):
    base_playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{duration}
#EXT-X-MEDIA-SEQUENCE:{sequence}
#EXT-X-ALLOW-CACHE:NO
"""
    start_time = time.time()
    sequence = 0
    
    while streaming_active["value"]:
        current_playlist = base_playlist.format(
            duration=duration,
            sequence=sequence
        )
        
        elapsed_time = time.time() - start_time
        timestamp = elapsed_time % duration
        
        for i in range(3):  
            current_playlist += f"#EXTINF:{duration:.3f},\nchunk.ts?_t={timestamp + (i * duration)}\n"
        
        with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
            f.write(current_playlist)
        
        sequence += 1
        time.sleep(0.5)

@app.route("/", methods=["GET", "POST"])
def index():
    global streaming_active, current_stream
    stream_url = None
    current_video_url = None
    repeat_count = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        repeat_count = int(request.form["repeat_count"])
        streaming_active["value"] = True

        if not current_stream["ts_file"] or not os.path.exists(os.path.join(UPLOAD_FOLDER, "chunk.ts")):
            try:
                # Get duration of original video
                duration_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_url
                ]
                
                single_duration = float(subprocess.check_output(duration_cmd).decode().strip())
                total_duration = single_duration * repeat_count

                # Concatenate video
                concatenated_video = concatenate_video(video_url, repeat_count)
                
                # Convert concatenated video to TS format
                ffmpeg_cmd = [
                    "ffmpeg", 
                    "-i", concatenated_video,
                    "-vf", "scale=640:-1",
                    "-b:v", "500k",
                    "-b:a", "64k",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-c:a", "aac",
                    "-bsf:v", "h264_mp4toannexb",
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
                
                # Clean up concatenated file
                os.remove(concatenated_video)
                
                current_stream["ts_file"] = "chunk.ts"
                current_stream["duration"] = total_duration
                current_stream["video_url"] = video_url
                
            except Exception as e:
                logger.error(f"Error processing video: {e}")
                return render_template_string(TEMPLATE, error=str(e))

        playlist_thread = threading.Thread(
            target=create_infinite_playlist,
            args=(current_stream["duration"],)
        )
        playlist_thread.daemon = True
        playlist_thread.start()

        stream_url = f"https://{request.host}/stream/stream.m3u8"
        current_video_url = current_stream["video_url"]

    return render_template_string(
        TEMPLATE, 
        stream_url=stream_url, 
        current_video_url=current_video_url,
        repeat_count=repeat_count
    )

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
    global streaming_active
    streaming_active["value"] = False
    try:
        os.remove(os.path.join(UPLOAD_FOLDER, "stream.m3u8"))
    except:
        pass
    return jsonify({"status": "stopped"})

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
