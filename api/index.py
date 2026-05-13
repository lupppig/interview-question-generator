import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from google import genai
from slowapi import Limiter
from slowapi.util import get_remote_address
from google.genai import types

from api.cache import QuestionCache
from api.errors import ConfigurationError, UpstreamError, register_error_handlers
from api.schemas import GenerateRequest, GenerateResponse, Settings

GEMINI_TIMEOUT_SECONDS = 25

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("interview_generator")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "public"
MODEL_NAME = "gemini-2.5-flash"

settings = Settings()
limiter = Limiter(key_func=get_remote_address)
cache = QuestionCache(settings.redis_url, settings.cache_ttl_seconds)

if not settings.gemini_api_key:
    logger.warning("GEMINI_API_KEY is not set — requests will fail until it is configured.")
    gemini_client: genai.Client | None = None
else:
    gemini_client = genai.Client(api_key=settings.gemini_api_key)

app = FastAPI(title="Interview Question Generator")
app.state.limiter = limiter
register_error_handlers(app)
logger.info("cache_enabled=%s", cache.enabled)


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
    if gemini_client is None:
        raise ConfigurationError("GEMINI_API_KEY is not set.")
    return gemini_client


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
@limiter.limit("5/minute")
async def generate(request: Request, req: GenerateRequest) -> GenerateResponse:
    job_title = req.job_title.strip()
    logger.info("generate_request: job_title=%r", job_title)

    cached = await cache.get(job_title)
    if cached is not None:
        logger.info("cache_hit: job_title=%r", job_title)
        return GenerateResponse(job_title=job_title, questions=cached)

    client = get_client()

    try:
        result = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=build_prompt(job_title),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            ),
            timeout=GEMINI_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        logger.warning("gemini_call_timeout after %ss", GEMINI_TIMEOUT_SECONDS)
        raise UpstreamError(f"AI provider timed out after {GEMINI_TIMEOUT_SECONDS}s.") from exc
    except Exception as exc:
        logger.exception("gemini_call_failed")
        raise UpstreamError("The AI provider request failed.") from exc

    logger.info("generate_response: chars=%d", len(result.text or ""))
    questions = parse_questions(result.text or "")
    await cache.set(job_title, questions)
    return GenerateResponse(job_title=job_title, questions=questions)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="public")
