"""
brief/views.py
~~~~~~~~~~~~~~
API and page views for AI Briefer.

Endpoints
---------
GET  /            → renders index.html (the single-page UI)
POST /api/generate/ → validates inputs, calls LLM, returns JSON
"""

import json
import logging

from better_profanity import profanity
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .services.llm import generate_brief
import openai

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowlists — only accepted values pass server-side validation
# ---------------------------------------------------------------------------

ALLOWED_PLATFORMS = {"Instagram", "TikTok", "UGC"}
ALLOWED_GOALS = {"Awareness", "Conversions", "Content Assets"}
ALLOWED_TONES = {"Professional", "Friendly", "Playful"}


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def index(request):
    """Serve the single-page UI."""
    return render(request, "brief/index.html")


@csrf_exempt   # AJAX from same origin; CSRF token is also sent via JS header
@require_http_methods(["POST"])
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
def generate(request):
    """
    POST /api/generate/

    Body (JSON):
        brand_name  str   required
        platform    str   one of ALLOWED_PLATFORMS
        goal        str   one of ALLOWED_GOALS
        tone        str   one of ALLOWED_TONES

    Response (JSON):
        brief           str
        angles          list[str]
        criteria        list[str]
        latency_ms      int
        prompt_tokens   int
        completion_tokens int
        total_tokens    int
    """
    # --- Parse body ---
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error("Invalid JSON body.", status=400)

    brand_name = (body.get("brand_name") or "").strip()
    platform   = (body.get("platform")   or "").strip()
    goal       = (body.get("goal")       or "").strip()
    tone       = (body.get("tone")       or "").strip()
    brand_description = (body.get("brand_description") or "").strip()

    # --- Required-field validation ---
    if not brand_name:
        return _error("brand_name is required.", status=400)
    if len(brand_name) > 80:
        return _error("brand_name must be 80 characters or fewer.", status=400)

    # --- Optional brand description validation ---
    if len(brand_description) > 500:
        return _error("brand_description must be 500 characters or fewer.", status=400)

    # --- Allowlist validation (prevents prompt injection via select fields) ---
    if platform not in ALLOWED_PLATFORMS:
        return _error(f"platform must be one of: {', '.join(sorted(ALLOWED_PLATFORMS))}.", status=400)
    if goal not in ALLOWED_GOALS:
        return _error(f"goal must be one of: {', '.join(sorted(ALLOWED_GOALS))}.", status=400)
    if tone not in ALLOWED_TONES:
        return _error(f"tone must be one of: {', '.join(sorted(ALLOWED_TONES))}.", status=400)

    # --- Profanity filter on the free-text fields ---
    profanity.load_censor_words()
    if profanity.contains_profanity(brand_name):
        return _error("Brand name contains disallowed language.", status=400)
    if brand_description and profanity.contains_profanity(brand_description):
        return _error("Brand description contains disallowed language.", status=400)

    # --- Call the LLM ---
    try:
        result = generate_brief(
            brand_name=brand_name,
            platform=platform,
            goal=goal,
            tone=tone,
            brand_description=brand_description,
        )
    except openai.AuthenticationError:
        logger.error("OpenAI authentication failed — check OPENAI_API_KEY.")
        return _error("LLM service is not configured. Please add a valid OPENAI_API_KEY.", status=503)
    except openai.RateLimitError:
        logger.warning("OpenAI rate limit hit.")
        return _error("The AI service is busy. Please try again in a moment.", status=429)
    except openai.OpenAIError as exc:
        logger.exception("OpenAI error: %s", exc)
        return _error("An error occurred while generating the brief. Please try again.", status=502)
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        return _error("An unexpected error occurred.", status=500)

    return JsonResponse({"ok": True, **result})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)
