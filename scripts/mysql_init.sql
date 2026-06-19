-- ============================================================
--  MySQL schema cho Batch View của hệ thống gợi ý phim
-- ============================================================
CREATE DATABASE IF NOT EXISTS movielens CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE movielens;

-- Bảng metadata phim
CREATE TABLE IF NOT EXISTS movies (
    movie_id    INT PRIMARY KEY,
    title       VARCHAR(512) NOT NULL,
    genres      VARCHAR(512),
    year        INT,
    avg_rating  FLOAT DEFAULT 0,
    num_ratings INT   DEFAULT 0,
    poster_url  VARCHAR(255),
    INDEX idx_title (title(100)),
    INDEX idx_avg_rating (avg_rating)
) ENGINE=InnoDB;

-- Bảng gợi ý batch: Top-N phim cho mỗi user (do Spark ALS sinh ra)
CREATE TABLE IF NOT EXISTS user_recommendations (
    user_id     INT NOT NULL,
    rank_pos    INT NOT NULL,
    movie_id    INT NOT NULL,
    score       FLOAT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, rank_pos),
    INDEX idx_user (user_id)
) ENGINE=InnoDB;

-- Bảng phim phổ biến (fallback cho user mới — cold start)
CREATE TABLE IF NOT EXISTS popular_movies (
    rank_pos    INT PRIMARY KEY,
    movie_id    INT NOT NULL,
    title       VARCHAR(512),
    avg_rating  FLOAT,
    num_ratings INT
) ENGINE=InnoDB;

-- Bảng thống kê tổng quan (cho dashboard)
CREATE TABLE IF NOT EXISTS stats (
    metric_name  VARCHAR(64) PRIMARY KEY,
    metric_value VARCHAR(128)
) ENGINE=InnoDB;
