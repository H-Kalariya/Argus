from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
import random
import tempfile
import os
from semantic import verify_semantic_video
from kyc_verify import verify_kyc
from graph_db import ArgusIdentityGraph, assess_transaction
from seed_data import seed
import scenario_events

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Payment-authorization challenge bank.
# Design goals:
#  - Actions are UNAMBIGUOUS (no reliance on the model knowing your left vs right,
#    which is mirror-flipped on a phone's front camera and unreliable to verify).
#  - Actions are easy to do while holding a phone with one hand.
#  - Each challenge includes a SPOKEN PHRASE for voice liveness + speaker match.
#  - Physical actions still create occlusion/motion that breaks live face-swap.
CHALLENGE_BANK = [
    {
        "id": 1,
        "action": "Cover your mouth and chin with your open palm, hold for 2 seconds, then remove it.",
        "occlusion_type": "self_face_touch",
        "expected_occlusion_pct": 40,
        "motion": "static_hold",
        "phrase_type": "authorize",
    },
    {
        "id": 2,
        "action": "Slowly nod your head up and down twice.",
        "occlusion_type": "none",
        "expected_occlusion_pct": 0,
        "motion": "vertical_nod",
        "phrase_type": "digits",
    },
    {
        "id": 3,
        "action": "Hold your phone still and lean your face in close to the camera, then lean back.",
        "occlusion_type": "scale_change",
        "expected_occlusion_pct": 0,
        "motion": "depth_change",
        "phrase_type": "authorize",
    },
    {
        "id": 4,
        "action": "Raise your hand and slowly wave it once across the front of your face.",
        "occlusion_type": "motion_sweep",
        "expected_occlusion_pct": 60,
        "motion": "high_velocity",
        "phrase_type": "digits",
    },
    {
        "id": 5,
        "action": "Place two fingers against your cheek and hold them there for 2 seconds.",
        "occlusion_type": "partial_face_touch",
        "expected_occlusion_pct": 25,
        "motion": "static_hold",
        "phrase_type": "digits",
    },
]

AUTHORIZE_PHRASES = [
    "I authorize this payment",
    "Confirm and pay now",
    "Approve this transaction",
    "Yes, complete my payment",
]


def _make_phrase(phrase_type: str) -> str:
    """Generate the spoken phrase for a challenge."""
    if phrase_type == "digits":
        # A random 4-digit code, spoken as separate digits, is a strong
        # challenge-response signal: unpredictable + easy to verify by transcription.
        code = "".join(str(random.randint(0, 9)) for _ in range(4))
        spaced = " ".join(code)
        return f"My code is {spaced}"
    return random.choice(AUTHORIZE_PHRASES)


