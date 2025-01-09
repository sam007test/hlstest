from flask import Flask, request, render_template_string, send_from_directory, jsonify
import subprocess
import os
import logging
import signal
import psutil

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Create upload folder in the project directory
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tmp')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Store the current FFmpeg process
current_ffmpeg_process = None

# Define the HTML template
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Stream Generator</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .status-container {
            display: none;
            margin-top: 20px;
        }
        .progress {
            height: 25px;
        }
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
                        <form id="streamForm" method="post">
                            <div class="mb-3">
                                <label for="video_url" class="form-label">Video URL</label>
                                <input type="url" class="form-control" id="video_url" name="video_url" 
                                       placeholder="Enter video URL (MP4)" required>
                            </div>
                            <button type="submit" class="btn btn-primary" id="submitBtn">Generate Stream</button>
                        </form>
                        
                        <!-- Status Container -->
                        <div class="status-container" id="statusContainer">
                            <div class="card">
                                <div class="card-body">
                                    <h5 class="card-title">Processing Status</h5>
                                    <div class="progress mb-3">
                                        <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                             role="progressbar" id="progressBar" style="width: 0%">
                                        </div>
                                    </div>
                                    <div id="statusText" class="mb-2">Initializing...</div>
                                    <div id="timeElapsed" class="text-muted">Time Elapsed: 0s</div>
                                </div>
                            </div>
                        </div>

                        <!-- Stream URL Container -->
                        <div class="mt-4" id="streamUrlContainer" style="display: none;">
                            <div class="alert alert-success">
                                <h5>Your Stream URL:</h5>
                                <p class="mb-2" id="streamUrl"></p>
                                <small class="text-muted">Use this URL in your media player (VLC, etc)</small>
                            </div>
                        </div>

                        <!-- Error Container -->
                        <div class="mt-4" id="errorContainer" style="display: none;">
                            <div class="alert alert-danger">
                                <h5>Error:</h5>
                                <p id="errorText"></p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let startTime;
        let statusCheckInterval;

        document.getElementById('streamForm').addEventListener('submit', function(e) {
            e.preventDefault();
            startStream();
        });

        function startStream() {
            const videoUrl = document.getElementById('video_url').value;
            const statusContainer = document.getElementById('statusContainer');
            const streamUrlContainer = document.getElementById('streamUrlContainer');
            const errorContainer = document.getElementById('errorContainer');
            const submitBtn = document.getElementById('submitBtn');

            // Reset and show status container
            statusContainer.style.display = 'block';
            streamUrlContainer.style.display = 'none';
            errorContainer.style.display = 'none';
            submitBtn.disabled = true;

            // Initialize progress tracking
            startTime = Date.now();
            updateTimeElapsed();
            statusCheckInterval = setInterval(updateTimeElapsed, 1000);

            fetch('/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `video_url=${encodeURIComponent(videoUrl)}`
            })
            .then(response => response.json())
            .then(data => {
                clearInterval(statusCheckInterval);
                submitBtn.disabled = false;
                statusContainer.style.display = 'none';

                if (data.error) {
                    showError(data.error);
                } else {
                    showStreamUrl(data.stream_url);
                }
            })
            .catch(error => {
                clearInterval(statusCheckInterval);
                submitBtn.disabled = false;
                showError('An error occurred while processing your request.');
            });

            // Simulate progress updates
            simulateProgress();
        }

        function simulateProgress() {
            let progress = 0;
            const progressBar = document.getElementById('progressBar');
            const statusText = document.getElementById('statusText');
            
            const interval = setInterval(() => {
                if (progress >= 90) {
                    clearInterval(interval);
                    return;
                }
                progress += Math.random() * 15;
                if (progress > 90) progress = 90;
                progressBar.style.width = `${progress}%`;
                progressBar.textContent = `${Math.round(progress)}%`;
                
                if (progress < 30) {
                    statusText.textContent = 'Initializing stream...';
                } else if (progress < 60) {
                    statusText.textContent = 'Processing video...';
                } else {
                    statusText.textContent = 'Generating stream URL...';
                }
            }, 1000);
        }

        function updateTimeElapsed() {
            const timeElapsed = Math.floor((Date.now() - startTime) / 1000);
            document.getElementById('timeElapsed').textContent = `Time Elapsed: ${timeElapsed}s`;
        }

        function showStreamUrl(url) {
            document.getElementById('streamUrl').textContent = url;
            document.getElementById('streamUrlContainer').style.display = 'block';
        }

        function showError(message) {
            document.getElementById('errorText').textContent = message;
            document.getElementById('errorContainer').style.display = 'block';
        }
    </script>
</body>
</html>
"""

def kill_ffmpeg():
    global current_ffmpeg_process
    if current_ffmpeg_process:
        try:
            current_ffmpeg_process.kill()
        except:
            pass
    
    # Kill any remaining FFmpeg processes
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'ffmpeg' in proc.info['name'].lower():
                proc.kill()
        except:
            pass

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        video_url = request.form['video_url']
        stream_path = os.path.join(UPLOAD_FOLDER, 'stream.m3u8')
        
        try:
            logger.info(f"Processing video URL: {video_url}")
            
            # Clean up old files
            for file in os.listdir(UPLOAD_FOLDER):
                if file.endswith('.ts') or file.endswith('.m3u8'):
                    try:
                        os.unlink(os.path.join(UPLOAD_FOLDER, file))
                    except Exception as e:
                        logger.error(f"Error cleaning up file {file}: {e}")

            # Kill any existing FFmpeg processes
            kill_ffmpeg()

            global current_ffmpeg_process
            ffmpeg_cmd = [
                'ffmpeg',
                '-stream_loop', '-1',
                '-re',
                '-i', video_url,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-hls_time', '30',
                '-hls_list_size', '20',
                '-hls_segment_filename', f'{UPLOAD_FOLDER}/segment%03d.ts',
                '-hls_flags', 'delete_segments+append_list+omit_endlist',
                '-hls_segment_type', 'mpegts',
                '-method', 'PUT',
                '-f', 'hls',
                stream_path
            ]
            
            current_ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                start_new_session=True
            )
            
            try:
                current_ffmpeg_process.wait(timeout=5)
                stdout, stderr = current_ffmpeg_process.communicate()
                if current_ffmpeg_process.returncode != 0:
                    return jsonify({'error': f"FFmpeg Error: {stderr}"})
            except subprocess.TimeoutExpired:
                if os.path.exists(stream_path):
                    stream_url = f"https://{request.host}/stream/stream.m3u8"
                    return jsonify({'stream_url': stream_url})
                else:
                    return jsonify({'error': 'Failed to create stream file'})
            
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return jsonify({'error': str(e)})
            
    return render_template_string(TEMPLATE)

@app.route('/stream/<path:filename>')
def serve_stream(filename):
    try:
        if os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
            response = send_from_directory(UPLOAD_FOLDER, filename)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Cache-Control'] = 'no-cache'
            return response
        else:
            logger.error(f"File not found: {filename}")
            return "File not found", 404
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

# Cleanup handler
def cleanup_handler(signum, frame):
    kill_ffmpeg()
    exit(0)

signal.signal(signal.SIGTERM, cleanup_handler)
signal.signal(signal.SIGINT, cleanup_handler)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
