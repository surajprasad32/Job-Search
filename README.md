# job-pipeline

An automated job-search pipeline for ML/AI roles that runs entirely on free
APIs and GitHub Actions — zero monthly cost.

---

## What this does

| Time (IST) | Action |
|------------|--------|
| 9:00 AM    | Search JSearch, Naukri, Internshala, Google Jobs; update `data/jobs.json` |
| 12:00 PM   | Same search pass (catches new postings) |
| 3:00 PM    | Same search pass |
| 7:00 PM    | Score jobs with Gemini, research compensation, build HTML report, email it |

Each evening you receive one email with up to 15 shortlisted jobs, each
containing:

- Relevance score (1–10) and reasoning
- Compensation table (salary range, equity, data sources, confidence)
- Company snapshot (size, funding, Glassdoor rating, tech stack, interview process)
- A pre-written Claude.ai prompt you can paste directly to tailor your resume

---

## Prerequisites

- A GitHub account with Actions enabled
- A Gmail account
- Python 3.11+ (only needed for local testing — CI runs on GitHub)

---

## Step-by-step setup

### 1. Fork / clone

```bash
git clone https://github.com/<your-username>/job-pipeline.git
cd job-pipeline
```

### 2. Get a Gemini API key (free — no credit card)

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with your Google account
3. Click **Get API key** → **Create API key**
4. Copy the key — this is your `GEMINI_API_KEY`

Free tier: 1 500 requests / day on `gemini-1.5-flash` — more than enough.

### 3. Get a RapidAPI key (free tier)

