"""
Sends alerts to Google Chat webhook and/or email.
Both are optional — if the env vars aren't set, that channel is silently skipped.
"""

import contextlib
import os
import smtplib
import socket
import requests
from email.mime.text import MIMEText
from datetime import datetime


# ---------- IPv4-only SMTP fix ----------
# Railway (and many container platforms) give the container IPv4 connectivity only,
# but smtp.gmail.com has AAAA records so Python resolves it to IPv6 first and
# fails with ENETUNREACH. Force AF_INET resolution for the duration of the SMTP
# call so it stays on IPv4 while the SSL cert is still validated against
# "smtp.gmail.com".

_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


@contextlib.contextmanager
def _force_ipv4():
    socket.getaddrinfo = _ipv4_only
    try:
        yield
    finally:
        socket.getaddrinfo = _orig_getaddrinfo


def _smtp_send(cfg: dict, msg: MIMEText) -> None:
    """Send an already-composed MIMEText message via Gmail SMTP over IPv4."""
    with _force_ipv4():
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(cfg["from"], cfg["password"])
            smtp.send_message(msg)


def _gchat_webhook() -> str | None:
    return os.environ.get("GCHAT_WEBHOOK_URL", "").strip() or None


def _connector_cfg() -> dict | None:
    """
    Config for pushing signals to the Connector web app.

    CONNECTOR_API_URL is the site base (e.g. https://connector.up.railway.app);
    we POST to {base}/api/v1/signals with the shared agent key. This replaces
    the flaky Gmail SMTP path — HTTP from the agent host is reliable, SMTP isn't.
    """
    base = os.environ.get("CONNECTOR_API_URL", "").strip().rstrip("/")
    key = os.environ.get("CONNECTOR_AGENT_KEY", "").strip()
    if base and key:
        return {"url": f"{base}/api/v1/signals", "key": key}
    return None


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


def _connector_payload(signal: dict) -> dict:
    """Map the internal signal dict to the Connector /signals schema."""
    keys = (
        "ticker", "signal", "confidence", "price", "entry_price", "target_price",
        "stop_loss", "shares", "score", "max_score", "risk_reward_ratio",
        "regime", "order_status", "reasoning", "exit_plan",
    )
    return {k: signal.get(k) for k in keys if signal.get(k) is not None}


def _send_connector(signal: dict) -> None:
    # HOLD is "do nothing" — don't push it to the dashboard feed.
    if str(signal.get("signal", "")).upper() == "HOLD":
        return
    cfg = _connector_cfg()
    if not cfg:
        return
    try:
        resp = requests.post(
            cfg["url"],
            json=_connector_payload(signal),
            headers={"X-Agent-Key": cfg["key"]},
            timeout=10,
        )
        if resp.status_code >= 300:
            print(f"[notifier] Connector error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[notifier] Connector push failed: {e}")


def send(signal: dict) -> None:
    _send_gchat(signal)
    _send_connector(signal)
    _send_email(signal)


# ---------- Exit alerts (position management) ----------


_URGENCY_ICON = {"IMMEDIATE": "🚨", "IMPORTANT": "⚠️", "ADVISORY": "💡"}


def _format_exit_gchat(alert) -> str:
    icon = _URGENCY_ICON.get(alert.urgency, "🔔")
    shares_str = f"{alert.shares:.4f}".rstrip("0").rstrip(".")
    lines = [
        f"{icon} *{alert.alert_type}* — *{alert.ticker}* [{alert.urgency}]",
        alert.message,
        f"Held: {alert.days_held}d  |  {shares_str} shares  |  Entry ${alert.entry_price:.2f}  →  Now ${alert.current_price:.2f}",
        f"Unrealized P&L: *${alert.unrealized_pnl:+,.2f}* ({alert.unrealized_pnl_pct:+.2f}%)",
        f"Current stop: ${alert.current_stop:.2f}  |  Target: ${alert.target:.2f}",
    ]
    return "\n".join(lines)


def _format_exit_email(alert) -> tuple[str, str]:
    subject = f"[Stock Agent] {alert.alert_type} — {alert.ticker} ({alert.urgency})"
    shares_str = f"{alert.shares:.4f}".rstrip("0").rstrip(".")
    body = "\n".join([
        f"POSITION ALERT — {alert.ticker}",
        f"Type       : {alert.alert_type}",
        f"Urgency    : {alert.urgency}",
        f"",
        alert.message,
        f"",
        f"Shares         : {shares_str}",
        f"Entry price    : ${alert.entry_price:.2f}",
        f"Current price  : ${alert.current_price:.2f}",
        f"Days held      : {alert.days_held}",
        f"Unrealized P&L : ${alert.unrealized_pnl:+.2f} ({alert.unrealized_pnl_pct:+.2f}%)",
        f"Current stop   : ${alert.current_stop:.2f}",
        f"Target         : ${alert.target:.2f}",
        f"",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}",
    ])
    return subject, body


def _send_connector_exit(alert, position_id: str = "") -> None:
    """
    Push a position-exit alert to the Connector dashboard so the site tells you
    when to stop out / take profit / raise your trailing stop — not just email.
    Maps the ExitAlert onto the same /signals schema (alert_type as the signal),
    tagged with position_id so it lands under the exact position it belongs to.
    """
    cfg = _connector_cfg()
    if not cfg:
        return
    payload = {
        "ticker": alert.ticker,
        "signal": alert.alert_type,          # HARD_STOP / TARGET_HIT / TRAIL_RAISED / ...
        "confidence": alert.urgency,         # IMMEDIATE / IMPORTANT / ADVISORY
        "price": alert.current_price,
        "entry_price": alert.entry_price,
        "target_price": alert.target,
        "stop_loss": alert.current_stop,
        "shares": alert.shares,
        "reasoning": alert.message,
    }
    if position_id:
        payload["position_id"] = position_id
    try:
        resp = requests.post(
            cfg["url"], json=payload, headers={"X-Agent-Key": cfg["key"]}, timeout=10
        )
        if resp.status_code >= 300:
            print(f"[notifier] Connector exit error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[notifier] Connector exit push failed: {e}")


def send_exit(alert, position_id: str = "") -> None:
    """Send a position-exit alert to all configured channels."""
    _send_connector_exit(alert, position_id)
    url = _gchat_webhook()
    if url:
        try:
            resp = requests.post(url, json={"text": _format_exit_gchat(alert)}, timeout=10)
            if resp.status_code != 200:
                print(f"[notifier] Exit-GChat error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[notifier] Exit-GChat failed: {e}")

    cfg = _email_cfg()
    if cfg:
        try:
            subject, body = _format_exit_email(alert)
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = cfg["from"]
            msg["To"] = cfg["to"]
            _smtp_send(cfg, msg)
        except Exception as e:
            print(f"[notifier] Exit-email failed: {e}")


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
        _smtp_send(cfg, msg)
    except Exception as e:
        print(f"[notifier] Email failed: {e}")
