# 2026-08-01 多阈值投票观测回归摘要

## 变更范围

- 新增 `get_threshold_vote_features`。
- 将多阈值投票特征接入 weak-fill diagnostics。
- 在 `Weak mark candidate review` 日志中输出：
  - `threshold_vote_count`
  - `threshold_vote_ratio`
  - `threshold_density_gaps`
- 当前仍为观测模式，不改变 CSV 答案，不启用新的自动恢复逻辑。

## 验证命令

```bash
. .venv/bin/activate && PYTHONPATH=. python -m pytest tests/test_weak_fill_features.py tests/test_omr_regression_runner.py -q
. .venv/bin/activate && PYTHONPATH=. python scripts/run_omr_regression.py | tee jcode_regression_summary_after_threshold_votes.txt
```

## 单测结果

`8 passed`

## 四场景结果

| 场景 | rows | ID 空白 | 题目空白 | 总空白 | 空白行 | Weak identifier fallback | Weak mark fallback | Weak mark candidate review | Single-choice conflict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak | 10 | 1 | 3 | 4 | 4 | 12 | 0 | 3 | 0 |
| normal | 56 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| underfill | 4 | 8 | 0 | 8 | 1 | 0 | 1 | 0 | 0 |
| overflow | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## 结论

- 与 review-only 阶段相比，四场景 CSV 指标不变。
- 淡涂场景仍有 3 条 `Weak mark candidate review`，用于后续特征分布分析。
- normal、underfill、overflow 保护场景无新增题目空白或冲突。
- 允许继续进入多尺度 ROI / 小型图像金字塔观测特征阶段。

## 注意

运行产物位于根目录日志和 `outputs_jcode_regression_*` 中，不提交。
长期追溯只保留本摘要。
