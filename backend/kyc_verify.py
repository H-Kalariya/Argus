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

    prompt = f"""You are a biometric KYC verification system for online payment authorization. 
You are given three inputs:
1. A REFERENCE FACE IMAGE — this is the enrolled user's face (ground truth identity).
2. A REFERENCE VOICE AUDIO — this is the enrolled user's voice sample (ground truth voice).
3. A CHALLENGE VIDEO (with audio) — recorded just now during the payment verification step.

The user was instructed to:
- Physical action: "{instruction}"
- Speak this exact phrase: "{spoken_phrase}"

Your job is to verify ALL of the following:

**FACE MATCH:** Compare the face in the challenge video against the reference image. 
Are they the same person? Consider facial structure, features, proportions. 
Be strict — this is a payment authorization. Rate confidence 0.0 to 1.0.

**VOICE MATCH:** Compare the voice/speech in the challenge video against the reference audio. 
Is it the same speaker? Consider pitch, timbre, speaking style, accent.
Be strict — this is a payment authorization. Rate confidence 0.0 to 1.0.

**ACTION VERIFICATION:** Did the person in the video actually perform the instructed physical action?

**SPEECH VERIFICATION:** Did the person say the exact phrase "{spoken_phrase}"? 
Transcribe what they actually said.

**LIVENESS:** Does this appear to be a live, present person? Look for:
- Natural head movements, blinking, micro-expressions
- Consistent lighting on face matching the environment  
- No screen/display edges visible (which would indicate a replay attack)
- No unnatural stillness or artifacting

**OVERALL:** Pass KYC only if ALL of the above pass (face match confidence >= 0.6, 
voice match confidence >= 0.5, action performed, correct phrase spoken, liveness confirmed).
"""

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[ref_image_file, ref_audio_file, video_file, prompt],
            config={
                'response_mime_type': 'application/json',
                'response_schema': KYCResult,
                'temperature': 0.1,
            },
        )

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
