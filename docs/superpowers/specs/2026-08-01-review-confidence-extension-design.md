# 2026-08-01 复核置信度输出扩展设计

## 背景

弱填优化已新增 `Results/WeakFillReview.csv`，用于输出弱填候选和置信度，且不改变原 `Results_*.csv`。人工复核确认：

- `MX-M3658N_20260731_162311_001.png` 中 `q5 -> D` 正确。
- `q3 -> B`、`q6 -> D` 实际未填涂，是误候选。
- 同一张图中 `q1` 实际为 `C`、`q2` 实际为 `A`，但当前 Results 输出 `q1=ABCD`、`q2=ABD`。
- `q9/q10/q11` 是正确多选题，不应按单选冲突处理。

## 目标

扩展人工复核辅助输出，使它覆盖三类通用审查场景：

1. `WEAK_MARK_REVIEW`：主流程空白但存在弱填候选。
2. `SINGLE_CHOICE_CONFLICT_REVIEW`：单选题识别出多个候选，需要给出推荐候选、置信度和证据。
3. `ID_REVIEW`：ID 位未识别或弱识别候选，需要给出候选、置信度和证据。

原 `Results_*.csv` 表头和答案列默认保持不变。多选题继续按模板的 `multi_select` 行为输出，不进入单选冲突解析。

## 非目标

- 不基于文件名、目录、题号、坐标或答案硬编码。
- 不降低全局阈值。
- 不引入 CNN。
- 不覆盖模板标记为多选的题目。
- 本阶段不默认自动修正 Results 中的答案，只增强复核输出和观测。

## 设计

### 辅助输出文件

继续使用 `Results/WeakFillReview.csv` 作为人工复核队列，后续可考虑重命名为更通用的 `ReviewCandidates.csv`。为保持兼容，本阶段不改文件名。

新增字段建议：

- `review_type`：`WEAK_MARK_REVIEW`、`SINGLE_CHOICE_CONFLICT_REVIEW`、`ID_REVIEW`
- `original_value`：主流程原始输出，例如 `ABCD`、`ABD` 或空白。
- `candidate`：推荐候选，例如 `C`、`A`、`D` 或 ID 位数字。
- `confidence`：0 到 1 的复核置信度。
- `status`：候选状态，例如 `REVIEW`、`RESOLVED_CANDIDATE`、`LOW_CONFIDENCE`。
- `reason`：主要原因，例如 `single_choice_conflict`、`weak_identifier_candidate`。
- `evidence`：触发证据，例如 `gap,delta_from_blank,center_density,multiscale_stability`。

保留已有弱填特征字段，并允许单选冲突与 ID 候选共用这些通用字段。

### 单选冲突复核

当字段满足以下条件时生成 `SINGLE_CHOICE_CONFLICT_REVIEW`：

- `field_block.multi_select == False`
- `field_block.field_type` 在弱填支持的单选字段类型内
- 主流程检测候选数大于 1

复核候选来自当前字段所有候选中的 darkest bubble。置信度使用通用特征组合：

- darkest 与 second darkest 的亮度 gap
- darkest 到局部 blank baseline 的 delta
- center density
- center/edge ratio
- threshold vote ratio
- multiscale stability

若证据强，状态为 `RESOLVED_CANDIDATE`。若证据弱，状态为 `REVIEW` 或 `LOW_CONFIDENCE`。本阶段默认仍不改变 Results。

### ID 候选复核

当 ID 位主流程为空白且存在 weak identifier candidate 或被 rejection 规则拦截但有观测证据时，生成 `ID_REVIEW`：

- `field_block.field_type` 在 ID 支持字段类型内。
- `field_block.direction == vertical`。
- 当前字段没有主流程检测结果。
- 不改变已有 ID fallback 安全边界。

置信度基于：gap、delta_from_blank、page_z、density_gap、center density。实际 fallback 已恢复的 ID 也可作为高置信复核记录输出，便于人工审计。

## 数据流

1. `read_omr_response` 每张图开始时重置 review records。
2. 每个字段完成主阈值检测后：
   - 多候选单选字段追加 conflict review record。
   - 空白 ID 字段追加 ID review record。
   - 空白单选弱填继续追加 weak mark review record。
3. `_process_single_image` 保持 Results 写入逻辑不变。
4. `_process_single_image` 将 review records 追加到 `WeakFillReview.csv`。

## 测试计划

单测：

- 单选多候选字段生成 `SINGLE_CHOICE_CONFLICT_REVIEW`，且多选字段不生成。
- ID 空白弱候选生成 `ID_REVIEW`。
- `WeakFillReview.csv` 新字段兼容原弱填候选输出。
- Results CSV 表头不变。

回归：

- `pytest tests/test_weak_fill_features.py tests/test_omr_regression_runner.py -q`
- `PYTHONPATH=. python scripts/run_omr_regression.py`

门禁：

- normal：56 行，0 空白。
- underfill：保持 ID 空白保护，不强行恢复。
- overflow：4 行，0 空白。
- weak：记录 q1/q2 conflict review、q5 weak review、现有 ID review，默认 Results 结构不变。

## 风险与边界

- 单选冲突解析不能误伤多选题，必须依赖模板 `multi_select`。
- ID 候选不能因为辅助输出而放松自动恢复。
- 置信度只是人工流程参考，不代表自动判定。
- 后续若启用自动修正，必须新增独立开关，并先用辅助 CSV 分布验证。
