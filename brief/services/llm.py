"""
services/llm.py
~~~~~~~~~~~~~~~
All OpenAI orchestration lives here.

Design decisions
----------------
* We use OpenAI's **function-calling** (tool-use) API to force the model to
  return a structured JSON object with exactly the fields we need:
  ``brief``, ``angles`` (list[str]), ``criteria`` (list[str]).
  This is more reliable than asking the model to format free-text JSON in the
  assistant message itself.

* ``temperature=0.4`` keeps output creative but predictable; anything above
  ~0.7 for a copywriting task tends to drift off-brand.

* ``max_tokens=600`` caps spend.  A 4-6 sentence brief + 6 bullets rarely
  needs more than ~350 tokens, so 600 is a comfortable ceiling.

* We time the wall-clock call and forward ``usage`` from the API response so
  callers can log cost/latency.
"""

import time
import json
from typing import TypedDict

import openai
from django.conf import settings


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class BriefResult(TypedDict):
    brief: str
    angles: list[str]
    criteria: list[str]
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


# ---------------------------------------------------------------------------
# JSON schema for the function-calling tool
# ---------------------------------------------------------------------------

BRIEF_TOOL = {
    "type": "function",
    "function": {
        "name": "return_brief",
        "description": (
            "Return a structured campaign brief with a paragraph, "
            "three content angles, and three creator selection criteria."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "brief": {
                    "type": "string",
                    "description": (
                        "A 4-6 sentence campaign brief tailored to the brand, "
                        "platform, goal, and tone provided."
                    ),
                },
                "angles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Three distinct content angle ideas for creators to execute.",
                },
                "criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Three creator selection criteria bullets (audience fit, style, metrics).",
                },
            },
            "required": ["brief", "angles", "criteria"],
            "additionalProperties": False,
        },
    },
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a senior influencer-marketing strategist at a top agency. "
    "Your briefs are concise, actionable, and tailored to the specific platform, goal, and brand tone. "
    "Write in clear, direct language. Avoid filler phrases like 'In conclusion' or 'As an AI'. "
    "Always call the `return_brief` function with your response — never reply in plain text."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_brief(
    brand_name: str,
    platform: str,
    goal: str,
    tone: str,
    brand_description: str = "",
) -> BriefResult:
    """
    Call the LLM and return a structured brief dict with telemetry fields.

    Raises openai.OpenAIError on API failure (callers should catch this).
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    user_prompt = (
        f"Brand: {brand_name}\n"
        f"Platform: {platform}\n"
        f"Goal: {goal}\n"
        f"Tone: {tone}\n"
    )

    if brand_description:
        user_prompt += f"Brand Description: {brand_description}\n"

    user_prompt += "\nGenerate a campaign brief for this brand."

    t_start = time.perf_counter()

    response = client.chat.completions.create(
        model="gpt-4o-mini",          # cost-efficient; swap for gpt-4o if needed
        temperature=0.4,              # low for determinism
        max_tokens=600,               # cost cap
        tools=[BRIEF_TOOL],
        tool_choice={"type": "function", "function": {"name": "return_brief"}},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    latency_ms = int((time.perf_counter() - t_start) * 1000)

    # Extract structured output from the forced function call
    tool_call = response.choices[0].message.tool_calls[0]
    result: dict = json.loads(tool_call.function.arguments)

    usage = response.usage

    return BriefResult(
        brief=result["brief"],
        angles=result["angles"],
        criteria=result["criteria"],
        latency_ms=latency_ms,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )
