#!/usr/bin/env bash
# ============================================================
#  Đưa dữ liệu MovieLens 25M từ máy host lên HDFS (Data Lake).
#  Chạy SAU khi cluster đã `docker compose up`.
# ============================================================
set -e

# Trên Git Bash (Windows), tắt path-conversion của MSYS để '/data/...' không bị
# biến thành đường dẫn Windows (gây lỗi "No FileSystem for scheme D").
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

HDFS_DIR=/data/movielens

echo "[..] Tạo thư mục trên HDFS: $HDFS_DIR"
docker exec namenode hdfs dfs -mkdir -p $HDFS_DIR

echo "[..] Copy dữ liệu vào container namenode"
docker cp ./data/ml-25m/ratings.csv namenode:/tmp/ratings.csv
docker cp ./data/ml-25m/movies.csv  namenode:/tmp/movies.csv
docker cp ./data/ml-25m/links.csv   namenode:/tmp/links.csv  || true
docker cp ./data/ml-25m/tags.csv    namenode:/tmp/tags.csv   || true

echo "[..] Put lên HDFS"
docker exec namenode hdfs dfs -put -f /tmp/ratings.csv $HDFS_DIR/ratings.csv
docker exec namenode hdfs dfs -put -f /tmp/movies.csv  $HDFS_DIR/movies.csv
docker exec namenode hdfs dfs -put -f /tmp/links.csv   $HDFS_DIR/links.csv  || true
docker exec namenode hdfs dfs -put -f /tmp/tags.csv    $HDFS_DIR/tags.csv   || true

echo "[OK] Dữ liệu đã nằm trên HDFS:"
docker exec namenode hdfs dfs -ls $HDFS_DIR
