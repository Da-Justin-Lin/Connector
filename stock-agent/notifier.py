"""
Sends alerts to Google Chat webhook and/or email.
Both are optional — if the env vars aren't set, that channel is silently skipped.
"""

import os
import smtplib
import requests
from email.mime.text import MIMEText
from datetime import datetime


def _gchat_webhook() -> str | None:
    return os.environ.get("GCHAT_WEBHOOK_URL", "").strip() or None


def _email_cfg() -> dict | None:
    frm = os.environ.get("EMAIL_FROM", "").strip()
    to = os.environ.get("EMAIL_TO", "").strip()
    pw = os.environ.get("EMAIL_APP_PASSWORD", "").strip()
    if frm and to and pw:
        return {"from": frm, "to": to, "password": pw}
    return None


def _icon(sig: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴"}.get(sig, "🟡")


def _format_gchat(signal: dict) -> str:
    sig = signal.get("signal", "HOLD")
    ticker = signal.get("ticker", "?")
    price = signal.get("price", 0)
    conf = signal.get("confidence", "")
    entry = signal.get("entry_price")
    target = signal.get("target_price")
    stop = signal.get("stop_loss")
    shares = signal.get("shares")
    pos_value = signal.get("position_value")
    risk = signal.get("risk_dollars")
    rr = signal.get("risk_reward_ratio")
    score = signal.get("score")
    max_score = signal.get("max_score")
    regime = signal.get("regime")
    order_status = signal.get("order_status", "")
    reason = signal.get("reasoning", "")
    now = datetime.now().strftime("%H:%M:%S ET")

    lines = [
        f"{_icon(sig)} *{sig} — {ticker}* [{conf}] @ {now}",
        f"Price: *${price:,.2f}*  |  Regime: {regime}  |  Score: {score}/{max_score}",
    ]
    if shares:
        shares_str = f"{shares:.4f}".rstrip("0").rstrip(".")
        lines.append(f"Size: *{shares_str} shares* (${pos_value:,.2f})")
    if entry and stop and target:
        lines.append(
            f"Entry: ${entry:,.2f}  →  Target: ${target:,.2f}  |  Stop: ${stop:,.2f}"
        )
    if risk is not None and rr is not None:
        lines.append(f"Risk: ${risk:,.2f}  |  R:R = {rr}")
    if order_status:
        lines.append(f"_{order_status}_")
    lines.append(f"_{reason}_")
    return "\n".join(lines)


def _format_email(signal: dict) -> tuple[str, str]:
    sig = signal.get("signal", "HOLD")
    ticker = signal.get("ticker", "?")
    price = signal.get("price", 0)
    conf = signal.get("confidence", "")
    entry = signal.get("entry_price")
    target = signal.get("target_price")
    stop = signal.get("stop_loss")
    shares = signal.get("shares")
    reason = signal.get("reasoning", "")
    order_status = signal.get("order_status", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S ET")

    subject = f"[Stock Agent] {sig} {ticker} @ ${price:,.2f} [{conf}]"
    lines = [
        f"{sig} SIGNAL — {ticker}",
        f"Confidence : {conf}",
        f"Price      : ${price:,.2f}",
    ]
    if shares:
        lines.append(f"Shares     : {shares}")
    if entry:
        lines.append(f"Entry      : ${entry:,.2f}")
    if target:
        lines.append(f"Target     : ${target:,.2f}")
    if stop:
        lines.append(f"Stop       : ${stop:,.2f}")
    if order_status:
        lines.append(f"Order      : {order_status}")
    lines.append(f"Time       : {now}")
    lines.append("")
    lines.append("Reasoning:")
    lines.append(reason)
    return subject, "\n".join(lines)


def send(signal: dict) -> None:
    _send_gchat(signal)
    _send_email(signal)


def _send_gchat(signal: dict) -> None:
    url = _gchat_webhook()
    if not url:
        return
    try:
        text = _format_gchat(signal)
        resp = requests.post(url, json={"text": text}, timeout=10)
        if resp.status_code != 200:
            print(f"[notifier] GChat error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[notifier] GChat failed: {e}")


def _send_email(signal: dict) -> None:
    cfg = _email_cfg()
    if not cfg:
        return
    try:
        subject, body = _format_email(signal)
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = cfg["to"]
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(cfg["from"], cfg["password"])
            smtp.send_message(msg)
    except Exception as e:
        print(f"[notifier] Email failed: {e}")
