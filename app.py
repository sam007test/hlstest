from flask import Flask, request, render_template_string, send_from_directory, jsonify
import subprocess
import os
import tempfile
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
progress = {"value": 0}
streaming_active = {"value": True}

# [Previous HTML template stays the same]

def create_infinite_playlist(duration):
    playlist_content = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{duration}
#EXT-X-MEDIA-SEQUENCE:{sequence}
#EXTINF:{duration:.3f},
chunk.ts
"""
    
    sequence = 0
    while streaming_active["value"]:
        current_playlist = playlist_content.format(
            duration=duration,
            sequence=sequence
        )
            
        with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
            f.write(current_playlist)
            
        sequence += 1
        time.sleep(duration)

@app.route("/", methods=["GET", "POST"])
def index():
    global progress, streaming_active
    error = None
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        stream_path = os.path.join(UPLOAD_FOLDER, "stream.m3u8")
        progress["value"] = 0
        streaming_active["value"] = True

        def process_video():
            try:
                logger.info(f"Processing video URL: {video_url}")
                
                # Get video duration
                duration_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_url
                ]
                
                duration = float(subprocess.check_output(duration_cmd).decode().strip())
                
                # Create single chunk
                ffmpeg_cmd = [
                    "ffmpeg", 
                    "-i", video_url,
                    "-c:v", "copy",
                    "-c:a", "copy",
                    "-f", "mpegts",
                    f"{UPLOAD_FOLDER}/chunk.ts"
                ]

                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
                
                process.wait()
                progress["value"] = 100
                
                # Start infinite playlist generation
                playlist_thread = threading.Thread(
                    target=create_infinite_playlist,
                    args=(duration,)
                )
                playlist_thread.daemon = True
                playlist_thread.start()

            except Exception as e:
                logger.error(f"Error during video processing: {e}")
                progress["value"] = 100

        video_thread = threading.Thread(target=process_video)
        video_thread.daemon = True
        video_thread.start()

        stream_url = f"https://{request.host}/stream/stream.m3u8"

    return render_template_string(TEMPLATE, stream_url=stream_url, error=error)

@app.route("/progress")
def get_progress():
    return jsonify(progress)

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
    global streaming_active
    streaming_active["value"] = False
    # Clean up files
    for file in ["chunk.ts", "stream.m3u8"]:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, file))
        except:
            pass
    return jsonify({"status": "stopped"})

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    try:
        response = send_from_directory(UPLOAD_FOLDER, filename)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = "no-cache"
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
