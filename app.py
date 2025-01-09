from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import tempfile
import logging
import threading
import queue
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Use /tmp directory which is writable on Render
UPLOAD_FOLDER = tempfile.gettempdir()

# Global variables for stream management
stream_queue = queue.Queue()
current_stream = None
next_stream = None
stream_lock = threading.Lock()

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

def process_stream(video_url, stream_id):
    """Process a single stream and return its path"""
    stream_path = os.path.join(UPLOAD_FOLDER, f'stream_{stream_id}.m3u8')
    
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', video_url,
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-hls_time', '6',
        '-hls_list_size', '0',
        '-hls_segment_filename', f'{UPLOAD_FOLDER}/segment_{stream_id}_%03d.ts',
        '-hls_flags', 'delete_segments+append_list',
        '-f', 'hls',
        stream_path
    ]
    
    logger.info(f"Running FFmpeg command for stream {stream_id}: {' '.join(ffmpeg_cmd)}")
    
    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    
    return process, stream_path

def stream_manager():
    """Manage the processing of streams"""
    global current_stream, next_stream
    
    while True:
        try:
            if stream_queue.empty():
                time.sleep(1)
                continue
                
            with stream_lock:
                if next_stream is None:
                    # Start processing next stream
                    video_url = stream_queue.get()
                    stream_id = int(time.time())
                    process, stream_path = process_stream(video_url, stream_id)
                    next_stream = {
                        'process': process,
                        'path': stream_path,
                        'id': stream_id
                    }
                    logger.info(f"Started processing next stream: {stream_id}")
                
                # Check if current stream is finished
                if current_stream and current_stream['process'].poll() is not None:
                    logger.info(f"Current stream {current_stream['id']} finished")
                    # Clean up current stream files
                    cleanup_stream(current_stream['id'])
                    
                    # Promote next stream to current
                    current_stream = next_stream
                    next_stream = None
                    
        except Exception as e:
            logger.error(f"Error in stream manager: {e}")
            time.sleep(1)

def cleanup_stream(stream_id):
    """Clean up files for a specific stream"""
    pattern = f"*{stream_id}*"
    for file in os.listdir(UPLOAD_FOLDER):
        if str(stream_id) in file and (file.endswith('.ts') or file.endswith('.m3u8')):
            try:
                os.unlink(os.path.join(UPLOAD_FOLDER, file))
            except Exception as e:
                logger.error(f"Error cleaning up file {file}: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    stream_url = None
    
    if request.method == 'POST':
        video_url = request.form['video_url']
        
        try:
            logger.info(f"Processing video URL: {video_url}")
            
            # Add to queue for processing
            stream_queue.put(video_url)
            
            # Wait for initial processing
            time.sleep(2)
            
            if current_stream:
                stream_url = f"https://{request.host}/stream/stream_{current_stream['id']}.m3u8"
                logger.info(f"Stream URL generated: {stream_url}")
            else:
                error = "Error starting stream"
                
        except Exception as e:
            error = f"Error: {str(e)}"
            logger.error(f"Error processing request: {e}")
            
    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route('/stream/<path:filename>')
def serve_stream(filename):
    try:
        response = send_from_directory(UPLOAD_FOLDER, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == '__main__':
    # Start stream manager thread
    stream_manager_thread = threading.Thread(target=stream_manager, daemon=True)
    stream_manager_thread.start()
    
    port = 5000
    app.run(host='0.0.0.0', port=port)
