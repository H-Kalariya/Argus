"""
KYC Verification Module — Face + Voice + Liveness via Gemini Multimodal

Architecture:
- Reference face image (ground truth) + reference voice audio (ground truth) 
  are provided by the user during enrollment.
- During a challenge, the user records a video performing a physical action 
  and speaking a phrase.
- Gemini receives ALL three inputs (ref image, ref audio, challenge video) 
  and performs:
    1. Face match: is the person in the video the same as the reference image?
    2. Voice match: is the speaker in the video the same as the reference audio?
    3. Semantic liveness: did they perform the instructed action?
    4. Speech verification: did they say the instructed phrase?
    5. Overall KYC pass/fail.
"""

from google import genai
from pydantic import BaseModel, Field
from typing import Optional
import os
import time
from dotenv import load_dotenv

load_dotenv()

# Model can be overridden via env var (useful when hitting quota on one model).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


def _retry_call(fn, max_retries=3, base_delay=3.0):
    """Retry a Gemini API call with exponential backoff on rate-limit errors."""
    import time as _time
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = base_delay * (2 ** attempt)
                _time.sleep(wait)
            else:
                raise
    # Final attempt, let it raise
    return fn()


def _upload(client, path: str, mime_type: str, label: str):
    """Upload a file with an explicit MIME type."""
    from google.genai import types
    return client.files.upload(
        file=path,
        config=types.UploadFileConfig(mime_type=mime_type, display_name=label),
    )


def _wait_until_active(client, file_obj, label: str, timeout: int = 120, poll: float = 1.0):
    """Poll an uploaded file until it reaches ACTIVE state.

    Uploaded media (especially video) is asynchronously processed by Gemini and
    starts in PROCESSING. Using it before it is ACTIVE raises FAILED_PRECONDITION.
    """
    deadline = time.time() + timeout
    current = file_obj
    while time.time() < deadline:
        state = getattr(current.state, "name", str(current.state))
        if state == "ACTIVE":
            return current
        if state == "FAILED":
            raise RuntimeError(
                f"{label} failed processing on Gemini (unsupported/corrupt media)."
            )
        time.sleep(poll)
        current = client.files.get(name=current.name)
    raise TimeoutError(f"{label} did not become ACTIVE within {timeout}s.")


class KYCResult(BaseModel):
    face_match: bool = Field(description="Is the face in the video the same person as the reference image?")
    face_confidence: float = Field(description="Confidence score for face match (0.0 to 1.0)")
    voice_match: bool = Field(description="Is the speaker's voice in the video the same as the reference audio?")
    voice_confidence: float = Field(description="Confidence score for voice match (0.0 to 1.0)")
    action_performed: bool = Field(description="Did the user perform the described physical action?")
    spoken_phrase_correct: bool = Field(description="Did the user say the exact instructed phrase?")
    spoken_text: str = Field(description="Transcription of what they actually said")
    liveness_pass: bool = Field(description="Does the video appear to be a live person (not a photo/video replay)?")
    overall_kyc_pass: bool = Field(description="Overall KYC verification pass/fail")
    reasoning: str = Field(description="Brief explanation of the decision")


def verify_kyc(
    reference_image_path: str,
    reference_audio_path: str,
    challenge_video_path: str,
    instruction: str,
    spoken_phrase: str,
    image_mime: str = "image/jpeg",
    audio_mime: str = "audio/webm",
    video_mime: str = "video/webm",
) -> KYCResult:
    """
    Perform full KYC verification comparing ground truth (image + audio)
    against a challenge video using Gemini multimodal.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("No API key found. Set GEMINI_API_KEY in your .env file.")

    client = genai.Client(api_key=api_key)

    # Upload all files to Gemini with explicit MIME types (extension-based
    # inference is unreliable for MediaRecorder blobs).
    ref_image_file = _upload(client, reference_image_path, image_mime, "reference image")
    ref_audio_file = _upload(client, reference_audio_path, audio_mime, "reference audio")
    video_file = _upload(client, challenge_video_path, video_mime, "challenge video")

    # Wait for each file to finish server-side processing before use.
    # Image is usually instant; audio and video may take a few seconds.
    ref_image_file = _wait_until_active(client, ref_image_file, "Reference image")
    ref_audio_file = _wait_until_active(client, ref_audio_file, "Reference audio")
    video_file = _wait_until_active(client, video_file, "Challenge video")

    prompt = f"""You are a strict biometric KYC verification system for high-value payment authorization.
