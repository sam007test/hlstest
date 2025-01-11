from flask import Flask, request, render_template_string, send_from_directory, jsonify 
import subprocess
import os
import tempfile
import threading
import time
import logging
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = tempfile.gettempdir()
streaming_active = {"value": True}
current_stream = {"ts_file": None, "duration": None, "video_url": None}

# [Previous TEMPLATE string stays exactly the same]
TEMPLATE = """ [Your existing template HTML code] """

def concatenate_video(video_url, repeat_count):
    """
    Downloads and concatenates the video file specified number of times
    """
    try:
        # Create a temporary file for the original MP4
        temp_mp4 = os.path.join(UPLOAD_FOLDER, "temp_original.mp4")
        
        # Download original video
        download_cmd = [
            "ffmpeg",
            "-i", video_url,
            "-c", "copy",
            temp_mp4
        ]
        subprocess.run(download_cmd, check=True)

        # Create output file for concatenated video
        output_mp4 = os.path.join(UPLOAD_FOLDER, "concatenated.mp4")
        
        # Read the original file
        with open(temp_mp4, 'rb') as f:
            original_data = f.read()

        # Write the data repeated times
        with open(output_mp4, 'wb') as f:
            for _ in range(repeat_count):
                f.write(original_data)

        # Clean up original temp file
        os.remove(temp_mp4)
        
        return output_mp4
    except Exception as e:
        logger.error(f"Error in concatenation: {e}")
        raise e

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
        
        for i in range(3):  
            current_playlist += f"#EXTINF:{duration:.3f},\nchunk.ts?_t={timestamp + (i * duration)}\n"
        
        with open(os.path.join(UPLOAD_FOLDER, "stream.m3u8"), "w") as f:
            f.write(current_playlist)
        
        sequence += 1
        time.sleep(0.5)

@app.route("/", methods=["GET", "POST"])
def index():
    global streaming_active, current_stream
    stream_url = None
    current_video_url = None
    repeat_count = None

    if request.method == "POST":
        video_url = request.form["video_url"]
        repeat_count = int(request.form["repeat_count"])
        streaming_active["value"] = True

        if not current_stream["ts_file"] or not os.path.exists(os.path.join(UPLOAD_FOLDER, "chunk.ts")):
            try:
                # Get duration of original video
                duration_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_url
                ]
                
                single_duration = float(subprocess.check_output(duration_cmd).decode().strip())
                total_duration = single_duration * repeat_count

                # Concatenate video
                concatenated_video = concatenate_video(video_url, repeat_count)
                
                # Convert concatenated video to TS format
                ffmpeg_cmd = [
                    "ffmpeg", 
                    "-i", concatenated_video,
                    "-vf", "scale=640:-1",
                    "-b:v", "500k",
                    "-b:a", "64k",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-c:a", "aac",
                    "-bsf:v", "h264_mp4toannexb",
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
                
                # Clean up concatenated file
                os.remove(concatenated_video)
                
                current_stream["ts_file"] = "chunk.ts"
                current_stream["duration"] = total_duration
                current_stream["video_url"] = video_url
                
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
        current_video_url = current_stream["video_url"]

    return render_template_string(
        TEMPLATE, 
        stream_url=stream_url, 
        current_video_url=current_video_url,
        repeat_count=repeat_count
    )

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
