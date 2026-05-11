import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

MODEL_NAME = "gemini-2.5-flash"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "public"

app = FastAPI(title="Interview Question Generator")


class GenerateRequest(BaseModel):
    job_title: str = Field(min_length=2, max_length=120)


class GenerateResponse(BaseModel):
    job_title: str
    questions: list[str]


def build_prompt(job_title: str) -> str:
    return (
        "You are an experienced hiring manager preparing for a structured interview.\n"
        f"Generate exactly 3 thoughtful, role-specific interview questions for the role: \"{job_title}\".\n\n"
        "Guidelines:\n"
        "- Each question should probe a distinct competency (e.g. behavioral, situational, technical/domain).\n"
        "- Questions should be open-ended and reveal how the candidate thinks, not yes/no.\n"
        "- Avoid generic filler like \"Tell me about yourself\".\n"
        "- Keep each question under 40 words.\n\n"
        "Respond ONLY with a JSON object of the form: {\"questions\": [\"q1\", \"q2\", \"q3\"]}"
    )


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured on the server.")
    return genai.Client(api_key=api_key)


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    job_title = req.job_title.strip()
    if not job_title:
        raise HTTPException(status_code=400, detail="Job title cannot be empty.")

    client = get_client()

    try:
        result = client.models.generate_content(
            model=MODEL_NAME,
            contents=build_prompt(job_title),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {exc}") from exc

    try:
        payload = json.loads(result.text)
        questions = [str(q).strip() for q in payload["questions"] if str(q).strip()]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="AI response was not valid JSON.") from exc

    if len(questions) != 3:
        raise HTTPException(status_code=502, detail="AI did not return exactly 3 questions.")

    return GenerateResponse(job_title=job_title, questions=questions)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.get("/app.js")
def script() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")
