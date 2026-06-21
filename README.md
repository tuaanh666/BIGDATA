#  Hệ thống gợi ý phim thời gian thực trên nền tảng dữ liệu lớn

### *Real-time Movie Recommendation System on Big Data Platform*

Đây là hệ thống gợi ý phim được xây dựng trên nền tảng **Big Data** theo mô hình **Lambda Architecture**, kết hợp giữa **Batch Layer**, **Speed Layer** và **Serving Layer**. Mô hình học máy trung tâm là **ALS (Alternating Least Squares)** của **Spark MLlib**, được huấn luyện trên bộ dữ liệu **MovieLens 25M** với hơn **25 triệu lượt đánh giá phim**.

Điểm nổi bật của dự án là không chỉ tạo gợi ý từ dữ liệu lịch sử mà còn tích hợp **nguồn dữ liệu thời gian thực từ Wikimedia EventStreams** để hiển thị các phim đang được quan tâm trên Wikipedia, toàn bộ hệ thống được triển khai bằng Docker Compose với 13 container.


#  Điểm nổi bật

* Huấn luyện mô hình **ALS phân tán** trên toàn bộ **25 triệu ratings** của MovieLens.
* Đạt kết quả đánh giá:

  * **RMSE:** `0.7965`
  * **MAE:** `0.6187`
* Triển khai đầy đủ kiến trúc **Lambda Architecture** gồm Batch Layer, Speed Layer và Serving Layer.
* Sử dụng dữ liệu thời gian thực thật từ **Wikimedia EventStreams** thay vì mô phỏng.
* Toàn bộ hệ thống được đóng gói bằng **Docker Compose với 13 container**, có thể chạy lại hoàn chỉnh trên máy cục bộ chỉ với một lệnh.


#  Kiến trúc hệ thống

![Kiến trúc Lambda của hệ thống gợi ý phim](docs/images/architecture_lambda.png)

## Batch Layer

* Dữ liệu **MovieLens 25M** được lưu trên **HDFS**.
* **Spark MLlib** huấn luyện mô hình ALS và sinh danh sách gợi ý Top-N.
* Kết quả được lưu vào **MySQL**.
* **Airflow** chịu trách nhiệm lập lịch ETL và retrain định kỳ.

## Speed Layer

* Nhận luồng sự kiện thời gian thực từ **Wikimedia EventStreams**.
* Kafka tiếp nhận dữ liệu, Consumer xử lý và cập nhật vào **HBase**.
* HBase lưu:

  * Danh sách phim đang thịnh hành (`__TRENDING__`).
  * Gợi ý theo thể loại cho từng người dùng.

## Serving Layer

* **Flask** kết hợp dữ liệu từ:

  * Batch View trong MySQL.
  * Speed View trong HBase.
  * Poster phim từ TMDB.
* Cung cấp giao diện web và REST API cho người dùng.

| Layer            | Công nghệ                         | Vai trò                                                                   |
| ---------------- | --------------------------------- | ------------------------------------------------------------------------- |
| Ingestion        | **Kafka + Zookeeper**             | Topic `ratings-stream`: replay rating và sự kiện Wikipedia thời gian thực |
| Data Lake        | **HDFS**                          | Lưu dữ liệu MovieLens 25M (`ratings.csv` ~647MB)                          |
| Batch            | **Spark (PySpark) + MLlib (ALS)** | Huấn luyện mô hình và sinh Top-N recommendation                           |
| Speed View       | **HBase**                         | Lưu gợi ý real-time và danh sách phim thịnh hành                          |
| Batch View       | **MySQL**                         | Metadata phim, poster, recommendation và thống kê                         |
| Orchestration    | **Airflow**                       | Điều phối ETL và retrain                                                  |
| Serving          | **Flask**                         | Web demo và REST API                                                      |
| Nguồn real-time  | **Wikimedia EventStreams**        | Luồng SSE công khai, không cần API key                                    |
| Làm giàu dữ liệu | **TMDB API**                      | Lấy poster phim thật                                                      |
| Deploy           | **Docker Compose**                | Triển khai toàn bộ hệ thống                                               |


#  Kết quả thực nghiệm

| Chỉ số                 | Giá trị                                 |
| ---------------------- | --------------------------------------- |
| Tổng số ratings        | **25.000.095**                          |
| Số người dùng          | **~162.541**                            |
| Số phim                | **62.423**                              |
| RMSE (test 20%)        | **0.7965**                              |
| MAE (test 20%)         | **0.6187**                              |
| Recommendation sinh ra | **400.000 dòng (20.000 user × Top-20)** |
| Poster TMDB            | **11.866 ảnh**                          |


#  Cấu trúc thư mục

```text
BIG DATA/
├── docker-compose.yml
├── .env.example
├── README.md
├── Tổng quan.md
├── data/ml-25m/
├── ingestion/
│   ├── download_data.py
│   ├── stream_producer.py
│   └── wiki_stream_producer.py
├── batch/
│   └── train_als.py
├── stream/
│   └── consumer.py
├── serving/
│   ├── app.py
│   ├── templates/
│   └── static/
├── scripts/
│   ├── load_to_hdfs.sh
│   ├── mysql_init.sql
│   ├── build_demo_db.py
│   ├── fetch_posters.py
│   ├── make_charts.py
│   └── run_local.ps1
├── airflow/
│   └── dags/
│       └── recsys_pipeline.py
└── docs/
    └── images/
```


