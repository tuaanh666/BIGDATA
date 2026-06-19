"""
consumer.py — STREAM LAYER
===========================
Đọc luồng "rating mới" từ Kafka, cập nhật hồ sơ user theo thời gian thực và
ghi gợi ý nhanh vào HBase (Real-time View của Lambda Architecture).

Logic real-time (nhẹ, độ trễ thấp):
  - Với mỗi rating mới của user, ta cập nhật danh sách thể loại (genre) ưa thích.
  - Sinh gợi ý "tức thời" = các phim cùng thể loại ưa thích, điểm cao, user chưa xem.
  - Ghi Top-N gợi ý real-time vào HBase, key = userId.

Đây là tầng "tốc độ" (speed layer) bổ sung cho gợi ý batch (ALS) — phản ánh ngay
sở thích vừa thay đổi của user mà không cần chờ train lại mô hình.
"""
import os
import json
import time
from collections import defaultdict, deque

from kafka import KafkaConsumer

KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "kafka:9092")
TOPIC = os.environ.get("KAFKA_TOPIC_RATINGS", "ratings-stream")
HBASE_HOST = os.environ.get("HBASE_HOST", "hbase")
HBASE_PORT = int(os.environ.get("HBASE_THRIFT_PORT", "9090"))
HBASE_TABLE = os.environ.get("HBASE_TABLE_RECS", "user_recommendations")
MOVIES_CSV = os.environ.get("MOVIES_PATH", "/app/data/ml-25m/movies.csv")
TOP_N = int(os.environ.get("ALS_TOP_N", "20"))

# Trending real-time (nguồn LIVE từ Wikimedia): cửa sổ trượt các phim vừa được quan tâm
TREND_WINDOW = int(os.environ.get("TREND_WINDOW_SEC", "21600"))   # 6 giờ
TREND_TOP_N = int(os.environ.get("TREND_TOP_N", "40"))           # số phim thịnh hành giữ trong HBase
TREND_ROW = os.environ.get("HBASE_TRENDING_ROW", "__TRENDING__")
trending_events = deque()   # (timestamp, movie_id, title)

# Bộ nhớ tạm trong tiến trình: hồ sơ thể loại ưa thích & lịch sử đã xem của user
user_genre_pref = defaultdict(lambda: defaultdict(float))
user_seen = defaultdict(set)


