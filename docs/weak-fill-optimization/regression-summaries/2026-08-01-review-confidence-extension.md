# 2026-08-01 复核置信度输出扩展回归摘要

## 变更范围

- 扩展 `WeakFillReview.csv` 辅助复核输出，新增 `review_type` 和 `original_value` 字段。
- 新增 `SINGLE_CHOICE_CONFLICT_REVIEW`，用于记录非多选题中已经被主流程识别为多个选项的冲突候选。
- 新增 `ID_REVIEW`，用于记录弱 ID fallback 已接受的候选，以及主流程仍为空白时被旧阈值规则拒绝的低置信候选。
- 本轮保持 observation-only：没有修改 `inputs/config.json`，没有启用 `resolve_single_choice_conflicts=true`，没有把候选写回 `Results_*.csv` 答案列。
- 多选题继续以模板 `multi_select` 为准，`q9/q10/q11` 未进入单选冲突复核逻辑。

## 验证命令

在隔离 worktree `/Users/apple/.config/superpowers/worktrees/OMRChecker/review-confidence-extension` 中执行：

```bash
PYTHONPATH=. /Volumes/wdata/work/tech/OMRChecker/.venv/bin/python -m pytest \
  tests/test_weak_fill_features.py tests/test_omr_regression_runner.py -q

PYTHONPATH=. /Volumes/wdata/work/tech/OMRChecker/.venv/bin/python \
  scripts/run_omr_regression.py | tee jcode_regression_summary_after_review_confidence_extension.txt
```

测试输出：`....................`。

四场景回归命令完成，输出文件：`jcode_regression_summary_after_review_confidence_extension.txt`。

## Results CSV 指标

`Results_*.csv` 指标保持在既有回归基线：

| 场景 | rows | id_blank_cells | q_blank_cells | blank_cells | blank_rows |
|---|---:|---:|---:|---:|---:|
| weak | 10 | 1 | 3 | 4 | 4 |
| normal | 56 | 0 | 0 | 0 | 0 |
| underfill | 4 | 8 | 0 | 8 | 1 |
| overflow | 4 | 0 | 0 | 0 | 0 |

已知 weak 样本保持不变：

- `MX-M3658N_20260731_162311_001.png q1 == ABCD`
- `MX-M3658N_20260731_162311_001.png q2 == ABD`
- `MX-M3658N_20260731_162311_001.png q5 == ""`

其中 `q1/q2/q5` 的人工判读候选分别可在辅助 CSV 中作为复核候选查看，但没有进入主结果列。

## Review CSV 分布

| 场景 | 总行数 | ID_REVIEW | SINGLE_CHOICE_CONFLICT_REVIEW | WEAK_MARK_REVIEW |
|---|---:|---:|---:|---:|
| weak | 21 | 13 | 5 | 3 |
| normal | 4 | 1 | 3 | 0 |
| underfill | 8 | 8 | 0 | 0 |
| overflow | 0 | 0 | 0 | 0 |

关键样例：

- `MX-M3658N_20260731_162311_001.png q1`：`SINGLE_CHOICE_CONFLICT_REVIEW`，`original_value=ABCD`，候选 `C`，`confidence=0.882`，`status=REVIEW`。
- `MX-M3658N_20260731_162311_001.png q2`：`SINGLE_CHOICE_CONFLICT_REVIEW`，`original_value=ABD`，候选 `A`，`confidence=0.825`，`status=REVIEW`。
- `MX-M3658N_20260731_162311_001.png q5`：`WEAK_MARK_REVIEW`，候选 `D`，`confidence=0.680`，旧规则拒绝原因 `adaptive_min_delta_from_blank`。
- `MX-M3658N_20260731_162311_004.png id7`：`ID_REVIEW`，候选 `4`，`confidence=0.466`，`status=LOW_CONFIDENCE`，旧规则拒绝原因 `max_mean_without_adaptive_support`。主 `Results` 中该格仍为空白。
- underfill 场景中的 8 个空白 ID 均只输出 `LOW_CONFIDENCE` ID 候选，置信度约 `0.070` 到 `0.178`，主结果保持空白。

## 多选题保护

验证脚本统计 `q9/q10/q11` 中 `SINGLE_CHOICE_CONFLICT_REVIEW` 行数为 `0`。

这说明当前单选冲突复核记录尊重模板 `multi_select=True`，不会把真实多选题误当作单选冲突处理，也不会覆盖多选输出。

## 结论

本轮变更适合进入人工复核和分布分析阶段，不适合直接作为自动修正启用。

原因：

- 主结果语义已保持稳定，辅助候选没有混入 `Results_*.csv`。
- weak 样本中 `q1/q2/q5` 和未识别 `id7` 都已有可审查候选及置信度。
- normal 场景也出现少量单选冲突复核行，说明后续如要做自动修正，必须单独设计默认关闭的开关，并用人工标注分布、四场景回归和多选保护验证后再考虑。
- 低置信 ID 候选用于人工审查，不代表新增自动恢复逻辑。已有 ID fallback 接受的候选也被写入 `ID_REVIEW`，这是把既有行为暴露到辅助 CSV，而不是扩大主流程恢复范围。
