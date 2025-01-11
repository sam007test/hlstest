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
streaming_active = {"value": True}
current_stream = {"ts_file": None, "duration": None}

# HTML template code remains unchanged for brevity

def create_infinite_playlist(duration):
    base_playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{duration}
#EXT-X-MEDIA-SEQUENCE:{sequence}
#EXT-X-ALLOW-CACHE:NO
"""
    start_time = time.time()
    sequence = 0
    
    while streaming_active["value"]:
        current_playlist = base_playlist.format(
            duration=duration,
            sequence=sequence
        )
        
        elapsed_time = time.time() - start_time
        timestamp = elapsed_time % duration
        
        for i in range(3):  # Keep 3 segments in the playlist
            current_playlist += f"#EXTINF:{duration:.3f},\nchunk.ts?_t={timestamp + (i * duration)}\n"
        
        with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
            f.write(current_playlist)
        
        sequence += 1
        time.sleep(0.5)  # Update playlist frequently

@app.route("/", methods=["GET", "POST"])
def index():
    global streaming_active, current_stream
    stream_url = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        streaming_active["value"] = True

        if not current_stream["ts_file"] or not os.path.exists(os.path.join(UPLOAD_FOLDER, "chunk.ts")):
            try:
                duration_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_url
                ]
                
                duration = float(subprocess.check_output(duration_cmd).decode().strip())
                
                # Convert video to TS format with reduced quality
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", video_url,
                    "-vf", "scale=640:-1",  # Scale video to 640px width
                    "-b:v", "500k",        # Lower video bitrate
                    "-b:a", "64k",         # Lower audio bitrate
                    "-c:v", "libx264",     # H.264 codec
                    "-preset", "veryfast", # Faster preset
                    "-c:a", "aac",         # AAC codec for audio
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
                
                current_stream["ts_file"] = "chunk.ts"
                current_stream["duration"] = duration
                
            except Exception as e:
                logger.error(f"Error processing video: {e}")
                return render_template_string(TEMPLATE, error=str(e))

        playlist_thread = threading.Thread(
            target=create_infinite_playlist,
            args=(current_stream["duration"],)
        )
        playlist_thread.daemon = True
        playlist_thread.start()

        stream_url = f"https://{request.host}/stream/stream.m3u8"

    return render_template_string(TEMPLATE, stream_url=stream_url)

@app.route("/stop-stream", methods=["POST"])
def stop_stream():
    global streaming_active
    streaming_active["value"] = False
    try:
        os.remove(os.path.join(UPLOAD_FOLDER, "stream.m3u8"))
    except:
        pass
    return jsonify({"status": "stopped"})

@app.route("/stream/<path:filename>")
def serve_stream(filename):
    try:
        response = send_from_directory(UPLOAD_FOLDER, filename.split('?')[0])
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = "no-cache"
        return response
    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
