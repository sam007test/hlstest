from flask import Flask, request, render_template_string, send_from_directory
import subprocess
import os
import tempfile
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.gettempdir()

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
      stream_path = os.path.join(UPLOAD_FOLDER, 'stream.m3u8')
      
      try:
          logger.info(f"Processing video URL: {video_url}")
          
          for file in os.listdir(UPLOAD_FOLDER):
              if file.endswith('.ts') or file.endswith('.m3u8'):
                  try:
                      os.unlink(os.path.join(UPLOAD_FOLDER, file))
                  except Exception as e:
                      logger.error(f"Error cleaning up file {file}: {e}")

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
              '-hls_time', '180',
              '-hls_list_size', '5',
              '-hls_segment_filename', f'{UPLOAD_FOLDER}/segment%03d.ts',
              '-hls_flags', 'delete_segments+append_list+omit_endlist+program_date_time',
              '-hls_playlist_type', 'event',
              '-hls_init_time', '1',
              '-hls_segment_type', 'mpegts', 
              '-start_number', '1',
              '-f', 'hls',
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
          
          try:
              process.wait(timeout=5)
              stdout, stderr = process.communicate()
              if process.returncode != 0:
                  error = f"FFmpeg Error: {stderr}"
                  logger.error(f"FFmpeg error: {stderr}")
              else:
                  stream_url = f"https://{request.host}/stream/stream.m3u8"
                  logger.info(f"Stream URL generated: {stream_url}")
          except subprocess.TimeoutExpired:
              stream_url = f"https://{request.host}/stream/stream.m3u8"
              logger.info(f"Stream URL generated: {stream_url}")
          
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
  port = 5000
  app.run(host='0.0.0.0', port=port)
