# 淡涂优化状态

## 当前阶段

已进入第一阶段：观测模式。

当前不会自动修改淡涂答案，只在主流程为空白的单选题上输出可解释 `REVIEW` 日志。

## 已完成

| 阶段 | 状态 | 提交 | 验证 |
| --- | --- | --- | --- |
| 方案边界冻结 | 完成 | `f58c3d1` | 文档明确 OMRChecker 专用、动态阈值、多尺度 ROI、CNN 远期 |
| 四场景 regression runner | 完成 | `f102988` | `PYTHONPATH=. python scripts/run_omr_regression.py` 通过 |
| blank-only 单选 REVIEW 日志 | 完成 | `cc525b6` | CSV 指标不变，淡涂新增 3 条 `Weak mark candidate review` |

## 当前四场景基线

| 场景 | rows | ID 空白 | 题目空白 | 总空白 | 空白行 | review |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| weak | 10 | 1 | 3 | 4 | 4 | 3 |
| normal | 56 | 0 | 0 | 0 | 0 | 0 |
| underfill | 4 | 8 | 0 | 8 | 1 | 0 |
| overflow | 4 | 0 | 0 | 0 | 0 | 0 |

## 观测结论

- 现有观测日志不改变 CSV 结果。
- 正常填涂 56 张无退化。
- 涂超出 4 张无退化。
- 没涂满场景仍保留预期 ID 空白。
- 淡涂场景 3 个题目空白已有 `REVIEW` 证据，后续可继续加入动态阈值和多尺度 ROI 特征。

## 下一步

1. 新增 ROI 多阈值投票特征。
2. 新增多尺度 ROI / 小型图像金字塔特征。
3. 将新增特征写入 `Weak mark candidate review` 日志。
4. 重新跑四场景，整理摘要到 `regression-summaries/`。
5. 只有保护场景不退化且特征可分，才考虑保守 `WEAK_MARK` 自动恢复。

## 管理规则

- 根目录运行日志和输出目录不提交。
- 只提交人工整理后的 Markdown 摘要。
- 每次阶段推进都更新本文件。
