"""
HTML email report builder.

Generates a self-contained HTML file with:
  - Summary header (stats, platform breakdown, role breakdown)
  - One card per shortlisted job containing score, compensation table,
    company snapshot table, and a copy-paste Claude.ai tailoring prompt.

Usage:
    from report import build_report
    html_path = build_report(shortlisted_jobs, total_found)
"""

import logging
from datetime import datetime
from pathlib import Path
from html import escape

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Score badge colours
# ---------------------------------------------------------------------------

def _score_colour(score: int) -> tuple[str, str]:
    """Return (background_hex, text_hex) for a relevance score badge."""
    if score >= 8:
        return "#1a7f37", "#ffffff"   # green
    elif score >= 6:
        return "#0969da", "#ffffff"   # blue
    else:
        return "#d1a317", "#000000"   # amber


# ---------------------------------------------------------------------------
# LaTeX resume loader
# ---------------------------------------------------------------------------

def _load_latex() -> str:
    try:
        return config.BASE_RESUME_PATH.read_text(encoding="utf-8")
    except Exception:
        return "[paste your base.tex content here]"


# ---------------------------------------------------------------------------
# Tailoring prompt block
# ---------------------------------------------------------------------------

TAILORING_PROMPT_TEMPLATE = """\
---COPY THIS PROMPT TO CLAUDE.AI TO TAILOR YOUR RESUME---

I need you to tailor my LaTeX resume for this specific job.

STRICT RULES — follow all without exception:
1. Return ONLY complete compilable LaTeX code. Nothing else — no explanation,
   no markdown fences.
2. Only modify these three sections: SKILLS SUMMARY, WORK EXPERIENCE, PROJECTS.
3. Never touch: Header, Education, Publications, Achievements.
4. Never add new bullet points without removing one of equal length.
   Net content size must stay identical.
5. Never change font sizes, margins, line spacing, or any formatting parameters.
6. Always keep the Samsung SRIB bullet about 15% latency reduction.
7. Always keep the 2.1x throughput speedup bullet in Speculative Decoding project.
8. Mirror exact keywords from the job description for ATS matching.
9. Never fabricate any metric or experience not in the base resume.
10. Output must fit exactly 1 page — same spatial budget as original.
11. If ML/AI/LLM role → keep ML Frameworks and Inference at top of skills.
12. If Backend/SDE role → move Golang, REST APIs, System Design to top of skills.
13. If Teaching/Mentoring → reframe bullets to emphasise knowledge transfer.

JOB TITLE:       {title}
COMPANY:         {company}
LOCATION:        {location}
ROLE CATEGORY:   {role_category}
KEYWORDS TO INCLUDE: {matched_keywords}

JOB DESCRIPTION:
{description}

BASE RESUME LATEX:
{latex}

---END OF PROMPT---\
"""


