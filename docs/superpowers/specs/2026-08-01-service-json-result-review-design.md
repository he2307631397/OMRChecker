# 2026-08-01 服务化 JSON 结果与复核参数设计

## 背景

当前 OMRChecker 已形成两类输出：

1. `Results_*.csv`：每张答题卡的推荐识别结果。
2. `WeakFillReview.csv`：对弱填、单选冲突、低置信 ID 等存疑项输出复核参数。

这套双 CSV 适合离线排查，但后续服务化接口需要应用端直接拿到结构化 JSON。应用端不应自己用 `file_id + field` 去关联两份 CSV。服务端应在接口层完成聚合，让每个具体识别字段同时包含推荐结果、参考候选和 review 参数。

## 目标

服务化识别接口输出一份按答题卡组织的 JSON，满足：

- 每张答题卡有完整推荐答案，应用端可直接展示或入库。
- 每个字段都有统一结构，包括普通明确识别项和存疑项。
- 存疑项与对应识别结果一一绑定，不依赖前端二次匹配 CSV。
- `WeakFillReview.csv` 中的参数完整映射到对应字段的 `reviews` 中。
- 兼容当前 CSV 输出。CSV 可继续用于离线验收和人工批量复核。
- 不改变当前识别算法和恢复策略。服务化阶段只做结果结构封装。

## 非目标

- 不继续放宽淡涂阈值。
- 不把 ID 低置信候选套用单选题恢复规则。
- 不用样本名、题号、坐标或答案硬编码。
- 不在本阶段实现 Web API 框架、上传接口或数据库持久化。
- 不替换当前 CSV 输出。

## 推荐方案

采用“双视图 + 字段内聚合”结构：

- `answers`：面向展示和兼容 CSV 的简单键值结果。
- `items`：每个字段一条结构化记录，包含推荐结果、状态、候选和 review 参数。
- `reviews`：可选的全局 review 列表，作为人工复核队列索引，引用 `items` 中的字段。
- `summary`：整张卡是否需要人工复核、review 数量、风险等级。

推荐原因：

- `answers` 方便应用端快速显示结果。
- `items` 方便应用端逐题渲染状态、置信度和解释参数。
- `reviews` 方便只展示待人工复核项。
- 字段级 `items` 是事实来源，避免结果和 review 分离造成错配。

## JSON 顶层结构

```json
{
  "schema_version": "omr-result-review.v1",
  "template_id": "default",
  "batch_id": "10PM",
  "generated_at": "2026-08-01T15:00:00Z",
  "records": [
    {
      "file_id": "MX-M3658N_20260731_162311_001.png",
      "input_path": "/path/to/input.png",
      "output_path": "/path/to/output.png",
      "recognition_status": "NEEDS_REVIEW",
      "answers": {
        "q1": "ABCD",
        "q5": "D",
        "q9": "CD"
      },
      "items": [],
      "reviews": [],
      "summary": {}
    }
  ]
}
```

## 字段 item 结构

所有字段都输出同样结构。普通明确识别项也输出，只是 `reviews` 为空。

```json
{
  "field": "q5",
  "field_type": "QTYPE_MCQ4",
  "multi_select": false,
  "result": "D",
  "status": "NEEDS_REVIEW",
  "recommended": {
    "value": "D",
    "confidence": 0.68,
    "source": "WEAK_MARK_REVIEW",
    "status": "NEEDS_REVIEW"
  },
  "candidates": [
    {
      "value": "D",
      "confidence": 0.68,
      "source": "WEAK_MARK_REVIEW"
    }
  ],
  "reviews": [
    {
      "review_type": "WEAK_MARK_REVIEW",
      "original_value": "",
      "candidate": "D",
      "status": "NEEDS_REVIEW",
      "confidence": 0.68,
      "score": 0.0,
      "reason": "score_disabled",
      "legacy_rejection": "adaptive_min_delta_from_blank",
      "evidence": [],
      "ambiguity": 0.0,
      "features": {
        "density_gap": 0.467,
        "center_density": 0.7,
        "center_edge_ratio": 70.0,
        "threshold_vote_ratio": 1.0,
        "multiscale_stability": 1.0
      }
    }
  ]
}
```

