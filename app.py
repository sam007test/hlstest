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
                           <div class="mb-3">
                               <label for="loop_count" class="form-label">Loop Count</label>
                               <input type="number" class="form-control" id="loop_count" name="loop_count" 
                                      placeholder="Enter number of times to loop" value="1" min="1" required>
                           </div>
                           <button type="submit" class="btn btn-primary">Generate Stream</button>
                           <button type="button" id="stop-stream" class="btn btn-danger ms-2">Stop Stream</button>
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
                               <h5>Your Stream URL:</h5>
                               <p class="mb-2">{{ stream_url }}</p>
                               <small class="text-muted">Use this URL in your media player</small>
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
           const stopButton = document.getElementById("stop-stream");

           stopButton.addEventListener("click", () => {
               fetch("/stop-stream", {method: "POST"})
                   .then(response => response.json())
                   .then(data => {
                       progressText.textContent = "Stream stopped";
                   });
           });

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
                           progressText.textContent = "Stream ready!";
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
   global progress, streaming_active
   error = None
   stream_url = None

   if request.method == "POST":
       video_url = request.form["video_url"]
       loop_count = int(request.form["loop_count"])
       stream_path = os.path.join(UPLOAD_FOLDER, "stream.m3u8")
       progress["value"] = 0
       streaming_active["value"] = True

       def process_video():
           try:
               logger.info(f"Processing video URL: {video_url}")
               while streaming_active["value"]:
                   # Get video duration
                   duration_cmd = [
                       "ffprobe",
                       "-v", "error",
                       "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1",
                       video_url
                   ]
                   
                   duration = float(subprocess.check_output(duration_cmd).decode().strip())
                   segment_time = int(duration)

                   # Create input string with specified number of concatenations
                   input_str = ""
                   filter_str = ""
                   for i in range(loop_count):
                       input_str += f"-i {video_url} "
                       if i > 0:
                           filter_str += f"[{i}:v][{i}:a]"

                   ffmpeg_cmd = f"ffmpeg {input_str} -filter_complex '{filter_str}concat=n={loop_count}:v=1:a=1[outv][outa]' " \
                              f"-map '[outv]' -map '[outa]' " \
                              f"-c:v copy -c:a copy " \
                              f"-hls_time {str(segment_time)} " \
                              f"-hls_list_size 2 " \
                              f"-hls_flags delete_segments+independent_segments " \
                              f"-hls_segment_filename {UPLOAD_FOLDER}/segment%03d.ts " \
                              f"-f hls {stream_path}"

                   process = subprocess.Popen(
                       ffmpeg_cmd,
                       shell=True,
                       stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,
                       universal_newlines=True,
                   )

                   time.sleep(2)
                   progress["value"] = 100

                   process.wait()
                   
                   if not streaming_active["value"]:
                       break

           except Exception as e:
               logger.error(f"Error during video processing: {e}")
               progress["value"] = 100

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
