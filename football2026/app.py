"""
Football Matches — одноfайловое приложение.

Отображает матчи 3 туров (предыдущий / текущий / следующий) по 4 лигам:
АПЛ (PL), Ла Лига (PD), Серия А (SA), Лига Чемпионов (CL).

Только для команд из WATCHED_TEAMS.
Данные: football-data.org API v4 → SQLite (4 запроса на обновление).
"""

import json
import os
import sqlite3
import threading
import tkinter as tk
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from tkinter import messagebox, ttk

import requests

# ── константы ─────────────────────────────────────────────────────────────────

API_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "2b7ff41203e64cde9d052df106d48e51")
BASE_URL = "https://api.football-data.org/v4"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matches.db")

# Лиги: код API → русский ярлык
COMPETITIONS = {
    "PL": "АПЛ",
    "PD": "Ла Лига",
    "SA": "Серия А",
    "CL": "ЛЧ",
}

# Подстроки для фильтрации (поиск case-insensitive)
WATCHED_TEAMS = [
    "Barcelona",
    "Real Madrid",
    "Chelsea",
    "Manchester City",
]

# ── база данных ───────────────────────────────────────────────────────────────

def init_db():
    """
    Инициализирует БД. Если обнаружена старая схема (без competition_code),
    пересоздаёт таблицы.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        # Миграция: проверяем наличие нужных столбцов
        cols = {row[1] for row in conn.execute("PRAGMA table_info(matches)").fetchall()}
        if cols and "competition_code" not in cols:
            conn.execute("DROP TABLE IF EXISTS matches")
            conn.execute("DROP TABLE IF EXISTS competitions")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS competitions (
                code         TEXT PRIMARY KEY,   -- 'PL', 'PD', 'SA', 'CL'
                name         TEXT,
                current_matchday INTEGER,
                updated_at   TEXT               -- ISO UTC datetime
            );

            CREATE TABLE IF NOT EXISTS matches (
                id              INTEGER PRIMARY KEY,  -- ID из API
                competition_code TEXT,
                matchday        INTEGER,
                home_team       TEXT,
                away_team       TEXT,
                home_team_id    INTEGER,
                away_team_id    INTEGER,
                status          TEXT,
                utc_date        TEXT,
                home_score      INTEGER,
                away_score      INTEGER,
                raw_json        TEXT,
                FOREIGN KEY (competition_code) REFERENCES competitions(code)
            );

            CREATE INDEX IF NOT EXISTS idx_matches_comp_md
                ON matches(competition_code, matchday);
            """
        )
        conn.commit()
    finally:
        conn.close()


# ── API ───────────────────────────────────────────────────────────────────────

def detect_current_matchday(matches: list) -> int | None:
    """
    Определяет номер текущего тура из свежих данных API.
    Вызывается только при fetch, когда API не вернул currentMatchday.

    Приоритет:
    1. Самый ранний SCHEDULED/TIMED тур (= тур который ещё не прошёл)
    2. Последний FINISHED тур
    """
    upcoming = [(m["utcDate"], m["matchday"]) for m in matches
                if m.get("status") in ("SCHEDULED", "TIMED")
                and m.get("matchday") and m.get("utcDate")]
    if upcoming:
        upcoming.sort()
        return upcoming[0][1]

    finished = [m["matchday"] for m in matches
                if m.get("status") == "FINISHED" and m.get("matchday")]
    if finished:
        return max(finished)

    return None


_KV = ZoneInfo("Europe/Kiev")


def infer_current_matchday_from_cache(conn: sqlite3.Connection, code: str) -> int | None:
    """
    Определяет «текущий» тур локально по датам матчей в кэше — без обращения к API.

    Логика: находим тур, чьи матчи ближайшие к «сейчас» (по utc_date).
    Конкретно: ищем тур, у которого минимальное абсолютное расстояние
    от середины окна матчей до текущего момента.
    """
    rows = conn.execute(
        """
        SELECT matchday, MIN(utc_date), MAX(utc_date)
        FROM matches
        WHERE competition_code = ? AND matchday IS NOT NULL AND utc_date IS NOT NULL
        GROUP BY matchday
        ORDER BY matchday
        """,
        (code,),
    ).fetchall()

    if not rows:
        return None

    now = datetime.now(timezone.utc)

    best_md = None
    best_dist = None

    for matchday, min_date, max_date in rows:
        try:
            dt_min = datetime.fromisoformat(min_date.replace("Z", "+00:00"))
            dt_max = datetime.fromisoformat(max_date.replace("Z", "+00:00"))
        except Exception:
            continue

        # Считаем середину окна тура
        midpoint = dt_min + (dt_max - dt_min) / 2
        dist = abs((now - midpoint).total_seconds())

        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_md = matchday

    return best_md


