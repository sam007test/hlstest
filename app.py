from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import time

app = Flask(__name__)

UPLOAD_FOLDER = 'streams'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
    if request.method == 'POST':
        video_url = request.form['video_url']
        stream_path = os.path.join(UPLOAD_FOLDER, 'stream.m3u8')
        
        # Kill any existing ffmpeg processes
        os.system("pkill ffmpeg")
        
        # Clean up old files
        for file in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, file)
            try:
                os.unlink(file_path)
            except:
                pass

        # Start FFmpeg process
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', video_url,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-b:v', '2M',
            '-b:a', '128k',
            '-hls_time', '10',
            '-hls_list_size', '0',
            '-hls_segment_filename', f'{UPLOAD_FOLDER}/segment%d.ts',
            '-f', 'hls',
            stream_path
        ]
        
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait briefly for the stream to start
        time.sleep(2)
        
        # Generate stream URL
        stream_url = f"http://{request.host}/streams/stream.m3u8"
        return render_template_string(TEMPLATE, stream_url=stream_url)
    
    return render_template_string(TEMPLATE, stream_url=None)

@app.route('/streams/<path:filename>')
def serve_stream(filename):
    response = send_from_directory(UPLOAD_FOLDER, filename)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
