"""
build_demo_db.py
================
Nạp kết quả Batch Layer (parquet do train_als.py sinh ra) vào CSDL mà Flask đọc.
  - Local: SQLite (serving/recsys.db)  — chạy demo không cần Docker.
  - Docker: MySQL (đặt DB_URL=mysql+pymysql://...).

Ngoài ra tạo bảng `user_history` từ một mẫu ratings để demo hiển thị
"phim user từng thích".

Dùng:
  python scripts/build_demo_db.py
Env:
  OUTPUT_DIR   (default ./batch/output)   — nơi chứa parquet
  DB_URL       (default sqlite:///serving/recsys.db)
  RATINGS_PATH (default ./data/ml-25m/ratings.csv) — để dựng user_history
"""
import os
import glob
import pandas as pd
from sqlalchemy import create_engine

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "./batch/output")
DB_URL = os.environ.get("DB_URL", "sqlite:///serving/recsys.db")
RATINGS_PATH = os.environ.get("RATINGS_PATH", "./data/ml-25m/ratings.csv")
HISTORY_SAMPLE_USERS = int(os.environ.get("HISTORY_SAMPLE_USERS", "2000"))


def read_parquet_dir(name):
    path = os.path.join(OUTPUT_DIR, name)
    files = glob.glob(os.path.join(path, "*.parquet"))
    if not files:
        print(f"[!!] Không thấy parquet cho '{name}' tại {path}")
        return None
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def main():
    engine = create_engine(DB_URL)
    print(f"[..] Ghi vào {DB_URL}")

    for tbl in ["movies", "popular_movies", "user_recommendations", "stats"]:
        df = read_parquet_dir(tbl)
        if df is not None:
            df.to_sql(tbl, engine, if_exists="replace", index=False)
            print(f"[OK] {tbl}: {len(df):,} dòng")

    # user_history từ mẫu ratings (chỉ lấy các user có trong user_recommendations)
    recs = read_parquet_dir("user_recommendations")
    if recs is not None and os.path.exists(RATINGS_PATH):
        sample_users = set(recs["user_id"].unique()[:HISTORY_SAMPLE_USERS])
        print(f"[..] Dựng user_history cho {len(sample_users)} user (đọc ratings theo chunk)")
        chunks = []
        for ch in pd.read_csv(RATINGS_PATH, chunksize=2_000_000):
            ch = ch[ch["userId"].isin(sample_users) & (ch["rating"] >= 4.0)]
            chunks.append(ch[["userId", "movieId", "rating"]])
        hist = pd.concat(chunks, ignore_index=True)
        hist = hist.sort_values("rating", ascending=False).groupby("userId").head(10)
        hist.columns = ["user_id", "movie_id", "rating"]
        hist.to_sql("user_history", engine, if_exists="replace", index=False)
        print(f"[OK] user_history: {len(hist):,} dòng")

    print("[DONE] Demo DB sẵn sàng.")


if __name__ == "__main__":
    main()