def fetch_all_leagues(status_callback=None) -> dict:
    """
    Загружает все матчи текущего сезона для каждой лиги из COMPETITIONS.
    Всего 4 HTTP-запроса.

    Возвращает:
        {
          "PL": {"name": str, "current_matchday": int|None, "matches": [...]},
          ...
        }
    """
    headers = {"X-Auth-Token": API_TOKEN}
    result = {}

    for i, (code, label) in enumerate(COMPETITIONS.items()):
        if status_callback:
            status_callback(f"Загрузка {label}… ({i + 1}/{len(COMPETITIONS)})")

        url = f"{BASE_URL}/competitions/{code}/matches"
        resp = requests.get(url, headers=headers, timeout=20)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Ошибка запроса [{code}]: HTTP {resp.status_code}\n{resp.text[:300]}"
            )

        data = resp.json()
        competition_obj = data.get("competition", {})
        current_season = competition_obj.get("currentSeason", {})
        current_matchday = current_season.get("currentMatchday")

        matches = data.get("matches", [])

        # Fallback: вычислить тур из самих матчей
        if current_matchday is None:
            current_matchday = detect_current_matchday(matches)

        result[code] = {
            "name": competition_obj.get("name", label),
            "current_matchday": current_matchday,
            "matches": matches,
        }

    return result


# ── сохранение в БД ───────────────────────────────────────────────────────────

def save_to_db(league_data: dict) -> None:
    """
    Сохраняет данные всех лиг в SQLite.
    Использует UPSERT (INSERT OR REPLACE / ON CONFLICT DO UPDATE), не удаляет старые матчи.
    """
    conn = sqlite3.connect(DB_PATH)
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        for code, data in league_data.items():
            # ── соревнование ──────────────────────────────────────────────────
            conn.execute(
                """
                INSERT INTO competitions (code, name, current_matchday, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name             = excluded.name,
                    current_matchday = excluded.current_matchday,
                    updated_at       = excluded.updated_at
                """,
                (code, data["name"], data["current_matchday"], now_iso),
            )

            # ── матчи (UPSERT по id) ──────────────────────────────────────────
            for match in data["matches"]:
                ft = match.get("score", {}).get("fullTime", {})
                conn.execute(
                    """
                    INSERT INTO matches (
                        id, competition_code, matchday,
                        home_team, away_team, home_team_id, away_team_id,
                        status, utc_date, home_score, away_score, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        status     = excluded.status,
                        home_score = excluded.home_score,
                        away_score = excluded.away_score,
                        raw_json   = excluded.raw_json
                    """,
                    (
                        match.get("id"),
                        code,
                        match.get("matchday"),
                        match.get("homeTeam", {}).get("name", ""),
                        match.get("awayTeam", {}).get("name", ""),
                        match.get("homeTeam", {}).get("id"),
                        match.get("awayTeam", {}).get("id"),
                        match.get("status", ""),
                        match.get("utcDate", ""),
                        ft.get("home"),
                        ft.get("away"),
                        json.dumps(match, ensure_ascii=False),
                    ),
                )

        conn.commit()
    finally:
        conn.close()


# ── чтение из БД для отображения ──────────────────────────────────────────────

def _is_watched(home: str, away: str) -> bool:
    """True, если хотя бы одна из команд есть в WATCHED_TEAMS."""
    combined = (home + " " + away).lower()
    return any(t.lower() in combined for t in WATCHED_TEAMS)


def _matches_for_round(conn: sqlite3.Connection, code: str, matchday: int) -> list:
    rows = conn.execute(
        """
        SELECT competition_code, matchday, home_team, away_team,
               status, utc_date, home_score, away_score
        FROM matches
        WHERE competition_code = ? AND matchday = ?
        ORDER BY utc_date ASC
        """,
        (code, matchday),
    ).fetchall()
    return [r for r in rows if _is_watched(r[2], r[3])]


