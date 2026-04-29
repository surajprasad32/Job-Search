"""
Compensation research and company snapshot module.

Uses Gemini 1.5 Flash with Google Search grounding to research:
  - Salary range, median, equity info for the specific role at the company
  - Company size, funding stage, Glassdoor rating, tech stack, interview process

Usage:
    from compensation import enrich_jobs
    shortlisted = enrich_jobs(shortlisted_jobs)
"""

import json
import logging
import re
import time
from pathlib import Path

import google.generativeai as genai

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini setup (with Search grounding)
# ---------------------------------------------------------------------------

def _get_grounded_model():
    genai.configure(api_key=config.GEMINI_API_KEY)
    # Google Search grounding is available on gemini-1.5-flash via tools
    model = genai.GenerativeModel(
        config.GEMINI_MODEL,
        tools="google_search_retrieval",   # built-in grounding tool
    )
    return model


def _get_plain_model():
    """Fallback plain model when grounding quota is exhausted."""
    genai.configure(api_key=config.GEMINI_API_KEY)
    return genai.GenerativeModel(config.GEMINI_MODEL)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

COMPENSATION_PROMPT = """
Research the compensation and company details for the following job and return
ONLY a valid JSON object (no markdown fences, no extra text).

Job Title:   {title}
Company:     {company}
Location:    {location}
Role Level:  Entry-level / 0-2 years experience

Return this exact JSON structure:
{{
  "compensation": {{
    "salary_range":    "<e.g. ₹8L – ₹14L per annum or 'Not disclosed'>",
    "median_salary":   "<e.g. ₹11L per annum or 'Not disclosed'>",
    "equity_esops":    "<Yes / No / Likely / Unknown>",
    "listed_salary":   "<salary from the job listing itself, or 'Not disclosed'>",
    "sources":         ["<source1>", "<source2>"],
    "confidence":      "<high | medium | low>"
  }},
  "company_snapshot": {{
    "size":             "<e.g. 50-200 employees or 'Unknown'>",
    "funding_stage":    "<e.g. Series B / Bootstrapped / Public / Unknown>",
    "glassdoor_rating": "<e.g. 4.2/5 or 'Not available'>",
    "tech_stack":       ["<tech1>", "<tech2>"],
    "interview_process":"<brief description of typical interview rounds or 'Unknown'>"
  }}
}}

Use AmbitionBox, Glassdoor, Levels.fyi, LinkedIn Salary, or any available data.
If data is unavailable for any field, use the placeholder strings shown above.
"""


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


# ---------------------------------------------------------------------------
# Core enrichment
# ---------------------------------------------------------------------------

def _research_job(model, job: dict) -> dict:
    """Call Gemini to fill compensation + company_snapshot for one job."""
    prompt = COMPENSATION_PROMPT.format(
        title=job.get("title",    "N/A"),
        company=job.get("company", "N/A"),
        location=job.get("location", "N/A"),
    )
    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 1024},
        )
        raw     = response.text
        cleaned = _strip_fences(raw)
        data    = json.loads(cleaned)

        job["compensation"]     = data.get("compensation",     {})
        job["company_snapshot"] = data.get("company_snapshot", {})

    except json.JSONDecodeError as exc:
        logger.warning(
            "Compensation JSON parse failed for '%s' @ '%s': %s",
            job.get("title"), job.get("company"), exc,
        )
        job.setdefault("compensation",     _empty_compensation())
        job.setdefault("company_snapshot", _empty_snapshot())

    except Exception as exc:
        logger.error(
            "Compensation research failed for '%s' @ '%s': %s",
            job.get("title"), job.get("company"), exc,
        )
        job.setdefault("compensation",     _empty_compensation())
        job.setdefault("company_snapshot", _empty_snapshot())

    return job


def _empty_compensation() -> dict:
    return {
        "salary_range":    "Not disclosed",
        "median_salary":   "Not disclosed",
        "equity_esops":    "Unknown",
        "listed_salary":   "Not disclosed",
        "sources":         [],
        "confidence":      "low",
    }


def _empty_snapshot() -> dict:
    return {
        "size":             "Unknown",
        "funding_stage":    "Unknown",
        "glassdoor_rating": "Not available",
        "tech_stack":       [],
        "interview_process": "Unknown",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_jobs(jobs: list[dict]) -> list[dict]:
    """
    Enrich each shortlisted job with compensation and company data.

    Tries grounded model first; falls back to plain model if grounding
    is unavailable (e.g. quota / region restriction).

    Args:
        jobs: List of scored job dicts from filter.score_and_filter().

    Returns:
        Same list with compensation and company_snapshot fields populated.
    """
    if not config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set — skipping compensation research")
        for j in jobs:
            j.setdefault("compensation",     _empty_compensation())
            j.setdefault("company_snapshot", _empty_snapshot())
        return jobs

    # Try grounded model; if it blows up on the first call, downgrade
    try:
        model = _get_grounded_model()
        # Quick probe — if grounding is unsupported an exception is raised here
        _ = model  # actual probe happens on first generate_content call
    except Exception as exc:
        logger.warning("Grounded model unavailable (%s); using plain model", exc)
        model = _get_plain_model()

    grounding_failed = False

    for idx, job in enumerate(jobs, start=1):
        logger.info(
            "[%d/%d] Researching compensation: %s @ %s",
            idx, len(jobs), job.get("title"), job.get("company"),
        )

        if grounding_failed:
            # Already downgraded
            _research_job(model, job)
        else:
            try:
                _research_job(model, job)
            except Exception as exc:
                if "grounding" in str(exc).lower() or "tool" in str(exc).lower():
                    logger.warning(
                        "Search grounding not available (%s); switching to plain model",
                        exc,
                    )
                    grounding_failed = True
                    model = _get_plain_model()
                    _research_job(model, job)
                else:
                    raise

        time.sleep(1)   # polite delay — free tier: 1500 req/day

    logger.info("Compensation research complete for %d jobs", len(jobs))
    return jobs
