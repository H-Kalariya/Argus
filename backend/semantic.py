from google import genai
from pydantic import BaseModel, Field
from typing import Optional
import os
import time
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


def _retry_call(fn, max_retries=3, base_delay=3.0):
    """Retry on 429 / RESOURCE_EXHAUSTED with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
            else:
                raise
    return fn()


def _wait_until_active(client, file_obj, timeout: int = 120, poll: float = 1.0):
    """Poll an uploaded file until it reaches ACTIVE state before use."""
    deadline = time.time() + timeout
    current = file_obj
    while time.time() < deadline:
        state = getattr(current.state, "name", str(current.state))
        if state == "ACTIVE":
            return current
        if state == "FAILED":
            raise RuntimeError(f"File {current.name} failed processing.")
        time.sleep(poll)
        current = client.files.get(name=current.name)
    raise TimeoutError(f"File {current.name} did not become ACTIVE within {timeout}s.")


class SemanticResult(BaseModel):
    action_performed: bool = Field(description="Did the user perform the described physical action?")
    fingers_held: Optional[int] = Field(description="How many fingers did they hold up (if applicable)?")
    spoken_text: str = Field(description="Transcribe exactly what they said.")
    occlusion_confirmed: bool = Field(description="Did the described occlusion actually occur?")
    semantic_pass: bool = Field(description="Overall pass/fail for the semantic check")

def verify_semantic_video(video_path: str, instruction: str) -> SemanticResult:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "No API key found. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your .env file."
        )
    client = genai.Client(api_key=api_key)
    video_file = client.files.upload(file=video_path)
    video_file = _wait_until_active(client, video_file)
    
    prompt = f"""
    You are a semantic verification system reviewing a video of a user performing a security challenge.
    Challenge: "{instruction}"
    
    1. Did the user perform the described physical action?
    2. How many fingers did they hold up (if applicable)?
    3. Transcribe exactly what they said.
    4. Did the described occlusion actually occur?
    """
    
    def _call():
        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[video_file, prompt],
            config={
                'response_mime_type': 'application/json',
                'response_schema': SemanticResult,
                'temperature': 0.1
            }
        )

    response = _retry_call(_call)
    
    client.files.delete(name=video_file.name)
    return SemanticResult.model_validate_json(response.text)
