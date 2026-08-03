# 本地答题卡四场景识别率测试报告

- 生成时间 UTC: `2026-08-03 01:54:50`
- 运行方式: 本地命令行 `python main.py`，非 web 服务方式
- 输出目录: `outputs/`
- 统计口径: 识别率 = 非空单元格数 / 应识别单元格数。ID 与题目分别统计，并给出总体识别率。

## 汇总

| 场景 | PDF 数 | rows | ID识别率 | 题目识别率 | 总体识别率 | ID空白 | 题目空白 | 总空白 | 空白行 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| weak (淡涂答题卡归档) | 10 | 10 | 98.75% | 97.27% | 97.89% | 1 | 3 | 4 | 4 |
| normal (正常填涂测试答题卡归档) | 56 | 56 | 100.00% | 100.00% | 100.00% | 0 | 0 | 0 | 0 |
| underfill (没涂满答题卡归档) | 4 | 4 | 75.00% | 100.00% | 89.47% | 8 | 0 | 8 | 1 |
| overflow (涂超出答题卡归档) | 4 | 4 | 100.00% | 100.00% | 100.00% | 0 | 0 | 0 | 0 |

## 明细

### weak (淡涂答题卡归档)

- 结果 CSV: `outputs\weak_20260803_015434\Results\Results_09AM.csv`
- 场景命名结果 CSV: `outputs\Results\weak_淡涂答题卡归档_Results.csv`
- 审核 CSV: `outputs\weak_20260803_015434\Results\WeakFillReview.csv`
- 场景命名审核 CSV: `outputs\Results\weak_淡涂答题卡归档_WeakFillReview.csv`
- ID: 79/80 = 98.75%
- 题目: 107/110 = 97.27%
- 总体: 186/190 = 97.89%
- fallback/review 事件: `{'Weak identifier fallback': 11, 'Weak mark fallback': 0, 'Weak multi-mark fallback': 0, 'Weak multi full-select fallback': 0, 'Weak mark candidate review': 3, 'Single-choice conflict': 0}`
- 审核记录数: 20
- 审核状态统计: `LEGACY=3, LOW_CONFIDENCE=1, RESOLVED_CANDIDATE=11, REVIEW=5`
- 审核类型统计: `ID_REVIEW=12, SINGLE_CHOICE_CONFLICT_REVIEW=5, WEAK_MARK_REVIEW=3`
- 空白单元格:
  - `MX-M3658N_20260731_162311_001.png` `q5`
  - `MX-M3658N_20260731_162311_004.png` `id7`
  - `MX-M3658N_20260731_162311_008.png` `q3`
  - `MX-M3658N_20260731_162311_009.png` `q6`

#### 审核识别结果

