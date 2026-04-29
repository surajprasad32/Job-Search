"""
Scoring and filtering module.

Sends each unprocessed job to Gemini 1.5 Flash for relevance scoring,
then returns the shortlisted jobs (score >= MIN_RELEVANCE_SCORE) sorted
by score descending, capped at MAX_JOBS_IN_REPORT.

Usage:
    from filter import score_and_filter
    shortlisted = score_and_filter(jobs_dict)
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
# Gemini setup
# ---------------------------------------------------------------------------

def _get_model():
    genai.configure(api_key=config.GEMINI_API_KEY)
    return genai.GenerativeModel(config.GEMINI_MODEL)


# ---------------------------------------------------------------------------
# Scoring prompt
# ---------------------------------------------------------------------------

SCORING_SYSTEM = """You are an expert technical recruiter evaluating job fit.
Return ONLY valid JSON — no markdown fences, no explanation, no extra text.
"""

SCORING_PROMPT_TEMPLATE = """
Evaluate this job posting for the candidate below and return a JSON object.

=== CANDIDATE PROFILE ===
Name:       {name}
Education:  M.Tech Software Engineering, DTU (GPA 8.33); B.Tech CSE (GPA 8.12)
Experience: 0-2 years (Fresher level); Samsung SRIB intern (PPO received)
Key skills: {skills}
Achievements: GATE CSE 2024 qualified (Rank 5943 / 123967), GATE DA 2024 qualified
Target roles: {roles}
Preferred locations: {locations}

=== JOB POSTING ===
Title:       {title}
Company:     {company}
Location:    {location}
Source:      {source}
Description:
{description}

=== SCORING INSTRUCTIONS ===
Score the job 1-10 based on:
- Skill overlap with candidate's key skills (weight 40%)
- Role category match with target roles (weight 30%)
- Experience level suitability — penalise heavily if 3+ years required (weight 20%)
- Location suitability including remote options (weight 10%)

=== REQUIRED JSON FORMAT ===
{{
  "score": <integer 1-10>,
  "reason": "<one sentence explaining the score>",
  "matched_keywords": ["keyword1", "keyword2"],
  "experience_match": "<suitable | borderline | not_suitable>",
  "location_match":   "<match | remote_ok | mismatch>",
  "role_category":    "<ML_Engineer | AI_Engineer | LLM_Engineer | SDE_Backend | Research_Engineer | Teaching_Mentoring | Other>"
}}
"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences from Gemini output before JSON parsing."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def score_job(model, job: dict) -> dict:
    """
    Call Gemini to score a single job.
    On any failure return score=0 and mark processed=True so we don't retry.
    """
    prompt = SCORING_PROMPT_TEMPLATE.format(
        name=config.CANDIDATE_NAME,
        skills=", ".join(config.KEY_SKILLS),
        roles=", ".join(config.TARGET_ROLES),
        locations=", ".join(config.PREFERRED_LOCATIONS),
        title=job.get("title",       "N/A"),
        company=job.get("company",   "N/A"),
        location=job.get("location", "N/A"),
        source=job.get("source",     "N/A"),
        description=(job.get("description", "") or "")[:3000],  # truncate
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": 512},
        )
        raw = response.text
        cleaned = _strip_fences(raw)
        data = json.loads(cleaned)

        job["score"]            = int(data.get("score", 0))
        job["score_reason"]     = str(data.get("reason", ""))
        job["matched_keywords"] = data.get("matched_keywords", [])
        job["experience_match"] = data.get("experience_match", "")
        job["location_match"]   = data.get("location_match",   "")
        job["role_category"]    = data.get("role_category",    "Other")

    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed for job '%s': %s | raw: %.200s",
                       job.get("title"), exc, raw if "raw" in dir() else "")
        job["score"] = 0
        job["score_reason"] = "Gemini response could not be parsed"

    except Exception as exc:
        logger.error("Gemini scoring failed for job '%s': %s",
                     job.get("title"), exc)
        job["score"] = 0
        job["score_reason"] = "Gemini API error"

    finally:
        job["processed"] = True

    return job


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_and_filter(jobs: dict) -> list[dict]:
    """
    Score all unprocessed jobs; return shortlisted list sorted by score desc.

    Args:
        jobs: Full {job_id: job_dict} mapping (mutated in place).

    Returns:
        List of job dicts with score >= MIN_RELEVANCE_SCORE, capped at
        MAX_JOBS_IN_REPORT, sorted highest score first.
    """
    if not config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set — cannot score jobs")
        return []

    model = _get_model()

    unprocessed = [j for j in jobs.values() if not j.get("processed")]
    logger.info("Scoring %d unprocessed jobs with Gemini...", len(unprocessed))

    for idx, job in enumerate(unprocessed, start=1):
        logger.info(
            "[%d/%d] Scoring: %s @ %s",
            idx, len(unprocessed), job.get("title"), job.get("company"),
        )
        score_job(model, job)
        time.sleep(0.5)   # stay comfortably within 1500 req/day free tier

    shortlisted = [
        j for j in jobs.values()
        if j.get("score", 0) >= config.MIN_RELEVANCE_SCORE
    ]
    shortlisted.sort(key=lambda j: j.get("score", 0), reverse=True)
    shortlisted = shortlisted[:config.MAX_JOBS_IN_REPORT]

    logger.info(
        "Shortlisted %d / %d total jobs (score >= %d)",
        len(shortlisted), len(jobs), config.MIN_RELEVANCE_SCORE,
    )
    return shortlisted
