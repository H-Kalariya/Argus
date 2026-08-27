# Argus — Project Medusa

**Physical challenge-response deepfake defense + tiered fraud-ring detection for payment flows.**

Argus doesn't chase deepfake detection pixel-by-pixel. It forces every payment-flow
attacker through short physical challenges that live face-swap pipelines cannot survive
intact, verifies identity against enrolled ground-truth biometrics (face + voice), and
correlates every event with a tiered identity graph that catches both bot-speed attacks
and slow-moving mule networks.

Grounded in [GOTCHA: Real-Time Video Deepfake Detection via Challenge-Response](https://arxiv.org/abs/2210.06186) (NYU).

---

## Features

### 1. Biometric KYC Scanner
- **Enrollment (ground truth):** capture a reference face photo and record a reference voice sample.
- **Challenge-response:** the user performs a randomized physical action and speaks a phrase
  (either an authorization phrase or a random 4-digit code) that is generated fresh per challenge.
- **Multimodal verification (Gemini):** a single call compares the challenge video against the
  ground-truth image and audio and returns:
  - Face match + confidence
  - Voice / speaker match + confidence
  - Action performed
  - Correct phrase spoken (transcription)
  - Liveness (replay / screen-edge / depth cues)
  - Overall pass/fail with reasoning

Challenges are **unambiguous and mobile-friendly** (no left/right prompts that a mirrored
front camera makes unverifiable) and still create the occlusion/motion that breaks live face-swap.

### 2. Fraud Network "Command Center"
A live-forensics dashboard that replays fraud scenarios event-by-event across three panels:
- **Left — Live Database:** SQLite rows appear in real time (newest flashes, fraud rows highlighted).
- **Center — Identity Graph:** nodes/edges grow as connections form (hard links solid, soft links dashed).
- **Right — Decision Engine:** running risk meter, three velocity-tier counters, and the final action.

A timeline scrubber lets you play, pause, step, and jump to any moment.

**Tiered velocity detection** (fraud operates at multiple speeds):

| Tier | Window | Catches | Action |
|------|--------|---------|--------|
| 1 — Bot-speed | 3+ events on one device in 15 min | Scripted creation / card testing | **BLOCK** |
| 2 — Human-speed | 2+ accounts on one device in 24h | Manual mule creation | **STEP-UP** |
| 3 — Long-game | 3+ accounts sharing a fingerprint across days | Patient mule recruitment | **FLAG** |

Hard links (phone, email, PAN, bank account, card) are deterministic; soft links
(device fingerprint, IP, failed-liveness, geolocation) accumulate evidence.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | React 19 + Vite, MediaRecorder API |
| Backend | Python FastAPI |
| Multimodal AI | Google Gemini (`gemini-3.6-flash`) |
| CV pipeline | OpenCV + MediaPipe |
| Identity graph | SQLite + NetworkX |
| Payments | Razorpay Test API |

Biometric matching runs through Gemini's multimodal API (no local torch/tensorflow),
keeping the footprint light and dependency-free.

---

## Project Structure

```
Argus/
├── backend/
│   ├── main.py             # FastAPI app + all endpoints
│   ├── semantic.py         # Gemini semantic liveness check
│   ├── kyc_verify.py       # Full KYC: face + voice + liveness vs ground truth
│   ├── graph_db.py         # MedusaIdentityGraph (SQLite + NetworkX, tiered velocity)
│   ├── seed_data.py        # Seeds the four demo scenarios
│   └── scenario_events.py  # Event timelines for the command-center replay
├── frontend/
│   └── src/
│       ├── App.jsx             # KYC scanner + tab navigation
│       ├── NetworkDashboard.jsx# Fraud network command center
│       └── *.css
├── requirements.txt
└── .env.example
```

---

## Setup

### Prerequisites
- Python 3.11+ and Node 18+
- A Google Gemini API key

### 1. Configure environment
```bash
cp .env.example .env
```
Edit `.env` and set at least:
```
GEMINI_API_KEY=your_gemini_api_key_here
```
(Razorpay keys are optional for the payment integration.)

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
| GET | `/challenge` | Generate a randomized challenge (action + spoken phrase) |
| POST | `/verify/semantic` | Semantic liveness check on a challenge video |
| POST | `/verify/kyc` | Full KYC: face + voice + liveness vs ground truth |
| POST | `/graph/seed` | (Re)seed the demo identity graph |
| GET | `/graph/scenarios` | Scenarios with live tier evaluation |
| GET | `/graph/network` | Nodes + links + clusters |
| GET | `/graph/timeline/scenarios` | Command-center scenario list |
| GET | `/graph/events` | Flat chronological event log |
| GET | `/graph/scenario/{id}/replay` | Step-by-step replay state |

---

## Demo Script

1. **Legitimate user** — enroll → complete a challenge → face+voice+liveness pass → **Approved**.
2. **Bot-speed attack** — Fraud Network tab → *Bot-Speed Attack* → 3 accounts on one device in
   ~10 min, liveness fails → Tier 1 fires → **BLOCK**.
3. **Human mule** — *Human-Speed Mule* → 2 accounts in 24h → Tier 2 → **STEP-UP**.
4. **Long-game ring** — *Long-Game Mule Ring* → 4 accounts across ~5 days → Tier 3 → **FLAG**.

---

## Security Notes

- **Never commit real secrets.** `.env` / `.env1` are gitignored; only `.env.example` is tracked.
- Face/voice data is biometric. In this demo it is sent to Gemini for the verification window and
  the uploaded files are deleted afterward. Use test/fake identifiers for PAN/Aadhaar/bank fields.

---

## Roadmap

- Replace hand-tuned artifact thresholds with a trained lightweight classifier on labeled swap video.
- Local MediaPipe CV artifact layer (landmark jitter, edge flicker, tracking loss) as an offline signal.
- Migrate the identity graph from SQLite/NetworkX to Neo4j/TigerGraph for production scale.
