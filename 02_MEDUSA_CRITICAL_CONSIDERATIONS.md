# Project Medusa — Critical Considerations
Read this before writing any code. Keep it open alongside the task list.

## 1. Research & prior art to internalize first
- **GOTCHA (arXiv:2210.06186, Mittal/Hegde/Memon, NYU)** — the foundational paper. Code + dataset: `github.com/mittalgovind/GOTCHA-Deepfakes`. Study their challenge taxonomy and automated scoring function before designing Layer 2 — don't reinvent metrics they already validated.
- Search arXiv for: "face swap detection occlusion robustness", "presentation attack detection challenge-response", "optical flow deepfake artifact detection", "silent liveness detection survey". Skim abstracts of the top 8-10 for any metric or threshold Medusa can borrow or cite.
- ISO/IEC 30107-3 — the standard for biometric Presentation Attack Detection (PAD) performance reporting (APCER/BPCER metrics). Use this vocabulary in the write-up; judges familiar with biometrics will recognize it.
- Graph fraud-ring literature: search "fraud ring detection graph device fingerprint", "synthetic identity network analysis fingerprinting", "GNN fraud ring community detection". Borrow the hard-link/soft-link and community-detection framing, not necessarily GNNs (out of scope for a hackathon timeline).
- Look at 2-3 open-source repos for each of: MediaPipe face mesh jitter/quality analysis, optical-flow-based deepfake detectors, and NetworkX-based fraud graphs (e.g. `Graph-Based-Fraud-Detection-Network` on GitHub) — for API patterns and pitfalls, not for copying wholesale.

## 2. Things that will break in a live demo if not handled
- **Webcam permission + lighting**: MediaPipe FaceMesh degrades badly in low light or backlight. Test the demo challenges in the actual room/lighting you'll present in, not just your dev setup.
- **Latency budget**: multimodal LLM calls (Layer 1) can take 2-5s. Don't block the CV pipeline (Layer 2) on it — run them concurrently and join results.
- **MediaRecorder codec compatibility**: Chrome, Safari, and mobile browsers encode differently (webm vs mp4). Test the actual browser you'll demo on.
- **False positives from the CV pipeline**: legitimate users blinking, wearing glasses, or having facial hair can spike jitter/edge-flicker metrics. Calibrate thresholds against a real "friendly" video set, not just synthetic swap videos, before finalizing numbers in Part 2 of the plan.
- **The "edge flicker" metric is a placeholder in the reference code** (`np.random.uniform`) — this MUST be replaced with a real boundary-intensity-variance calculation before any threshold or demo number is trusted. Treat this as a blocking task, not polish.

## 3. Data you need before you can tune thresholds
- A small labeled set of: (a) real users performing each challenge, (b) at least one real-time face-swap tool (e.g. an open-source live face-swap demo) performing the same challenges. Without (b) the Medusa Score thresholds in Part 2 are guesses — budget explicit time for this in the task list.
- If you cannot get a live face-swap tool running in time, a pre-recorded deepfake video reenacting the challenge (even offline-rendered) is an acceptable demo substitute — but say so honestly if asked, don't imply it was live.

## 4. Privacy / compliance framing (judges will ask)
- Face video is biometric data. Mention: encrypted in transit, not stored beyond the verification window (or explicitly note if you *are* storing it and why), and a clear retention/deletion policy — even a one-line policy statement is enough for a hackathon judge.
- PAN/Aadhaar/bank account are sensitive identifiers — in the demo, use fake/test values only, and say so on screen.

## 5. Architecture decisions worth stating explicitly to judges (not hiding them)
- Why SQLite + NetworkX and not Neo4j: zero setup risk during judging, same graph semantics, straightforward migration path — state this as a deliberate build-time decision.
- Why hand-tuned thresholds and not a trained classifier for the hackathon: no time to collect/label a large enough swap-video dataset in the window — state the exact next step (labeled dataset + lightweight classifier) rather than leaving it vague.
- Why challenges are template-based, not LLM-generated at runtime: guarantees physical validity, avoids hallucinated/impossible prompts, keeps latency low.

## 6. Team logistics
- Decide LLM provider (Gemini 1.5 Flash vs GPT-4o-mini) early based on whichever has a free/dev tier your team can get keys for fastest — don't lose build time to API key provisioning.
- Razorpay Test Mode API keys should be provisioned on day 1, not left until integration day.
