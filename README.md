# 🚀 Orbit Wars — Kế hoạch nâng cấp Agent

> **Cuộc thi:** [Kaggle Orbit Wars](https://www.kaggle.com/competitions/orbit-wars)  
> **Deadline nộp thầy:** 08/06/2026  
> **Mục tiêu:** Score 800+ → 1000+ → 1200+  
> **Thời gian:** 15 ngày (24/05 – 08/06)

---

## 📊 Tổng quan lộ trình

```
24/05        27/05        01/06        05/06     08/06
  │            │            │            │          │
  ▼            ▼            ▼            ▼          ▼
[Submit]───[800+]───────[1000+]──────[1200+]───[Nộp]
  │            │            │            │
Baseline    Fix &        Heuristic    Heuristic
 chạy OK    tune         cấp 2        cấp 2+RL
```

| Giai đoạn | Thời gian | Mục tiêu | Kỹ thuật chính |
|---|---|---|---|
| 🔵 **Phase 1** | 24–27/05 | Score ≥ 800 | Submit baseline, fix lỗi |
| 🟢 **Phase 2** | 28/05–01/06 | Score ≥ 1000 | Cải thiện heuristic |
| 🟣 **Phase 3** | 02–05/06 | Score ≥ 1200 | Heuristic cấp 2 + RL |
| 🟡 **Phase 4** | 06–08/06 | Nộp bài | Report + cleanup |

---

## 🔵 Giai đoạn 1 — Baseline hoạt động (24–27/05)

**Mục tiêu:** Agent chạy không lỗi, submit lên Kaggle, đạt score ≥ 800

### Chủ nhật 25/05 — Ngày 1

- [ ] Chạy notebook theo thứ tự: Cell 1 → 2 → 5 → 12 → 13
- [ ] Test 10 game vs `random`, win rate phải ≥ 80%
- [ ] **Submit lần 1** lên Kaggle, ghi nhận score ban đầu (~700–800)

```bash
kaggle competitions submit orbit-wars -f main.py -m "Baseline v1"
```

### Thứ 2 26/05 — Ngày 2

- [ ] Kiểm tra submission có bị Error không
- [ ] Nếu lỗi → tải log về phân tích

```bash
# Xem trạng thái submission
kaggle competitions submissions orbit-wars

# Tải log nếu bị lỗi
kaggle competitions logs <SUBMISSION_ID> 0
```

- [ ] Chạy benchmark 20 game, win rate phải ≥ 85%
- [ ] **Submit lần 2** sau khi win rate ổn định

### Thứ 3 27/05 — Ngày 3

- [ ] Tải replay các game thua về phân tích

```bash
kaggle competitions replay <EPISODE_ID> -p ./replays
```

- [ ] Tìm nguyên nhân thua: hay mất planet? Gửi thiếu tàu? Bay qua mặt trời?
- [ ] Điều chỉnh `KEEP_RATIO` và `MIN_KEEP` theo kết quả phân tích

> ✅ **Checkpoint Phase 1:** Score Kaggle ≥ 800 | Win rate vs random ≥ 85%

---

## 🟢 Giai đoạn 2 — Nâng cấp heuristic (28/05–01/06)

**Mục tiêu:** Score ≥ 1000 bằng cách cải thiện 4 điểm yếu của agent hiện tại

### Thứ 4 28/05 — Ngày 4

#### Cải tiến 1: Tính đúng số tàu cần gửi

Vấn đề hiện tại: Chỉ xét `target.ships + 1`, bỏ qua tàu địch đang bay về reinforce.

```python
# ❌ Cũ — thiếu chính xác
ships_needed = target.ships + 1

# ✅ Mới — tính cả reinforcement địch đang đến
def enemy_fleet_incoming(target, fleets, player):
    incoming = 0
    for f in fleets:
        if f.owner in (player, -1) or f.owner != target.owner:
            continue
        if dist(f.x, f.y, target.x, target.y) > 60:
            continue
        diff = abs(f.angle - angle_to(f.x, f.y, target.x, target.y)) % (2*math.pi)
        if min(diff, 2*math.pi - diff) < 0.18:
            incoming += f.ships
    return incoming

ships_needed = target.ships + enemy_fleet_incoming(target, fleets, player) + 1
```

#### Cải tiến 2: Orbit intercept chính xác hơn

```python
# ✅ Binary search thay vì iterative đơn giản
def intercept_binary(planet, av, sx, sy, n, iters=12):
    t_lo, t_hi = 0.0, 200.0
    for _ in range(iters):
        t_mid = (t_lo + t_hi) / 2
        px, py = predict_pos(planet, av, t_mid)
        t_actual = travel_turns(sx, sy, px, py, n)
        if t_actual < t_mid:
            t_hi = t_mid
        else:
            t_lo = t_mid
    return predict_pos(planet, av, (t_lo + t_hi) / 2)
```

- [ ] Implement 2 cải tiến trên vào `environment/game_utils.py`
- [ ] Test win rate lại: mục tiêu ≥ 88%

### Thứ 5 29/05 — Ngày 5

#### Cải tiến 3: Multi-target expand — bắn nhiều neutral cùng lúc

```python
# ✅ Early game: 1 planet bắn 2–3 neutral nhỏ gần nhau cùng lượt
if phase == "early":
    small_neutrals = sorted(
        [t for t in neutral if t.ships < can_send // 3],
        key=lambda t: (t.ships, dist(mine.x, mine.y, t.x, t.y))
    )
    for target in small_neutrals[:3]:   # tối đa 3 mục tiêu
        tx, ty  = predict_iterative(target, av, mine.x, mine.y, target.ships+1)
        ang, ok = safe_angle(mine.x, mine.y, tx, ty)
        if not ok: continue
        send = target.ships + 1
        if mine.ships - committed[mine.id] - send < keep:
            break
        moves.append([mine.id, ang, send])
        committed[mine.id] += send
```

#### Cải tiến 4: Điều chỉnh scoring theo leaderboard

```python
# Nếu đang thua nhiều → aggressive hơn
PHASE_WEIGHTS = {
    "early": {"neutral": 2.5, "weak_enemy": 1.5, "other": 0.8},
    "mid":   {"neutral": 1.5, "weak_enemy": 2.5, "other": 1.0},
    "late":  {"neutral": 0.8, "weak_enemy": 3.0, "other": 0.5},
}
```

- [ ] Implement cải tiến 3 & 4
- [ ] **Submit lần 3**, mục tiêu score ≥ 900

### Thứ 6 30/05 — Ngày 6

#### Cải tiến 5: Chiến lược late game thận trọng

```python
def late_game_strategy(my_planets, others, committed, phase, step):
    """
    Sau turn 350: không tấn công xa, chỉ đánh khi chắc thắng.
    Ưu tiên bảo vệ planet production cao.
    """
    if phase != "late":
        return
    # Chỉ tấn công planet trong bán kính 30 units
    close_targets = [t for t in others
                     if any(dist(mine.x, mine.y, t.x, t.y) < 30
                            for mine in my_planets)]
    return close_targets
```

#### Cải tiến 6: Comet capture thông minh

```python
# Tính thời điểm comet spawn: turn 50, 150, 250, 350, 450
COMET_SPAWN_TURNS = [50, 150, 250, 350, 450]

def should_chase_comet(comet, my_planet, step, av):
    """Có nên đuổi comet này không?"""
    d = dist(my_planet.x, my_planet.y, comet.x, comet.y)
    turns_to_reach = travel_turns(my_planet.x, my_planet.y,
                                   comet.x, comet.y, 20)
    # Chỉ đuổi nếu đến kịp và comet còn đủ thời gian tạo ship
    remaining_on_board = 100 - (step % 100)   # ước tính
    return (d < 25 and
            comet.ships < 15 and
            remaining_on_board > turns_to_reach + 10)
```

### Chủ nhật 01/06 — Ngày 7

- [ ] Benchmark toàn diện: 30 game vs `random`, 20 game vs `heuristic`
- [ ] Win rate mục tiêu: ≥ 90% vs random, ≥ 55% vs self
- [ ] **Submit lần 4** → mục tiêu vượt **1000**
- [ ] Nếu chưa đạt 1000: xem replay kỹ, tìm pattern hay thua

> ✅ **Checkpoint Phase 2:** Score Kaggle ≥ 1000 | Win rate vs random ≥ 90%

---

## 🟣 Giai đoạn 3 — Heuristic cấp 2 + RL (02–05/06)

**Mục tiêu:** Score ≥ 1200 bằng cải tiến sâu hơn và thử Reinforcement Learning

### Thứ 2 02/06 — Ngày 8

#### Cải tiến 7: Safe angle bypass chính xác

```python
def safe_angle_tangent(fx, fy, tx, ty):
    """
    Tính đường vòng tránh mặt trời theo tiếp tuyến — ngắn nhất có thể.
    Thay vì lệch cố định ±15°, tính điểm tiếp tuyến chính xác.
    """
    base = angle_to(fx, fy, tx, ty)
    if not hits_sun(fx, fy, tx, ty):
        return base, True

    # Vector từ nguồn đến tâm mặt trời
    dx_s, dy_s = SUN_X - fx, SUN_Y - fy
    d_to_sun   = math.hypot(dx_s, dy_s)
    r_safe     = SUN_RADIUS + SUN_MARGIN + 1.0

    if d_to_sun <= r_safe:
        return base, False   # Đang trong vùng nguy hiểm

    # Góc tiếp tuyến: arcsin(r / d)
    theta = math.asin(min(r_safe / d_to_sun, 1.0))
    sun_angle = math.atan2(dy_s, dx_s)

    for sign in [1, -1]:
        ang = sun_angle + sign * (math.pi/2 + theta)
        ex  = fx + 150 * math.cos(ang)
        ey  = fy + 150 * math.sin(ang)
        if not hits_sun(fx, fy, ex, ey):
            return ang, True

    return base, False
```

- [ ] Bắt đầu train PPO song song (chạy qua đêm)

```bash
python training/train.py --config training/config.yaml
```

### Thứ 3 03/06 — Ngày 9

#### Cải tiến 8: Fleet coordination — tránh gửi trùng mục tiêu

```python
def get_targeted_planets(fleets, player):
    """Các planet đã có fleet thân thiện đang bay đến."""
    targeted = {}   # planet_id → total_ships_incoming
    for f in fleets:
        if f.owner != player:
            continue
        targeted[f.from_planet_id] = targeted.get(f.from_planet_id, 0) + f.ships
    return targeted

# Khi tính score_target: trừ đi ships đã được gửi đến
already_sent = get_targeted_planets(fleets, player)
effective_garrison = target.ships - already_sent.get(target.id, 0)
ships_needed = max(1, effective_garrison + enemy_reinforce + 1)
```

#### Cải tiến 9: Adaptive keep_ratio theo tình hình

```python
def adaptive_keep(planet, phase, my_total_ships, enemy_total_ships):
    """
    Điều chỉnh keep_ratio động theo tỷ lệ lực lượng.
    Đang mạnh hơn → giữ nhiều hơn (bảo vệ lead).
    Đang yếu hơn → all-in tấn công.
    """
    base_ratio = {"early": 0.10, "mid": 0.20, "late": 0.25}.get(phase, 0.20)

    if my_total_ships > enemy_total_ships * 1.5:
        # Đang dẫn xa → thận trọng hơn
        ratio = base_ratio * 1.3
    elif my_total_ships < enemy_total_ships * 0.7:
        # Đang thua → aggressive hơn
        ratio = base_ratio * 0.6
    else:
        ratio = base_ratio

    return max(5, int(planet.ships * ratio), planet.production + 2)
```

- [ ] **Submit** sau khi implement cải tiến 7 & 8 & 9

### Thứ 4 04/06 — Ngày 10

- [ ] Đánh giá PPO đã train qua đêm

```bash
python training/evaluate.py --mode rl --model models/best_model.zip --games 30
```

- [ ] **Nếu PPO win rate vs heuristic ≥ 55%** → dùng PPO làm agent chính

```python
# Export PPO thành main.py độc lập (không cần import stable-baselines3)
import numpy as np

# Lấy weights từ model
model = PPO.load("models/best_model.zip")
weights = {k: v.numpy() for k, v in model.policy.state_dict().items()}
np.save("model_weights.npy", weights)

# Trong main.py: load weights và forward pass thủ công
```

- [ ] **Nếu PPO chưa đủ tốt** → tiếp tục cải thiện heuristic

### Thứ 5 05/06 — Ngày 11

- [ ] **Submit agent tốt nhất → mục tiêu ≥ 1200**
- [ ] Chụp màn hình leaderboard (dùng cho report)
- [ ] **FREEZE agent** — không thay đổi thêm sau bước này

```bash
# Submit lần cuối
kaggle competitions submit orbit-wars -f main.py -m "Final v3 - heuristic+RL"

# Xem leaderboard
kaggle competitions leaderboard orbit-wars -s

# Chụp ranking (lưu vào report/)
```

> ⚠️ Score cần 24–48h để ổn định. Thay đổi muộn dễ làm tụt điểm.

> ✅ **Checkpoint Phase 3:** Score Kaggle ≥ 1200 | Screenshot ranking đã lưu

---

## 🟡 Giai đoạn 4 — Hoàn thiện & nộp bài (06–08/06)

**Mục tiêu:** Report đầy đủ, code sạch, nộp đúng hạn

### Thứ 7 06/06 — Ngày 12

- [ ] Viết report IEEE — phần **Method & Results**
  - Mô tả 4 phase agent (Defense → Attack → Expand → Surplus)
  - Giải thích orbit prediction và sun avoidance
  - Vẽ biểu đồ win rate theo từng version agent
- [ ] Clean code toàn bộ repo
  - Xóa debug `print()` thừa
  - Thêm docstring cho các hàm quan trọng
  - Cập nhật README với kết quả thực tế

### Chủ nhật 07/06 — Ngày 13

- [ ] Hoàn thiện report — **Introduction + Related Work + Conclusion**
  - Tổng cộng 4–6 trang, có hình minh họa game
  - Biểu đồ so sánh score qua từng version
- [ ] Chuẩn bị phỏng vấn nhóm
  - Giải thích được: Tại sao dùng iterative orbit prediction?
  - Reward shaping ảnh hưởng thế nào đến RL?
  - Heuristic vs RL: trade-off là gì?
- [ ] Export report → `report/report.pdf`

### Thứ 2 08/06 — DEADLINE

- [ ] Nộp thầy đầy đủ 3 thứ:
  - 📄 `report/report.pdf` — IEEE Conference format
  - 💻 Link GitHub repo — code sạch, README rõ ràng
  - 🏆 Screenshot leaderboard Kaggle

---

## 📈 Kỳ vọng score theo từng version

| Version | Thời điểm | Score | Cải tiến chính |
|---|---|---|---|
| v1 Baseline | 25/05 | ~700 | Agent mẫu gốc |
| v1.1 Fixed | 26/05 | ~800 | Fix lỗi, tune keep_ratio |
| v2 Heuristic | 29/05 | ~900 | Enemy reinforcement, multi-target |
| v2.1 Advanced | 01/06 | ~1000 | Late game, comet capture |
| v3 Heuristic++ | 03/06 | ~1100 | Fleet coord, adaptive keep |
| v3.1 Final | 05/06 | ~1200+ | Best of heuristic + RL |

---

## ⚠️ Rủi ro & xử lý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| Score không tăng sau submit | Plateau ở 800–900 | Xem replay, tìm pattern thua cụ thể |
| PPO không hội tụ | Win rate vs random < 60% | Bỏ RL, tập trung heuristic cấp 2 |
| Submission bị Error | Status = Error trên Kaggle | `kaggle competitions logs <ID> 0` |
| Hết thời gian chạy | Kaggle timeout 1s/turn | Tối ưu vòng lặp, bỏ tính toán thừa |
| Score tụt sau khi submit mới | Leaderboard giảm | Rollback về version trước |

---

## 🔧 Lệnh hay dùng

```bash
# Submit
kaggle competitions submit orbit-wars -f main.py -m "version description"

# Xem submissions
kaggle competitions submissions orbit-wars

# Xem leaderboard
kaggle competitions leaderboard orbit-wars -s

# Tải replay
kaggle competitions replay <EPISODE_ID> -p ./replays

# Tải log lỗi
kaggle competitions logs <EPISODE_ID> 0

# Train PPO
python training/train.py

# Benchmark
python training/evaluate.py --mode heuristic --games 30
```

---

## 📂 Cấu trúc repo

```
orbit-wars/
├── main.py                   # ← Submit Kaggle
├── agents/
│   └── heuristic_agent.py
├── environment/
│   ├── game_utils.py         # Vật lý + orbit prediction
│   ├── reward.py
│   ├── gym_wrapper.py
│   └── visualize.py
├── training/
│   ├── train.py
│   ├── evaluate.py
│   └── config.yaml
├── models/                   # PPO weights
├── replays/                  # Replay JSON để phân tích
├── report/
│   └── report.pdf
├── PLAN.md                   # File này
└── README.md
```

---

## 🔗 Tài nguyên

- [Kaggle Orbit Wars](https://www.kaggle.com/competitions/orbit-wars)
- [Notebook mẫu — RL Pipeline](https://www.kaggle.com/code/thisisn0mad/orbit-wars-rl-pipelinepublic)
- [Notebook mẫu — Heuristic scored 1000](https://www.kaggle.com/code/zacharymaronek/orbit-wars-heuristicagent-scored-1000)
- [IEEE Conference Template](https://www.ieee.org/conferences/publishing/templates)
- [Local Arena Tool](https://www.kaggle.com/datasets/penguin069/orbit-wars-local-arena)
