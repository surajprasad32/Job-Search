"""
Gmail SMTP email sender for the job pipeline report.

Sends the HTML report via Gmail on port 465 (SSL).
Credentials are read exclusively from environment variables — never
hard-coded.

Usage:
    from email_send import send_report
    ok = send_report(html_content, num_shortlisted, avg_score)
"""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

logger = logging.getLogger(__name__)


def send_report(html_content: str, num_shortlisted: int, avg_score: float) -> bool:
    """
    Send the HTML report via Gmail SMTP SSL.

    Args:
        html_content:    Full HTML string of the report.
        num_shortlisted: Number of jobs in the report (used in subject).
        avg_score:       Average relevance score (used in subject).

    Returns:
        True on success, False on any failure.
    """
    if not config.GMAIL_USER or not config.GMAIL_APP_PASSWORD:
        logger.error(
            "GMAIL_USER or GMAIL_APP_PASSWORD not set — cannot send email"
        )
        return False

    date_str = datetime.now().strftime("%d %b %Y")
    subject  = (
        f"[Job Report] {num_shortlisted} roles shortlisted "
        f"· Avg {avg_score}/10 · {date_str}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.GMAIL_USER
    msg["To"]      = config.REPORT_RECIPIENT

    # Plain-text fallback for email clients that don't render HTML
    plain_text = (
        f"Job Pipeline Report — {date_str}\n\n"
        f"{num_shortlisted} jobs shortlisted today (avg score {avg_score}/10).\n"
        "Open the HTML version of this email to view the full report with "
        "job cards, compensation data, and Claude.ai tailoring prompts.\n\n"
        f"— job-pipeline bot"
    )
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html",  "utf-8"))

    try:
        with smtplib.SMTP_SSL(
            config.GMAIL_SMTP_HOST,
            config.GMAIL_SMTP_PORT,
        ) as server:
            server.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
            server.sendmail(
                config.GMAIL_USER,
                config.REPORT_RECIPIENT,
                msg.as_string(),
            )
        logger.info(
            "Email sent to %s — subject: %s",
            config.REPORT_RECIPIENT,
            subject,
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail authentication failed — check GMAIL_USER and "
            "GMAIL_APP_PASSWORD (must be an App Password, not your "
            "regular Gmail password)"
        )
        return False

    except smtplib.SMTPException as exc:
        logger.error("SMTP error while sending email: %s", exc)
        return False

    except Exception as exc:
        logger.error("Unexpected error while sending email: %s", exc)
        return False
