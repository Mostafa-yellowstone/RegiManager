"""
Public website assistant (Gemini free tier) for DMV, title, plate, TLC and insurance-agency questions.

Conversations are not stored. Visitors are told not to share personal data because free-tier
requests may be used by Google to improve its products.
"""

import json
import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .ratelimit import client_ip, consume_rate_limit

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_MESSAGE_CHARS = 1500
MAX_HISTORY_TURNS = 12
REQUEST_TIMEOUT_SECONDS = 30

LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "ar": "Arabic",
    "zh": "Chinese (Simplified)",
    "ru": "Russian",
    "bn": "Bengali",
    "ht": "Haitian Creole",
    "fr": "French",
    "ko": "Korean",
    "pl": "Polish",
    "ur": "Urdu",
    "hi": "Hindi",
    "pt": "Portuguese",
    "it": "Italian",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "yi": "Yiddish",
    "el": "Greek",
    "pa": "Punjabi",
    "de": "German",
}

SYSTEM_PROMPT = """You are "Regi", the friendly, expert DMV and insurance guide on the RegiManager website.
If asked who you are, say you are Regi, RegiManager's AI guide.
RegiManager is software used by professional service bureaus (PSBs) and insurance agencies. It is NOT a government
agency and is not affiliated with or endorsed by any DMV or the NYC Taxi & Limousine Commission (TLC).

LANGUAGE
- The visitor chose {language}. Always reply in {language}, even when their message (or a suggested question) is
  written in another language, unless they explicitly ask you to switch languages.
- Keep official form numbers, agency names and website addresses exactly as written (e.g. MV-82, dmv.ny.gov).

WHAT YOU HELP WITH (New York first, other US states in general terms)
- Vehicle registration (new, used, out-of-state transfer, leased, commercial), registration renewals, duplicate
  registrations, plate transfers and plate surrender, personalized/custom plates.
- Titles: getting a title, transferring ownership, duplicate/replacement titles, liens and lien releases, gifts and
  family transfers, buying from a private seller or dealer, salvage and rebuilt basics.
- Sales tax on vehicle purchases and gifts, bills of sale, insurance cards, inspections.
- Insurance: auto, commercial and TLC/for-hire insurance basics, insurance lapses and what to do, why to surrender
  plates before cancelling insurance, SR-22-style filings (explain that New York does not use SR-22).
- NYC TLC: TLC vehicle license and driver license renewals, typical requirements (TLC-approved commercial insurance,
  DMV registration, TLC inspections, base affiliation, drug test and courses for drivers), and that TLC services are
  handled through the TLC's own online system and facilities.
- What PSBs and insurance agencies can do for customers: prepare and file DMV paperwork, renewals, plate transfers,
  title work, insurance quotes and policies, TLC paperwork; how they save trips and mistakes.

HOW TO ANSWER
- Be practical: give the steps, the documents to bring, the official forms by number, and where it can be done
  (online, mail, DMV office, or a PSB/insurance agency).
- Well-known New York forms you may cite: MV-82 (Vehicle Registration/Title Application), MV-902 (Application for
  Duplicate Certificate of Title), MV-912 (Bill of Sale), DTF-802 (Statement of Transaction - Sale or Gift of Motor
  Vehicle, for sales tax), FS-20 (New York Insurance Identification Card), MV-44 (driver license/ID application).
- Fees, tax rates, deadlines and rules change. Never invent exact amounts. Give typical ranges only if you are
  confident and always tell the visitor to confirm on the official site: dmv.ny.gov for New York DMV,
  nyc.gov/tlc for TLC, tax.ny.gov for sales tax, or their state's DMV website.
- Use short paragraphs and bullet lists. Keep most answers under 250 words unless the visitor asks for detail.
- Ask one short clarifying question when the answer depends on details (state, new vs used, dealer vs private
  sale, leased, commercial, TLC).
- If the visitor wants help doing it, suggest visiting a local PSB or insurance agency that uses RegiManager, or
  the contact page at /contact/ (phone (914) 292-9743, email mail@regimanager.com).

LIMITS
- Do not ask for, and tell visitors not to share, personal data (SSN, license or policy numbers, VINs tied to a
  person, dates of birth, payment details). This chat is not private storage.
- No legal advice: for tickets, court, accidents or disputes, recommend a licensed attorney or the agency itself.
- Stay on topic (vehicles, DMV, titles, plates, TLC, insurance, PSB services). Politely decline unrelated requests.
- If you are unsure, say so and point to the official source instead of guessing.
"""

