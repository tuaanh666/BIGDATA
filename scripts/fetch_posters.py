"""
fetch_posters.py — Lấy poster phim THẬT từ TMDB và lưu vào DB (cột movies.poster_url).
=====================================================================================
MovieLens cung cấp `links.csv` (movieId -> tmdbId). Script dùng tmdbId gọi TMDB API
lấy `poster_path`, ghép thành URL ảnh trên CDN TMDB rồi UPDATE vào bảng `movies`.

Web (serving/app.py) đọc cột này và hiển thị poster; phim nào thiếu ảnh sẽ tự rơi về
placeholder emoji.

Cách dùng (chạy trên HOST, kết nối MySQL trong Docker đang mở cổng 3306):

    set TMDB_API_KEY=xxxxxxxx                  # PowerShell: $env:TMDB_API_KEY="xxxx"
    python scripts/fetch_posters.py            # mặc định: MySQL localhost:3306

Tham số (qua env hoặc CLI):
    TMDB_API_KEY   : API key TMDB (bắt buộc)
    DB_URL         : SQLAlchemy URL (mặc định mysql+pymysql://mluser:mlpassword@localhost:3306/movielens)
    LINKS_CSV      : đường dẫn links.csv (mặc định data/ml-25m/links.csv)
    --limit N      : lấy thêm poster cho N phim nhiều lượt đánh giá nhất (mặc định 3000)
    --workers N    : số luồng tải song song (mặc định 12)
    --size S       : kích cỡ ảnh TMDB: w185 / w342 / w500 (mặc định w342)
    --force        : tải lại cả phim đã có poster_url
"""
import os
import csv
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import create_engine, text, inspect

DEFAULT_DB = "mysql+pymysql://mluser:mlpassword@localhost:3306/movielens"
TMDB_API = "https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={key}"
TMDB_IMG = "https://image.tmdb.org/t/p/{size}{path}"


# --------------------------------------------------------------------------- #
def ensure_poster_column(engine):
    """Thêm cột poster_url vào bảng movies nếu chưa có (MySQL & SQLite đều chạy)."""
    cols = [c["name"] for c in inspect(engine).get_columns("movies")]
    if "poster_url" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE movies ADD COLUMN poster_url VARCHAR(255)"))
        print("[OK] Đã thêm cột movies.poster_url")
    else:
        print("[..] Cột movies.poster_url đã tồn tại")


def load_links(path):
    """links.csv -> dict movieId -> tmdbId."""
    mapping = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tmdb = row.get("tmdbId", "").strip()
            if tmdb:
                mapping[int(row["movieId"])] = tmdb
    print(f"[OK] Nạp {len(mapping):,} ánh xạ movieId->tmdbId từ links.csv")
    return mapping


def target_movies(engine, limit):
    """Tập phim cần poster: phim được gợi ý + phim phổ biến + top theo lượt đánh giá."""
    need = set()
    with engine.connect() as conn:
        for r in conn.execute(text("SELECT DISTINCT movie_id FROM user_recommendations")):
            need.add(r[0])
        for r in conn.execute(text("SELECT movie_id FROM popular_movies")):
            need.add(r[0])
        if limit > 0:
            q = text("SELECT movie_id FROM movies ORDER BY num_ratings DESC LIMIT :n")
            for r in conn.execute(q, {"n": limit}):
                need.add(r[0])
    return need


def already_have(engine):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT movie_id FROM movies WHERE poster_url IS NOT NULL AND poster_url <> ''"))
        return {r[0] for r in rows}


# --------------------------------------------------------------------------- #
def fetch_one(movie_id, tmdb_id, key, size, retries=3):
    """Trả (movie_id, poster_url|None). Raise nếu key sai (401) để dừng sớm."""
    url = TMDB_API.format(tmdb_id=tmdb_id, key=key)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "movielens-recsys"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            path = data.get("poster_path")
            if path:
                return movie_id, TMDB_IMG.format(size=size, path=path)
            return movie_id, None
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError("TMDB API key không hợp lệ (401). Kiểm tra TMDB_API_KEY.")
            if e.code == 404:
                return movie_id, None
            if e.code == 429:  # rate limit
                wait = int(e.headers.get("Retry-After", "1")) + 1
                time.sleep(wait)
                continue
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    return movie_id, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DB_URL", DEFAULT_DB))
    ap.add_argument("--links", default=os.environ.get(
        "LINKS_CSV", os.path.join("data", "ml-25m", "links.csv")))
    ap.add_argument("--api-key", default=os.environ.get("TMDB_API_KEY", ""))
    ap.add_argument("--limit", type=int, default=int(os.environ.get("POSTER_LIMIT", "3000")))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--size", default="w342")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("[!!] Thiếu TMDB API key. Đặt biến môi trường TMDB_API_KEY hoặc dùng --api-key.")
    if not os.path.exists(args.links):
        sys.exit(f"[!!] Không thấy links.csv tại {args.links}")

    engine = create_engine(args.db_url, pool_pre_ping=True)
    print(f"[..] DB: {args.db_url.split('://')[0]} | links: {args.links}")
    ensure_poster_column(engine)

    links = load_links(args.links)
    need = target_movies(engine, args.limit)
    have = set() if args.force else already_have(engine)
    todo = [m for m in need if m in links and m not in have]
    print(f"[..] Cần poster: {len(need):,} phim | đã có: {len(have):,} | sẽ tải: {len(todo):,}")

    if not todo:
        print("[OK] Không có gì để tải. Xong.")
        return

    results, done, found = [], 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, m, links[m], args.api_key, args.size): m for m in todo}
        for fut in as_completed(futs):
            mid, url = fut.result()
            done += 1
            if url:
                results.append({"u": url, "m": mid})
                found += 1
            if done % 200 == 0 or done == len(todo):
                print(f"  -> {done:,}/{len(todo):,} (có ảnh: {found:,})")
            # ghi theo lô để an toàn
            if len(results) >= 500:
                _flush(engine, results); results = []
    _flush(engine, results)
    print(f"[OK] Hoàn tất: cập nhật poster cho {found:,}/{len(todo):,} phim.")


def _flush(engine, rows):
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(text("UPDATE movies SET poster_url=:u WHERE movie_id=:m"), rows)


if __name__ == "__main__":
    main()
