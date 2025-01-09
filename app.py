from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import tempfile
import logging
import time
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Create a dedicated directory for streams
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'streams')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Store active FFmpeg processes
active_processes = {}

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

def create_stream_directory():
    """Create a unique stream directory"""
    stream_dir = os.path.join(UPLOAD_FOLDER, str(int(time.time())))
    os.makedirs(stream_dir, exist_ok=True)
    return stream_dir

def cleanup_old_streams():
    """Clean up old stream directories"""
    try:
        for dir_name in os.listdir(UPLOAD_FOLDER):
            dir_path = os.path.join(UPLOAD_FOLDER, dir_name)
            if os.path.isdir(dir_path) and dir_name.isdigit():
                if int(time.time()) - int(dir_name) > 3600:  # Older than 1 hour
                    shutil.rmtree(dir_path, ignore_errors=True)
    except Exception as e:
        logger.error(f"Error cleaning up old streams: {e}")

def start_stream(video_url, stream_dir):
    """Start FFmpeg process for streaming"""
    stream_path = os.path.join(stream_dir, 'stream.m3u8')
    
    # First command: Create a looped input file
    concat_file = os.path.join(stream_dir, 'concat.txt')
    with open(concat_file, 'w') as f:
        f.write(f"file '{video_url}'\n" * 3)  # Write the same file 3 times

    ffmpeg_cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-c', 'copy',
        '-f', 'hls',
        '-hls_time', '2',  # Smaller segments for smoother transitions
        '-hls_list_size', '15',  # Keep more segments
        '-hls_flags', 'delete_segments+append_list+discont_start',
        '-hls_segment_filename', os.path.join(stream_dir, 'segment%03d.ts'),
        '-live_start_index', '-3',  # Start playback from 3 segments before the end
        stream_path
    ]

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        start_new_session=True
    )
    
    return process, stream_path

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    stream_url = None
    
    if request.method == 'POST':
        video_url = request.form['video_url']
        
        try:
            cleanup_old_streams()
            stream_dir = create_stream_directory()
            
            process, stream_path = start_stream(video_url, stream_dir)
            stream_id = os.path.basename(stream_dir)
            active_processes[stream_id] = process
            
            # Wait for initial segments
            time.sleep(3)
            
            if os.path.exists(stream_path):
                stream_url = f"https://{request.host}/stream/{stream_id}/stream.m3u8"
                logger.info(f"Stream URL generated: {stream_url}")
            else:
                error = "Failed to generate stream"
                
        except Exception as e:
            error = f"Error: {str(e)}"
            logger.error(f"Error processing request: {e}")
            
    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route('/stream/<stream_id>/<path:filename>')
def serve_stream(stream_id, filename):
    try:
        stream_dir = os.path.join(UPLOAD_FOLDER, stream_id)
        response = send_from_directory(stream_dir, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == '__main__':
    port = 5000
    app.run(host='0.0.0.0', port=port)
