# 2026-08-01 弱填候选置信度辅助输出回归摘要

## 变更范围

本次实现第 7 项的第一步：新增弱填候选/置信度辅助输出，供人工流程参考。

- 新增独立输出文件：`Results/WeakFillReview.csv`
- 不修改原 `Results_*.csv` 表头和答案列语义。
- 对主流程识别为空白且触发弱填 review 的单选候选输出：
  - `candidate`
  - `confidence`
  - `status`
  - `reason`
  - `evidence`
  - 关键观测特征摘要
- 仍不启用自动弱填恢复，`Weak mark fallback=0` 保持不变。

## 辅助 CSV 字段

`WeakFillReview.csv` 字段：

```text
file_id,input_path,output_path,field,candidate,confidence,status,reason,evidence,score,legacy_rejection,ambiguity,density_gap,center_density,center_edge_ratio,threshold_vote_ratio,multiscale_stability
```

`confidence` 是 0 到 1 的辅助置信度，来自已有观测证据的归一化组合：

- score evidence
- density gap
- center density
- threshold vote ratio
- multiscale stability

当前配置下弱填评分仍未作为自动恢复开关启用，因此弱填场景中的 `status` 为 `LEGACY`、`reason=score_disabled`，但会保留候选和置信度供人工复核。

## 验证命令

```bash
. .venv/bin/activate && PYTHONPATH=. python -m pytest tests/test_weak_fill_features.py -q
. .venv/bin/activate && PYTHONPATH=. python scripts/run_omr_regression.py | tee jcode_regression_summary_after_confidence_review.txt
```

## 单测结果

```text
11 passed
```

新增覆盖：

- review candidate metadata 中包含 candidate/confidence/status/reason/evidence。
- `WeakFillReview.csv` 独立创建，不改变 `Results_*.csv` 表头。
- review rows 按候选逐行写入，浮点字段稳定格式化。

## 四场景 Results CSV 回归结果

```text
weak:      rows=10 id_blank_cells=1 q_blank_cells=3 blank_cells=4 blank_rows=4
normal:    rows=56 id_blank_cells=0 q_blank_cells=0 blank_cells=0 blank_rows=0
underfill: rows=4  id_blank_cells=8 q_blank_cells=0 blank_cells=8 blank_rows=1
overflow:  rows=4  id_blank_cells=0 q_blank_cells=0 blank_cells=0 blank_rows=0
```

与多尺度 ROI 观测阶段一致，说明新增辅助输出没有污染原答案输出。

## WeakFillReview.csv 结果

```text
weak rows=3
MX-M3658N_20260731_162311_001.png q5 D confidence=0.680 status=LEGACY reason=score_disabled legacy_rejection=adaptive_min_delta_from_blank
MX-M3658N_20260731_162311_008.png q3 B confidence=0.278 status=LEGACY reason=score_disabled legacy_rejection=adaptive_min_delta_from_blank
MX-M3658N_20260731_162311_009.png q6 D confidence=0.381 status=LEGACY reason=score_disabled legacy_rejection=adaptive_min_delta_from_blank

normal rows=0
underfill rows=0
overflow rows=0
```

## 结论

- 已满足用户确认的新方向：所有弱填 review 候选可作为独立辅助结果输出。
- 原答案列默认保持不变，正常填涂、没涂满、涂超出场景无新增候选干扰。
- `q5 -> D` 在现有样本中置信度最高，可优先进入人工复核。
- `q3 -> B` 与 `q6 -> D` 保持低置信辅助候选，不建议自动恢复。

## 后续建议

下一步可以在第 7b 项中设计保守自动恢复门槛，但默认仍应关闭，并继续只作用于主流程为空白的单选题。建议以 `WeakFillReview.csv` 的置信度分布作为门槛验证输入。
