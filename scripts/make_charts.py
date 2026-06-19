"""
make_charts.py — Sinh biểu đồ minh họa cho báo cáo (lưu vào docs/images).
  1. Phân bố điểm đánh giá (rating distribution)
  2. Top thể loại phim theo số lượt đánh giá
  3. Top phim phổ biến (weighted rating)

Chỉ dùng pandas + matplotlib, đọc dữ liệu từ ratings.csv + SQLite demo DB.
"""
import os
import sqlite3
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RATINGS_PATH = os.environ.get("RATINGS_PATH", "./data/ml-25m/ratings.csv")
DB_PATH = os.environ.get("DB_PATH", "./serving/recsys.db")
OUT = os.environ.get("CHART_DIR", "./docs/images")
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"figure.dpi": 120, "font.size": 11})


def chart_rating_distribution():
    counts = {}
    for ch in pd.read_csv(RATINGS_PATH, usecols=["rating"], chunksize=3_000_000):
        for r, c in ch["rating"].value_counts().items():
            counts[r] = counts.get(r, 0) + int(c)
    s = pd.Series(counts).sort_index()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(s.index.astype(str), s.values / 1e6, color="#e50914")
    ax.set_title("Phân bố điểm đánh giá — MovieLens 25M")
    ax.set_xlabel("Điểm (sao)"); ax.set_ylabel("Số lượt (triệu)")
    fig.tight_layout(); fig.savefig(f"{OUT}/rating_distribution.png"); plt.close(fig)
    print("[OK] rating_distribution.png")


def chart_top_genres():
    con = sqlite3.connect(DB_PATH)
    movies = pd.read_sql("SELECT genres, num_ratings FROM movies WHERE num_ratings>0", con)
    con.close()
    g = {}
    for _, row in movies.iterrows():
        for genre in str(row["genres"]).split("|"):
            if genre and genre != "(no genres listed)":
                g[genre] = g.get(genre, 0) + row["num_ratings"]
    s = pd.Series(g).sort_values(ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(s.index[::-1], s.values[::-1] / 1e6, color="#f5b50a")
    ax.set_title("Top 15 thể loại theo số lượt đánh giá")
    ax.set_xlabel("Số lượt đánh giá (triệu)")
    fig.tight_layout(); fig.savefig(f"{OUT}/top_genres.png"); plt.close(fig)
    print("[OK] top_genres.png")


def chart_top_popular():
    con = sqlite3.connect(DB_PATH)
    pop = pd.read_sql("SELECT title, avg_rating, num_ratings FROM popular_movies ORDER BY rank_pos LIMIT 15", con)
    con.close()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(pop["title"][::-1], pop["avg_rating"][::-1], color="#5fb0ff")
    ax.set_xlim(3.5, 5); ax.set_title("Top 15 phim phổ biến (theo weighted rating)")
    ax.set_xlabel("Điểm trung bình")
    fig.tight_layout(); fig.savefig(f"{OUT}/top_popular.png"); plt.close(fig)
    print("[OK] top_popular.png")


if __name__ == "__main__":
    chart_top_genres()
    chart_top_popular()
    chart_rating_distribution()
    print("[DONE] Charts saved to", OUT)
