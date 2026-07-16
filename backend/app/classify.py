"""
Calls the Groq API to classify a raw complaint message into one or more
linked issue classifications.

Handles:
  - bundled multi-issue messages -> multiple issues in one response
  - sarcasm / hedged tone / tone-urgency mismatch -> instructed explicitly
  - Hinglish / multilingual text -> instructed explicitly
  - praise, test/QA noise, low-signal / emoji-only messages -> is_noise=True
  - driver-originated complaints about a customer -> hr_driver_relations
  - Groq API failures / malformed responses -> raises ClassificationError,
    caller is responsible for turning that into an HTTP error
"""
import json
import os
import re
from typing import List, Dict, Any

import groq

GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

VALID_CATEGORIES = {
    "delivery_delay",
    "food_quality",
    "food_safety",
    "billing_dispute",
    "order_mixup",
    "coverage_request",
    "praise",
    "driver_safety",
    "legal_compliance",
    "account_management",
    "test_noise",
    "low_signal",
    "other",
}
VALID_URGENCY = {"low", "medium", "high", "critical"}
VALID_TEAMS = {
    "support",
    "ops",
    "trust_and_safety",
    "finance",
    "hr_driver_relations",
    "legal",
    "none",
}

SYSTEM_PROMPT = """You are a triage classifier for UrbanDash, a quick-commerce \
delivery platform. You read a single raw inbound message (from the app, \
email, or a Twitter DM) and break it into one or more distinct "issues".

Most messages contain exactly one issue. Some messages bundle multiple \
distinct issues (e.g. a late delivery AND a billing overcharge in the same \
message) — in that case return one entry per distinct issue, each fully \
classified on its own.

For EACH issue, determine:
- category: one of delivery_delay, food_quality, food_safety, \
billing_dispute, order_mixup, coverage_request, praise, driver_safety, \
legal_compliance, account_management, test_noise, low_signal, other
- urgency: one of low, medium, high, critical
- routed_team: one of support, ops, trust_and_safety, finance, \
hr_driver_relations, legal, none
- reasoning: one or two sentences explaining the call
- is_noise: true if this is praise, test/QA noise, or a low-signal message \
(e.g. emoji-only, gibberish, or no actionable content) that should NOT be \
routed to any team. If is_noise is true, routed_team must be "none".

Important judgment calls you must make correctly:
- Distinguish genuine complaints from praise and from test/QA noise (e.g. \
"test 123", "ignore this", employee smoke-testing the ticketing system). \
Praise and test/QA noise and low-signal emoji-only messages are all \
is_noise=true.
- Messages can be sarcastic ("wow, only 2 hours late, incredible service") — \
classify by the real underlying issue and its real urgency, not the surface \
politeness or tone.
- Messages can be calmly or diplomatically worded but describe something \
genuinely dangerous (e.g. a calmly-worded report of mold, a foreign object, \
or food poisoning symptoms). Urgency must reflect actual risk \
(food_safety issues describing contamination, illness, or injury should \
generally be high or critical), not the emotional tone of the writing.
- Messages may be hedged ("might just be me but...", "not 100% sure but...") \
— take hedged food-safety or driver-safety reports seriously; do not \
downgrade urgency just because the writer is uncertain or polite.
- Messages may be in Hinglish or mix English with Hindi (transliterated). \
Understand and classify them correctly regardless of language mixing.
- complainant_type tells you who is writing. If complainant_type is "driver" \
and they are reporting an unsafe, abusive, or threatening CUSTOMER, this is \
a driver-relations / HR matter, not a support ticket — route to \
hr_driver_relations (and consider trust_and_safety as well if there's \
physical danger — but routed_team is a single value, pick the primary \
owning team, typically hr_driver_relations for driver welfare issues). If a \
driver reports being unsafe on the road generally (traffic, area is unsafe \
at night), that's still hr_driver_relations or trust_and_safety, use your \
judgment based on whether it's a personnel/welfare issue (hr_driver_relations) \
or a public safety incident (trust_and_safety).
- legal_compliance covers things like MRP (maximum retail price) overcharging, \
regulatory violations, or explicit legal threats — route to legal.
- coverage_request means someone (often a driver) is asking about service \
area / delivery zone coverage — route to ops.

Respond with ONLY a raw JSON object (no markdown fences, no prose before or \
after) matching exactly this shape:

{"issues": [
  {"category": "...", "urgency": "...", "routed_team": "...", \
"reasoning": "...", "is_noise": false}
]}
"""


class ClassificationError(Exception):
    pass


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Strip markdown fences if the model added them despite instructions.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Try to find the first {...} block as a fallback.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise ClassificationError(f"Groq returned non-JSON output: {exc}") from exc


def _validate_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
    category = issue.get("category")
    urgency = issue.get("urgency")
    routed_team = issue.get("routed_team")
    reasoning = issue.get("reasoning")
    is_noise = bool(issue.get("is_noise", False))

    if category not in VALID_CATEGORIES:
        category = "other"
    if urgency not in VALID_URGENCY:
        urgency = "medium"
    if routed_team not in VALID_TEAMS:
        routed_team = "none" if is_noise else "support"
    if not reasoning or not isinstance(reasoning, str):
        reasoning = "No reasoning provided by classifier."
    if is_noise:
        routed_team = "none"

    return {
        "category": category,
        "urgency": urgency,
        "routed_team": routed_team,
        "reasoning": reasoning.strip(),
        "is_noise": is_noise,
    }


def classify_message(
    raw_message: str, complainant_type: str, channel: str
) -> List[Dict[str, Any]]:
    """
    Calls the Groq API and returns a validated list of issue dicts.
    Raises ClassificationError on any failure (missing key, API error,
    malformed/unparseable response) so the caller can surface a clean
    HTTP error instead of crashing.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ClassificationError(
            "GROQ_API_KEY is not set on the backend environment."
        )

    if not raw_message or not raw_message.strip():
        raise ClassificationError("Cannot classify an empty message.")

    user_prompt = (
        f"channel: {channel}\n"
        f"complainant_type: {complainant_type}\n"
        f"raw_message: {raw_message}\n\n"
        "Classify this message now."
    )

    try:
        client = groq.Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
    except groq.APIStatusError as exc:
        raise ClassificationError(f"Groq API error ({exc.status_code}): {exc.message}") from exc
    except groq.APIConnectionError as exc:
        raise ClassificationError(f"Could not reach Groq API: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ClassificationError(f"Unexpected error calling Groq API: {exc}") from exc

    choices = response.choices
    if not choices or not choices[0].message or not choices[0].message.content:
        raise ClassificationError("Groq API returned no text content.")

    raw_text = choices[0].message.content
    parsed = _extract_json(raw_text)

    issues = parsed.get("issues")
    if not isinstance(issues, list) or len(issues) == 0:
        raise ClassificationError(
            "Groq response did not contain a non-empty 'issues' list."
        )

    return [_validate_issue(issue) for issue in issues]
