# Argus

**Challenge-response deepfake & fraud-ring defense for payment flows.**

Argus doesn't chase deepfake detection pixel-by-pixel. It forces every payment-flow
attacker through physical challenges that live face-swap pipelines cannot survive
intact, verifies identity against enrolled ground-truth biometrics (face + voice), and
correlates every event with a tiered identity graph that catches both bot-speed attacks
and slow-moving mule networks.

Grounded in [GOTCHA: Real-Time Video Deepfake Detection via Challenge-Response](https://arxiv.org/abs/2210.06186) (NYU).

---

## Core Anti-Replay: Delayed Challenge Reveal

The strongest liveness signal is **unpredictability**, not pixel analysis.

```
0s ─── 2s ─────── 7s ──────── 12s (stop)
│      │          │           │
Record Action     Spoken      End
starts revealed   code
       on screen  revealed
```

- The challenge is generated **server-side** and revealed **after recording starts**.
- No re-recording allowed — one attempt per challenge, then a new challenge is required.
- A pre-recorded video cannot predict the action or the random 4-digit code.
- The spoken code appears at **7 seconds** — giving only 5s to say it.
- Gemini checks **timing**: if the action/phrase appears too early, it's flagged.

| Attack | Why it fails |
|--------|-------------|
| Pre-recorded video | Can't predict the action or code |
| Replay of a past session | Different random code every time + no re-recording |
| Someone watching your screen | Wrong voice, wrong face, limited reaction time |
| Live face-swap | Voice won't match + physical occlusion breaks swap |

---

## Features

### 1. Biometric KYC Scanner
- **Enrollment:** capture a reference face photo + record a reference voice sample.
- **Challenge-response:** randomized physical action + random 4-digit spoken code,
  revealed incrementally during a **12-second** recording window.
- **No re-recording:** one attempt per challenge — must fetch a new challenge to retry.
- **Multimodal verification (Gemini):** compares challenge video against ground truth:
  - Face match + confidence
  - Voice / speaker match + confidence
  - Action performed (with timing check)
  - Correct phrase spoken (exact transcription)
  - Liveness (replay indicators, timing analysis)
  - Overall pass/fail with reasoning

### 2. Fraud Network Command Center
A live-forensics dashboard that replays fraud scenarios event-by-event:
- **Left — Live Database:** rows appear in real time
- **Center — Identity Graph:** nodes/edges grow as connections form
- **Right — Decision Engine:** risk meter, velocity-tier counters, final action
- **Bottom — Timeline scrubber:** play/pause/step through events

**Tiered velocity detection:**

| Tier | Window | Catches | Action |
|------|--------|---------|--------|
| 1 — Bot-speed | 3+ events on one device in 15 min | Scripted creation | **BLOCK** |
| 2 — Human-speed | 2+ accounts on one device in 24h | Manual mule creation | **STEP-UP** |
| 3 — Long-game | 3+ accounts sharing fingerprint across days | Patient recruitment | **FLAG** |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | React 19 + Vite |
| Backend | Python FastAPI |
| AI | Google Gemini (configurable model) |
| Graph | SQLite + NetworkX |
| Payments | Razorpay Test API |

No torch, no tensorflow. Biometric matching through Gemini multimodal API.
Auto-retry with exponential backoff on rate limits.

---

## Project Structure

```
Argus/
├── backend/
│   ├── main.py             # FastAPI app + all endpoints
│   ├── kyc_verify.py       # Full KYC: face + voice + liveness vs ground truth
│   ├── graph_db.py         # ArgusIdentityGraph (SQLite + NetworkX)
│   ├── seed_data.py        # Seeds the four demo scenarios
│   ├── scenario_events.py  # Event timelines for command-center replay
│   ├── semantic.py         # Legacy semantic liveness endpoint
│   └── antispoof.py        # Local CV utilities (experimental)
├── frontend/
│   └── src/
│       ├── App.jsx              # KYC scanner + tab navigation
│       ├── App.css              # Scanner styles (dark premium theme)
│       ├── NetworkDashboard.jsx # Fraud network command center
│       └── NetworkDashboard.css # Command center styles
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Setup

### Prerequisites
- Python 3.11+ and Node 18+
- Google Gemini API key ([get one](https://aistudio.google.com/apikey))

### 1. Configure environment
```bash
cp .env.example .env
```
Edit `.env`:
```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
```

**Quota tip:** Free tier = 20 req/day per model per project.
Switch `GEMINI_MODEL` between models (separate quotas) or create a new project for fresh quota.

### 2. Backend
```bash
python -m venv venv
venv\Scripts\activate
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

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/challenge` | Generate a randomized challenge |
| POST | `/verify/kyc` | Full KYC verification |
| POST | `/verify/semantic` | Semantic liveness (legacy) |
| POST | `/graph/seed` | (Re)seed the demo graph |
| GET | `/graph/scenarios` | Scenarios with live tier evaluation |
| GET | `/graph/network` | Full graph (nodes + links + clusters) |
| GET | `/graph/timeline/scenarios` | Command-center scenario list |
| GET | `/graph/scenario/{id}/replay` | Step-by-step replay state |

---

## Demo Script

### KYC Scanner

1. **Legitimate user** — Enroll → Challenge → perform action + say code → ✅ Authorized
2. **Replay attack** — Get new challenge (different code) → play old video → ❌ Wrong phrase
3. **Different person** — Someone else attempts → ❌ Face + voice mismatch

### Fraud Network

4. **Bot-speed** → 3 accounts in 10 min → Tier 1 → **BLOCK**
5. **Human mule** → 2 accounts in 24h → Tier 2 → **STEP-UP**
6. **Long-game ring** → 4 accounts over 5 days → Tier 3 → **FLAG**

---

## Why This Wins

1. **Unpredictability > pixel detection** — no arms race, no retraining needed.
2. **No re-recording** — one shot per challenge, generated fresh each time.
3. **Delayed reveal** — pre-recording is fundamentally impossible.
4. **Multi-factor** — face + voice + action + phrase + timing must all pass.
5. **Three velocity tiers** — catches fraud at every speed.
6. **Zero heavy ML** — runs on any machine, deploys today.

---

## Security

- `.env` files are gitignored. Only `.env.example` is tracked.
- Biometric data sent to Gemini for verification only; uploaded files deleted immediately.
- Use test/fake identifiers for PAN/Aadhaar in demos.
