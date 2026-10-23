"""Checks cgpeers.to for open registration and alerts via Telegram.

Signals that registration is open:
  - visible page text mentions register / sign up / applications open, or
  - a register-like page stops returning 404.
State is kept in state.json so the same signal is only reported once.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://cgpeers.to"
PAGES = ["/", "/login"]
REGISTER_PATHS = ["/register", "/signup", "/register.php", "/apply", "/invite"]
KEYWORDS = re.compile(
    r"\b(register|sign\s?-?up|registration|applications?\s+(are\s+)?open|open\s+signups?)\b",
    re.IGNORECASE,
)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def fetch(path):
    req = urllib.request.Request(BASE + path, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def visible_text(html):
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"].strip("﻿ \r\n")
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip("﻿ \r\n")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30)


def main():
    signals = []
    for page in PAGES:
        status, html = fetch(page)
        if status != 200:
            continue
        text = visible_text(html)
        for m in KEYWORDS.finditer(text):
            start = max(0, m.start() - 60)
            signals.append(f"{page}: «…{text[start:m.end() + 60]}…»")
        for href in re.findall(r'href=["\']([^"\']+)["\']', html):
            if re.search(r"regist|signup|sign-up|apply", href, re.IGNORECASE):
                signals.append(f"{page}: ссылка {href}")
    for path in REGISTER_PATHS:
        status, _ = fetch(path)
        if status not in (404, 410):
            signals.append(f"{path} отвечает {status} (раньше 404)")

    simulate = os.environ.get("SIMULATE") == "1"
    if simulate:
        signals.append("ТЕСТ-ИМИТАЦИЯ: это проверка, регистрация на самом деле не открыта")

    fingerprint = hashlib.sha256("\n".join(sorted(signals)).encode()).hexdigest() if signals else ""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            last = json.load(f).get("fingerprint", "")
    except (FileNotFoundError, ValueError):
        last = ""

    if os.environ.get("FORCE_TEST") == "1":
        send_telegram("🧪 Тест: облачная проверка CGPeers работает.\n"
                      f"Сейчас признаков регистрации: {len(signals)}.\n{BASE}")
    elif signals and fingerprint != last:
        send_telegram("🚨🚨🚨 CGPeers: похоже, открылась регистрация!\n\n"
                      + "\n".join(signals[:8])
                      + f"\n\n👉 {BASE}\n👉 Discord: https://discord.com/channels/"
                        "1381341157421748444/1382681623581167656")
        # Repeat so the phone rings several times and the alert is not missed.
        for n in (2, 3):
            time.sleep(20)
            send_telegram(f"🔔 Напоминание {n}/3: CGPeers — проверьте регистрацию! {BASE}")
    elif not signals and last and not simulate:
        send_telegram("ℹ️ CGPeers: признаки регистрации пропали — похоже, набор снова закрыт.\n"
                      "Слежение продолжается, при следующем открытии придёт новое уведомление.")

    if simulate:
        print(f"simulated alert sent, signals={len(signals)}")
        return
    # The month field changes state.json once a month, so the workflow commits and
    # GitHub does not disable the schedule after 60 days without repo activity.
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"fingerprint": fingerprint, "signals": signals,
                   "month": time.strftime("%Y-%m", time.gmtime())}, f, ensure_ascii=False, indent=1)
    print(f"signals={len(signals)} changed={fingerprint != last}")


if __name__ == "__main__":
    sys.exit(main())
