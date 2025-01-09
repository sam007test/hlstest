from flask import Flask, request, render_template_string, send_from_directory, jsonify
import subprocess
import os
import tempfile
import threading
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
progress = {"value": 0}  # Dictionary to track progress globally

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
   <meta charset="UTF-8">
   <meta name="viewport" content="width=device-width, initial-scale=1">
   <title>Live Stream Generator</title>
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
                       <h3 class="mb-0">Live Stream Generator</h3>
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
                           <small class="text-muted" id="progress-text">Processing...</small>
                       </div>

                       {% if stream_url %}
                       <div class="mt-4">
                           <div class="alert alert-success">
                               <h5>Your Live Stream URL:</h5>
                               <p class="mb-2">{{ stream_url }}</p>
                               <small class="text-muted">Use this URL in your media player (VLC, etc)</small>
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
                       progressBar.style.width = progress + "%";
                       progressText.textContent = `Processing... ${progress}%`;
                       if (progress < 100) {
                           setTimeout(updateProgress, 500);
                       } else {
                           progressText.textContent = "Live Stream Ready!";
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

@app.route("/", methods=["GET", "POST"])
def index():
    global progress
    error = None
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        stream_path = os.path.join(UPLOAD_FOLDER, "stream.m3u8")
        progress["value"] = 0

        def process_video():
            try:
                logger.info(f"Processing video URL: {video_url}")

                # Clean up old files
                for file in os.listdir(UPLOAD_FOLDER):
                    if file.endswith(".ts") or file.endswith(".m3u8"):
                        os.unlink(os.path.join(UPLOAD_FOLDER, file))

                # FFmpeg command for infinite live stream
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-stream_loop", "-1",  # Loop infinitely
                    "-re",  # Read input at native frame rate
                    "-i", video_url,
                    "-c:v", "copy",
                    "-c:a", "copy",
                    "-hls_time", "6",
                    "-hls_list_size", "5",  # Keep the latest 5 segments for live streaming
                    "-hls_flags", "delete_segments+append_list",
                    "-hls_segment_filename", f"{UPLOAD_FOLDER}/segment%03d.ts",
                    "-method", "PUT",
                    "-f", "hls",
                    stream_path,
                ]

                logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
                process = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE, universal_newlines=True)

                # Simulate progress updates
                while process.poll() is None:
                    time.sleep(1)
                    progress["value"] = min(progress["value"] + 10, 100)

                progress["value"] = 100  # Processing complete
                logger.info("Live streaming initiated.")

            except Exception as e:
                logger.error(f"Error during live stream setup: {e}")
                progress["value"] = 100  # Stop progress on error

        threading.Thread(target=process_video).start()
        stream_url = f"https://{request.host}/stream/stream.m3u8"

    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)


@app.route("/progress")
def get_progress():
    global progress
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