FALLBACK_BUSY = (
    "The assistant is very busy right now. Please try again in a minute, or contact us at (914) 292-9743 / "
    "mail@regimanager.com."
)
FALLBACK_UNCONFIGURED = "The assistant isn't available yet. Please contact us at (914) 292-9743 or mail@regimanager.com."


def _reply(payload, status=200):
    response = JsonResponse(payload, status=status)
    # Keep JSON for the widget; FriendlyErrorMiddleware would swap 5xx bodies for an HTML page.
    response["X-Regi-Error-Page"] = "1"
    return response


def assistant_enabled():
    return bool(getattr(settings, "GEMINI_API_KEY", ""))


def _models():
    raw = getattr(settings, "GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite")
    return [m.strip() for m in str(raw).split(",") if m.strip()]


def _daily_budget_ok():
    """Global daily cap keeps usage inside the free tier."""
    limit = int(getattr(settings, "ASSISTANT_DAILY_LIMIT", 1000))
    day = time.strftime("%Y%m%d", time.gmtime())
    return consume_rate_limit(f"assistant-day:{day}", limit=limit, window_seconds=26 * 60 * 60)


def _clean_history(raw_messages):
    history = []
    for message in raw_messages[-MAX_HISTORY_TURNS:]:
        if not isinstance(message, dict):
            continue
        role = "model" if message.get("role") == "assistant" else "user"
        text = str(message.get("content") or "").strip()[:MAX_MESSAGE_CHARS]
        if text:
            history.append({"role": role, "parts": [{"text": text}]})
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def _extract_text(payload):
    for candidate in payload.get("candidates") or []:
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
        if text:
            return text
    return ""


def ask_gemini(history, language_name):
    """Return (reply_text, model) or raise RuntimeError('busy'|'error')."""
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT.format(language=language_name)}]},
        "contents": history,
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1200, "thinkingConfig": {"thinkingBudget": 0}},
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ],
    }
    if getattr(settings, "GEMINI_GROUNDING", False):
        body["tools"] = [{"google_search": {}}]
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"}
    outcome = "error"
    for model in _models():
        try:
            response = requests.post(
                GEMINI_URL.format(model=model), headers=headers, data=json.dumps(body), timeout=REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException:
            logger.warning("Assistant request to %s failed", model)
            continue
        if response.status_code in (429, 500, 503):
            outcome = "busy"
            continue
        if response.status_code != 200:
            logger.warning("Assistant model %s returned HTTP %s", model, response.status_code)
            continue
        try:
            text = _extract_text(response.json())
        except ValueError:
            text = ""
        if text:
            return text, model
    raise RuntimeError(outcome)


@require_POST
def assistant_chat(request):
    if not assistant_enabled():
        return _reply({"ok": False, "reply": FALLBACK_UNCONFIGURED}, status=503)

    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return _reply({"ok": False, "error": "Invalid request."}, status=400)

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return _reply({"ok": False, "error": "Send at least one message."}, status=400)
    last = messages[-1] if isinstance(messages[-1], dict) else {}
    if last.get("role") != "user" or not str(last.get("content") or "").strip():
        return _reply({"ok": False, "error": "The last message must be a question."}, status=400)
    if len(str(last.get("content"))) > MAX_MESSAGE_CHARS:
        return _reply(
            {"ok": False, "error": f"Please keep each message under {MAX_MESSAGE_CHARS} characters."}, status=400
        )

    language_code = str(payload.get("language") or "en")
    language_name = LANGUAGES.get(language_code, "English")

    ip = client_ip(request)
    if not consume_rate_limit(f"assistant-min:{ip}", limit=8, window_seconds=60) or not consume_rate_limit(
        f"assistant-ip-day:{ip}", limit=int(getattr(settings, "ASSISTANT_PER_VISITOR_DAILY_LIMIT", 80)),
        window_seconds=24 * 60 * 60,
    ):
        return _reply(
            {"ok": False, "reply": "You've asked a lot of questions in a short time. Please wait a little and try again."},
            status=429,
        )
    if not _daily_budget_ok():
        return _reply({"ok": False, "reply": FALLBACK_BUSY}, status=429)

    history = _clean_history(messages)
    if not history:
        return _reply({"ok": False, "error": "Send at least one message."}, status=400)

    try:
        reply, model = ask_gemini(history, language_name)
    except RuntimeError as exc:
        status = 429 if str(exc) == "busy" else 502
        return _reply({"ok": False, "reply": FALLBACK_BUSY}, status=status)

    return _reply({"ok": True, "reply": reply, "language": language_code})


def assistant_context(request):
    """Template context for the floating widget."""
    return {"assistant_enabled": assistant_enabled(), "assistant_languages": LANGUAGES}
