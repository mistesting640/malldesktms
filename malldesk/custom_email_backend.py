"""
malldesk/custom_email_backend.py
Custom SMTP backend using SMTP_SSL with certificate verification disabled.
Required for DreamHost/cPanel where cert hostname doesn't match mail domain.
"""

import ssl
import smtplib
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail import EmailMessage
from django.conf import settings


class SSLBypassEmailBackend(BaseEmailBackend):

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.host     = settings.EMAIL_HOST
        self.port     = settings.EMAIL_PORT
        self.username = settings.EMAIL_HOST_USER
        self.password = settings.EMAIL_HOST_PASSWORD

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        # SSL context that ignores hostname mismatch
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        num_sent = 0
        try:
            with smtplib.SMTP_SSL(self.host, self.port, context=context) as smtp:
                smtp.login(self.username, self.password)
                for message in email_messages:
                    try:
                        recipients = (
                            message.to
                            + (message.cc or [])
                            + (message.bcc or [])
                        )
                        smtp.sendmail(
                            message.from_email,
                            recipients,
                            message.message().as_bytes(),
                        )
                        num_sent += 1
                    except Exception as e:
                        if not self.fail_silently:
                            raise
        except Exception as e:
            if not self.fail_silently:
                raise

        return num_sent