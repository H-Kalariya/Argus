from google import genai
from pydantic import BaseModel, Field
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

class SemanticResult(BaseModel):
    action_performed: bool = Field(description="Did the user perform the described physical action?")
    fingers_held: Optional[int] = Field(description="How many fingers did they hold up (if applicable)?")
    spoken_text: str = Field(description="Transcribe exactly what they said.")
    occlusion_confirmed: bool = Field(description="Did the described occlusion actually occur?")
    semantic_pass: bool = Field(description="Overall pass/fail for the semantic check")

def verify_semantic_video(video_path: str, instruction: str) -> SemanticResult:
    client = genai.Client()
    video_file = client.files.upload(file=video_path)
    
    prompt = f"""
    You are a semantic verification system reviewing a video of a user performing a security challenge.
    Challenge: "{instruction}"
    
    1. Did the user perform the described physical action?
    2. How many fingers did they hold up (if applicable)?
    3. Transcribe exactly what they said.
    4. Did the described occlusion actually occur?
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[video_file, prompt],
        config={
            'response_mime_type': 'application/json',
            'response_schema': SemanticResult,
            'temperature': 0.1
        }
    )
    
    client.files.delete(name=video_file.name)
    return SemanticResult.model_validate_json(response.text)