def get_display_data() -> dict:
    """
    Возвращает матчи для трёх секций и мета-информацию:
        {
          "prev": [...], "current": [...], "next": [...],
          "updated_at": str|None,   # ISO UTC datetime последнего обновления
          "stale_hours": float|None # сколько часов с момента обновления
        }

    Текущий тур определяется локально по датам матчей в кэше —
    не зависит от сохранённого current_matchday и всегда актуален.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        comp_rows = conn.execute(
            "SELECT code, updated_at FROM competitions"
        ).fetchall()

        result: dict = {"prev": [], "current": [], "next": [],
                        "updated_at": None, "stale_hours": None}

        # Дата последнего обновления (берём самую свежую среди лиг)
        update_times = [r[1] for r in comp_rows if r[1]]
        if update_times:
            latest_update = max(update_times)
            result["updated_at"] = latest_update
            try:
                dt_upd = datetime.fromisoformat(latest_update)
                result["stale_hours"] = (
                    datetime.now(timezone.utc) - dt_upd
                ).total_seconds() / 3600
            except Exception:
                pass

        for code, _updated_at in comp_rows:
            # Локально определяем текущий тур по датам матчей
            current_md = infer_current_matchday_from_cache(conn, code)
            if current_md is None:
                continue
            for section, delta in (("prev", -1), ("current", 0), ("next", 1)):
                md = current_md + delta
                if md >= 1:
                    result[section].extend(_matches_for_round(conn, code, md))

        # Сортировка внутри каждой секции по дате
        for section in ("prev", "current", "next"):
            result[section].sort(key=lambda r: r[5])  # utc_date

        return result
    finally:
        conn.close()


# ── вспомогательные функции ────────────────────────────────────────────────────

def fmt_score(home_score, away_score) -> str:
    if home_score is not None and away_score is not None:
        return f"{home_score} : {away_score}"
    return "—"


def fmt_date(utc_date: str) -> str:
    """Конвертирует ISO UTC → киевское время (Europe/Kiev, с учётом DST)."""
    try:
        dt_utc = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
        dt_kv = dt_utc.astimezone(_KV)
        return dt_kv.strftime("%d.%m %H:%M")
    except Exception:
        return utc_date[:16] if utc_date else "—"


STATUS_RU = {
    "SCHEDULED": "Запланирован",
    "TIMED":     "Запланирован",
    "IN_PLAY":   "🔴 LIVE",
    "PAUSED":    "🔴 Перерыв",
    "FINISHED":  "Завершён",
    "POSTPONED": "Перенесён",
    "SUSPENDED": "Приостановлен",
    "CANCELLED": "Отменён",
}


def get_match_video_url(comp_code: str, home_team: str, away_team: str, status: str) -> str | None:
    """
    Формирует ссылку на YouTube-обзор для завершённых матчей:
    - АПЛ (PL): канал Setanta Sports Premier League
    - Испания (PD): поиск 'megogo {home} — {away}' на YouTube
    - Остальные турниры (SA, CL): поиск 'megogo {home} — {away}' на YouTube
    """
    if status != "FINISHED":
        return None

    if comp_code == "PL":
        return "https://www.youtube.com/@SetantaSportsPremierLeague/videos"
    elif comp_code == "PD":
        query = f"megogo {home_team} — {away_team}"
        return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
    elif comp_code in ("SA", "CL"):
        query = f"megogo {home_team} — {away_team}"
        return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
    else:
        query = f"обзор {home_team} — {away_team}"
        return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"


# ── UI ─────────────────────────────────────────────────────────────────────────

COLUMNS = ("competition", "home_team", "score", "away_team", "date", "status")
COL_CFG = {
    "competition": ("Лига",       72,  "center", False),
    "home_team":   ("Хозяева",   165,  "e",      True),
    "score":       ("Счёт",       64,  "center", False),
    "away_team":   ("Гости",     165,  "w",      True),
    "date":        ("Киев",       88,  "center", False),
    "status":      ("Статус",    108,  "center", False),
}


class RoundFrame(ttk.LabelFrame):
    """Одна секция (тур) — заголовок + таблица матчей."""

    def __init__(self, parent, title: str, **kw):
        super().__init__(parent, text=f"  {title}  ", padding=(6, 4), **kw)
        self.item_urls = {}

        self.tree = ttk.Treeview(self, columns=COLUMNS, show="headings", height=5)
        for col, (heading, width, anchor, stretch) in COL_CFG.items():
            self.tree.heading(col, text=heading)
            self.tree.column(col, anchor=anchor, width=width, minwidth=40, stretch=stretch)

        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        # Теги по статусу
        self.tree.tag_configure("finished",  foreground="#1a5fb4")
        self.tree.tag_configure("live",      foreground="#00aa44", font=("", 9, "bold"))
        self.tree.tag_configure("scheduled", foreground="#1a1a1a")
        self.tree.tag_configure("other",     foreground="#cc7700")

        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Интерактивность: курсор "рука" при наведении и открытие видео при клике
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_activate)
        self.tree.bind("<Return>", self._on_activate)

    def _on_motion(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id in self.item_urls:
            self.tree.config(cursor="hand2")
        else:
            self.tree.config(cursor="")

    def _on_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id in self.item_urls:
            url = self.item_urls[item_id]
            webbrowser.open(url)

    def _on_activate(self, event=None):
        selection = self.tree.selection()
        if selection:
            item_id = selection[0]
            url = self.item_urls.get(item_id)
            if url:
                webbrowser.open(url)

    def populate(self, rows: list) -> None:
        self.item_urls.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in rows:
            comp_code, _md, home, away, status, utc_date, hs, aws = row

            tag = (
                "live"      if status in ("IN_PLAY", "PAUSED")  else
                "finished"  if status == "FINISHED"              else
                "scheduled" if status in ("SCHEDULED", "TIMED")  else
                "other"
            )

            status_text = STATUS_RU.get(status, status)
            if status == "FINISHED":
                status_text += " ↗"

            item_id = self.tree.insert(
                "", tk.END,
                values=(
                    COMPETITIONS.get(comp_code, comp_code),
                    home,
                    fmt_score(hs, aws),
                    away,
                    fmt_date(utc_date),
                    status_text,
                ),
                tags=(tag,),
            )

            url = get_match_video_url(comp_code, home, away, status)
            if url:
                self.item_urls[item_id] = url


class FootballApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Football Matches")
        self.geometry("1020x680")
        self.minsize(820, 500)
        self.refresh_in_progress = False

        self._build_ui()
        self.load_display()

    def _build_ui(self):
        # ── верхняя панель ────────────────────────────────────────────────────
        top = ttk.Frame(self, padding=(10, 8, 10, 4))
        top.pack(fill="x")

        self.refresh_btn = ttk.Button(
            top, text="⟳  Обновить", command=self.start_refresh, width=14
        )
        self.refresh_btn.pack(side="left")

        self.status_var = tk.StringVar(value="Загрузка…")
        ttk.Label(top, textvariable=self.status_var, foreground="#555555").pack(
            side="left", padx=12
        )

        ttk.Label(
            top,
            text="💡 Клик по завершённому матчу (↗) открывает видео на YouTube",
            foreground="#666666"
        ).pack(side="left", padx=10)

        teams_label = " · ".join(WATCHED_TEAMS)
        ttk.Label(top, text=f"Команды: {teams_label}", foreground="#888888").pack(
            side="right"
        )

        # ── три секции туров (разделитель) ────────────────────────────────────
        pane = ttk.PanedWindow(self, orient="vertical")
        pane.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self.prev_frame = RoundFrame(pane, "◀  Предыдущий тур")
        self.curr_frame = RoundFrame(pane, "●  Текущий тур")
        self.next_frame = RoundFrame(pane, "▶  Следующий тур")

        pane.add(self.prev_frame, weight=1)
        pane.add(self.curr_frame, weight=1)
        pane.add(self.next_frame, weight=1)

    def load_display(self) -> None:
        try:
            data = get_display_data()
        except Exception as exc:
            self.status_var.set(f"Ошибка чтения БД: {exc}")
            return

        self.prev_frame.populate(data["prev"])
        self.curr_frame.populate(data["current"])
        self.next_frame.populate(data["next"])

        total = len(data["prev"]) + len(data["current"]) + len(data["next"])
        if total:
            status = (
                f"Показано {total} матчей  "
                f"(пред.: {len(data['prev'])}, "
                f"тек.: {len(data['current'])}, "
                f"след.: {len(data['next'])})"
            )
            # Предупреждение об устаревших данных
            stale = data.get("stale_hours")
            if stale is not None:
                if stale >= 24:
                    days = int(stale // 24)
                    status += f"  ⚠ данные {days} д. назад"
                elif stale >= 2:
                    status += f"  ⚠ данные {int(stale)} ч. назад"
            self.status_var.set(status)
        else:
            self.status_var.set("В БД нет данных — нажмите «Обновить»")

    def start_refresh(self) -> None:
        if self.refresh_in_progress:
            return
        self.refresh_in_progress = True
        self.refresh_btn.config(state="disabled")
        self.status_var.set("Загрузка данных из API…")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            league_data = fetch_all_leagues(
                status_callback=lambda msg: self.after(
                    0, lambda m=msg: self.status_var.set(m)
                )
            )
            save_to_db(league_data)
            self.after(0, self.load_display)
        except Exception as exc:
            self.after(0, lambda: self.status_var.set("Ошибка обновления"))
            self.after(0, lambda: messagebox.showerror("Ошибка обновления", str(exc)))
        finally:
            self.after(0, lambda: self.refresh_btn.config(state="normal"))
            self.after(0, lambda: setattr(self, "refresh_in_progress", False))


# ── точка входа ───────────────────────────────────────────────────────────────

def main():
    init_db()
    app = FootballApp()
    app.mainloop()


if __name__ == "__main__":
    main()