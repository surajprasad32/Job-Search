"""
Evening orchestrator — runs at 7 PM IST via GitHub Actions.

Pipeline steps:
  1. Load jobs.json and score all unprocessed jobs (filter.py)
  2. Enrich shortlisted jobs with compensation + company data (compensation.py)
  3. Build HTML report (report.py)
  4. Send email (email_send.py)
  5. Persist enriched jobs.json back to disk

On email failure the HTML report is still saved to output/ as a fallback.
Exit code: 0 on success, 1 on any fatal error.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure src/ is on the path when called from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import filter as filter_module
import compensation as comp_module
import report as report_module
import email_send
from search import load_existing_jobs, save_jobs


def _setup_logging() -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = config.LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Evening pipeline started")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Step 1 — Score & filter
    # ------------------------------------------------------------------
    logger.info("STEP 1: Scoring unprocessed jobs with Gemini …")
    try:
        jobs = load_existing_jobs()
        total_found = len(jobs)
        logger.info("Loaded %d jobs from jobs.json", total_found)

        shortlisted = filter_module.score_and_filter(jobs)
        logger.info("Shortlisted %d jobs (score >= %d)",
                    len(shortlisted), config.MIN_RELEVANCE_SCORE)
    except Exception as exc:
        logger.error("STEP 1 FAILED: %s", exc, exc_info=True)
        return 1

    if not shortlisted:
        logger.warning("No jobs met the minimum score — sending empty report")

    # ------------------------------------------------------------------
    # Step 2 — Enrich with compensation data
    # ------------------------------------------------------------------
    logger.info("STEP 2: Researching compensation and company snapshots …")
    try:
        shortlisted = comp_module.enrich_jobs(shortlisted)
    except Exception as exc:
        logger.error("STEP 2 FAILED (non-fatal): %s", exc, exc_info=True)
        # Pipeline continues — report will just have empty compensation blocks

    # ------------------------------------------------------------------
    # Step 3 — Build HTML report
    # ------------------------------------------------------------------
    logger.info("STEP 3: Building HTML report …")
    try:
        report_path = report_module.build_report(shortlisted, total_found)
        html_content = report_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("STEP 3 FAILED: %s", exc, exc_info=True)
        return 1

    # ------------------------------------------------------------------
    # Step 4 — Send email
    # ------------------------------------------------------------------
    logger.info("STEP 4: Sending email report …")
    avg_score = 0.0
    if shortlisted:
        avg_score = round(
            sum(j.get("score", 0) for j in shortlisted) / len(shortlisted), 1
        )

    email_ok = email_send.send_report(
        html_content,
        num_shortlisted=len(shortlisted),
        avg_score=avg_score,
    )
    if not email_ok:
        logger.warning(
            "Email failed — HTML report saved to %s as fallback", report_path
        )

    # ------------------------------------------------------------------
    # Step 5 — Persist enriched data back to jobs.json
    # ------------------------------------------------------------------
    logger.info("STEP 5: Saving enriched jobs.json …")
    try:
        # Merge shortlisted enrichments back into full jobs dict
        shortlisted_by_id = {j["id"]: j for j in shortlisted}
        for jid, job in jobs.items():
            if jid in shortlisted_by_id:
                jobs[jid] = shortlisted_by_id[jid]
        save_jobs(jobs)
    except Exception as exc:
        logger.error("STEP 5 FAILED (non-fatal): %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info(
        "Pipeline complete — %d jobs shortlisted, avg score %.1f, email %s",
        len(shortlisted),
        avg_score,
        "sent" if email_ok else "FAILED (see fallback HTML)",
    )
    logger.info("=" * 60)

    return 0 if email_ok else 0   # still exit 0 — email fail is non-fatal


if __name__ == "__main__":
    sys.exit(main())
