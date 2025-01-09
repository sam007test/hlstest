from flask import Flask, request, render_template_string, redirect, url_for
import subprocess
import os

app = Flask(__name__, static_folder='hls')

stream_process = None
hls_output_dir = "hls"

# Ensure the HLS output directory exists
if not os.path.exists(hls_output_dir):
    os.makedirs(hls_output_dir)

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HLS Streamer</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha3/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- HLS.js -->
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
</head>
<body class="bg-light">
    <div class="container py-5">
        <h1 class="text-center text-primary mb-4">HLS Streamer</h1>
        <div class="card shadow">
            <div class="card-body">
                <form method="post" class="mb-3">
                    <div class="mb-3">
                        <label for="mp4_url" class="form-label">MP4 URL</label>
                        <input type="url" class="form-control" id="mp4_url" name="mp4_url" 
                               placeholder="Enter MP4 URL (e.g., https://example.com/video.mp4)" required>
                    </div>
                    <button type="submit" name="start" class="btn btn-primary w-100 mb-2">Start Streaming</button>
                </form>
                
                {% if stream_url %}
                <div class="alert alert-success">
                    <strong>Stream URL:</strong> 
                    <a href="{{ stream_url }}" target="_blank">{{ stream_url }}</a>
                </div>
                <div class="mb-3">
                    <video id="video" class="w-100" controls></video>
                </div>
                <form method="post">
                    <button type="submit" name="stop" class="btn btn-danger w-100">Stop Streaming</button>
                </form>
                {% endif %}
            </div>
        </div>
    </div>

    <!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha3/dist/js/bootstrap.bundle.min.js"></script>
    
    <!-- HLS Player Script -->
    <script>
        {% if stream_url %}
        document.addEventListener('DOMContentLoaded', function() {
            var video = document.getElementById('video');
            if(Hls.isSupported()) {
                var hls = new Hls({
                    debug: true,
                    enableWorker: true
                });
                hls.loadSource('{{ stream_url }}');
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, function() {
                    video.play();
                });
            }
            // For browsers that have native HLS support (Safari/iOS)
            else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = '{{ stream_url }}';
                video.addEventListener('loadedmetadata', function() {
                    video.play();
                });
            }
        });
        {% endif %}
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    global stream_process
    stream_url = None
    
    if request.method == "POST":
        if "start" in request.form:
            mp4_url = request.form["mp4_url"]
            if stream_process:
                stream_process.terminate()
            
            stream_process = subprocess.Popen([
                "ffmpeg",
                "-i", mp4_url,
                "-c:v", "copy",
                "-c:a", "copy",
                "-hls_time", "2",
                "-hls_list_size", "0",
                "-hls_segment_filename", f"{hls_output_dir}/segment%d.ts",
                "-hls_flags", "delete_segments",
                "-f", "hls",
                f"{hls_output_dir}/playlist.m3u8"
            ])
            
            base_url = request.host_url.rstrip("/")
            stream_url = f"{base_url}/hls/playlist.m3u8"
            
        elif "stop" in request.form:
            if stream_process:
                stream_process.terminate()
                stream_process = None
                # Clean up HLS output
                for file in os.listdir(hls_output_dir):
                    os.remove(os.path.join(hls_output_dir, file))
    
    return render_template_string(TEMPLATE, stream_url=stream_url)

@app.route("/hls/<path:filename>")
def hls_files(filename):
    response = app.send_from_directory(hls_output_dir, filename)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
