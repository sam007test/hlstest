from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import tempfile
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'stream')
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

def process_video(video_url):
    output_dir = os.path.join(UPLOAD_FOLDER, 'segments')
    os.makedirs(output_dir, exist_ok=True)
    
    # Clean existing files
    for file in os.listdir(output_dir):
        try:
            os.unlink(os.path.join(output_dir, file))
        except:
            pass

    # Generate segments
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', video_url,
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-f', 'segment',
        '-segment_time', '2',
        '-segment_format', 'mpegts',
        os.path.join(output_dir, 'segment%03d.ts')
    ]

    process = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if process.returncode != 0:
        raise Exception(f"FFmpeg error: {process.stderr}")

    return output_dir

def create_playlist(segments_dir):
    segments = sorted([f for f in os.listdir(segments_dir) if f.endswith('.ts')])
    playlist_path = os.path.join(UPLOAD_FOLDER, 'playlist.m3u8')
    
    with open(playlist_path, 'w') as f:
        f.write('#EXTM3U\n')
        f.write('#EXT-X-VERSION:3\n')
        f.write('#EXT-X-TARGETDURATION:2\n')
        f.write('#EXT-X-MEDIA-SEQUENCE:0\n')
        
        for segment in segments:
            f.write('#EXTINF:2.0,\n')
            f.write(f'segments/{segment}\n')
        
        # Loop back to start
        f.write('#EXT-X-DISCONTINUITY\n')
        for segment in segments:
            f.write('#EXTINF:2.0,\n')
            f.write(f'segments/{segment}\n')

    return playlist_path

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    stream_url = None
    
    if request.method == 'POST':
        video_url = request.form['video_url']
        try:
            segments_dir = process_video(video_url)
            playlist_path = create_playlist(segments_dir)
            stream_url = f'http://{request.host}/stream/playlist.m3u8'
        except Exception as e:
            error = str(e)
            logger.error(f"Error: {error}")
    
    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route('/stream/<path:filename>')
def serve_stream(filename):
    if 'segments/' in filename:
        directory = os.path.join(UPLOAD_FOLDER, 'segments')
        filename = os.path.basename(filename)
    else:
        directory = UPLOAD_FOLDER
    
    try:
        response = send_from_directory(directory, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
