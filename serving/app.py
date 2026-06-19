import os
import json

from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text

DB_URL = os.environ.get("DB_URL", "sqlite:///./recsys.db")
HBASE_HOST = os.environ.get("HBASE_HOST", "hbase")
HBASE_PORT = int(os.environ.get("HBASE_THRIFT_PORT", "9090"))
HBASE_TABLE = os.environ.get("HBASE_TABLE_RECS", "user_recommendations")
HBASE_TRENDING_ROW = os.environ.get("HBASE_TRENDING_ROW", "__TRENDING__")

app = Flask(__name__)
engine = create_engine(DB_URL, pool_pre_ping=True)

def query(sql, **params):
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def get_stats():
    try:
        rows = query("SELECT metric_name, metric_value FROM stats")
        return {r["metric_name"]: r["metric_value"] for r in rows}
    except Exception:
        return {}


def get_popular(limit=20):
    try:
        return query(
            """
            SELECT p.rank_pos, p.movie_id, p.title, p.avg_rating, p.num_ratings,
                   m.poster_url
            FROM popular_movies p LEFT JOIN movies m ON m.movie_id = p.movie_id
            ORDER BY p.rank_pos LIMIT :lim
            """,
            lim=limit,
        )
    except Exception:
        return []


def get_user_recs(user_id, limit=20):
    try:
        return query(
            """
            SELECT r.rank_pos, r.movie_id, r.score,
                   m.title, m.genres, m.avg_rating, m.poster_url
            FROM user_recommendations r
            LEFT JOIN movies m ON m.movie_id = r.movie_id
            WHERE r.user_id = :uid
            ORDER BY r.rank_pos LIMIT :lim
            """,
            uid=user_id, lim=limit,
        )
    except Exception as e:
        app.logger.warning(f"get_user_recs lỗi: {e}")
        return []


def get_user_history(user_id, limit=10):
    try:
        return query(
            """
            SELECT m.title, m.genres, h.rating, m.poster_url
            FROM user_history h LEFT JOIN movies m ON m.movie_id = h.movie_id
            WHERE h.user_id = :uid ORDER BY h.rating DESC LIMIT :lim
            """,
            uid=user_id, lim=limit,
        )
    except Exception:
        return []


def posters_for(movie_ids):
    ids = [int(m) for m in movie_ids if m is not None]
    if not ids:
        return {}
    try:
        placeholders = ",".join(str(i) for i in set(ids))
        rows = query(
            f"SELECT movie_id, poster_url FROM movies WHERE movie_id IN ({placeholders})"
        )
        return {r["movie_id"]: r["poster_url"] for r in rows if r.get("poster_url")}
    except Exception:
        return {}


def get_realtime_recs(user_id, limit=20):
    try:
        import happybase
        conn = happybase.Connection(HBASE_HOST, port=HBASE_PORT, timeout=4000)
        conn.open()
        table = conn.table(HBASE_TABLE)
        row = table.row(str(user_id).encode())
        conn.close()
        recs = []
        for k, v in row.items():
            key = k.decode()
            if key.startswith("rec:") and key != "rec:updated_at":
                try:
                    recs.append(json.loads(v.decode()))
                except Exception:
                    pass
        return recs[:limit]
    except Exception:
        return []


def get_trending(limit=12):
    try:
        import happybase
        conn = happybase.Connection(HBASE_HOST, port=HBASE_PORT, timeout=4000)
        conn.open()
        row = conn.table(HBASE_TABLE).row(HBASE_TRENDING_ROW.encode())
        conn.close()
        recs = []
        for k, v in row.items():
            key = k.decode()
            if key.startswith("rec:") and key != "rec:updated_at":
                try:
                    recs.append(json.loads(v.decode()))
                except Exception:
                    pass
        recs.sort(key=lambda r: -r.get("score", 0))
        recs = recs[:limit]
        pmap = posters_for([r.get("movie_id") for r in recs])
        for r in recs:
            r["poster_url"] = pmap.get(r.get("movie_id"))
        return recs
    except Exception:
        return []


def search_movies(keyword, limit=20):
    try:
        return query(
            """SELECT movie_id, title, genres, avg_rating, num_ratings, poster_url
               FROM movies WHERE title LIKE :kw
               ORDER BY num_ratings DESC LIMIT :lim""",
            kw=f"%{keyword}%", lim=limit,
        )
    except Exception:
        return []

@app.route("/")
def index():
    stats = get_stats()
    popular = get_popular(12)
    trending = get_trending(24)
    return render_template("index.html", stats=stats, popular=popular, trending=trending)


@app.route("/api/trending")
def api_trending():
    return jsonify({"trending": get_trending(40)})


@app.route("/recommend")
def recommend():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return render_template("recommend.html", user_id=None)
    batch_recs = get_user_recs(user_id)
    realtime_recs = get_realtime_recs(user_id)
    pmap = posters_for([r.get("movie_id") for r in realtime_recs])
    for r in realtime_recs:
        r["poster_url"] = pmap.get(r.get("movie_id"))
    history = get_user_history(user_id)
    cold_start = len(batch_recs) == 0
    popular = get_popular(12) if cold_start else []
    return render_template(
        "recommend.html",
        user_id=user_id,
        batch_recs=batch_recs,
        realtime_recs=realtime_recs,
        history=history,
        cold_start=cold_start,
        popular=popular,
    )


@app.route("/search")
def search():
    kw = request.args.get("q", "").strip()
    results = search_movies(kw) if kw else []
    return render_template("search.html", q=kw, results=results)


@app.route("/api/recommend/<int:user_id>")
def api_recommend(user_id):
    return jsonify({
        "user_id": user_id,
        "batch": get_user_recs(user_id),
        "realtime": get_realtime_recs(user_id),
    })


@app.route("/health")
def health():
    try:
        query("SELECT 1 AS ok")
        return jsonify({"status": "ok", "db": DB_URL.split("://")[0]})
    except Exception as e:
        return jsonify({"status": "degraded", "error": str(e)}), 503


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
