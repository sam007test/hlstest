from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import tempfile
import logging
import time
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'streams')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    stream_url = None
    
    if request.method == 'POST':
        video_url = request.form['video_url']
        stream_dir = os.path.join(UPLOAD_FOLDER, 'current')
        os.makedirs(stream_dir, exist_ok=True)
        stream_path = os.path.join(stream_dir, 'stream.m3u8')
        
        try:
            # Clean up old files
            for file in os.listdir(stream_dir):
                if file.endswith('.ts') or file.endswith('.m3u8'):
                    try:
                        os.unlink(os.path.join(stream_dir, file))
                    except Exception as e:
                        logger.error(f"Error cleaning up file {file}: {e}")

            # Kill any existing FFmpeg processes
            try:
                subprocess.run(['pkill', 'ffmpeg'])
            except Exception as e:
                logger.error(f"Error killing existing FFmpeg processes: {e}")

            ffmpeg_cmd = [
                'ffmpeg',
                '-stream_loop', '-1',
                '-re',
                '-i', video_url,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-f', 'hls',
                '-hls_time', '2',
                '-hls_list_size', '15',
                '-hls_flags', 'delete_segments+append_list+omit_endlist+discont_start',
                '-hls_segment_filename', os.path.join(stream_dir, 'segment%03d.ts'),
                '-live_start_index', '-3',
                stream_path
            ]
            
            logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
            
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                start_new_session=True
            )
            
            # Wait for initial segments
            time.sleep(3)
            
            if os.path.exists(stream_path):
                stream_url = f"http://{request.host}/stream/current/stream.m3u8"
                logger.info(f"Stream URL generated: {stream_url}")
            else:
                error = "Failed to generate stream"
                
        except Exception as e:
            error = f"Error: {str(e)}"
            logger.error(f"Error processing request: {e}")
            
    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route('/stream/<path:filename>')
def serve_stream(filename):
    try:
        dir_name = os.path.dirname(filename)
        base_name = os.path.basename(filename)
        stream_dir = os.path.join(UPLOAD_FOLDER, dir_name)
        response = send_from_directory(stream_dir, base_name)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == '__main__':
    port = 5000
    app.run(host='0.0.0.0', port=port)