## 普通明确识别字段示例

```json
{
  "field": "q4",
  "field_type": "QTYPE_MCQ4",
  "multi_select": false,
  "result": "B",
  "status": "ACCEPTED",
  "recommended": {
    "value": "B",
    "confidence": null,
    "source": "PRIMARY_DETECTION",
    "status": "ACCEPTED"
  },
  "candidates": [],
  "reviews": []
}
```

## 低置信但不恢复字段示例

`008 q3` 和 `009 q6` 属于有 review 候选但低于恢复阈值的情况。推荐结果仍为空，review 参数保留给人工参考。

```json
{
  "field": "q3",
  "field_type": "QTYPE_MCQ4",
  "multi_select": false,
  "result": "",
  "status": "LOW_CONFIDENCE",
  "recommended": {
    "value": "",
    "confidence": null,
    "source": "PRIMARY_DETECTION",
    "status": "LOW_CONFIDENCE"
  },
  "candidates": [
    {
      "value": "B",
      "confidence": 0.278,
      "source": "WEAK_MARK_REVIEW"
    }
  ],
  "reviews": [
    {
      "review_type": "WEAK_MARK_REVIEW",
      "original_value": "",
      "candidate": "B",
      "status": "LEGACY",
      "confidence": 0.278,
      "reason": "score_disabled",
      "legacy_rejection": "adaptive_min_delta_from_blank",
      "features": {
        "density_gap": 0.0,
        "center_density": 0.0,
        "center_edge_ratio": 0.0,
        "threshold_vote_ratio": 0.0,
        "multiscale_stability": 0.0
      }
    }
  ]
}
```

## ID review 示例

ID 不使用单选恢复规则。即使有候选，也只作为 ID 专用 review 输出。

```json
{
  "field": "id7",
  "field_type": "QTYPE_INT",
  "multi_select": false,
  "result": "",
  "status": "ID_REVIEW",
  "recommended": {
    "value": "",
    "confidence": null,
    "source": "PRIMARY_DETECTION",
    "status": "ID_REVIEW"
  },
  "candidates": [
    {
      "value": "4",
      "confidence": 0.466,
      "source": "ID_REVIEW"
    }
  ],
  "reviews": [
    {
      "review_type": "ID_REVIEW",
      "original_value": "",
      "candidate": "4",
      "status": "LOW_CONFIDENCE",
      "confidence": 0.466,
      "reason": "weak_identifier_candidate",
      "legacy_rejection": "max_mean_without_adaptive_support",
      "features": {
        "density_gap": 0.0,
        "center_density": 0.0,
        "center_edge_ratio": 0.0,
        "threshold_vote_ratio": 0.0,
        "multiscale_stability": 0.0
      }
    }
  ]
}
```

## 多选题示例

多选题正常识别时不进入单选冲突或弱填恢复逻辑。结果保留多选字符串。

```json
{
  "field": "q9",
  "field_type": "QTYPE_MCQ4",
  "multi_select": true,
  "result": "CD",
  "status": "ACCEPTED",
  "recommended": {
    "value": "CD",
    "confidence": null,
    "source": "PRIMARY_DETECTION",
    "status": "ACCEPTED"
  },
  "candidates": [],
  "reviews": []
}
```

## 状态枚举

### 字段状态 `item.status`

- `ACCEPTED`：主流程明确识别，无需人工复核。
- `RESOLVED_CANDIDATE`：辅助逻辑高置信恢复，推荐结果已写入 `result`。
- `NEEDS_REVIEW`：辅助逻辑中置信恢复，推荐结果已写入 `result`，但需要人工确认。
- `LOW_CONFIDENCE`：存在候选，但未恢复到推荐结果。
- `CONFLICT_REVIEW`：单选多识别冲突，存在候选和冲突参数。
- `ID_REVIEW`：ID 专用低置信候选。
- `BLANK`：无结果且无可用候选。

### review 状态 `reviews[].status`

沿用当前 `WeakFillReview.csv`：