def load_movies():
    """Đọc metadata phim vào RAM: movie_id -> (title, set(genres), avg điểm giả lập)."""
    movies = {}
    genre_index = defaultdict(list)  # genre -> [movie_id,...]
    import csv
    if not os.path.exists(MOVIES_CSV):
        print(f"[!!] Không thấy {MOVIES_CSV}; stream layer chạy ở chế độ trống.")
        return movies, genre_index
    with open(MOVIES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid = int(row["movieId"])
            genres = set(row["genres"].split("|")) if row["genres"] != "(no genres listed)" else set()
            movies[mid] = {"title": row["title"], "genres": genres}
            for g in genres:
                genre_index[g].append(mid)
    print(f"[OK] Nạp {len(movies)} phim, {len(genre_index)} thể loại")
    return movies, genre_index


def connect_hbase():
    """Kết nối HBase qua Thrift (happybase). Trả None nếu không kết nối được."""
    try:
        import happybase
        for attempt in range(20):
            try:
                conn = happybase.Connection(HBASE_HOST, port=HBASE_PORT, timeout=20000)
                conn.open()
                # tạo bảng nếu chưa có
                tables = [t.decode() for t in conn.tables()]
                if HBASE_TABLE not in tables:
                    conn.create_table(HBASE_TABLE, {"rec": dict()})
                    print(f"[OK] Tạo bảng HBase '{HBASE_TABLE}'")
                print(f"[OK] Kết nối HBase {HBASE_HOST}:{HBASE_PORT}")
                return conn
            except Exception as e:
                print(f"[..] Chờ HBase ({attempt+1}/20): {e}")
                time.sleep(6)
    except ImportError:
        print("[!!] Chưa cài happybase.")
    return None


def recommend_realtime(user_id, movies, genre_index):
    """Sinh Top-N gợi ý real-time dựa trên thể loại ưa thích hiện tại của user."""
    prefs = user_genre_pref[user_id]
    if not prefs:
        return []
    top_genres = sorted(prefs.items(), key=lambda x: -x[1])[:3]
    scores = defaultdict(float)
    for genre, weight in top_genres:
        for mid in genre_index.get(genre, [])[:500]:
            if mid in user_seen[user_id]:
                continue
            scores[mid] += weight
    ranked = sorted(scores.items(), key=lambda x: -x[1])[:TOP_N]
    return [{"movie_id": mid, "title": movies[mid]["title"], "score": round(s, 3)}
            for mid, s in ranked if mid in movies]


def update_trending(ev, table):
    """Sự kiện LIVE từ Wikipedia: cập nhật danh sách phim 'thịnh hành real-time' vào HBase.

    Dùng cửa sổ trượt TREND_WINDOW: đếm số lần mỗi phim được nhắc tới gần đây,
    xếp hạng và ghi Top-N vào HBase row đặc biệt (key = TREND_ROW)."""
    now = int(time.time())
    trending_events.append((now, ev["movieId"], ev.get("title", "")))
    while trending_events and now - trending_events[0][0] > TREND_WINDOW:
        trending_events.popleft()

    counts = defaultdict(float)
    titles = {}
    for _, mid, title in trending_events:
        counts[mid] += 1.0
        titles[mid] = title
    ranked = sorted(counts.items(), key=lambda x: -x[1])[:TREND_TOP_N]

    if table is not None:
        data = {f"rec:{i}".encode(): json.dumps(
                    {"movie_id": mid, "title": titles[mid], "score": round(sc, 2)}
                ).encode()
                for i, (mid, sc) in enumerate(ranked)}
        data[b"rec:updated_at"] = str(now).encode()
        table.delete(TREND_ROW.encode())          # xoá danh sách cũ tránh sót mục hết hạn
        table.put(TREND_ROW.encode(), data)
    return len(ranked)


def main():
    movies, genre_index = load_movies()
    hbase_conn = connect_hbase()
    table = hbase_conn.table(HBASE_TABLE) if hbase_conn else None

    consumer = None
    for attempt in range(30):
        try:
            consumer = KafkaConsumer(
                TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
                group_id="stream-recsys",
            )
            print(f"[OK] Kết nối Kafka, lắng nghe topic '{TOPIC}'")
            break
        except Exception as e:
            print(f"[..] Chờ Kafka ({attempt+1}/30): {e}")
            time.sleep(5)
    if consumer is None:
        raise RuntimeError("Không kết nối được Kafka")

    processed = 0
    trended = 0
    for msg in consumer:
        ev = msg.value

        # --- Nguồn REAL-TIME THẬT: sự kiện phim live từ Wikimedia EventStreams ---
        if ev.get("event_type") == "trending" or ev.get("source") == "wikipedia":
            n = update_trending(ev, table)
            trended += 1
            print(f"  🔥 [LIVE Wikipedia] '{ev.get('title')}' "
                  f"-> trending now: {n} phim (tổng {trended} sự kiện)")
            continue

        # --- Luồng rating (replay) -> gợi ý real-time theo thể loại cho từng user ---
        uid, mid, rating = ev["userId"], ev["movieId"], ev["rating"]
        user_seen[uid].add(mid)
        # cập nhật điểm ưa thích theo thể loại (rating >=3.5 mới tính là thích)
        if mid in movies and rating >= 3.5:
            for g in movies[mid]["genres"]:
                user_genre_pref[uid][g] += (rating - 3.0)

        recs = recommend_realtime(uid, movies, genre_index)
        if recs and table is not None:
            data = {f"rec:{i}".encode(): json.dumps(r).encode() for i, r in enumerate(recs)}
            data[b"rec:updated_at"] = str(int(time.time())).encode()
            table.put(str(uid).encode(), data)

        processed += 1
        if processed % 50 == 0:
            print(f"  -> Đã xử lý {processed} events (user {uid}: {len(recs)} gợi ý real-time)")


if __name__ == "__main__":
    main()
