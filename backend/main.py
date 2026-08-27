from fastapi import FastAPI, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
import random
import tempfile
import os
from semantic import verify_semantic_video

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHALLENGE_BANK = [
    {
        "id": 1,
        "instruction": "Touch your chin with your {hand} palm and hold for {duration} seconds.",
        "occlusion_type": "self_face_touch",
        "expected_occlusion_pct": 40,
        "motion": "static_hold",
        "params": {"hand": ["right", "left"], "duration": [2, 3, 4]}
    },
    {
        "id": 2,
        "instruction": "Turn your head completely to the {direction}, hold 1s, then turn completely to the {opposite_direction}.",
        "occlusion_type": "extreme_profile",
        "expected_occlusion_pct": 30,
        "motion": "rapid_rotation",
        "params": {"direction": ["left", "right"], "opposite_direction": ["right", "left"]}
    },
    {
        "id": 3,
        "instruction": "Pick up your phone and hold it over the {side} half of your face for {duration} seconds.",
        "occlusion_type": "foreground_object",
        "expected_occlusion_pct": 50,
        "motion": "object_hold",
        "params": {"side": ["left", "right"], "duration": [2, 3]}
    },
    {
        "id": 4,
        "instruction": "Wave your {hand} hand across your face from {start_dir} to {end_dir}.",
        "occlusion_type": "motion_sweep",
        "expected_occlusion_pct": 70,
        "motion": "high_velocity",
        "params": {"hand": ["right", "left"], "start_dir": ["left", "right"], "end_dir": ["right", "left"]}
    }
]

def generate_challenge():
    base_challenge = random.choice(CHALLENGE_BANK)
    # Instantiate params
    instantiated_instruction = base_challenge["instruction"]
    if base_challenge["id"] == 1:
        instantiated_instruction = instantiated_instruction.format(
            hand=random.choice(base_challenge["params"]["hand"]),
            duration=random.choice(base_challenge["params"]["duration"])
        )
    elif base_challenge["id"] == 2:
        dir_choice = random.choice([("left", "right"), ("right", "left")])
        instantiated_instruction = instantiated_instruction.format(
            direction=dir_choice[0],
            opposite_direction=dir_choice[1]
        )
    elif base_challenge["id"] == 3:
        instantiated_instruction = instantiated_instruction.format(
            side=random.choice(base_challenge["params"]["side"]),
            duration=random.choice(base_challenge["params"]["duration"])
        )
    elif base_challenge["id"] == 4:
        dir_choice = random.choice([("left", "right"), ("right", "left")])
        instantiated_instruction = instantiated_instruction.format(
            hand=random.choice(base_challenge["params"]["hand"]),
            start_dir=dir_choice[0],
            end_dir=dir_choice[1]
        )
        
    return {
        "id": base_challenge["id"],
        "instruction": instantiated_instruction,
        "occlusion_type": base_challenge["occlusion_type"],
        "expected_occlusion_pct": base_challenge["expected_occlusion_pct"],
        "motion": base_challenge["motion"]
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/challenge")
def get_challenge():
    return generate_challenge()

@app.post("/verify/semantic")
async def verify_semantic(instruction: str = Form(...), video: UploadFile = File(...)):
    # Save the uploaded video temporarily
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