def _build_tailoring_prompt(job: dict, latex: str) -> str:
    return TAILORING_PROMPT_TEMPLATE.format(
        title=job.get("title",    ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        role_category=job.get("role_category", ""),
        matched_keywords=", ".join(job.get("matched_keywords", [])),
        description=(job.get("description", "") or "")[:4000],
        latex=latex,
    )


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _keyword_pills(keywords: list) -> str:
    pills = "".join(
        f'<span style="display:inline-block;background:#e8f0fe;color:#1a73e8;'
        f'border-radius:12px;padding:2px 10px;font-size:12px;margin:2px;">'
        f'{escape(str(k))}</span>'
        for k in keywords
    )
    return pills or '<span style="color:#999;font-size:12px;">none</span>'


def _fit_badge(label: str, value: str) -> str:
    colour_map = {
        "suitable":     ("#d4edda", "#155724"),
        "borderline":   ("#fff3cd", "#856404"),
        "not_suitable": ("#f8d7da", "#721c24"),
        "match":        ("#d4edda", "#155724"),
        "remote_ok":    ("#d1ecf1", "#0c5460"),
        "mismatch":     ("#f8d7da", "#721c24"),
    }
    key = (value or "").lower().replace(" ", "_")
    bg, fg = colour_map.get(key, ("#e2e3e5", "#383d41"))
    display = (value or "").replace("_", " ").title()
    return (
        f'<span style="background:{bg};color:{fg};border-radius:4px;'
        f'padding:2px 8px;font-size:12px;font-weight:600;">'
        f'{escape(label)}: {escape(display)}</span> '
    )


def _comp_table(comp: dict) -> str:
    if not comp:
        return "<p style='color:#999;font-size:13px;'>No data available</p>"
    rows = [
        ("Salary Range",    comp.get("salary_range",  "—")),
        ("Median Salary",   comp.get("median_salary", "—")),
        ("Equity / ESOPs",  comp.get("equity_esops",  "—")),
        ("Listed Salary",   comp.get("listed_salary", "—")),
        ("Sources",         ", ".join(comp.get("sources", [])) or "—"),
        ("Confidence",      comp.get("confidence",    "—")),
    ]
    html  = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
    for label, value in rows:
        html += (
            f'<tr>'
            f'<td style="padding:4px 8px;font-weight:600;color:#555;'
            f'white-space:nowrap;width:140px;">{escape(label)}</td>'
            f'<td style="padding:4px 8px;color:#222;">{escape(str(value))}</td>'
            f'</tr>'
        )
    html += "</table>"
    return html


def _snapshot_table(snap: dict) -> str:
    if not snap:
        return "<p style='color:#999;font-size:13px;'>No data available</p>"
    tech = ", ".join(snap.get("tech_stack", [])) or "—"
    rows = [
        ("Company Size",      snap.get("size",              "—")),
        ("Funding Stage",     snap.get("funding_stage",     "—")),
        ("Glassdoor Rating",  snap.get("glassdoor_rating",  "—")),
        ("Tech Stack",        tech),
        ("Interview Process", snap.get("interview_process", "—")),
    ]
    html  = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
    for label, value in rows:
        html += (
            f'<tr>'
            f'<td style="padding:4px 8px;font-weight:600;color:#555;'
            f'white-space:nowrap;width:160px;">{escape(label)}</td>'
            f'<td style="padding:4px 8px;color:#222;">{escape(str(value))}</td>'
            f'</tr>'
        )
    html += "</table>"
    return html


# ---------------------------------------------------------------------------
# Per-job card
# ---------------------------------------------------------------------------

def _job_card(job: dict, latex: str) -> str:
    score          = job.get("score", 0)
    bg_col, fg_col = _score_colour(score)
    prompt_text    = escape(_build_tailoring_prompt(job, latex))

    source_badge = (
        f'<span style="background:#f0f0f0;color:#555;border-radius:4px;'
        f'padding:2px 8px;font-size:11px;">{escape(job.get("source",""))}</span>'
    )
    posted = job.get("date_posted", "") or ""
    posted_html = f'<span style="color:#888;font-size:12px;">Posted: {escape(posted)}</span>' if posted else ""

    return f"""
<div style="background:#ffffff;border:1px solid #e1e4e8;border-radius:8px;
            padding:24px;margin-bottom:28px;box-shadow:0 1px 3px rgba(0,0,0,.08);">

  <!-- Title row -->
  <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div>
      <h2 style="margin:0 0 4px 0;font-size:18px;color:#24292f;">
        {escape(job.get("title",""))}
      </h2>
      <div style="font-size:14px;color:#57606a;">
        <strong>{escape(job.get("company",""))}</strong>
        &nbsp;·&nbsp;{escape(job.get("location",""))}
        &nbsp;&nbsp;{source_badge}&nbsp;&nbsp;{posted_html}
      </div>
    </div>
    <!-- Score badge -->
    <div style="background:{bg_col};color:{fg_col};border-radius:50%;
                width:52px;height:52px;display:flex;align-items:center;
                justify-content:center;font-size:20px;font-weight:700;
                flex-shrink:0;">
      {score}
    </div>
  </div>

  <!-- Score reason -->
  <p style="margin:10px 0 6px 0;font-size:13px;color:#57606a;font-style:italic;">
    {escape(job.get("score_reason",""))}
  </p>

  <!-- Keywords -->
  <div style="margin-bottom:10px;">
    <span style="font-size:12px;font-weight:600;color:#555;">Matched: </span>
    {_keyword_pills(job.get("matched_keywords", []))}
  </div>

  <!-- Fit badges -->
  <div style="margin-bottom:14px;">
    {_fit_badge("Experience", job.get("experience_match",""))}
    {_fit_badge("Location",   job.get("location_match",""))}
  </div>

  <!-- Apply button -->
  <a href="{escape(job.get('url','#'))}"
     style="display:inline-block;background:#2da44e;color:#fff;
            text-decoration:none;border-radius:6px;padding:8px 20px;
            font-size:14px;font-weight:600;margin-bottom:18px;">
    Apply Now ↗
  </a>

  <!-- Compensation -->
  <details open>
    <summary style="cursor:pointer;font-weight:700;font-size:14px;
                    color:#24292f;margin-bottom:8px;">💰 Compensation</summary>
    <div style="background:#f6f8fa;border-radius:6px;padding:12px;margin-top:6px;">
      {_comp_table(job.get("compensation",{}))}
    </div>
  </details>

  <!-- Company snapshot -->
  <details style="margin-top:12px;" open>
    <summary style="cursor:pointer;font-weight:700;font-size:14px;
                    color:#24292f;margin-bottom:8px;">🏢 Company Snapshot</summary>
    <div style="background:#f6f8fa;border-radius:6px;padding:12px;margin-top:6px;">
      {_snapshot_table(job.get("company_snapshot",{}))}
    </div>
  </details>

  <!-- Tailoring prompt -->
  <details style="margin-top:16px;">
    <summary style="cursor:pointer;font-weight:700;font-size:14px;
                    color:#24292f;margin-bottom:8px;">
      ✏️ Claude.ai Resume Tailoring Prompt
      <span style="background:#6e40c9;color:#fff;border-radius:4px;
                   padding:1px 8px;font-size:11px;margin-left:8px;">COPY</span>
    </summary>
    <div style="background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;
                padding:16px;margin-top:8px;position:relative;">
      <pre style="font-family:'Courier New',Courier,monospace;font-size:12px;
                  color:#24292f;white-space:pre-wrap;word-break:break-word;
                  margin:0;line-height:1.5;">{prompt_text}</pre>
    </div>
  </details>

</div>
"""


# ---------------------------------------------------------------------------
# Summary header
# ---------------------------------------------------------------------------

def _summary_header(jobs: list[dict], total_found: int, date_str: str) -> str:
    if jobs:
        avg_score = round(sum(j.get("score", 0) for j in jobs) / len(jobs), 1)
    else:
        avg_score = 0.0

    platforms = sorted({j.get("source", "") for j in jobs if j.get("source")})

    from collections import Counter
    cat_counts = Counter(j.get("role_category", "Other") for j in jobs)
    cat_rows = "".join(
        f'<li style="margin:2px 0;">'
        f'<span style="font-weight:600;">{escape(cat)}</span>: {count}'
        f'</li>'
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1])
    )

    return f"""
<div style="background:#0969da;color:#fff;border-radius:8px;padding:24px;
            margin-bottom:32px;">
  <h1 style="margin:0 0 4px 0;font-size:22px;">Job Pipeline Report · {escape(date_str)}</h1>
  <p style="margin:0 0 16px 0;font-size:15px;opacity:.85;">
    {config.CANDIDATE_NAME} — {config.CANDIDATE_EMAIL}
  </p>

  <div style="display:flex;flex-wrap:wrap;gap:24px;">
    <div>
      <div style="font-size:36px;font-weight:700;">{len(jobs)}</div>
      <div style="font-size:13px;opacity:.8;">Jobs shortlisted</div>
    </div>
    <div>
      <div style="font-size:36px;font-weight:700;">{total_found}</div>
      <div style="font-size:13px;opacity:.8;">Total found today</div>
    </div>
    <div>
      <div style="font-size:36px;font-weight:700;">{avg_score}</div>
      <div style="font-size:13px;opacity:.8;">Avg relevance score</div>
    </div>
  </div>

  <div style="margin-top:16px;font-size:13px;">
    <strong>Platforms searched:</strong> {escape(', '.join(platforms) or 'none')}
  </div>

  <div style="margin-top:10px;font-size:13px;">
    <strong>By role category:</strong>
    <ul style="margin:4px 0 0 16px;padding:0;">{cat_rows}</ul>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------

def build_report(jobs: list[dict], total_found: int = 0) -> Path:
    """
    Build and save the HTML report.

    Args:
        jobs:        Shortlisted, scored, enriched job list.
        total_found: Raw total jobs collected across all platforms today.

    Returns:
        Path to the saved HTML file.
    """
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str  = datetime.now().strftime("%Y-%m-%d")
    out_path  = config.OUTPUT_DIR / f"report_{datetime.now().strftime('%Y%m%d')}.html"

    latex = _load_latex()
    cards = "".join(_job_card(j, latex) for j in jobs)

    if not jobs:
        cards = (
            '<p style="text-align:center;color:#888;padding:40px;">'
            'No jobs met the minimum relevance score today.</p>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Job Pipeline Report · {escape(date_str)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica,
                   Arial, sans-serif;
      background: #f0f2f5;
      color: #24292f;
      margin: 0;
      padding: 0;
    }}
    .container {{
      max-width: 780px;
      margin: 0 auto;
      padding: 32px 16px;
    }}
    details > summary {{
      list-style: none;
    }}
    details > summary::-webkit-details-marker {{
      display: none;
    }}
  </style>
</head>
<body>
<div class="container">
  {_summary_header(jobs, total_found, date_str)}
  {cards}
  <p style="text-align:center;color:#999;font-size:12px;margin-top:32px;">
    Generated by job-pipeline · {datetime.now().strftime("%Y-%m-%d %H:%M IST")}
  </p>
</div>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    logger.info("Report saved to %s", out_path)
    return out_path
