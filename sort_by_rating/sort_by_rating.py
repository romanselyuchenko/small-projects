"""Сбор каталога с безопасным долгим запуском.

Данные сохраняются после каждой страницы в SQLite. Скрипт можно прервать
Ctrl+C и запустить снова: обработанные тайтлы пропустятся.

Примеры:
  python sort_by_rating.py --clean
  python sort_by_rating.py --max-pages 10 --workers 3
  python sort_by_rating.py --retry-failed
  python sort_by_rating.py --refresh --max-pages 2
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import requests
from lxml import html as lxml_html

BASE = "https://demonicscans.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RatingSorter/2.0)"}
RATING_XPATH = "/html/body/div[3]/div[2]/div[2]/li[1]"
FIELDS = ["title", "rating", "chapters", "description", "url"]


class RateLimiter:
    """Общий лимит запросов: потоки не перегружают сайт."""
    def __init__(self, delay):
        self.delay, self.lock, self.next_at = max(0, delay), threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            sleep_for = self.next_at - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            self.next_at = time.monotonic() + self.delay


def arguments():
    parser = argparse.ArgumentParser(description="Собрать каталог и отсортировать по рейтингу.")
    parser.add_argument("--min-chapters", type=int, default=30)
    parser.add_argument("--max-pages", type=int, help="страниц каталога; по умолчанию — все")
    parser.add_argument("--workers", type=int, default=4, help="одновременных загрузок; по умолчанию 4")
    parser.add_argument("--delay", type=float, default=.25, help="минимальная пауза между запросами, сек.")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--progress-every", type=int, default=10,
                        help="выводить прогресс через столько страниц; по умолчанию 10")
    parser.add_argument("--db", type=Path, default=Path("ratings.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("ratings.csv"))
    parser.add_argument("--retry-failed", action="store_true", help="повторить страницы с ошибками")
    parser.add_argument("--refresh", action="store_true", help="перезагрузить все найденные тайтлы")
    parser.add_argument("--clean", action="store_true", help="очистить базу данных и начать сбор с чистого листа")
    return parser.parse_args()


def database(path, clean=False):
    conn = sqlite3.connect(path)
    if clean:
        conn.execute("DROP TABLE IF EXISTS manga")
        conn.commit()
    conn.execute("""CREATE TABLE IF NOT EXISTS manga (
        path TEXT PRIMARY KEY, title TEXT NOT NULL, rating REAL, chapters INTEGER,
        description TEXT, status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0, error TEXT, updated_at TEXT)""")
    conn.commit()
    return conn


def fetch(url, limiter, retries):
    last_error = "unknown error"
    for attempt in range(1, retries + 1):
        try:
            limiter.wait()
            response = requests.get(url, headers=HEADERS, timeout=(10, 35))
            if response.status_code == 200:
                return response.text
            last_error = f"HTTP {response.status_code}"
            if 400 <= response.status_code < 500 and response.status_code != 429:
                break
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(min(20, 2 ** (attempt - 1)))
    raise RuntimeError(last_error)


def collect_links(conn, limiter, args):
    page = 1
    while args.max_pages is None or page <= args.max_pages:
        url = f"{BASE}/advanced.php" if page == 1 else f"{BASE}/advanced.php?list={page}"
        try:
            tree = lxml_html.fromstring(fetch(url, limiter, args.retries))
        except (RuntimeError, ValueError) as exc:
            print(f"Каталог, страница {page}: {exc}. Останавливаюсь.")
            return
        rows = []
        for link in tree.xpath("//a[starts-with(@href, '/manga/')]"):
            path, title = link.get("href"), (link.get("title") or link.text_content() or "").strip()
            if path and title:
                rows.append((path, title))
        if not rows:
            print(f"Каталог, страница {page}: ссылок нет — конец каталога.")
            return
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO manga(path, title) VALUES (?, ?)", rows)
        conn.commit()
        print(f"Каталог, страница {page}: {len(rows)} ссылок, новых в кэше: {conn.total_changes - before}")
        page += 1


def number(text):
    match = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(match.group().replace(",", ".")) if match else None


def rating(tree):
    elements = tree.xpath(RATING_XPATH)
    if elements:
        value = number(elements[0].text_content())
        if value is not None and 0 <= value <= 10:
            return value
    for element in tree.xpath("//*[normalize-space(text())='Rate']"):
        parent = element.getparent()
        if parent is not None and parent.getparent() is not None:
            for sibling in parent.getparent().findall("li"):
                value = number(sibling.text_content())
                if value is not None and 0 <= value <= 10:
                    return value
    return None


def description(tree):
    nodes = tree.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' white-font ')]")
    text = " ".join(nodes[0].text_content().split()) if nodes else ""
    return text.split("The Summary is ", 1)[-1].strip() if "The Summary is " in text else text


def process(path, limiter, retries):
    tree = lxml_html.fromstring(fetch(urljoin(BASE, path), limiter, retries))
    found = re.search(r"(\d+)\s+Chapters?\s+Available", tree.text_content(), re.I)
    return rating(tree), int(found.group(1)) if found else None, description(tree)


def worklist(conn, args):
    if args.refresh:
        conn.execute("UPDATE manga SET status='pending', error=NULL")
        conn.commit()
        query = "SELECT path FROM manga"
    elif args.retry_failed:
        query = "SELECT path FROM manga WHERE status='error'"
    else:
        query = "SELECT path FROM manga WHERE status='pending'"
    return [row[0] for row in conn.execute(query + " ORDER BY path")]


def process_all(conn, limiter, args):
    paths = worklist(conn, args)
    if not paths:
        print("Новых страниц для обработки нет.")
        return
    print(f"Нужно обработать: {len(paths)}. Ctrl+C безопасен: готовые страницы сразу в кэше.")
    completed = errors = 0
    started_at = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(process, path, limiter, args.retries): path for path in paths}
        try:
            for future in as_completed(futures):
                path = futures[future]
                try:
                    result = future.result()
                    conn.execute("""UPDATE manga SET rating=?, chapters=?, description=?, status='done',
                        attempts=attempts+1, error=NULL, updated_at=CURRENT_TIMESTAMP WHERE path=?""", (*result, path))
                except Exception as exc:
                    errors += 1
                    conn.execute("""UPDATE manga SET status='error', attempts=attempts+1, error=?,
                        updated_at=CURRENT_TIMESTAMP WHERE path=?""", (str(exc)[:500], path))
                conn.commit()
                completed += 1
                if completed % args.progress_every == 0 or completed == len(paths):
                    elapsed = time.monotonic() - started_at
                    speed = completed / elapsed if elapsed else 0
                    remaining = (len(paths) - completed) / speed if speed else 0
                    print(
                        f"Прогресс: {completed}/{len(paths)} "
                        f"({completed / len(paths):.0%}); ошибок: {errors}; "
                        f"скорость: {speed:.2f} стр./с; осталось: {format_duration(remaining)}"
                    )
        except KeyboardInterrupt:
            print("\nОстановлено. Завершённые страницы сохранены; запустите скрипт ещё раз.")
            raise


def format_duration(seconds):
    """Короткое отображение ожидаемого оставшегося времени."""
    seconds = max(0, round(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"~{hours} ч {minutes} мин"
    if minutes:
        return f"~{minutes} мин {seconds} с"
    return f"~{seconds} с"


def export(conn, output, min_chapters):
    rows = conn.execute("""SELECT title, rating, chapters, description, path FROM manga
        WHERE status='done' AND chapters >= ?
        ORDER BY rating IS NULL, rating DESC, title COLLATE NOCASE""", (min_chapters,))
    count = 0
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, delimiter=";")
        writer.writeheader()
        for title, value, chapters, text, path in rows:
            writer.writerow(dict(zip(FIELDS, (title, value, chapters, text or "", urljoin(BASE, path)))))
            count += 1
    return count


def main():
    args = arguments()
    if args.max_pages is not None and args.max_pages < 1:
        raise SystemExit("--max-pages должен быть не меньше 1")
    if args.min_chapters < 0 or args.retries < 1 or args.progress_every < 1:
        raise SystemExit("--min-chapters должен быть >= 0, --retries и --progress-every — >= 1")
    conn = database(args.db, clean=args.clean)
    try:
        print("Собираю ссылки каталога...")
        collect_links(conn, RateLimiter(args.delay), args)
        process_all(conn, RateLimiter(args.delay), args)
        written = export(conn, args.output, args.min_chapters)
        failed = conn.execute("SELECT COUNT(*) FROM manga WHERE status='error'").fetchone()[0]
        print(f"Готово: {args.output}; тайтлов в CSV: {written}.")
        print(f"Кэш: {args.db}; страниц с ошибками: {failed} (повторите с --retry-failed).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
