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
            
            # Wait for initial segments
            try:
                # Check if the process is running after 5 seconds
                current_ffmpeg_process.wait(timeout=5)
                stdout, stderr = current_ffmpeg_process.communicate()
                if current_ffmpeg_process.returncode != 0:
                    return jsonify({'error': f"FFmpeg Error: {stderr}"})
            except subprocess.TimeoutExpired:
                # Process is still running (expected behavior)
                if os.path.exists(stream_path):
                    stream_url = f"https://{request.host}/stream/stream.m3u8"
                    return jsonify({'stream_url': stream_url})
                else:
                    return jsonify({'error': 'Failed to create stream file'})
            
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return jsonify({'error': str(e)})
            
    return render_template_string(TEMPLATE)  # Your existing template

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
    port = 5000
    app.run(host='0.0.0.0', port=port)
