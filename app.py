from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import tempfile
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Get timestamp for unique folder
timestamp = str(int(time.time()))
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), timestamp)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

current_process = None

@app.route('/', methods=['GET', 'POST'])
def index():
    global current_process
    error = None
    stream_url = None
    
    if request.method == 'POST':
        video_url = request.form['video_url']
        stream_path = os.path.join(UPLOAD_FOLDER, 'stream.m3u8')
        
        try:
            # Kill existing FFmpeg process if any
            if current_process:
                current_process.terminate()
            
            # Clean up old files
            for file in os.listdir(UPLOAD_FOLDER):
                if file.endswith('.ts') or file.endswith('.m3u8'):
                    try:
                        os.unlink(os.path.join(UPLOAD_FOLDER, file))
                    except:
                        pass

            ffmpeg_cmd = [
                'ffmpeg',
                '-stream_loop', '-1',
                '-i', video_url,
                '-c', 'copy',
                '-f', 'hls',
                '-hls_time', '1',
                '-hls_list_size', '5',
                '-hls_flags', 'delete_segments+append_list+omit_endlist',
                '-hls_segment_type', 'mpegts',
                stream_path
            ]
            
            current_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            time.sleep(2)
            
            if os.path.exists(stream_path):
                stream_url = f'http://{request.host}/stream/{timestamp}/stream.m3u8'
            else:
                error = "Failed to start stream"
                
        except Exception as e:
            error = str(e)
            logger.error(f"Error: {error}")
    
    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route('/stream/<timestamp>/<path:filename>')
def serve_stream(timestamp, filename):
    directory = os.path.join(tempfile.gettempdir(), timestamp)
    try:
        response = send_from_directory(directory, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stream Generator</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
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
                        
                        {% if stream_url %}
                        <div class="mt-4">
                            <div class="alert alert-success">
                                <h5>Your Stream URL:</h5>
                                <p class="mb-2">{{ stream_url }}</p>
                                <small class="text-muted">Use this URL in your media player (VLC, etc)</small>
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
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
