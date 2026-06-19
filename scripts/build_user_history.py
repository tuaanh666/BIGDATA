"""
build_user_history.py
======================
Dựng bảng `user_history` (vài phim mỗi user từng đánh giá cao) để demo hiển thị
"phim user từng thích". Chỉ dùng pandas (không cần Spark) nên chạy ổn định.

Đọc danh sách user từ bảng user_recommendations trong DB, rồi quét ratings.csv
theo chunk để lấy top phim điểm cao của các user đó.

Env:
  DB_URL        (default sqlite:///serving/recsys_full.db)
  RATINGS_PATH  (default ./data/ml-25m/ratings.csv)
  TOP_PER_USER  (default 10)
"""
import os
import pandas as pd
from sqlalchemy import create_engine, text

DB_URL = os.environ.get("DB_URL", "sqlite:///serving/recsys_full.db")
RATINGS_PATH = os.environ.get("RATINGS_PATH", "./data/ml-25m/ratings.csv")
TOP_PER_USER = int(os.environ.get("TOP_PER_USER", "10"))


def main():
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        users = {r[0] for r in conn.execute(text("SELECT DISTINCT user_id FROM user_recommendations"))}
    print(f"[..] {len(users):,} user cần dựng lịch sử; quét {RATINGS_PATH}")

    parts = []
    for ch in pd.read_csv(RATINGS_PATH, chunksize=2_000_000):
        ch = ch[ch["userId"].isin(users) & (ch["rating"] >= 4.0)]
        if len(ch):
            parts.append(ch[["userId", "movieId", "rating"]])
    hist = pd.concat(parts, ignore_index=True)
    hist = hist.sort_values("rating", ascending=False).groupby("userId").head(TOP_PER_USER)
    hist.columns = ["user_id", "movie_id", "rating"]
    hist.to_sql("user_history", engine, if_exists="replace", index=False)
    print(f"[OK] user_history: {len(hist):,} dòng cho {hist['user_id'].nunique():,} user")


if __name__ == "__main__":
    main()
