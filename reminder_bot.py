"""
Saylo Sprint Reminder Bot

Рассчитывает, какой сегодня день спринта, проверяет совпадение с напоминалками,
учитывает переносы/отмены из overrides, отправляет в Telegram.
"""

import json
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ── Конфигурация ──────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
FAKE_DATE = os.environ.get("FAKE_DATE", "")  # для тестирования: YYYY-MM-DD

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ── Загрузка конфига ──────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Логика спринтов ───────────────────────────────────────────

def get_today(tz_offset_hours: int) -> datetime:
    """Возвращает сегодняшнюю дату в заданном часовом поясе."""
    tz = timezone(timedelta(hours=tz_offset_hours))
    return datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)


def compute_sprint_day(today: datetime, sprint_start: datetime, sprint_length: int) -> int:
    """
    Возвращает день внутри текущего спринта (0-indexed).
    Спринты повторяются циклично от start_date.
    """
    delta = (today - sprint_start).days
    if delta < 0:
        log.warning("Сегодня (%s) раньше начала первого спринта (%s).", today.date(), sprint_start.date())
        return -1
    return delta % sprint_length


def get_sprint_number(today: datetime, sprint_start: datetime, sprint_length: int) -> int:
    """Номер текущего спринта (1-indexed)."""
    delta = (today - sprint_start).days
    if delta < 0:
        return 0
    return delta // sprint_length + 1


def find_reminder_for_today(today: datetime, config: dict) -> dict | None:
    """
    Определяет, нужно ли сегодня отправлять напоминание.
    Учитывает overrides (move/skip).
    """
    today_str = today.strftime("%Y-%m-%d")
    sprint_cfg = config["sprint"]
    sprint_start = datetime.strptime(sprint_cfg["start_date"], "%Y-%m-%d").replace(
        tzinfo=timezone(timedelta(hours=sprint_cfg["timezone_offset_hours"]))
    )
    sprint_length = sprint_cfg["length_days"]
    reminders = config["reminders"]
    overrides = config.get("overrides", [])

    # ── Шаг 1: проверяем, не перенесена ли какая-то напоминалка НА сегодня
    for ov in overrides:
        if ov["action"] == "move" and ov.get("new_date") == today_str:
            # Ищем, какая напоминалка была в original_date
            orig_date = datetime.strptime(ov["original_date"], "%Y-%m-%d").replace(
                tzinfo=timezone(timedelta(hours=sprint_cfg["timezone_offset_hours"]))
            )
            orig_sprint_day = compute_sprint_day(orig_date, sprint_start, sprint_length)
            for r in reminders:
                if r["day_offset"] == orig_sprint_day:
                    sprint_num = get_sprint_number(orig_date, sprint_start, sprint_length)
                    log.info(
                        "Перенос: напоминалка '%s' перенесена с %s на %s (%s).",
                        r["id"], ov["original_date"], today_str, ov.get("reason", "")
                    )
                    return {**r, "sprint_number": sprint_num, "moved_from": ov["original_date"]}

    # ── Шаг 2: проверяем, не отменена/перенесена ли сегодняшняя напоминалка
    for ov in overrides:
        if ov.get("original_date") == today_str:
            if ov["action"] == "skip":
                log.info("Пропуск: напоминалка на %s отменена (%s).", today_str, ov.get("reason", ""))
                return None
            if ov["action"] == "move":
                log.info(
                    "Перенос: напоминалка с %s перенесена на %s (%s).",
                    today_str, ov.get("new_date"), ov.get("reason", "")
                )
                return None

    # ── Шаг 3: обычная проверка по дню спринта
    sprint_day = compute_sprint_day(today, sprint_start, sprint_length)
    sprint_num = get_sprint_number(today, sprint_start, sprint_length)

    if sprint_day < 0:
        return None

    for r in reminders:
        if r["day_offset"] == sprint_day:
            log.info(
                "Совпадение: день спринта %d → напоминалка '%s' (%s).",
                sprint_day, r["id"], r["label"]
            )
            return {**r, "sprint_number": sprint_num}

    log.info("День спринта %d (спринт #%d) — напоминалок нет.", sprint_day, sprint_num)
    return None


# ── Telegram ──────────────────────────────────────────────────

def send_to_telegram(text: str) -> dict:
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def format_message(reminder: dict) -> str:
    """Формирует финальное сообщение с метаданными спринта."""
    sprint_num = reminder.get("sprint_number", "?")
    header = f"🔄 Спринт #{sprint_num} — {reminder['label']}\n\n"
    return header + reminder["message"]


# ── Main ──────────────────────────────────────────────────────

def main():
    config = load_config(CONFIG_PATH)
    tz_hours = config["sprint"]["timezone_offset_hours"]

    if FAKE_DATE:
        tz = timezone(timedelta(hours=tz_hours))
        today = datetime.strptime(FAKE_DATE, "%Y-%m-%d").replace(tzinfo=tz)
        log.info("FAKE_DATE режим: симулируем дату %s", FAKE_DATE)
    else:
        today = get_today(tz_hours)

    log.info("Сегодня: %s", today.strftime("%Y-%m-%d, %A"))

    reminder = find_reminder_for_today(today, config)

    if reminder is None:
        log.info("Сегодня отправлять нечего.")
        return

    message = format_message(reminder)

    if DRY_RUN:
        print("\n===== СООБЩЕНИЕ =====")
        print(message)
        print("=====================\n")
        return

    log.info("Отправляю в Telegram (%s)...", TELEGRAM_CHAT_ID)
    result = send_to_telegram(message)
    log.info("Отправлено! Message ID: %s", result.get("result", {}).get("message_id"))


if __name__ == "__main__":
    main()
