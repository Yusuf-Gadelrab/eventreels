import sys
import subprocess
from pathlib import Path

def generate_thumbnail(video_path: Path, output_path: Path):
    subprocess.run([
        "ffmpeg", "-y", "-ss", "00:00:01", "-i", str(video_path),
        "-vframes", "1", "-s", "300x168", str(output_path)
    ], check=True)

if __name__ == "__main__":
    generate_thumbnail(Path(sys.argv[1]), Path(sys.argv[2]))
