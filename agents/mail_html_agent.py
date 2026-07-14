"""Agent: send saved HTML reports via SMTP email.

This module provides a small reusable SMTP helper that can send an HTML
report file as an attachment, along with a plain-text message body.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import List, Optional
import smtplib


@dataclass
class EmailSendResult:
    success: bool
    message: str
    sender_identity_hint: str


def parse_email_list(raw_value: str) -> List[str]:
    """Parse comma/semicolon separated email IDs into a cleaned list."""
    if not raw_value:
        return []
    value = raw_value.replace(";", ",")
    return [item.strip() for item in value.split(",") if item.strip()]


def send_html_report_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    from_email: str,
    sender_name: str,
    to_emails: List[str],
    cc_emails: Optional[List[str]],
    subject: str,
    body_text: str,
    html_file_name: str,
    html_content: str,
    use_tls: bool = True,
) -> EmailSendResult:
    """Send an HTML report as attachment using SMTP credentials."""

    cc_emails = cc_emails or []
    recipients = list(to_emails) + list(cc_emails)

    if not recipients:
        return EmailSendResult(
            success=False,
            message="No recipients provided.",
            sender_identity_hint="Recipients list is empty.",
        )

    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, from_email))
    msg["To"] = ", ".join(to_emails)
    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)
    msg["Subject"] = subject

    msg.set_content(body_text)

    # Attach the exported interactive dashboard HTML so the recipient can open
    # it in any browser and interact with charts.
    msg.add_attachment(
        html_content.encode("utf-8"),
        maintype="text",
        subtype="html",
        filename=html_file_name,
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if use_tls:
                server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg, from_addr=from_email, to_addrs=recipients)
    except Exception as exc:  # pragma: no cover - network/SMTP failures are runtime dependent
        return EmailSendResult(
            success=False,
            message=f"Failed to send email: {exc}",
            sender_identity_hint=(
                "Recipient mailbox usually shows the From header, but some providers "
                "may add 'via' or 'on behalf of' depending on SMTP/domain policy."
            ),
        )

    return EmailSendResult(
        success=True,
        message="Email sent successfully.",
        sender_identity_hint=(
            "Recipients will typically see the From value configured here. "
            "If SMTP credentials belong to another mailbox/domain, clients may show "
            "'via' or 'on behalf of'."
        ),
    )