You are given three inputs:
1. A REFERENCE FACE IMAGE — the enrolled user's face (ground truth).
2. A REFERENCE VOICE AUDIO — the enrolled user's voice (ground truth).
3. A CHALLENGE VIDEO (with audio) — supposedly recorded live just now.

The user was instructed to:
- Physical action: "{instruction}"
- Speak this EXACT phrase: "{spoken_phrase}"

Verify ALL of the following with STRICT criteria:

**FACE MATCH:** Is the person in the video the same as the reference image?
Rate confidence 0.0 to 1.0. Be strict.

**VOICE MATCH:** Is the speaker the same as the reference audio?
Rate confidence 0.0 to 1.0. Be strict.

**ACTION VERIFICATION:** Did they actually perform the specific instructed action?

**SPEECH VERIFICATION:** Did they say EXACTLY "{spoken_phrase}"?
Transcribe what they actually said. Even one wrong digit = fail.

**LIVENESS (CRITICAL — be extremely strict here):**
This is the most important check. You must determine if this is a LIVE person 
or a REPLAY ATTACK (someone playing a pre-recorded video on a phone/screen).

IMPORTANT CONTEXT: The challenge was revealed to the user DURING recording:
- The physical action instruction appeared 2 seconds into the recording
- The spoken phrase appeared 7 seconds into the recording
Therefore, the user should NOT start the action in the very first 2 seconds, and 
should NOT speak the phrase before ~7 seconds in. If the action starts immediately 
at frame 0 or the phrase is spoken in the first 5 seconds, this is strong evidence 
of a pre-recorded replay attack.

Signs of a REPLAY ATTACK (any ONE = liveness FAIL):
- The video appears to be of a screen/display (look for: pixel grid texture, 
  slight color banding, unnaturally uniform lighting across the face, 
  screen reflections/glare, slight barrel/pincushion distortion from filming a flat surface)
- The face appears perfectly flat with no real 3D depth cues
- Lighting on the face doesn't match what you'd expect from a webcam pointed at a real person
- The background looks like it's on a screen (too sharp edges, UI elements, notification bars)
- Motion looks like it's from a recording (too smooth, no micro-jitter from handheld device)
- The spoken phrase sounds like it's coming through a speaker (tinny, compressed audio quality 
  vs. direct microphone capture)

Signs of a LIVE person:
- Natural 3D depth in the face (nose shadow, cheek contour responding to light)
- Micro-movements and slight imperfections in motion
- Direct microphone audio quality (room reverb, natural dynamics)
- Background is a real environment (not a flat image)
- Reactive behavior (slight adjustments, natural pauses)

If you CANNOT confidently determine liveness, default to FAIL (false reject is safer 
than false accept in payment authorization).

**OVERALL:** Pass ONLY if ALL checks pass (face >= 0.6, voice >= 0.5, 
action correct, exact phrase spoken, AND liveness confirmed).
"""

    try:
        def _call():
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[ref_image_file, ref_audio_file, video_file, prompt],
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': KYCResult,
                    'temperature': 0.1,
                },
            )

        response = _retry_call(_call)
        result = KYCResult.model_validate_json(response.text)
    finally:
        # Clean up uploaded files
        try:
            client.files.delete(name=ref_image_file.name)
        except Exception:
            pass
        try:
            client.files.delete(name=ref_audio_file.name)
        except Exception:
            pass
        try:
            client.files.delete(name=video_file.name)
        except Exception:
            pass

    return result