- `RESOLVED_CANDIDATE`
- `NEEDS_REVIEW`
- `LOW_CONFIDENCE`
- `LEGACY`
- `REVIEW`

接口层可以把 review 状态映射成字段状态，但不应丢弃原始 review 状态。

## CSV 到 JSON 映射

### `Results_*.csv`

- 每一行对应一个 `record`。
- `file_id`、路径字段映射到 `record` 元数据。
- 每个答案列映射到：
  - `record.answers[field]`
  - `record.items[].result`

### `WeakFillReview.csv`

用以下键关联到字段：

- `file_id`
- `field`

关联后：

- `review_type` 映射到 `reviews[].review_type` 和候选 `source`。
- `candidate` 映射到 `candidates[].value`。
- `confidence` 映射到 `candidates[].confidence` 和 `reviews[].confidence`。
- `status` 映射到 `reviews[].status`。
- `density_gap`、`center_density`、`center_edge_ratio`、`threshold_vote_ratio`、`multiscale_stability` 映射到 `reviews[].features`。

## 推荐结果选择规则

1. `Results_*.csv` 中已有值时，`result` 使用该值。
2. 如果对应 review 的 status 是 `RESOLVED_CANDIDATE` 或 `NEEDS_REVIEW`，`recommended.value` 等于 `candidate`，`source` 等于 `review_type`。
3. 如果 `Results_*.csv` 为空且 review 低置信未恢复，`result` 保持空，候选只进入 `candidates` 和 `reviews`。
4. 如果没有 review，`recommended.source` 为 `PRIMARY_DETECTION`。
5. 多个 review 候选时，按 `confidence` 降序排序，最高候选作为 `candidates[0]`。本阶段不覆盖 `Results_*.csv`。

## record summary

每张答题卡提供摘要，便于应用端快速判断是否需要人工处理。

```json
{
  "requires_review": true,
  "review_count": 3,
  "resolved_candidate_count": 1,
  "needs_review_count": 1,
  "low_confidence_count": 1,
  "id_review_count": 1,
  "blank_count": 2,
  "risk_level": "MEDIUM"
}
```

建议风险等级：

- `NONE`：无 review，无空白。
- `LOW`：只有 `RESOLVED_CANDIDATE`。
- `MEDIUM`：存在 `NEEDS_REVIEW` 或 `LOW_CONFIDENCE`。
- `HIGH`：存在 `ID_REVIEW`、单选冲突未恢复、关键字段空白或处理异常。

## 兼容策略

- 当前 CSV 输出继续保留。
- 服务化封装优先从内存中的识别结果和 review records 生成 JSON。
- 过渡阶段也可以提供一个 CSV 聚合器，从 `Results_*.csv` + `WeakFillReview.csv` 生成同结构 JSON，用于回归测试和前端联调。
- JSON schema 使用 `schema_version` 管理，后续新增字段只做向后兼容扩展。

## 明日服务化封装建议顺序

1. 先实现纯函数聚合器：`build_result_review_json(results_rows, review_rows, template)`。
2. 用当前 weak 输出做测试样例，验证：
   - `001 q5` 为 `result=D`，`status=NEEDS_REVIEW`，review confidence 为 `0.680`。
   - `008 q3` 和 `009 q6` 结果为空，候选保留在 `candidates`。
   - `004 id7` 结果为空，状态为 `ID_REVIEW`。
   - `q9/q10/q11` 保持多选结果，reviews 为空。
3. 再把聚合器接到服务接口返回值。
4. 最后保留 CSV 生成作为离线审计输出。

## 验收项

- JSON 中每个 `answers` 字段都能在 `items` 中找到同名 item。
- 每条 `WeakFillReview.csv` review 都能在对应 `record.items[field].reviews` 中找到。
- `result` 与当前 `Results_*.csv` 完全一致。
- 普通明确识别字段输出 `status=ACCEPTED` 且 `reviews=[]`。
- `NEEDS_REVIEW` 字段既有推荐结果，也有完整 review 参数。
- 低置信字段不写推荐结果，但保留候选和 review 参数。
- ID review 不触发单选恢复语义。
- 多选题不被单选冲突或弱填恢复 review 污染。
