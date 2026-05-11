import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from google import genai
from google.genai import types

from api.errors import ConfigurationError, UpstreamError, register_error_handlers
from api.schemas import GenerateRequest, GenerateResponse, Settings

GEMINI_TIMEOUT_SECONDS = 25

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("interview_generator")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "public"
MODEL_NAME = "gemini-2.5-flash"

settings = Settings()
app = FastAPI(title="Interview Question Generator")
register_error_handlers(app)


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
    if not settings.gemini_api_key:
        raise ConfigurationError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=settings.gemini_api_key)


def parse_questions(raw_text: str) -> list[str]:
    try:
        payload = json.loads(raw_text)
        questions = [str(q).strip() for q in payload["questions"] if str(q).strip()]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise UpstreamError("AI response could not be parsed as JSON.") from exc

    if len(questions) != 3:
        raise UpstreamError("AI did not return exactly 3 questions.")
    return questions


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    job_title = req.job_title.strip()
    client = get_client()
    logger.info("generate_request: job_title=%r", job_title)

    def _call_gemini():
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=build_prompt(job_title),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call_gemini), timeout=GEMINI_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        logger.warning("gemini_call_timeout after %ss", GEMINI_TIMEOUT_SECONDS)
        raise UpstreamError(f"AI provider timed out after {GEMINI_TIMEOUT_SECONDS}s.") from exc
    except Exception as exc:
        logger.exception("gemini_call_failed")
        raise UpstreamError("The AI provider request failed.") from exc

    logger.info("generate_response: chars=%d", len(result.text or ""))
    questions = parse_questions(result.text or "")
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