1. Go to [rapidapi.com](https://rapidapi.com) and create an account
2. Search for **JSearch** and click **Subscribe to Test** on the free tier
3. Copy your API key from the dashboard — this is your `RAPIDAPI_KEY`

Free tier: 200 requests / month — the pipeline makes ≈ 18 calls/day (stays under).

### 4. Get a SerpAPI key (free tier)

1. Go to [serpapi.com](https://serpapi.com) and create an account
2. Copy the API key from the dashboard — this is your `SERPAPI_KEY`

Free tier: 100 searches / month — the pipeline caps itself automatically.

### 5. Set up a Gmail App Password

Regular Gmail passwords won't work with SMTP. You need an **App Password**:

1. Go to your Google Account → **Security**
2. Under "How you sign in to Google", enable **2-Step Verification** if not already on
3. Back on Security, click **App passwords** (may be under "2-Step Verification")
4. Select **Mail** → **Other (custom name)** → type `job-pipeline` → **Generate**
5. Copy the 16-character password — this is your `GMAIL_APP_PASSWORD`

### 6. Add secrets to GitHub

Go to your repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret** for each of the five secrets:

| Secret name          | Value                              |
|----------------------|------------------------------------|
| `RAPIDAPI_KEY`       | Your RapidAPI key                  |
| `SERPAPI_KEY`        | Your SerpAPI key                   |
| `GEMINI_API_KEY`     | Your Gemini / AI Studio key        |
| `GMAIL_USER`         | Your full Gmail address            |
| `GMAIL_APP_PASSWORD` | The 16-char App Password           |

### 7. Enable GitHub Actions

Go to **Actions** tab → click **I understand my workflows, go ahead and enable them**.

### 8. Test with manual dispatch

Go to **Actions** → **Job Search (3x Daily)** → **Run workflow** → **Run workflow**.

Check the run logs. After it completes, `data/jobs.json` should have entries.

Then trigger **Evening Report (7 PM IST)** the same way to get a test email.

---

## Project structure

```
job-pipeline/
├── .github/workflows/
│   ├── search.yml          # runs 3x daily, populates jobs.json
│   └── report.yml          # runs at 7 PM IST, emails the report
├── src/
│   ├── config.py           # all settings — edit this to customise
│   ├── search.py           # platform fetchers (JSearch, Naukri, etc.)
│   ├── filter.py           # Gemini scoring & shortlisting
│   ├── compensation.py     # Gemini compensation & company research
│   ├── report.py           # HTML report builder
│   ├── email_send.py       # Gmail SMTP sender
│   └── main.py             # evening orchestrator
├── resume/
│   └── base.tex            # your base LaTeX resume
├── data/
│   └── jobs.json           # persistent job store (grows over time)
├── output/                 # HTML reports saved here
├── logs/                   # daily log files
└── requirements.txt
```

---

## How to customise (`config.py`)

| Setting | Default | What it controls |
|---------|---------|------------------|
| `TARGET_ROLES` | ML Engineer, SDE, … | Search queries sent to each platform |
| `PREFERRED_LOCATIONS` | Bangalore, Delhi, … | Location filter |
| `INTERNATIONAL_REMOTE` | `True` | Include international remote results |
| `MIN_RELEVANCE_SCORE` | `6` | Jobs below this score are not emailed |
| `MAX_JOBS_IN_REPORT` | `15` | Cap on jobs per daily email |
| `EXCLUDE_KEYWORDS` | senior, lead, … | Job titles containing these are skipped |
| `PLATFORMS` | all `True` | Toggle platforms on/off |

---

## Cost breakdown

| Component | Service | Cost |
|-----------|---------|------|
| Scoring + compensation research | Gemini 1.5 Flash | Free (1 500 req/day) |
| LinkedIn / Indeed / Glassdoor jobs | JSearch via RapidAPI | Free (200 req/month) |
| Google Jobs | SerpAPI | Free (100 searches/month) |
| Naukri | Direct scraper | Free |
| Internshala | Direct scraper | Free |
| Email delivery | Gmail SMTP | Free |
| CI/CD scheduling | GitHub Actions | Free (2 000 min/month) |

**Total monthly cost: $0**

---

## How to use the Claude.ai tailoring prompt

Each job card in the email contains a grey box labelled **COPY** with a
pre-written prompt. Here is how to use it:

1. Open the email and find a job you want to apply for
2. Expand the **Claude.ai Resume Tailoring Prompt** section
3. Select all the text in the grey box and copy it (Ctrl+C / Cmd+C)
4. Go to [claude.ai](https://claude.ai) and start a new conversation
5. Paste the prompt and press Enter
6. Claude will return complete, compilable LaTeX for a tailored resume
7. Compile it with `pdflatex` or paste into [Overleaf](https://overleaf.com)

The prompt enforces strict rules: it only modifies Skills, Work Experience,
and Projects; never fabricates metrics; and always keeps your Samsung SRIB
and Speculative Decoding highlights.

---

## Troubleshooting

**Email not received**
- Check spam folder
- Verify `GMAIL_USER` and `GMAIL_APP_PASSWORD` secrets are set correctly
- Confirm the App Password is 16 characters with no spaces
- Check the `logs/` folder in the repo for the error message

**No jobs found / very few results**
- JSearch and SerpAPI have monthly quotas — check your usage dashboards
- Naukri sometimes blocks scrapers; the pipeline retries gracefully
- Try reducing `TARGET_ROLES` to 3–4 roles to reduce API calls
- Run `python src/search.py` locally to debug

**Gemini scoring fails**
- Confirm `GEMINI_API_KEY` is set and valid
- Check AI Studio quota at [aistudio.google.com](https://aistudio.google.com)
- Jobs that fail Gemini scoring get `score=0` and are silently skipped

**LinkedIn / Glassdoor results blocked**
- This happens when JSearch rate-limits you; the pipeline backs off automatically
- If persistent, set `PLATFORMS["jsearch"] = False` in `config.py` and rely
  on Naukri and Google Jobs

**GitHub Actions workflow not running**
- Make sure you clicked "Enable Actions" in the Actions tab
- Scheduled workflows only fire if the repo has had a commit in the last 60 days;
  push a trivial change if the repo has been idle
