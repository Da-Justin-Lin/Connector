import os
from datetime import datetime
from colorama import Fore, Style, init
import notifier

init(autoreset=True)

_LOG_FILE = os.path.join(os.path.dirname(__file__), "alerts.log")

_SIGNAL_COLOR = {
    "BUY": Fore.GREEN,
    "SELL": Fore.RED,
    "HOLD": Fore.YELLOW,
}

_CONFIDENCE_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def should_alert(signal: dict, min_confidence: str) -> bool:
    if signal.get("signal") == "HOLD":
        return False
    return _CONFIDENCE_ORDER.get(signal.get("confidence", "LOW"), 0) >= _CONFIDENCE_ORDER[min_confidence]


def display(signal: dict) -> None:
    sig = signal.get("signal", "HOLD")
    conf = signal.get("confidence", "LOW")
    ticker = signal.get("ticker", "?")
    price = signal.get("price", 0)
    entry = signal.get("entry_price")
    target = signal.get("target_price")
    stop = signal.get("stop_loss")
    reason = signal.get("reasoning", "")

    color = _SIGNAL_COLOR.get(sig, Fore.WHITE)
    now = datetime.now().strftime("%H:%M:%S")

    line = "=" * 60
    print(f"\n{color}{line}")
    print(f"  {sig} SIGNAL  [{conf} confidence]  {now}")
    print(f"  Ticker : {ticker}")
    print(f"  Price  : ${price:,.2f}")
    if entry:
        print(f"  Entry  : ${entry:,.2f}")
    if target:
        print(f"  Target : ${target:,.2f}")
    if stop:
        print(f"  Stop   : ${stop:,.2f}")
    print(f"  Reason : {reason}")
    print(f"{line}{Style.RESET_ALL}")

    _write_log(signal)
    notifier.send(signal)


def display_scan_header(tickers: list[str]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{Fore.CYAN}[{now}] Scanning {', '.join(tickers)}...{Style.RESET_ALL}")


def display_hold(signal: dict) -> None:
    ticker = signal.get("ticker", "?")
    sig = signal.get("signal", "HOLD")
    conf = signal.get("confidence", "")
    color = _SIGNAL_COLOR.get(sig, Fore.YELLOW)
    print(f"  {color}{ticker}: {sig} ({conf}){Style.RESET_ALL}")


def _write_log(signal: dict) -> None:
    with open(_LOG_FILE, "a") as f:
        ts = datetime.now().isoformat()
        f.write(
            f"{ts} | {signal.get('ticker')} | {signal.get('signal')} | "
            f"{signal.get('confidence')} | ${signal.get('price')} | "
            f"entry={signal.get('entry_price')} target={signal.get('target_price')} "
            f"stop={signal.get('stop_loss')} | {signal.get('reasoning', '').replace(chr(10), ' ')}\n"
        )
