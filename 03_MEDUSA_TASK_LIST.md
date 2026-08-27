# Project Medusa — Implementation Task List
For an AI coding agent (Kiro / Antigravity). Follow phases in order. **Do not start Phase N+1 until Phase N's testing gate passes.** Read `01_PROJECT_MEDUSA_MASTER_PLAN.md` and `02_MEDUSA_CRITICAL_CONSIDERATIONS.md` fully before Phase 0.

---

## Phase 0 — Research & Grounding (no code)
**Goal:** don't build blind.
- [ ] Read GOTCHA paper (arXiv:2210.06186) in full; extract its challenge taxonomy and scoring approach into notes.
- [ ] Skim GOTCHA's repo (`github.com/mittalgovind/GOTCHA-Deepfakes`) structure — note any reusable challenge definitions or scoring code.
- [ ] Search and skim 5+ papers/blogs on: face-swap detection under occlusion, optical-flow deepfake artifacts, silent/active liveness detection surveys.
- [ ] Search and skim 3+ resources on graph-based fraud-ring detection (hard/soft link modeling, device fingerprinting, community detection).
- [ ] Identify and shortlist an open-source real-time face-swap tool usable for generating test attack videos (for later phases).
- [ ] Write a 1-page internal notes doc: key metrics/thresholds found in literature, and where Medusa's approach matches or diverges.

**Testing gate:** notes doc exists and names at least: (a) GOTCHA's challenge categories, (b) 2+ CV artifact metrics with literature-backed rationale, (c) 1 candidate face-swap tool for test data generation. If any are missing, do not proceed.

---

## Phase 1 — Project Skeleton & Environment
- [ ] Initialize repo structure: `/frontend` (React), `/backend` (FastAPI), `/cv_pipeline`, `/graph`, `/data`, `/docs`.
- [ ] Set up Python env (FastAPI, OpenCV, MediaPipe, NetworkX, SQLite driver), pin versions in `requirements.txt`.
- [ ] Set up React app with MediaRecorder-based webcam capture component (record-only, no logic yet).
- [ ] Provision API keys: chosen multimodal LLM (Gemini 1.5 Flash or GPT-4o-mini), Razorpay Test Mode keys.
- [ ] `.env.example` with all required keys documented.

**Testing gate:** `npm run dev` renders webcam preview and can record a short clip; `uvicorn` backend boots and returns 200 on a `/health` endpoint. Confirm on the actual browser/OS you intend to demo on (see Critical Considerations §2).

---

## Phase 2 — Challenge Engine
- [ ] Implement `CHALLENGE_BANK` with the 4+ categories from the master plan (self-occlusion, extreme rotation, foreground object, rapid motion), each parameterized (hand/direction/duration).
- [ ] Backend endpoint: `GET /challenge` returns a randomized challenge instruction + metadata.
- [ ] Frontend: display instruction, countdown timer, record challenge-response video, upload to backend.
- [ ] Validate: instructions are never physically impossible (manual review of every bank entry).

**Testing gate:** 5 different team members can each read a random challenge and complete it correctly on the first try within the given time limit, on camera. If any instruction is confusing or too hard, rewrite it before moving on.

---

## Phase 3 — Layer 1: Semantic Verification
- [ ] Implement the semantic verification prompt (from master plan Part 2) against the chosen multimodal LLM.
- [ ] Backend endpoint: `POST /verify/semantic` — takes video + challenge instruction, returns the specified JSON schema.
- [ ] Handle LLM latency asynchronously (don't block Layer 2).
- [ ] Add retry/error handling for malformed LLM JSON output (schema validation + one retry).

**Testing gate:** run against 10 real self-recorded challenge videos (mix of all challenge types). `semantic_pass` must be `true` for all 10 legitimate attempts, with correctly transcribed speech and correct finger counts where applicable. Fix prompt/parsing before proceeding if any fail.

---

## Phase 4 — Layer 2: Temporal Artifact Detection (Medusa Score)
- [ ] Implement `MedusaArtifactDetector` class: MediaPipe FaceMesh setup, per-frame processing loop.
- [ ] Implement landmark jitter metric (frame-to-frame keypoint displacement on the specified key indices).
- [ ] Implement **real** edge-flicker metric — jawline boundary pixel-intensity variance across frames. Do NOT ship the placeholder `np.random.uniform` version — this is a blocking correctness task per Critical Considerations §2.
- [ ] Implement tracking-loss counter (consecutive frames with no detected face mesh).
- [ ] Implement motion-vector anomaly via Farneback optical flow.
- [ ] Implement score aggregation into a single Medusa Score.
- [ ] Backend endpoint: `POST /verify/artifacts` — takes video, returns per-metric scores + aggregate Medusa Score.

**Testing gate (two parts, both required):**
1. Run against the same 10 legitimate videos from Phase 3 — Medusa Score should cluster low and consistently below your provisional block threshold.
2. Run against at least 3 attack videos (from the face-swap tool identified in Phase 0, or pre-recorded deepfake substitutes per Critical Considerations §3) performing the same challenges — Medusa Score should cluster clearly higher than the legitimate set. If separation is not clean, tune metric weights/thresholds before proceeding — this calibration step is not optional.

---

## Phase 5 — Identity Graph & Tiered Velocity
- [ ] Implement `MedusaIdentityGraph` class: SQLite schema for edges + risk_scores, NetworkX in-memory graph, load-on-init.
- [ ] Implement `add_edge` (hard/soft, subtype, weight, timestamp).
- [ ] Implement `check_velocity_tiers` for the three windows (15 min / 24h / 7d) with the specified thresholds.
- [ ] Implement `find_connected_components` (hard-link clusters) and `get_soft_link_score`.
- [ ] Implement `assess_transaction` risk-decision function combining artifact score + graph signals into BLOCK / STEP_UP_CHALLENGE / FLAG_FOR_REVIEW / APPROVE.

**Testing gate:** write unit tests simulating each tier independently (script: 3 signals in 15 min → Tier 1 fires; 2 accounts in 24h → Tier 2 fires; pattern across 7 days → Tier 3 fires; none of the above → no false trigger on a normal single-account flow). All four scenarios must produce the correct `action` before proceeding.

---

## Phase 6 — Razorpay Payment Flow Integration
- [ ] Integrate Razorpay Test Mode order creation.
- [ ] Gate the payment confirmation step behind the challenge → semantic check → artifact check → graph check → risk decision pipeline.
- [ ] Wire decision outcomes to actual flow behavior: APPROVE → complete payment; STEP_UP_CHALLENGE → issue a second, different challenge; BLOCK → halt with a clear message; FLAG_FOR_REVIEW → complete payment but log for review queue.

**Testing gate:** run a full end-to-end legitimate transaction from checkout to Razorpay test payment completion with zero manual intervention. Confirm a BLOCK scenario actually halts payment (not just logs it).

---

## Phase 7 — Dashboard & Visualization
- [ ] Build a live dashboard: current transaction's semantic score, Medusa Score breakdown (per-metric), graph view of the identity graph with hard/soft edges color-coded.
- [ ] Real-time update as a demo scenario plays out (no full-page reloads).
- [ ] Add a "scenario trigger" panel for demo purposes: buttons to replay each of the 4 demo scenarios on cue.

**Testing gate:** each of the 4 demo scenarios (legitimate user, bot attack, live face-swap attack, slow mule network) can be triggered from the dashboard and produces the correct visual outcome end-to-end, matching Part 4 of the master plan, with no console errors.

---

## Phase 8 — Full Demo Rehearsal & Hardening
- [ ] Run the complete 4-scene demo script back-to-back, timed, at least 3 times without a code change in between.
- [ ] Test in the actual room / lighting / browser / network conditions you'll present in (see Critical Considerations §2).
- [ ] Prepare fallback: pre-recorded backup video of a full successful demo run, in case live webcam/network fails on stage.
- [ ] Write the 1-page write-up covering: thesis, architecture, GOTCHA grounding, roadmap (Part 5 of master plan), and the privacy/compliance framing from Critical Considerations §4.
- [ ] Prepare Q&A answers for: "how do you know the threshold isn't overfit to your test videos", "what happens with a real face-swap model you haven't seen", "how does this scale past NetworkX/SQLite".

**Testing gate:** 3 consecutive full dry-runs complete within your pitch time limit with no manual fixes mid-run. If any run fails, fix and re-run all 3 before presentation day.

---

## Ownership note
Assign each phase a clear owner before starting. Phases 2-4 (challenge engine + both AI layers) and Phase 5 (identity graph) can run in parallel by two sub-teams once Phase 1 is done; Phase 6 onward is sequential and requires both streams merged.
