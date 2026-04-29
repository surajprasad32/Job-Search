"""
Central configuration for the job-search pipeline.

All tuneable parameters live here — edit this file to customise
roles, locations, scoring thresholds, and platform toggles.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
BASE_RESUME_PATH = BASE_DIR / "resume" / "base.tex"
JOBS_DATA_PATH   = BASE_DIR / "data"  / "jobs.json"
OUTPUT_DIR       = BASE_DIR / "output"
LOGS_DIR         = BASE_DIR / "logs"

# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------
CANDIDATE_NAME  = "Suraj Prasad Kalauni"
CANDIDATE_EMAIL = "spkalauni7789@gmail.com"

# ---------------------------------------------------------------------------
# Target roles  (used as search queries — order matters: most important first)
# ---------------------------------------------------------------------------
TARGET_ROLES = [
    "ML Engineer",
    "AI Engineer",
    "LLM Engineer",
    "Machine Learning Engineer",
    "Software Engineer",
    "SDE",
    "Backend Engineer",
    "Research Engineer",
    "AI Research Engineer",
    "Teaching Assistant",
    "Mentoring",
]

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
PREFERRED_LOCATIONS = [
    "Bangalore",
    "Delhi NCR",
    "Hyderabad",
    "Pune",
    "Mumbai",
    "Remote",
]
INTERNATIONAL_REMOTE = True

# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------
EXPERIENCE_LEVEL = "0-2"  # years

# ---------------------------------------------------------------------------
# Scoring & report caps
# ---------------------------------------------------------------------------
MIN_RELEVANCE_SCORE = 6   # 1-10; jobs below this are dropped from the report
MAX_JOBS_IN_REPORT  = 15  # top-N by score

# ---------------------------------------------------------------------------
# Key skills (used in scoring prompt and tailoring prompts)
# ---------------------------------------------------------------------------
KEY_SKILLS = [
    "Python",
    "PyTorch",
    "LLM",
    "vLLM",
    "LangChain",
    "Speculative Decoding",
    "Quantization",
    "Pruning",
    "ONNX",
    "Hugging Face",
    "Docker",
    "Kubernetes",
    "AWS",
    "REST API",
    "System Design",
    "DSA",
    "Golang",
    "C++",
    "TensorFlow",
    "SGLang",
    "BitsAndBytes",
    "Transformers",
    "RAG",
    "Prompt Engineering",
    "Linux",
    "CI/CD",
]

# ---------------------------------------------------------------------------
# Exclude these keywords from job titles (case-insensitive)
# ---------------------------------------------------------------------------
EXCLUDE_KEYWORDS = [
    "senior",
    "lead",
    "manager",
    "director",
    "VP",
    "principal",
    "head of",
    "staff engineer",
]

# ---------------------------------------------------------------------------
# Platform toggles  (set False to disable a platform without deleting code)
# ---------------------------------------------------------------------------
PLATFORMS = {
    "jsearch":     True,   # JSearch via RapidAPI (LinkedIn / Indeed / Glassdoor)
    "naukri":      True,   # Naukri.com scraper
    "internshala": True,   # Internshala (teaching / part-time only)
    "google_jobs": True,   # Google Jobs via SerpAPI
}

# ---------------------------------------------------------------------------
# API credentials  (always from environment — never hard-coded)
# ---------------------------------------------------------------------------
RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY",  "")
SERPAPI_KEY   = os.environ.get("SERPAPI_KEY",   "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GMAIL_USER         = os.environ.get("GMAIL_USER",         "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-1.5-flash"

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
REPORT_RECIPIENT = CANDIDATE_EMAIL
GMAIL_SMTP_HOST  = "smtp.gmail.com"
GMAIL_SMTP_PORT  = 465  # SSL

# ---------------------------------------------------------------------------
# Search run limits  (keep well within free-tier quotas)
# ---------------------------------------------------------------------------
JSEARCH_MAX_PAGES   = 2   # pages per query
NAUKRI_MAX_PAGES    = 2
SERPAPI_MAX_RESULTS = 10  # results per query (free tier is limited)
