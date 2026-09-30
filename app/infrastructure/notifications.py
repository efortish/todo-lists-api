"""Fake email delivery: messages are logged instead of sent."""

import logging

logger = logging.getLogger("app.notifications")


class LoggingEmailNotifier:
    """Writes each email to the application log. Swap for an SMTP/SES adapter in production."""

    def send_email(self, to: str, subject: str, body: str) -> None:
        logger.info("[fake email] to=%s subject=%r body=%r", to, subject, body)
