"""
Email Sender.

Sends HTML reports via SMTP (Gmail or other providers).
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from typing import Optional, List

from loguru import logger

from src.utils import load_config, load_credentials


class EmailSender:
    """Sends HTML email reports via SMTP."""

    def __init__(self):
        self.config = load_config().get("email", {})
        self._credentials = {}

        try:
            creds = load_credentials()
            self._credentials = creds.get("email", {})
        except Exception:
            logger.info("Email credentials not configured")

    @property
    def is_configured(self) -> bool:
        return bool(
            self._credentials.get("sender_email")
            and self._credentials.get("sender_password")
            and self._credentials.get("recipients")
        )

    def send_report(
        self,
        html_content: str,
        subject: Optional[str] = None,
        recipients: Optional[List[str]] = None,
    ) -> bool:
        """
        Send an HTML email report.

        Returns True if sent successfully.
        """
        if not self.config.get("enabled", False):
            logger.info("Email sending is disabled in config")
            return False

        if not self.is_configured:
            logger.warning("Email not configured. Set credentials in credentials.yaml")
            return False

        if subject is None:
            prefix = self.config.get("subject_prefix", "[Trading System]")
            subject = f"{prefix} Morning Report - {date.today().strftime('%B %d, %Y')}"

        if recipients is None:
            recipients = self._credentials.get("recipients", [])

        sender = self._credentials["sender_email"]
        password = self._credentials["sender_password"]
        smtp_server = self.config.get("smtp_server", "smtp.gmail.com")
        smtp_port = self.config.get("smtp_port", 587)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        # Plain text fallback
        text_part = MIMEText(
            "Your trading report is attached. Please view in an HTML-compatible email client.",
            "plain",
        )
        html_part = MIMEText(html_content, "html")

        msg.attach(text_part)
        msg.attach(html_part)

        try:
            if self.config.get("use_tls", True):
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port)

            server.login(sender, password)
            server.sendmail(sender, recipients, msg.as_string())
            server.quit()

            logger.info(f"Report email sent to {', '.join(recipients)}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
