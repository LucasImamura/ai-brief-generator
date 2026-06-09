# AI Briefer

A minimal, production-minded AI feature that generates a tailored influencer campaign brief given a brand name, platform, goal, and tone.

▶️ **[Watch the demo on Loom](https://www.loom.com/share/3cea67e483c04b56a192842732c788aa)**

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd ai-brief-generator

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 5. Run the dev server
python manage.py runserver

# 6. Open http://127.0.0.1:8000
```

---

## Architecture

```
ai-brief-generator/
├── manage.py
├── ai_brief_generator/       ← Django project config
│   ├── settings.py
│   └── urls.py
└── brief/                    ← Feature app
    ├── services/
    │   └── llm.py            ← All LLM logic
    ├── views.py              ← API + page views
    ├── urls.py
    ├── templates/brief/
    │   └── index.html        ← Single-page UI
    └── static/brief/
        ├── style.css         ← Design system CSS
        └── app.js            ← jQuery AJAX
```

---

## Technical Notes

### 1. Prompt Design

**System prompt** establishes the persona and format contract:
> *"You are a senior influencer-marketing strategist at a top agency. Your briefs are concise, actionable, and tailored to the specific platform, goal, and brand tone. Always call the `return_brief` function — never reply in plain text."*

This is deliberately short. Long system prompts waste tokens on every call and tend to dilute instruction following. The key constraint is the last sentence — it forces function calling and prevents prose-only responses.

**User prompt** is a compact key-value block:
```
Brand: Glossier
Platform: Instagram
Goal: Awareness
Tone: Friendly

Generate a campaign brief for this brand.
```

This format minimises token usage while giving the model unambiguous signal for each field.

**Function-calling (JSON schema)** replaces the old "respond in JSON" pattern:
- The model is forced to populate `brief`, `angles[]`, and `criteria[]`.
- `additionalProperties: false` on the schema prevents hallucinated extra fields.
- `tool_choice: { type: function, function: { name: return_brief } }` ensures the model cannot choose to skip the call.

**`temperature: 0.4`** — low enough for consistent, on-brand copy; high enough to avoid robotic repetition across calls. Values above ~0.7 risk off-topic drift for structured outputs.

---

### 2. Guardrails

| Layer | Implementation |
|---|---|
| **Allowlist validation** | `platform`, `goal`, and `tone` are checked against hard-coded sets in `views.py`. Any value not in the allowlist returns HTTP 400. This blocks prompt injection via select fields. |
| **Profanity filter** | `brand_name` is checked with [`better-profanity`](https://github.com/snguyenthanh/better_profanity) before it ever reaches the LLM. |
| **Max tokens** | `max_tokens=600` caps per-request spend. A typical response uses ~250–350 tokens. |
| **Low temperature** | `temperature=0.4` reduces hallucination risk on structured fields. |
| **Rate limiting** | `django-ratelimit` restricts each IP to **5 POST requests per minute** on the generate endpoint. Exceeding this returns HTTP 403. |
| **Brand name length** | Server rejects brand names over 80 characters to prevent excessively long prompts. |
| **API error handling** | `AuthenticationError`, `RateLimitError`, and generic `OpenAIError` are caught separately and surfaced to the UI with appropriate HTTP status codes. |

---

### 3. Tokens & Latency Measurement

**Latency** is measured with `time.perf_counter()` around the blocking `client.chat.completions.create()` call:

```python
t_start = time.perf_counter()
response = client.chat.completions.create(...)
latency_ms = int((time.perf_counter() - t_start) * 1000)
```

`perf_counter()` provides the highest-resolution timer available on the system, suitable for sub-millisecond precision. The value is wall-clock time including network round-trip to OpenAI.

**Token usage** is read directly from the API response object:

```python
usage = response.usage
# usage.prompt_tokens     — tokens in system + user messages
# usage.completion_tokens — tokens in the function call arguments
# usage.total_tokens      — sum of above
```

Both `latency_ms` and all three token counts are returned in the JSON response and displayed in the UI as a telemetry badge. This makes cost/latency visible during development without needing a separate logging backend.

**Rough cost estimate** (as of June 2026, gpt-4o-mini):
- Input: ~120 tokens × $0.15/M = ~$0.000018
- Output: ~250 tokens × $0.60/M = ~$0.000150
- **Total per call ≈ $0.00017** (~$0.17 per 1,000 briefs)

---

## API Reference

### `POST /api/generate/`

**Request body (JSON):**
```json
{
  "brand_name": "Glossier",
  "platform": "Instagram",
  "goal": "Awareness",
  "tone": "Friendly"
}
```

**Success response (200):**
```json
{
  "ok": true,
  "brief": "Glossier is looking to...",
  "angles": ["Angle 1", "Angle 2", "Angle 3"],
  "criteria": ["Criterion 1", "Criterion 2", "Criterion 3"],
  "latency_ms": 1243,
  "prompt_tokens": 118,
  "completion_tokens": 267,
  "total_tokens": 385
}
```

**Error response:**
```json
{ "ok": false, "error": "brand_name is required." }
```

---

## Tech Stack

- **Backend:** Python 3.12, Django 4.2, OpenAI Python SDK v1.x
- **LLM:** GPT-4o-mini (function-calling mode)
- **Frontend:** HTML5, Vanilla CSS, jQuery 3.7
- **Safety:** `better-profanity`, `django-ratelimit`
- **Config:** `python-dotenv`