def generate_challenge():
    base = random.choice(CHALLENGE_BANK)
    spoken_phrase = _make_phrase(base["phrase_type"])
    instruction = f'{base["action"]} While doing this, say clearly: "{spoken_phrase}"'
    return {
        "id": base["id"],
        "instruction": instruction,
        "action": base["action"],
        "spoken_phrase": spoken_phrase,
        "occlusion_type": base["occlusion_type"],
        "expected_occlusion_pct": base["expected_occlusion_pct"],
        "motion": base["motion"],
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/challenge")
def get_challenge():
    return generate_challenge()


@app.post("/verify/semantic")
async def verify_semantic(instruction: str = Form(...), video: UploadFile = File(...)):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    temp_file.write(await video.read())
    temp_file.close()

    try:
        result = verify_semantic_video(temp_file.name, instruction)
        return result.model_dump()
    except Exception as e:
        return {"error": str(e)}
    finally:
        os.unlink(temp_file.name)


def _save_upload(upload: UploadFile, data: bytes, default_suffix: str) -> str:
    suffix = os.path.splitext(upload.filename or "")[1] or default_suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    return tmp.name


def _clean_mime(raw: str, fallback: str) -> str:
    """Strip codec params: 'video/webm;codecs=vp8,opus' -> 'video/webm'."""
    if not raw:
        return fallback
    return raw.split(";")[0].strip() or fallback


@app.post("/verify/kyc")
async def verify_kyc_endpoint(
    instruction: str = Form(...),
    spoken_phrase: str = Form(...),
    reference_image: UploadFile = File(...),
    reference_audio: UploadFile = File(...),
    video: UploadFile = File(...),
):
    """
    Full KYC: compares a ground-truth face image and voice audio against a
    live challenge video (face match + voice match + action + speech + liveness).
    """
    img_bytes = await reference_image.read()
    audio_bytes = await reference_audio.read()
    video_bytes = await video.read()

    image_mime = _clean_mime(reference_image.content_type, "image/jpeg")
    audio_mime = _clean_mime(reference_audio.content_type, "audio/webm")
    video_mime = _clean_mime(video.content_type, "video/webm")

    img_path = _save_upload(reference_image, img_bytes, ".jpg")
    audio_path = _save_upload(reference_audio, audio_bytes, ".webm")
    video_path = _save_upload(video, video_bytes, ".webm")

    try:
        result = verify_kyc(
            reference_image_path=img_path,
            reference_audio_path=audio_path,
            challenge_video_path=video_path,
            instruction=instruction,
            spoken_phrase=spoken_phrase,
            image_mime=image_mime,
            audio_mime=audio_mime,
            video_mime=video_mime,
        )
        return result.model_dump()
    except Exception as e:
        return {"error": str(e)}
    finally:
        for p in (img_path, audio_path, video_path):
            try:
                os.unlink(p)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Identity Graph / Network Fraud Detection endpoints
# ---------------------------------------------------------------------------

# Human-friendly descriptions for each seeded demo scenario.
SCENARIOS = {
    "legit": {
        "signal_type": "device_fingerprint",
        "signal_value": "device_A1",
        "title": "Legitimate User",
        "story": "A single genuine user on their own device. No shared signals, passes liveness.",
    },
    "tier1": {
        "signal_type": "device_fingerprint",
        "signal_value": "device_BOT_ff31",
        "title": "Tier 1 — Bot-Speed Attack",
        "story": "3 accounts created on ONE device within ~10 minutes, all failing liveness. Scripted account creation / card testing.",
    },
    "tier2": {
        "signal_type": "device_fingerprint",
        "signal_value": "device_MULE_7a2c",
        "title": "Tier 2 — Human-Speed Mule",
        "story": "2 accounts on the same device within 24 hours. Manual mule account creation.",
    },
    "tier3": {
        "signal_type": "device_fingerprint",
        "signal_value": "device_RING_e91b",
        "title": "Tier 3 — Long-Game Mule Ring",
        "story": "4 accounts sharing one device fingerprint, spread over ~5 days with different emails. Patient mule recruitment.",
    },
}


def _get_graph() -> ArgusIdentityGraph:
    return ArgusIdentityGraph()


@app.post("/graph/seed")
def graph_seed():
    """(Re)seed the demo identity graph with all attack scenarios."""
    g = _get_graph()
    try:
        seed(g)
        return {"status": "seeded", "scenarios": list(SCENARIOS.keys())}
    finally:
        g.close()


@app.get("/graph/scenarios")
def graph_scenarios():
    """List the demo scenarios with a live risk assessment for each."""
    g = _get_graph()
    try:
        out = []
        for key, meta in SCENARIOS.items():
            stype, sval = meta["signal_type"], meta["signal_value"]
            liveness = "FAILED" if key == "tier1" else "PASSED"
            artifact = 7.2 if key == "tier1" else 1.5
            # Assess WITHOUT mutating (tier1 already has failed_liveness seeded).
            tiers = g.check_velocity_tiers(stype, sval)
            soft = g.get_soft_link_score(stype, sval)
            total_risk = round(soft * 0.3 + artifact * 0.7, 2)
            if tiers["tier1_triggered"] or artifact > 5.0:
                decision = {"action": "BLOCK", "reason": "Bot-speed attack or high artifact score"}
            elif tiers["tier2_triggered"] or total_risk > 3.0:
                decision = {"action": "STEP_UP_CHALLENGE", "reason": "Suspicious pattern"}
            elif tiers["tier3_triggered"]:
                decision = {"action": "FLAG_FOR_REVIEW", "reason": "Long-term mule network pattern"}
            else:
                decision = {"action": "APPROVE", "reason": "Low risk"}
            out.append({
                "key": key,
                "title": meta["title"],
                "story": meta["story"],
                "signal_type": stype,
                "signal_value": sval,
                "tiers": tiers,
                "soft_score": soft,
                "total_risk": total_risk,
                "decision": decision,
            })
        return {"scenarios": out}
    finally:
        g.close()


@app.get("/graph/network")
def graph_network():
    """Return nodes + links for the whole identity graph (for visualization)."""
    g = _get_graph()
    try:
        gx = g.build_networkx()
        nodes = []
        for n, attrs in gx.nodes(data=True):
            nodes.append({
                "id": n,
                "kind": attrs.get("kind"),
                "label": attrs.get("label") or attrs.get("signal_value") or n,
                "signal_type": attrs.get("signal_type"),
                "link_class": attrs.get("link_class"),
            })
        links = []
        for u, v, attrs in gx.edges(data=True):
            links.append({"source": u, "target": v, "link_class": attrs.get("link_class"),
                           "signal_type": attrs.get("signal_type")})
        clusters = g.clusters()
        return {"nodes": nodes, "links": links, "cluster_count": len(clusters), "clusters": clusters}
    finally:
        g.close()


# ---------------------------------------------------------------------------
# Command Center — event-timeline replay endpoints
# ---------------------------------------------------------------------------

@app.get("/graph/timeline/scenarios")
def timeline_scenarios():
    """List demo scenarios (id, name, icon, story, event count) for the command center."""
    return {"scenarios": scenario_events.scenario_list()}


@app.get("/graph/events")
def graph_events():
    """Flat chronological event log across all scenarios."""
    return {"events": scenario_events.all_events()}


@app.get("/graph/scenario/{scenario_id}/replay")
def graph_scenario_replay(scenario_id: str):
    """Full step-by-step replay state (DB rows, graph, tiers, risk, decision)."""
    data = scenario_events.replay(scenario_id)
    if data is None:
        return {"error": f"Unknown scenario '{scenario_id}'"}
    return data
