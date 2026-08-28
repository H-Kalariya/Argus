# Argus — Project Medusa

**Physical challenge-response deepfake & fraud-ring defense for payment flows.**

Argus doesn't chase deepfake detection pixel-by-pixel. It forces every payment-flow
attacker through short physical challenges that live face-swap pipelines cannot survive
intact, verifies identity against enrolled ground-truth biometrics (face + voice), and
correlates every event with a tiered identity graph that catches both bot-speed attacks
and slow-moving mule networks.

Grounded in [GOTCHA: Real-Time Video Deepfake Detection via Challenge-Response](https://arxiv.org/abs/2210.06186) (NYU).

---

## Core Anti-Replay Mechanism: Delayed Challenge Reveal

The strongest liveness signal isn't a pixel-level detector — it's **unpredictability**.

```
0s ─────── 1s ─────── 4s ─────── 7s (stop)
│          │          │          │
Recording  Action     Spoken     End
starts     revealed   code
(camera    on screen  revealed
 rolling)             on screen
```

- The challenge (action + spoken code) is generated **server-side** and revealed
  **after recording has already started**.
- A pre-recorded video cannot know the action or code (they didn't exist yet).
- The random 4-digit spoken code appears at **4 seconds** — leaving only 3 seconds
  to say it. Even a live attacker watching your screen can't react with the right voice.
- Gemini verifies **timing**: if the action starts at frame 0 or the phrase is spoken
  before ~4s, it's flagged as a replay.

| Attack | Why it fails |
|--------|-------------|
| Pre-recorded video | Can't predict the action or code |
| Replay of a past session | Different random code every time |
| Someone watching your screen | Wrong voice, wrong face, <3s to react |
| Live face-swap (DeepFace etc.) | Voice won't match + physical occlusion causes swap artifacts |

---

## Features

### 1. Biometric KYC Scanner
- **Enrollment:** capture a reference face photo + record a reference voice sample (ground truth).
- **Challenge-response:** randomized physical action + random 4-digit spoken code, revealed
  incrementally during recording.
- **Multimodal verification (Gemini):** compares challenge video against ground truth and returns:
  - Face match + confidence
  - Voice / speaker match + confidence
  - Action performed (with timing check)
  - Correct phrase spoken (exact transcription match)
  - Liveness (replay indicators, timing analysis, audio quality)
  - Overall pass/fail with reasoning

Challenge actions are **unambiguous and mobile-friendly** (no left/right prompts) and create
occlusion/motion that breaks live face-swap.

### 2. Fraud Network Command Center
A live-forensics dashboard that replays fraud scenarios event-by-event across three panels:
- **Left — Live Database:** SQLite rows appear in real time (newest flashes, fraud highlighted).
- **Center — Identity Graph:** nodes/edges grow as connections form (hard links solid, soft dashed).
- **Right — Decision Engine:** running risk meter, three velocity-tier counters, final action.

Timeline scrubber with play/pause/step.

**Tiered velocity detection:**

| Tier | Window | Catches | Action |
|------|--------|---------|--------|
| 1 — Bot-speed | 3+ events on one device in 15 min | Scripted creation / card testing | **BLOCK** |
| 2 — Human-speed | 2+ accounts on one device in 24h | Manual mule creation | **STEP-UP** |
| 3 — Long-game | 3+ accounts sharing a fingerprint across days | Patient mule recruitment | **FLAG** |

Hard links are deterministic; soft links accumulate evidence.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | React 19 + Vite, MediaRecorder API |
| Backend | Python FastAPI |
| Multimodal AI | Google Gemini (configurable: `gemini-3.6-flash`, `gemini-3.5-flash-lite`) |
| Identity graph | SQLite + NetworkX |
| Payments | Razorpay Test API |

No torch, no tensorflow — biometric matching runs through Gemini's multimodal API.
Automatic retry with exponential backoff on rate limits.

---

## Project Structure

```
Argus/
├── backend/
│   ├── main.py             # FastAPI app + all endpoints
│   ├── semantic.py         # Gemini semantic liveness check (legacy endpoint)
│   ├── kyc_verify.py       # Full KYC: face + voice + liveness vs ground truth
│   ├── graph_db.py         # MedusaIdentityGraph (SQLite + NetworkX)
│   ├── seed_data.py        # Seeds the four demo scenarios
│   ├── scenario_events.py  # Event timelines for the command-center replay
│   └── antispoof.py        # Local CV anti-spoof utilities (experimental)
├── frontend/
│   └── src/
│       ├── App.jsx              # KYC scanner + tab navigation
│       ├── App.css              # Scanner styles
│       ├── NetworkDashboard.jsx # Fraud network command center
│       └── NetworkDashboard.css # Command center dark theme
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Setup

### Prerequisites
- Python 3.11+ and Node 18+
- A Google Gemini API key ([get one here](https://aistudio.google.com/apikey))

### 1. Configure environment
```bash
cp .env.example .env
```
Edit `.env`:
```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash-lite   # or gemini-3.6-flash
```

**Tip:** Free tier is 20 requests/day per model per project. To get more:
- Switch `GEMINI_MODEL` between `gemini-3.6-flash` and `gemini-3.5-flash-lite` (separate quotas).
- Or create a new project at [AI Studio](https://aistudio.google.com/apikey) → "Create key in new project".

### 2. Backend
```bash
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS/Linux
pip install -r requirements.txt

cd backend
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```
Open the URL Vite prints (e.g. http://localhost:5173).

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/challenge` | Generate a randomized challenge |
| POST | `/verify/semantic` | Semantic liveness check (legacy) |
| POST | `/verify/kyc` | Full KYC verification |
| POST | `/graph/seed` | (Re)seed the demo identity graph |
| GET | `/graph/scenarios` | Scenarios with live tier evaluation |
| GET | `/graph/network` | Nodes + links + clusters |
| GET | `/graph/timeline/scenarios` | Command-center scenario list |
| GET | `/graph/events` | Flat chronological event log |
| GET | `/graph/scenario/{id}/replay` | Step-by-step replay state |

---

## Demo Script

### KYC Scanner (2-3 minutes)

1. **Legitimate user:**
   - Enroll (capture face + record voice)
   - Click "Get Challenge" → Start Recording
   - Action appears at 1s, spoken code at 4s → perform both
   - Result: ✅ All checks pass → **Payment Authorized**

2. **Replay attack:**
   - Record yourself doing a challenge, save the video
   - Get a NEW challenge (different code!) → play the old video to the camera
   - Result: ❌ Wrong spoken phrase (old code ≠ new code) → **Blocked**

3. **Different person:**
   - Enroll yourself → have someone else attempt the challenge
   - Result: ❌ Face mismatch + ❌ Voice mismatch → **Blocked**

### Fraud Network Command Center (2-3 minutes)

4. **Bot-speed attack:** 3 accounts in 10 min → Tier 1 fires → **BLOCK**
5. **Human mule:** 2 accounts in 24h → Tier 2 → **STEP-UP**
6. **Long-game ring:** 4 accounts over 5 days → Tier 3 → **FLAG**

---

## Why This Design Wins

1. **Challenge unpredictability is the primary defense** — not pixel analysis. No detector
   arms race, no model to retrain, no false positives on legitimate users.
2. **Delayed reveal** makes pre-recording fundamentally impossible.
3. **Multi-factor** (face + voice + liveness + correct phrase + timing) means an attacker
   must defeat ALL checks simultaneously.
4. **Three velocity tiers** catch fraud at bot speed, human speed, and patient-mule speed —
   not one arbitrary threshold.
5. **Fully buildable with standard tools** — no bespoke infra, no heavy ML, deployable today.

---

## Security Notes

- `.env` / `.env1` are gitignored. Only `.env.example` is tracked.
- Face/voice data is sent to Gemini for the verification window only; uploaded files are
  deleted immediately after processing.
- Use test/fake identifiers for PAN/Aadhaar/bank fields in demos.

---

## Roadmap

- Local MediaPipe CV artifact layer (landmark jitter, edge flicker) as an offline anti-deepfake signal.
- Razorpay payment flow integration (challenge gates the payment).
- Migrate identity graph from SQLite/NetworkX to Neo4j/TigerGraph for production scale.
- Labeled dataset of real vs. live-swap video under occlusion → trained lightweight classifier.
