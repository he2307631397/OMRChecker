# 2026-08-01 REVIEW 特征分布分析

## 分析目标

评估当前观测特征是否足够支持进入保守 `WEAK_MARK` 自动恢复阶段。

分析范围只包括：

- 主流程识别为空白的单选题 `Weak mark candidate review`。
- 保护场景中的既有 fallback 事件作为风险参考。
- 当前不分析 ID 行，不分析多选题，不引入样本硬编码。

## 数据来源

- `jcode_regression_weak.log`
- `jcode_regression_normal.log`
- `jcode_regression_underfill.log`
- `jcode_regression_overflow.log`
- `jcode_regression_summary_after_multiscale.txt`

运行产物不提交，本文件只保存人工整理后的可追溯摘要。

## 四场景事件概览

| 场景 | Weak mark candidate review | Weak mark fallback | 结论 |
| --- | ---: | ---: | --- |
| weak | 3 | 0 | 有 3 个题目空白候选需要分析 |
| normal | 0 | 0 | 无新增 review 风险 |
| underfill | 0 | 1 | 存在 1 个既有题目 fallback，可作为保护参考 |
| overflow | 0 | 0 | 无新增 review 风险 |

## weak 场景 REVIEW 候选特征

| field | candidate | page_delta | gap | center_density | density_gap | threshold_ratio | multiscale | 判断 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| q5 | D | 20.94 | 5.93 | 0.600 | 0.230 | 1.000 | 1.000 | 强候选 |
| q3 | B | 21.36 | 0.63 | 0.247 | 0.008 | 0.750 | 0.750 | 弱且歧义高 |
| q6 | D | 19.90 | 1.11 | 0.393 | -0.107 | 1.000 | 1.000 | 密度差为负，风险高 |

补充特征：

- q5：`page_z=15.31`，`delta=10.54`，`center_edge_ratio=1.993`，`density=0.524`。
- q3：`page_z=14.19`，`delta=4.25`，`center_edge_ratio=0.723`，`density=0.282`。
- q6：`page_z=14.80`，`delta=5.35`，`center_edge_ratio=1.284`，`density=0.349`。

## 保护场景参考

underfill 场景中有 1 个既有题目 fallback：

| 场景 | field | candidate | page_delta | page_z | delta | gap | density | density_gap | threshold_vote_count | threshold_vote_ratio | multiscale_vote_count | multiscale_stability |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| underfill | q5 | C | 33.64 | 24.82 | 22.78 | 17.58 | 0.405 | 0.115 | 4 | 1.000 | 4 | 1.000 |

该样本不是 ID 空白恢复，不属于当前禁止恢复的 ID 行。但它提醒我们：强特征并不只出现在 weak 场景，因此自动恢复必须继续限定在 blank-only 单选题，且不能放宽到 ID 或多选。

## 可分性判断

### 可以区分的正向信号

q5 同时满足：

- 页面动态差异强：`page_delta=20.94`，`page_z=15.31`。
- 中心填涂明显：`center_density=0.600`。
- 候选密度领先明显：`density_gap=0.230`。
- 多阈值稳定：`threshold_vote_ratio=1.000`。
- 多尺度稳定：`multiscale_stability=1.000`。
- 中心/边缘关系合理：`center_edge_ratio=1.993`。

这类候选具备进入保守自动恢复的基础。

### 仍不安全的信号

q3 和 q6 不建议自动恢复：

- q3 的 `gap=0.63`、`density_gap=0.008`，候选与次候选几乎不可分。
- q3 的 `center_edge_ratio=0.723`，中心不比边缘更强，可能是噪声或边框影响。
- q6 的 `density_gap=-0.107`，最暗均值候选在密度上反而弱于其他候选。
- q6 虽然多阈值和多尺度稳定，但该稳定性可能来自区域整体灰度，不足以单独决定答案。

## 结论

当前特征已经具备**局部正向可分性**，但还不足以一次性恢复全部淡涂空白。

建议进入第 7 项时只启用极保守规则：

1. 仍然只作用于主流程为空白的单选题。
2. 仍然排除 ID 和多选。
3. 必须同时满足：
   - `density_gap` 明显为正。
   - `center_density` 足够高。
   - `center_edge_ratio` 大于 1。
   - `threshold_vote_ratio` 为 1。
   - `multiscale_stability` 为 1。
   - 页面动态证据达到要求。
4. 不恢复 q3/q6 这类候选与次候选不可分或密度差为负的样本。

在当前数据上，最安全的预期提升是先恢复 weak 场景中的 1 个题目空白，而不是 3 个全部恢复。

## 下一步建议

进入第 7 项：实现保守 `WEAK_MARK` 自动恢复，但目标设为：

- weak 场景题目空白从 3 降到 2。
- normal 保持 56 行、0 空白。
- overflow 保持 4 行、0 空白。
- underfill 不减少预期 ID 空白。
- 不新增多选冲突。

若该阶段稳定，再继续分析 q3/q6 是否需要新的特征或保持人工 review。
