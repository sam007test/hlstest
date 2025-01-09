from flask import Flask, send_file, render_template_string, request
import subprocess
import os

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Video Player</title>
    <link href="https://vjs.zencdn.net/8.10.0/video-js.css" rel="stylesheet" />
    <script src="https://vjs.zencdn.net/8.10.0/video.min.js"></script>
</head>
<body>
    <div style="max-width: 800px; margin: 20px auto;">
        <form method="POST" style="margin-bottom: 20px;">
            <input type="url" name="video_url" placeholder="Enter video URL" style="width: 80%;" required>
            <button type="submit">Load Video</button>
        </form>
        
        {% if video_path %}
        <video
            id="my-video"
            class="video-js"
            controls
            preload="auto"
            width="100%"
            height="auto"
            data-setup="{}"
        >
            <source src="{{ video_path }}" type="video/mp4" />
        </video>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        video_url = request.form['video_url']
        output_path = 'downloaded_video.mp4'
        
        # Download video using ffmpeg
        subprocess.run([
            'ffmpeg', '-y',
            '-i', video_url,
            '-c', 'copy',
            output_path
        ])
        
        return render_template_string(TEMPLATE, video_path='/video')
    
    return render_template_string(TEMPLATE, video_path=None)

@app.route('/video')
def video():
    video_path = 'downloaded_video.mp4'
    return send_file(video_path, mimetype='video/mp4')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
