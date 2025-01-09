from flask import Flask, request, jsonify, send_from_directory
import os
import subprocess
import threading
import requests

app = Flask(__name__)

HLS_DIR = "hls_output"
HLS_PORT = 8000
server_thread = None


def download_mp4(mp4_url, output_path="input_video.mp4"):
    """
    Downloads an MP4 file from a given URL.

    Args:
        mp4_url (str): URL of the MP4 file.
        output_path (str): Path to save the downloaded file.
    """
    response = requests.get(mp4_url, stream=True)
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return output_path
    else:
        raise Exception(f"Failed to download MP4. HTTP status code: {response.status_code}")


def generate_hls(input_mp4, output_dir, segment_time=10):
    """
    Converts MP4 to HLS (.m3u8 and .ts files).

    Args:
        input_mp4 (str): Path to the input MP4 file.
        output_dir (str): Directory to save HLS files.
        segment_time (int): Duration of each segment in seconds.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    command = [
        "ffmpeg",
        "-i", input_mp4,
        "-codec:V", "libx264",
        "-codec:a", "aac",
        "-ac", "2",
        "-hls_time", str(segment_time),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", os.path.join(output_dir, "segment_%03d.ts"),
        os.path.join(output_dir, "playlist.m3u8"),
    ]
    subprocess.run(command, check=True)


def start_http_server(directory, port=HLS_PORT):
    """
    Starts an HTTP server to serve files in a directory.
    """
    os.chdir(directory)

    handler = threading.Thread(target=lambda: os.system(f"python3 -m http.server {port}"))
    handler.daemon = True
    handler.start()


@app.route("/start", methods=["POST"])
def start_streaming():
    """
    API endpoint to start HLS streaming.
    """
    global server_thread

    try:
        data = request.json
        mp4_url = data.get("mp4_url")

        if not mp4_url:
            return jsonify({"error": "No MP4 URL provided"}), 400

        # Step 1: Download the MP4
        input_mp4 = "input_video.mp4"
        download_mp4(mp4_url, input_mp4)

        # Step 2: Convert MP4 to HLS
        if os.path.exists(HLS_DIR):
            subprocess.run(["rm", "-rf", HLS_DIR])  # Clean up old files
        generate_hls(input_mp4, HLS_DIR)

        # Step 3: Start HTTP Server
        if server_thread is None:
            server_thread = threading.Thread(target=start_http_server, args=(HLS_DIR,))
            server_thread.start()

        return jsonify({"message": f"Streaming started at http://0.0.0.0:{HLS_PORT}/playlist.m3u8"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stop", methods=["POST"])
def stop_streaming():
    """
    API endpoint to stop HLS streaming.
    """
    global server_thread

    if server_thread is not None:
        os.system("pkill -f 'python3 -m http.server'")  # Stop the HTTP server
        server_thread = None

    return jsonify({"message": "Streaming stopped."})


@app.route("/")
def home():
    """
    Home page with instructions.
    """
    return jsonify({
        "message": "Use /start (POST) to start streaming and /stop (POST) to stop streaming.",
        "example_start": {"mp4_url": "http://example.com/video.mp4"}
    })


if __name__ == "__main__":
    app.run(port=5000)
