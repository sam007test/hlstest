from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import tempfile

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.gettempdir()

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Video Stream</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        input[type="text"] { width: 100%; padding: 10px; margin: 10px 0; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }
        video { width: 100%; margin: 20px 0; }
        .error { color: red; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Video Stream</h1>
        <form method="POST">
            <input type="text" name="video_url" placeholder="Enter video URL" required>
            <input type="checkbox" name="loop" id="loop" checked>
            <label for="loop">Enable infinite loop</label>
            <button type="submit">Start Stream</button>
        </form>
        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
        {% if stream_url %}
        <video id="video" controls></video>
        <script>
            var video = document.getElementById('video');
            var loop = {{ loop_enabled|tojson }};
            
            if(Hls.isSupported()) {
                var hls = new Hls();
                hls.loadSource('{{ stream_url }}');
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, function() {
                    if(loop) {
                        video.loop = true;
                    }
                    video.play();
                });
            }
            else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                video.src = '{{ stream_url }}';
                if(loop) {
                    video.loop = true;
                }
                video.addEventListener('loadedmetadata', function() {
                    video.play();
                });
            }
        </script>
        {% endif %}
    </div>
</body>
</html>
"""

def process_video_to_hls(video_url, enable_loop=True):
    output_path = os.path.join(UPLOAD_FOLDER, "stream")
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    
    # Add loop input flag if looping is enabled
    input_args = ["-stream_loop", "-1"] if enable_loop else []
    
    ffmpeg_cmd = [
        "ffmpeg", 
        *input_args,
        "-i", video_url,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:v", "500k",
        "-b:a", "64k",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "0",
        "-hls_flags", "delete_segments",
        "-hls_segment_filename", f"{output_path}/segment_%03d.ts",
        f"{output_path}/playlist.m3u8"
    ]
    
    # Kill any existing FFmpeg processes
    try:
        subprocess.run(["pkill", "ffmpeg"])
    except:
        pass
    
    # Start new FFmpeg process
    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    return f"{output_path}/playlist.m3u8"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        video_url = request.form["video_url"]
        loop_enabled = 'loop' in request.form
        try:
            playlist_path = process_video_to_hls(video_url, loop_enabled)
            stream_url = f"http://{request.host}/stream/playlist.m3u8"
            return render_template_string(
                TEMPLATE, 
                stream_url=stream_url,
                loop_enabled=loop_enabled
            )
        except Exception as e:
            return render_template_string(TEMPLATE, error=str(e))
    
    return render_template_string(TEMPLATE)

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, "stream"), filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
