"""Beat detection helpers for optional local beat-synced cuts."""

import logging

logger = logging.getLogger(__name__)


def detect_beats(audio_path: str) -> list[float]:
    """Return beat timestamps in seconds, or [] when librosa is unavailable."""
    try:
        import librosa
    except Exception as exc:  # pragma: no cover - environment-dependent fallback
        logger.warning("beat sync unavailable: could not import librosa (%s)", exc)
        return []

    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        if len(y) == 0:
            return []
        _, frames = librosa.beat.beat_track(y=y, sr=sr)
        times = librosa.frames_to_time(frames, sr=sr)
        return [round(float(t), 3) for t in times if float(t) >= 0]
    except Exception as exc:  # pragma: no cover - depends on media/container codecs
        logger.warning("beat sync unavailable for %s: %s", audio_path, exc)
        return []