#  Hướng dẫn chạy dự án

## Yêu cầu

* Python **3.10 – 3.12**
* JDK **8 / 11 / 17**
* Docker Desktop (8GB RAM)
* TMDB API Key (hiển thị poster)

 tạo file cấu hình môi trường:

```bash
cp .env.example .env
```

Sau đó chỉnh sửa `.env`, thay đổi mật khẩu MySQL và thêm `TMDB_API_KEY` nếu có.

---

#  Cách 1- Chạy nhanh trên LOCAL (demo)

Script PowerShell sẽ tự động:

* Tải dữ liệu nếu chưa có.
* Huấn luyện ALS.
* Tạo SQLite (`serving/recsys.db`).
* Khởi động Flask Web.

```powershell
.\scripts\run_local.ps1
```

Hoặc chạy bản mẫu nhỏ:

```powershell
.\scripts\run_local.ps1 -Sample
```

Sau khi xong, truy cập:

```
http://localhost:5000
```

Repository cũng đã kèm sẵn:

```
serving/recsys.db
```
có thể mở web ngay mà chưa cần train:

```bas
cd serving
python app.py
```

### Chạy từng bước

```bash
pip install pyspark==3.5.1 "setuptools<81" pandas pyarrow flask sqlalchemy

python ingestion/download_data.py
python batch/train_als.py
python scripts/build_demo_db.py

cd serving
python app.py
```


# Cách 2- Chạy đầy đủ bằng Docker (13 container)

## Bước 1: Khởi động hệ thống

```bash
docker compose up -d --build
docker compose ps
```

## Bước 2: Đưa dữ liệu lên HDFS

```bash
MSYS_NO_PATHCONV=1 bash scripts/load_to_hdfs.sh
```

MySQL sẽ tự tạo schema từ:

```
scripts/mysql_init.sql
```

khi khởi động lần đầu.

## Bước 3: Huấn luyện ALS

```bash
docker exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages com.mysql:mysql-connector-j:8.3.0 \
  /app/batch/train_als.py
```

Hoặc kích hoạt DAG:

```
movielens_recsys_batch
```

trên Airflow.

## Bước 4: Chạy luồng thời gian thực

* `wiki` lấy dữ liệu trực tiếp từ Wikimedia.
* `stream` đọc Kafka và cập nhật HBase.
* `ingestion` replay dữ liệu ratings.

## Bước 5: Lấy poster từ TMDB (tùy chọn)

```bash
pip install pymysql sqlalchemy

export TMDB_API_KEY=...

python scripts/fetch_posters.py \
  --links data/ml-25m/links.csv \
  --limit 5000
```

## Bước 6: Mở web demo

```
http://localhost:5000
```

Để mục ** Thịnh hành real-time** hiển thị dữ liệu, chỉ cần để service `wiki` chạy vài phút rồi tải lại trang.


# Cách Xử lý sự cố 

| Vấn đề                 | Cách xử lý                                                                  |
| ---------------------- | --------------------------------------------------------------------------------- |
| HBase không hoạt động  | `docker compose up -d --force-recreate hbase` rồi `docker compose restart stream` |
| Spark thiếu numpy      | `docker exec spark-master apk add py3-numpy` (thực hiện tương tự với worker)      |
| Cổng 5000 bị chiếm     | Tắt Flask local trước khi chạy Docker                                             |
| Container tự dừng      | Kiểm tra RAM và tăng bộ nhớ cho Docker Desktop                                    |
| Spark lỗi trên Windows | Thiết lập `PYSPARK_PYTHON` trỏ tới `python.exe` thật và dùng `setuptools<81`      |
| `wiki` không ghi log   | Đảm bảo `PYTHONUNBUFFERED=1` đã được thiết lập                                    |


#  Thuật toán ALS

ALS phân rã ma trận đánh giá `R (users × movies)` thành hai ma trận ẩn:

* `U (users × k)`
* `V (movies × k)`

với mục tiêu tối ưu:

```text
min Σ_(u,i) (r_ui − uᵤᵀ·vᵢ)² + λ(Σ‖uᵤ‖² + Σ‖vᵢ‖²)
```

Thuật toán giải theo cách **luân phiên**, tức là:

1. Giữ cố định `V` để tính `U`.
2. Giữ cố định `U` để tính `V`.


Các siêu tham số sử dụng:

* `rank = 64`
* `maxIter = 10`
* `regParam = 0.08`
* `coldStartStrategy = drop`
* `Top-N = 20`
* Chỉ giữ các phim có ít nhất **1000 lượt đánh giá**

Mô hình được đánh giá bằng **RMSE** và **MAE** trên tập kiểm thử chiếm **20% dữ liệu**.


> Bộ dữ liệu **MovieLens 25M** (~647MB) không được đưa vào repository do kích thước lớn. Tải bằng `ingestion/download_data.py` hoặc trực tiếp từ trang chính thức của GroupLens trước khi chạy huấn luyện mô hình.
