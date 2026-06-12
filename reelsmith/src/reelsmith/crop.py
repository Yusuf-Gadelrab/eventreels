"""Face/subject-aware cropping using MediaPipe."""

import subprocess
import tempfile
from pathlib import Path

def get_subject_cx(video_path: str, start: float, dur: float) -> float:
    """Find the median relative X center (0.0 to 1.0) of faces in the video segment.
    Returns 0.5 (center) if no faces are found or mediapipe fails.
    """
    try:
        import cv2
        import urllib.request
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError:
        return 0.5
        
    model_path = Path(__file__).parent / "blaze_face_short_range.tflite"
    if not model_path.exists():
        url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
        try:
            urllib.request.urlretrieve(url, str(model_path))
        except Exception:
            return 0.5
            
    base_options = python.BaseOptions(model_asset_path=str(model_path))
    options = vision.FaceDetectorOptions(base_options=base_options)
    
    with tempfile.TemporaryDirectory(prefix="reelsmith-crop-") as tmpdir:
        tmp = Path(tmpdir)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-y", "-ss", str(start), "-t", str(dur),
            "-i", video_path, "-vf", "fps=2,scale=480:-1", str(tmp / "%04d.jpg")
        ], capture_output=True)
        
        frames = list(tmp.glob("*.jpg"))
        if not frames:
            return 0.5
            
        centers_x = []
        
        try:
            with vision.FaceDetector.create_from_options(options) as detector:
                for f in frames:
                    img = cv2.imread(str(f))
                    if img is None:
                        continue
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
                    
                    detection_result = detector.detect(mp_image)
                    if detection_result.detections:
                        for detection in detection_result.detections:
                            box = detection.bounding_box
                            # bounding_box gives pixel coordinates
                            cx = (box.origin_x + box.width / 2) / img.shape[1]
                            centers_x.append(cx)
        except Exception:
            return 0.5
        
        if not centers_x:
            return 0.5
            
        return sorted(centers_x)[len(centers_x) // 2]
