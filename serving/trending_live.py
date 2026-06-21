"""
trending_live.py — SPEED LAYER gọn nhẹ cho bản web deploy (Render/free).
========================================================================
Phiên bản "tất-cả-trong-một-tiến-trình" của tầng tốc độ: đọc thẳng luồng
**Wikimedia EventStreams** (SSE live) trong một luồng nền, khớp tên phim và
giữ danh sách "thịnh hành real-time" trong RAM — KHÔNG cần Kafka + HBase.

Dùng cho bản web nhẹ (Flask + SQLite) khi deploy public: vẫn có mục
" Thịnh hành real-time" sống thật từ Wikipedia, đúng điểm nhấn Big Data.

Logic giữ y hệt stream/consumer.py + ingestion/wiki_stream_producer.py, chỉ
gộp lại: SSE -> lọc -> khớp tên (từ bảng movies trong SQLite) -> cửa sổ trượt.

Bật bằng biến môi trường ENABLE_LIVE_TRENDING=1 (xem render.yaml).
"""
import os
import re
import json
import time
import threading
import urllib.request
from collections import deque, defaultdict

from sqlalchemy import create_engine, text

STREAM_URL = os.environ.get(
    "WIKI_STREAM_URL", "https://stream.wikimedia.org/v2/stream/recentchange")
WIKI = os.environ.get("WIKI_FILTER", "enwiki")
TREND_WINDOW = int(os.environ.get("TREND_WINDOW_SEC", "21600"))   # 6 giờ
TREND_TOP_N = int(os.environ.get("TREND_TOP_N", "40"))

_ARTICLE_RE = re.compile(r"^(.*),\s+(The|A|An|La|Le|Les|Il|El|Die|Das|Der|Une|Un)$", re.I)

# Trạng thái dùng chung giữa luồng nền và web request
_events = deque()                 # (timestamp, movie_id, title)
_lock = threading.Lock()
_index = {}                       # canonical title -> (movie_id, full_title)
_started = False
_stats = {"seen": 0, "matched": 0, "started_at": None, "error": None}


#  Chuẩn hoá tên phim #
def _canon(title: str) -> str:
    """Bỏ năm, đảo ', The' -> 'The ', lowercase, bỏ dấu câu."""
    t = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    m = _ARTICLE_RE.match(t)
    if m:
        t = f"{m.group(2)} {m.group(1)}"
    t = t.lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _canon_wiki(title: str) -> str:
    """Tiêu đề Wikipedia: bỏ hậu tố '(film)' / '(2010 film)' rồi chuẩn hoá."""
    t = re.sub(r"\s*\((?:\d{4} )?(?:American |British )?film\)\s*$", "", title, flags=re.I)
    return _canon(t)


def _build_index(db_url):
    """canonical title -> (movie_id, title) lấy từ bảng movies trong SQLite/MySQL."""
    engine = create_engine(db_url, pool_pre_ping=True)
    index = {}
    with engine.connect() as conn:
        for r in conn.execute(text("SELECT movie_id, title FROM movies")):
            key = _canon(r[1] or "")
            if not key:
                continue
            mid = int(r[0])
            if key not in index or mid < index[key][0]:
                index[key] = (mid, r[1])
    engine.dispose()
    return index


# Đọc luồng SSE  #
_USER_AGENT = ("MovieRec/1.0 (https://github.com/tuaanh666/BIGDATA; "
               "movie-recsys demo) Python-urllib")


def _iter_stream(url):
    # User-Agent mô tả rõ + Accept SSE: Wikimedia yêu cầu UA đúng chuẩn, nếu không
    # (đặc biệt từ IP trung tâm dữ liệu như Render) có thể bị chặn/treo kết nối.
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "text/event-stream",
    })
    resp = urllib.request.urlopen(req, timeout=20)
    for raw in resp:
        line = raw.decode("utf-8", "ignore").strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue


def _record(movie_id, title):
    """Thêm 1 sự kiện vào cửa sổ trượt, dọn các mục đã hết hạn."""
    now = int(time.time())
    with _lock:
        _events.append((now, movie_id, title))
        while _events and now - _events[0][0] > TREND_WINDOW:
            _events.popleft()
        _stats["matched"] += 1


def _run(db_url):
    global _index
    # Đánh dấu thread đã chạy NGAY (để debug biết thread có khởi động không)
    _stats["started_at"] = int(time.time())
    while True:
        try:
            if not _index:
                _index = _build_index(db_url)
                _stats["error"] = None
                print(f"[trending_live] Nạp {len(_index):,} tên phim. Lắng nghe Wikimedia ({WIKI})...")
            for ev in _iter_stream(STREAM_URL):
                _stats["seen"] += 1
                if ev.get("wiki") != WIKI or ev.get("namespace") != 0:
                    continue
                if ev.get("type") not in ("edit", "new"):
                    continue
                hit = _index.get(_canon_wiki(ev.get("title", "")))
                if hit:
                    _record(hit[0], hit[1])
        except Exception as e:
            _stats["error"] = repr(e)
            print(f"[trending_live] Lỗi ({e!r}); thử lại sau 5s...")
            time.sleep(5)


#  API cho app.py  #
def start(db_url):
    """Khởi động luồng nền (idempotent). Gọi 1 lần khi app khởi động."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_run, args=(db_url,), daemon=True)
    t.start()


def top(limit=12):
    """Trả Top phim thịnh hành hiện tại: [{movie_id, title, score}]."""
    with _lock:
        snapshot = list(_events)
    counts = defaultdict(float)
    titles = {}
    for _, mid, title in snapshot:
        counts[mid] += 1.0
        titles[mid] = title
    ranked = sorted(counts.items(), key=lambda x: -x[1])[:max(limit, TREND_TOP_N)]
    return [{"movie_id": mid, "title": titles[mid], "score": round(sc, 2)}
            for mid, sc in ranked[:limit]]


def info():
    return dict(_stats, window_sec=TREND_WINDOW, in_window=len(_events))
