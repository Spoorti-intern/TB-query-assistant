import os
import random
import smtplib
import time
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# In-memory OTP store: { email: { "code": "123456", "expires": timestamp } }
_otp_store: dict[str, dict] = {}

OTP_EXPIRY_SECONDS = 300  # 5 minutes


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def store_otp(email: str, code: str):
    _otp_store[email.lower()] = {
        "code": code,
        "expires": time.time() + OTP_EXPIRY_SECONDS,
    }


def verify_otp(email: str, code: str) -> bool:
    key = email.lower()
    entry = _otp_store.get(key)
    if not entry:
        return False
    if time.time() > entry["expires"]:
        _otp_store.pop(key, None)
        return False
    if entry["code"] != code:
        return False
    # OTP verified — remove it so it can't be reused
    _otp_store.pop(key, None)
    return True


def send_otp_email(to_email: str, otp_code: str) -> tuple[bool, str]:
    """Send OTP email. Returns (success, error_reason)."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_email = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        logger.warning("SMTP not configured — SMTP_USER or SMTP_PASS is empty. OTP code: %s", otp_code)
        return False, "SMTP credentials not configured. Set SMTP_USER and SMTP_PASS environment variables."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Query Ops — Your verification code: {otp_code}"
    msg["From"] = from_email
    msg["To"] = to_email

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 24px;">
        <div style="text-align: center; margin-bottom: 32px;">
            <div style="display: inline-block; width: 56px; height: 56px; line-height: 56px; border-radius: 16px; background: linear-gradient(135deg, #2563eb, #1d4ed8); color: white; font-size: 24px; font-weight: 700;">Q</div>
            <h1 style="margin: 16px 0 4px; font-size: 24px; font-weight: 700; color: #111;">Query Ops</h1>
            <p style="color: #666; font-size: 14px; margin: 0;">Verify your email address</p>
        </div>
        <div style="background: #f8f9fa; border: 1px solid #e5e7eb; border-radius: 12px; padding: 32px; text-align: center;">
            <p style="color: #333; font-size: 15px; margin: 0 0 20px;">Your one-time verification code is:</p>
            <div style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #2563eb; padding: 16px 0;">{otp_code}</div>
            <p style="color: #888; font-size: 13px; margin: 20px 0 0;">This code expires in 5 minutes. Do not share it with anyone.</p>
        </div>
        <p style="text-align: center; color: #aaa; font-size: 11px; margin-top: 24px;">If you didn't request this code, you can safely ignore this email.</p>
    </div>
    """

    msg.attach(MIMEText(html, "html"))

    try:
        logger.info("Connecting to SMTP %s:%s as %s ...", smtp_host, smtp_port, smtp_user)
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())
        logger.info("OTP email sent to %s", to_email)
        return True, ""
    except smtplib.SMTPAuthenticationError as e:
        reason = f"SMTP login failed — check SMTP_USER/SMTP_PASS. Gmail requires an App Password. ({e})"
        logger.error(reason)
        return False, reason
    except (ConnectionRefusedError, OSError, TimeoutError) as e:
        reason = f"Cannot connect to {smtp_host}:{smtp_port} — SMTP port may be blocked by hosting provider. ({e})"
        logger.error(reason)
        return False, reason
    except Exception as e:
        reason = f"SMTP error: {e}"
        logger.error("Failed to send OTP email: %s", e)
        return False, reason