| file_id | 类型 | 字段 | 原值 | 候选值 | 置信度 | 状态 | 原因 |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| `MX-M3658N_20260731_162311_001.png` | ID_REVIEW | id7 | `` | `1` | 0.663 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_001.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q1 | `ABCD` | `C` | 0.879 | REVIEW | single_choice_conflict |
| `MX-M3658N_20260731_162311_001.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q2 | `ABD` | `A` | 0.800 | REVIEW | single_choice_conflict |
| `MX-M3658N_20260731_162311_001.png` | WEAK_MARK_REVIEW | q5 | `` | `D` | 0.631 | LEGACY | score_disabled |
| `MX-M3658N_20260731_162311_002.png` | ID_REVIEW | id1 | `` | `2` | 0.672 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_002.png` | ID_REVIEW | id2 | `` | `4` | 0.636 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_002.png` | ID_REVIEW | id3 | `` | `3` | 0.538 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_002.png` | ID_REVIEW | id5 | `` | `1` | 0.607 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_002.png` | ID_REVIEW | id6 | `` | `0` | 0.572 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_002.png` | ID_REVIEW | id7 | `` | `7` | 0.774 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_002.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q2 | `ABD` | `A` | 0.902 | REVIEW | single_choice_conflict |
| `MX-M3658N_20260731_162311_003.png` | ID_REVIEW | id2 | `` | `3` | 0.706 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_003.png` | ID_REVIEW | id7 | `` | `1` | 0.669 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_003.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q2 | `ABD` | `B` | 0.876 | REVIEW | single_choice_conflict |
| `MX-M3658N_20260731_162311_004.png` | ID_REVIEW | id5 | `` | `4` | 0.662 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_004.png` | ID_REVIEW | id6 | `` | `8` | 0.766 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_004.png` | ID_REVIEW | id7 | `` | `4` | 0.472 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_162311_004.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q2 | `ABCD` | `A` | 0.735 | REVIEW | single_choice_conflict |
| `MX-M3658N_20260731_162311_008.png` | WEAK_MARK_REVIEW | q3 | `` | `B` | 0.249 | LEGACY | score_disabled |
| `MX-M3658N_20260731_162311_009.png` | WEAK_MARK_REVIEW | q6 | `` | `D` | 0.377 | LEGACY | score_disabled |

### normal (正常填涂测试答题卡归档)

- 结果 CSV: `outputs\normal\Results\Results_09AM.csv`
- 场景命名结果 CSV: `outputs\Results\normal_正常填涂测试答题卡归档_Results.csv`
- 审核 CSV: `outputs\normal\Results\WeakFillReview.csv`
- 场景命名审核 CSV: `outputs\Results\normal_正常填涂测试答题卡归档_WeakFillReview.csv`
- ID: 448/448 = 100.00%
- 题目: 616/616 = 100.00%
- 总体: 1064/1064 = 100.00%
- fallback/review 事件: `{'Weak identifier fallback': 1, 'Weak mark fallback': 0, 'Weak multi-mark fallback': 0, 'Weak multi full-select fallback': 2, 'Weak mark candidate review': 0, 'Single-choice conflict': 0}`
- 审核记录数: 4
- 审核状态统计: `RESOLVED_CANDIDATE=1, REVIEW=3`
- 审核类型统计: `ID_REVIEW=1, SINGLE_CHOICE_CONFLICT_REVIEW=3`
- 空白单元格: 无

#### 审核识别结果

| file_id | 类型 | 字段 | 原值 | 候选值 | 置信度 | 状态 | 原因 |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| `MX-M3658N_20260731_160125_005.png` | ID_REVIEW | id8 | `` | `6` | 0.902 | RESOLVED_CANDIDATE | weak_identifier_candidate |
| `MX-M3658N_20260731_160125_016.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q4 | `CD` | `D` | 0.464 | REVIEW | single_choice_conflict |
| `MX-M3658N_20260731_160125_021.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q2 | `AC` | `C` | 0.469 | REVIEW | single_choice_conflict |
| `MX-M3658N_20260731_160125_026.png` | SINGLE_CHOICE_CONFLICT_REVIEW | q1 | `AC` | `A` | 0.452 | REVIEW | single_choice_conflict |

### underfill (没涂满答题卡归档)

- 结果 CSV: `outputs\underfill\Results\Results_09AM.csv`
- 场景命名结果 CSV: `outputs\Results\underfill_没涂满答题卡归档_Results.csv`
- 审核 CSV: `outputs\underfill\Results\WeakFillReview.csv`
- 场景命名审核 CSV: `outputs\Results\underfill_没涂满答题卡归档_WeakFillReview.csv`
- ID: 24/32 = 75.00%
- 题目: 44/44 = 100.00%
- 总体: 68/76 = 89.47%
- fallback/review 事件: `{'Weak identifier fallback': 0, 'Weak mark fallback': 1, 'Weak multi-mark fallback': 0, 'Weak multi full-select fallback': 0, 'Weak mark candidate review': 0, 'Single-choice conflict': 0}`
- 审核记录数: 8
- 审核状态统计: `LOW_CONFIDENCE=8`
- 审核类型统计: `ID_REVIEW=8`
- 空白单元格:
  - `MX-M3658N_20260731_164536_004.png` `id1`
  - `MX-M3658N_20260731_164536_004.png` `id2`
  - `MX-M3658N_20260731_164536_004.png` `id3`
  - `MX-M3658N_20260731_164536_004.png` `id4`
  - `MX-M3658N_20260731_164536_004.png` `id5`
  - `MX-M3658N_20260731_164536_004.png` `id6`
  - `MX-M3658N_20260731_164536_004.png` `id7`
  - `MX-M3658N_20260731_164536_004.png` `id8`

#### 审核识别结果

| file_id | 类型 | 字段 | 原值 | 候选值 | 置信度 | 状态 | 原因 |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id1 | `` | `8` | 0.160 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id2 | `` | `8` | 0.140 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id3 | `` | `8` | 0.152 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id4 | `` | `9` | 0.104 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id5 | `` | `8` | 0.115 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id6 | `` | `8` | 0.066 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id7 | `` | `8` | 0.098 | LOW_CONFIDENCE | weak_identifier_candidate |
| `MX-M3658N_20260731_164536_004.png` | ID_REVIEW | id8 | `` | `8` | 0.183 | LOW_CONFIDENCE | weak_identifier_candidate |

### overflow (涂超出答题卡归档)

- 结果 CSV: `outputs\overflow\Results\Results_09AM.csv`
- 场景命名结果 CSV: `outputs\Results\overflow_涂超出答题卡归档_Results.csv`
- 审核 CSV: `outputs\overflow\Results\WeakFillReview.csv`
- 场景命名审核 CSV: `无`
- ID: 32/32 = 100.00%
- 题目: 44/44 = 100.00%
- 总体: 76/76 = 100.00%
- fallback/review 事件: `{'Weak identifier fallback': 0, 'Weak mark fallback': 0, 'Weak multi-mark fallback': 0, 'Weak multi full-select fallback': 0, 'Weak mark candidate review': 0, 'Single-choice conflict': 0}`
- 审核记录数: 0
- 审核状态统计: `无`
- 审核类型统计: `无`
- 空白单元格: 无
- 审核识别结果: 无
