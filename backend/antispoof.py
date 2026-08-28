"""
Anti-Spoof / Replay-Attack Detection Layer

PRIMARY SIGNAL: Challenge-Color Reflection
During recording, the frontend flashes a random sequence of colors on screen.
A live person's face reflects those colors (skin acts as a diffuse reflector).
A replayed video was recorded BEFORE those colors existed — the reflection won't match.

This is the most reliable local signal because it's fundamentally impossible to fake
without a real-time face-swap (which has its own artifacts).

SECONDARY SIGNALS (supportive, not standalone):
- Response latency: live user reacts to challenge with slight delay; replay starts instantly
- Micro-movement correlation: real face has involuntary micro-tremors between frames
"""

import cv2
import numpy as np
from typing import Dict, List
import os


def _extract_face_region(frame):
    """Extract the face region using a simple cascade (fast, no model download needed)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    x, y, w, h = faces[0]
    # Use forehead + cheeks (most reflective skin areas, avoid mouth area)
    return frame[y:y + h // 2, x:x + w]


def _mean_color(region):
    """Get mean BGR color of a region."""
    if region is None or region.size == 0:
        return None
    return np.mean(region, axis=(0, 1))  # returns [B, G, R]


def analyze_color_reflection(
    video_path: str,
    color_sequence: List[str],
    flash_duration_ms: int = 500,
    fps: float = 30.0,
) -> Dict:
    """
    Analyze whether the face in the video reflects the challenge color sequence.

    Args:
        video_path: path to the recorded video
        color_sequence: list of hex colors that were flashed (e.g. ["#ff0000", "#00ff00", "#0000ff"])
        flash_duration_ms: how long each color was shown (ms)
        fps: video framerate

    Returns:
        dict with correlation score, per-color analysis, and verdict
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Cannot open video", "is_spoof": False, "reflection_score": 0}

    actual_fps = cap.get(cv2.CAP_PROP_FPS) or fps
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames_per_flash = int(actual_fps * flash_duration_ms / 1000)

    # Parse expected colors (hex -> BGR)
    expected_colors = []
    for hex_color in color_sequence:
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        expected_colors.append(np.array([b, g, r], dtype=np.float32))

    # Skip the first 1 second (user is still reading the challenge)
    start_frame = int(actual_fps * 1.0)

    # For each color in the sequence, sample the face during that flash window
    # and check if the face's color shifted toward the expected color
    baseline_color = None
    per_color_results = []

    for i, expected in enumerate(expected_colors):
        window_start = start_frame + i * frames_per_flash
        window_end = min(window_start + frames_per_flash, total_frames)
        
        if window_start >= total_frames:
            break

        # Sample frames in this window
        face_colors = []
        sample_count = min(5, window_end - window_start)
        sample_indices = np.linspace(window_start, window_end - 1, sample_count, dtype=int)

        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if not ret:
                continue
            region = _extract_face_region(frame)
            c = _mean_color(region)
            if c is not None:
                face_colors.append(c)

        if not face_colors:
            per_color_results.append({"expected": color_sequence[i], "detected_shift": 0, "match": False})
            continue

        avg_face_color = np.mean(face_colors, axis=0)

        # Get baseline from before the flashes started
        if baseline_color is None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, start_frame - int(actual_fps * 0.5)))
            ret, frame = cap.read()
            if ret:
                region = _extract_face_region(frame)
                baseline_color = _mean_color(region)
            if baseline_color is None:
                baseline_color = avg_face_color

        # The color SHIFT from baseline (what the flash induced)
        shift = avg_face_color - baseline_color

        # Normalize expected color direction
        expected_dir = expected / (np.linalg.norm(expected) + 1e-5)
        shift_magnitude = np.linalg.norm(shift)

        # How much of the shift aligns with the expected color direction?
        if shift_magnitude > 1.0:
            shift_dir = shift / shift_magnitude
            correlation = float(np.dot(shift_dir, expected_dir))
        else:
            correlation = 0.0

        # A genuine reflection typically shows correlation > 0.3 with shift > 2-3 units
        match = correlation > 0.2 and shift_magnitude > 1.5

        per_color_results.append({
            "expected": color_sequence[i],
            "shift_magnitude": round(float(shift_magnitude), 2),
            "correlation": round(correlation, 3),
            "match": match,
        })

    cap.release()

    # Verdict
    if not per_color_results:
        return {"is_spoof": False, "reflection_score": 5.0, "reason": "No color analysis possible",
                "per_color": [], "matches": 0, "total": 0}

    matches = sum(1 for r in per_color_results if r["match"])
    total = len(per_color_results)
    reflection_score = round(matches / max(total, 1) * 10, 1)

    # If less than half the colors reflected correctly, likely a replay
    is_spoof = matches < total * 0.4

    reasons = []
    if is_spoof:
        reasons.append(f"Only {matches}/{total} challenge colors reflected on face (replay attack likely)")

    return {
        "reflection_score": reflection_score,
        "is_spoof": is_spoof,
        "matches": matches,
        "total": total,
        "per_color": per_color_results,
        "reasons": reasons,
    }


def analyze_micro_movement(video_path: str, sample_frames: int = 20) -> Dict:
    """
    Check for involuntary micro-movements between frames.
    A live person has involuntary tremors/sway even when "still".
    A screen replay has ZERO movement between identical display frames
    (or perfectly smooth interpolated movement from the original recording).

    This checks for the PATTERN of movement, not amount:
    - Live: random, non-zero movement every frame pair
    - Replay of replay: potential duplicate frames or unnaturally smooth motion
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"micro_movement_ok": True}

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 10:
        cap.release()
        return {"micro_movement_ok": True}

    indices = np.linspace(0, total_frames - 1, sample_frames, dtype=int)
    prev_gray = None
    flows = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (160, 120))

        if prev_gray is not None:
            # Optical flow magnitude between consecutive samples
            flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
            flows.append(float(np.mean(mag)))
        prev_gray = gray

    cap.release()

    if not flows:
        return {"micro_movement_ok": True}

    # Check for suspicious patterns:
    # 1. Zero-flow frames (exact duplicate frames from a screen not refreshing)
    zero_frames = sum(1 for f in flows if f < 0.05)
    # 2. Very uniform flow (robotic/interpolated movement)
    flow_std = float(np.std(flows))

    suspicious = zero_frames > len(flows) * 0.3 or flow_std < 0.1

    return {
        "micro_movement_ok": not suspicious,
        "zero_flow_frames": zero_frames,
        "flow_std": round(flow_std, 3),
        "avg_flow": round(float(np.mean(flows)), 3),
        "suspicious": suspicious,
    }

