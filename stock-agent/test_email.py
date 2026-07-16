#!/usr/bin/env python3
"""
Manual email connectivity test.

Locally:
    python test_email.py

On Railway (one-off command from the service shell):
    python test_email.py

Prints a clear success or failure diagnosis. Does NOT depend on market hours,
watchlist, or Anthropic API — just exercises the SMTP path with a fake signal.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from notifier import _email_cfg, _smtp_send  # noqa: E402
from email.mime.text import MIMEText  # noqa: E402
from datetime import datetime  # noqa: E402


def main() -> None:
    cfg = _email_cfg()
    if not cfg:
        print("❌ Email not configured. Missing one of:")
        print(f"   EMAIL_FROM         : {'✓' if os.environ.get('EMAIL_FROM') else '✗ MISSING'}")
        print(f"   EMAIL_TO           : {'✓' if os.environ.get('EMAIL_TO') else '✗ MISSING'}")
        print(f"   EMAIL_APP_PASSWORD : {'✓' if os.environ.get('EMAIL_APP_PASSWORD') else '✗ MISSING'}")
        sys.exit(1)

    print(f"Sending test email from {cfg['from']} → {cfg['to']}")

    body = (
        f"This is a test email from the stock-agent.\n\n"
        f"If you see this, SMTP delivery is working correctly.\n\n"
        f"Time: {datetime.now().isoformat()}\n"
        f"Host: {os.environ.get('RAILWAY_SERVICE_NAME', 'local')}\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = "[Stock Agent] Test email — connectivity check"
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]

    try:
        _smtp_send(cfg, msg)
        print("✅ Test email sent. Check your inbox (and spam folder).")
    except Exception as e:
        print(f"❌ SMTP send failed: {type(e).__name__}: {e}")
        print()
        print("Common causes:")
        print("  • Wrong EMAIL_APP_PASSWORD — must be the 16-char Gmail App Password,")
        print("    not your Google account login password. Get one at:")
        print("    https://myaccount.google.com/apppasswords")
        print("  • Copy-paste with spaces — the app password should have NO spaces.")
        print("  • EMAIL_FROM must be the same Gmail account that owns the app password.")
        sys.exit(1)


if __name__ == "__main__":
    main()
