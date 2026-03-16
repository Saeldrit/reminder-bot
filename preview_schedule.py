"""
Превью расписания напоминалок на N спринтов вперёд.
Удобно для проверки после редактирования config.json.

Использование:
    python preview_schedule.py           # 3 спринта
    python preview_schedule.py 5         # 5 спринтов
"""

import json
import sys
from datetime import datetime, timedelta, timezone

WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def main():
    num_sprints = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    sprint_cfg = config["sprint"]
    tz = timezone(timedelta(hours=sprint_cfg["timezone_offset_hours"]))
    sprint_start = datetime.strptime(sprint_cfg["start_date"], "%Y-%m-%d").replace(tzinfo=tz)
    sprint_length = sprint_cfg["length_days"]
    reminders = config["reminders"]
    overrides = {ov["original_date"]: ov for ov in config.get("overrides", [])}

    # Индекс: new_date → override (для переносов НА эту дату)
    move_targets = {}
    for ov in config.get("overrides", []):
        if ov["action"] == "move" and "new_date" in ov:
            move_targets[ov["new_date"]] = ov

    print(f"\n{'='*60}")
    print(f"  Расписание напоминалок на {num_sprints} спринтов")
    print(f"  Старт: {sprint_start.strftime('%Y-%m-%d')} | Длина спринта: {sprint_length} дней")
    print(f"{'='*60}\n")

    for sprint_num in range(1, num_sprints + 1):
        sprint_begin = sprint_start + timedelta(days=(sprint_num - 1) * sprint_length)
        sprint_end = sprint_begin + timedelta(days=sprint_length - 1)
        print(f"── Спринт #{sprint_num}: {sprint_begin.strftime('%d.%m')} — {sprint_end.strftime('%d.%m.%Y')} ──")

        for r in reminders:
            date = sprint_begin + timedelta(days=r["day_offset"])
            date_str = date.strftime("%Y-%m-%d")
            day_name = WEEKDAYS_RU[date.weekday()]
            status = ""

            if date_str in overrides:
                ov = overrides[date_str]
                if ov["action"] == "skip":
                    status = f"  ❌ ПРОПУСК ({ov.get('reason', '')})"
                elif ov["action"] == "move":
                    status = f"  ➡️  ПЕРЕНОС на {ov['new_date']} ({ov.get('reason', '')})"

            print(f"  {r['id']:14s} | {date.strftime('%d.%m')} {day_name} | {r['label']}{status}")

        print()

    # Показываем все переносы отдельно
    if move_targets:
        print("── Переносы (целевые даты) ──")
        for new_date, ov in sorted(move_targets.items()):
            d = datetime.strptime(new_date, "%Y-%m-%d")
            day_name = WEEKDAYS_RU[d.weekday()]
            print(f"  {new_date} {day_name} ← перенос с {ov['original_date']} ({ov.get('reason', '')})")
        print()


if __name__ == "__main__":
    main()
