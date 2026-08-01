# 2026-08-01 多尺度 ROI 观测回归摘要

## 变更范围

- 新增 `get_multiscale_roi_features`。
- 观测局部 ROI 的四个变体：
  - 原始 ROI。
  - 中心裁剪 ROI。
  - 轻微高斯模糊 ROI。
  - 缩小后放大的小型图像金字塔 ROI。
- 将多尺度特征接入 weak-fill diagnostics。
- 在 `Weak mark candidate review` 日志中输出：
  - `multiscale_vote_count`
  - `multiscale_stability`
  - `multiscale_density_gaps`
- 当前仍为观测模式，不改变 CSV 答案，不启用新的自动恢复逻辑。

## 验证命令

```bash
. .venv/bin/activate && PYTHONPATH=. python -m pytest tests/test_weak_fill_features.py tests/test_omr_regression_runner.py -q
. .venv/bin/activate && PYTHONPATH=. python scripts/run_omr_regression.py | tee jcode_regression_summary_after_multiscale.txt
```

## 单测结果

`10 passed`

## 四场景结果

| 场景 | rows | ID 空白 | 题目空白 | 总空白 | 空白行 | Weak identifier fallback | Weak mark fallback | Weak mark candidate review | Single-choice conflict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak | 10 | 1 | 3 | 4 | 4 | 12 | 0 | 3 | 0 |
| normal | 56 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| underfill | 4 | 8 | 0 | 8 | 1 | 0 | 1 | 0 | 0 |
| overflow | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## 结论

- 与多阈值投票阶段相比，四场景 CSV 指标不变。
- 淡涂场景仍有 3 条 `Weak mark candidate review`。
- 多尺度 ROI 特征已进入日志，可用于下一步特征分布分析。
- normal、underfill、overflow 保护场景无新增题目空白或冲突。
- 下一步应抽取 review 行特征，分析 weak 与保护场景是否可分。

## 注意

运行产物位于根目录日志和 `outputs_jcode_regression_*` 中，不提交。
长期追溯只保留本摘要。
