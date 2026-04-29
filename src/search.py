"""
Job-search fetchers for all configured platforms.

Each fetcher returns a dict of {job_id: job_dict} and never raises —
exceptions are caught, logged, and an empty dict is returned so the
rest of the pipeline continues unaffected.

Run this module directly to execute a single search pass:
    python src/search.py
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def job_id(title: str, company: str, url: str) -> str:
    """Return a stable MD5 deduplication key for a job posting."""
    raw = (title.lower() + company.lower() + url).encode()
    return hashlib.md5(raw).hexdigest()


def make_job(
    title: str,
    company: str,
    location: str,
    url: str,
    description: str,
    source: str,
    date_posted: str = "",
) -> dict:
    """Return a standard job dict with all required fields."""
    jid = job_id(title, company, url)
    return {
        "id":               jid,
        "title":            title,
        "company":          company,
        "location":         location,
        "url":              url,
        "description":      description,
        "source":           source,
        "date_posted":      date_posted,
        "date_found":       datetime.now(timezone.utc).isoformat(),
        "processed":        False,
        "score":            0,
        "score_reason":     "",
        "matched_keywords": [],
        "experience_match": "",
        "location_match":   "",
        "role_category":    "",
        "compensation":     {},
        "company_snapshot": {},
    }


def load_existing_jobs() -> dict:
    """Load jobs.json; return empty dict if file missing or corrupt."""
    path = config.JOBS_DATA_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Could not load jobs.json: %s", exc)
        return {}


def save_jobs(jobs: dict) -> None:
    """Persist the job dict to jobs.json (creates parent dirs if needed)."""
    config.JOBS_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.JOBS_DATA_PATH, "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, indent=2, ensure_ascii=False)
    logger.info("Saved %d jobs to %s", len(jobs), config.JOBS_DATA_PATH)


def _is_excluded(title: str) -> bool:
    """Return True if the title contains any exclude keyword."""
    lower = title.lower()
    return any(kw.lower() in lower for kw in config.EXCLUDE_KEYWORDS)


# ---------------------------------------------------------------------------
# JSearch (RapidAPI) — covers LinkedIn, Indeed, Glassdoor, ZipRecruiter
# ---------------------------------------------------------------------------

def fetch_jsearch(existing: dict) -> dict:
    """Fetch jobs from JSearch API; return new {id: job} additions."""
    if not config.PLATFORMS.get("jsearch"):
        return {}
    if not config.RAPIDAPI_KEY:
        logger.warning("RAPIDAPI_KEY not set — skipping JSearch")
        return {}

    found: dict = {}
    headers = {
        "X-RapidAPI-Key":  config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }

    locations = config.PREFERRED_LOCATIONS.copy()
    if config.INTERNATIONAL_REMOTE:
        locations.append("remote worldwide")

    for role in config.TARGET_ROLES[:6]:          # cap to avoid rate limits
        for loc in locations[:4]:
            query = f"{role} {loc}"
            try:
                for page in range(1, config.JSEARCH_MAX_PAGES + 1):
                    params = {
                        "query":            query,
                        "page":             page,
                        "num_pages":        1,
                        "date_posted":      "week",
                        "employment_types": "FULLTIME,PARTTIME,INTERN",
                    }
                    resp = requests.get(
                        "https://jsearch.p.rapidapi.com/search",
                        headers=headers,
                        params=params,
                        timeout=15,
                    )
                    if resp.status_code == 429:
                        logger.warning("JSearch rate-limited; pausing 10 s")
                        time.sleep(10)
                        continue
                    resp.raise_for_status()
                    data = resp.json()

                    for item in data.get("data", []):
                        title   = item.get("job_title",      "")
                        company = item.get("employer_name",  "")
                        url     = item.get("job_apply_link", "") or item.get("job_google_link", "")
                        desc    = item.get("job_description", "")
                        posted  = item.get("job_posted_at_datetime_utc", "")
                        loc     = item.get("job_city", "") or item.get("job_country", "")

                        if not title or not company or not url:
                            continue
                        if _is_excluded(title):
                            continue

                        jid = job_id(title, company, url)
                        if jid in existing or jid in found:
                            continue

                        found[jid] = make_job(
                            title, company, loc, url, desc, "JSearch", posted
                        )

                    time.sleep(1)   # polite delay between pages

            except Exception as exc:
                logger.error("JSearch error for '%s' / '%s': %s", role, loc, exc)
                continue

    logger.info("JSearch: %d new jobs", len(found))
    return found


# ---------------------------------------------------------------------------
# Naukri.com scraper
# ---------------------------------------------------------------------------

NAUKRI_HEADERS = {
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":       "application/json",
    "appid":        "109",
    "systemid":     "Naukri",
}

def fetch_naukri(existing: dict) -> dict:
    """Scrape Naukri job search API; return new {id: job} additions."""
    if not config.PLATFORMS.get("naukri"):
        return {}

    found: dict = {}

    for role in config.TARGET_ROLES[:6]:
        keyword = role.replace(" ", "%20")
        try:
            for page in range(0, config.NAUKRI_MAX_PAGES):
                url = (
                    f"https://www.naukri.com/jobapi/v3/search"
                    f"?keyword={keyword}"
                    f"&experience=0&experience=1&experience=2"
                    f"&pageNo={page + 1}&count=20"
                    f"&noJobsChk=true"
                )
                resp = requests.get(url, headers=NAUKRI_HEADERS, timeout=15)
                if resp.status_code != 200:
                    logger.warning("Naukri returned %s for role '%s'", resp.status_code, role)
                    break
                data = resp.json()
                jobs_list = data.get("jobDetails", [])

                for item in jobs_list:
                    title   = item.get("title",       "")
                    company = item.get("companyName", "")
                    job_url = item.get("jdURL",       "") or item.get("staticUrl", "")
                    desc    = item.get("jobDescription", "") or ""
                    loc_raw = item.get("placeholders", [])
                    loc     = ""
                    for ph in loc_raw:
                        if ph.get("type") == "location":
                            loc = ph.get("label", "")
                            break
                    posted  = item.get("footerPlaceholderLabel", "")

                    if not title or not company:
                        continue
                    if not job_url:
                        job_url = f"https://www.naukri.com{item.get('jdURL', '')}"
                    if _is_excluded(title):
                        continue

                    jid = job_id(title, company, job_url)
                    if jid in existing or jid in found:
                        continue

                    found[jid] = make_job(
                        title, company, loc, job_url, desc, "Naukri", posted
                    )

                time.sleep(1.5)

        except Exception as exc:
            logger.error("Naukri error for role '%s': %s", role, exc)
            continue

    logger.info("Naukri: %d new jobs", len(found))
    return found


# ---------------------------------------------------------------------------
# Internshala scraper — teaching / mentoring / part-time only
# ---------------------------------------------------------------------------

INTERNSHALA_ROLES = [
    "machine-learning",
    "data-science",
    "python",
    "ai",
    "teaching",
]

def fetch_internshala(existing: dict) -> dict:
    """Scrape Internshala for teaching/part-time roles."""
    if not config.PLATFORMS.get("internshala"):
        return {}

    found: dict = {}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    for role_slug in INTERNSHALA_ROLES:
        try:
            url = f"https://internshala.com/jobs/{role_slug}-jobs"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning("Internshala returned %s for '%s'", resp.status_code, role_slug)
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            # Each job card has class "individual_internship"
            cards = soup.select(".individual_internship")
            if not cards:
                # Fallback selector
                cards = soup.select("[id^='job-internship-card']")

            for card in cards:
                try:
                    title_el   = card.select_one(".job-internship-name, .profile")
                    company_el = card.select_one(".company-name")
                    loc_el     = card.select_one(".locations span, .location_link")
                    link_el    = card.select_one("a.view_detail_button, a[href*='/jobs/detail/']")

                    title   = title_el.get_text(strip=True)   if title_el   else ""
                    company = company_el.get_text(strip=True) if company_el else ""
                    loc     = loc_el.get_text(strip=True)     if loc_el     else "India"
                    href    = link_el["href"]                 if link_el    else ""
                    if href and not href.startswith("http"):
                        href = "https://internshala.com" + href

                    if not title or not company or not href:
                        continue
                    if _is_excluded(title):
                        continue

                    jid = job_id(title, company, href)
                    if jid in existing or jid in found:
                        continue

                    # Fetch description from detail page (best-effort)
                    desc = ""
                    try:
                        detail = requests.get(href, headers=headers, timeout=10)
                        if detail.status_code == 200:
                            dsoup = BeautifulSoup(detail.text, "lxml")
                            desc_el = dsoup.select_one(".internship_other_details_container, #about_company")
                            desc = desc_el.get_text(" ", strip=True) if desc_el else ""
                    except Exception:
                        pass

                    found[jid] = make_job(
                        title, company, loc, href, desc, "Internshala", ""
                    )
                    time.sleep(0.5)

                except Exception as card_exc:
                    logger.debug("Internshala card parse error: %s", card_exc)
                    continue

        except Exception as exc:
            logger.error("Internshala error for slug '%s': %s", role_slug, exc)
            continue

    logger.info("Internshala: %d new jobs", len(found))
    return found


# ---------------------------------------------------------------------------
# Google Jobs via SerpAPI
# ---------------------------------------------------------------------------

def fetch_google_jobs(existing: dict) -> dict:
    """Fetch jobs from SerpAPI Google Jobs engine."""
    if not config.PLATFORMS.get("google_jobs"):
        return {}
    if not config.SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set — skipping Google Jobs")
        return {}

    found: dict = {}

    locations = config.PREFERRED_LOCATIONS[:3]
    if config.INTERNATIONAL_REMOTE:
        locations.append("remote")

    for role in config.TARGET_ROLES[:5]:
        for loc in locations[:3]:
            query = f"{role} jobs {loc} 0-2 years experience"
            try:
                params = {
                    "engine":   "google_jobs",
                    "q":        query,
                    "api_key":  config.SERPAPI_KEY,
                    "num":      config.SERPAPI_MAX_RESULTS,
                    "gl":       "in",   # India
                    "hl":       "en",
                }
                resp = requests.get(
                    "https://serpapi.com/search",
                    params=params,
                    timeout=20,
                )
                if resp.status_code == 429:
                    logger.warning("SerpAPI rate-limited; pausing 15 s")
                    time.sleep(15)
                    continue
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("jobs_results", []):
                    title   = item.get("title",          "")
                    company = item.get("company_name",   "")
                    loc_raw = item.get("location",       "")
                    desc    = item.get("description",    "")
                    posted  = item.get("detected_extensions", {}).get("posted_at", "")

                    # Best available URL
                    apply_options = item.get("apply_options", [])
                    url = apply_options[0].get("link", "") if apply_options else ""
                    if not url:
                        url = item.get("job_id", "")
                        url = f"https://www.google.com/search?q={url}" if url else ""

                    if not title or not company:
                        continue
                    if _is_excluded(title):
                        continue

                    jid = job_id(title, company, url)
                    if jid in existing or jid in found:
                        continue

                    found[jid] = make_job(
                        title, company, loc_raw, url, desc, "Google Jobs", posted
                    )

                time.sleep(2)

            except Exception as exc:
                logger.error("SerpAPI error for '%s' / '%s': %s", role, loc, exc)
                continue

    logger.info("Google Jobs: %d new jobs", len(found))
    return found


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all fetchers, merge results into jobs.json."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = config.LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    logger.info("=== Search run started ===")
    existing = load_existing_jobs()
    before   = len(existing)

    new: dict = {}
    new.update(fetch_jsearch(existing))
    new.update(fetch_naukri({**existing, **new}))
    new.update(fetch_internshala({**existing, **new}))
    new.update(fetch_google_jobs({**existing, **new}))

    merged = {**existing, **new}
    save_jobs(merged)

    logger.info(
        "=== Search complete — %d new jobs found (total: %d) ===",
        len(new),
        len(merged),
    )


if __name__ == "__main__":
    main()
