# Phase 0 — Research & Grounding Notes

## 1. GOTCHA Challenge Categories
Based on the GOTCHA paper (arXiv:2210.06186), the challenge taxonomy focuses on active presentation attacks:
- **Self-occlusion:** Hand covering part of the face, breaking facial landmark detection.
- **Extreme angular rotation:** Profile views where models fail to interpolate missing facial features.
- **Foreground object insertion:** Objects partially obstructing the face.
- **Rapid motion:** High-velocity movements causing motion blur and tracking loss.

## 2. CV Artifact Metrics
Literature highlights the following metrics for detecting face-swap deepfakes, particularly under occlusion:
- **Landmark Jitter:** Measures the frame-to-frame displacement of facial landmarks (e.g., via MediaPipe). Deepfakes exhibit higher jitter due to unstable tracking.
  - *Rationale:* Trackers struggle when facial features are partially occluded.
- **Edge Flicker / Intensity Variance:** Measures pixel intensity variance at the boundary (e.g., jawline).
  - *Rationale:* Mask blending in deepfakes creates inconsistencies and flickering at the edges.
- **Tracking Loss:** Counts consecutive frames where face detection fails.
  - *Rationale:* Real faces are consistent; deepfakes lose tracking entirely under severe occlusion.
- **Motion Vector Anomaly:** Uses optical flow (e.g., Farneback) to detect discontinuities.
  - *Rationale:* Deepfakes insert synthetic frames that violate smooth motion continuity.

## 3. Candidate Face-Swap Tool
For testing purposes, we can use open-source tools like:
- **DeepFaceLive** (or pre-recorded deepfake videos using similar algorithms) for generating real-time face-swap artifacts.

## 4. Graph-Based Fraud Ring Detection
- **Hard Links:** Deterministic connections (e.g., same phone number, email, bank account).
- **Soft Links:** Behavioral or probabilistic connections (e.g., shared device fingerprint, IP address, geolocation).
- **Community Detection:** Identifying clusters of suspicious behavior (velocity checks) over varying time windows (e.g., bot-speed vs. long-game mule networks).
