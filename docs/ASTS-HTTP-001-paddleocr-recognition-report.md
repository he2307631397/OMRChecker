# ASTS-HTTP-001 PaddleOCR 批量识别与 OMR 回归报告

生成时间: 2026-08-08 20:06 本地时间

## 1. 环境与版本

- 分支: `paddlocr-integration`
- OCR 环境: `.venv-ocr-prod`
- Python: 3.12
- PaddlePaddle: `3.2.0`
- PaddleOCR: `3.7.0`
- 运行方式: CPU-only PaddleOCR, 无 GPU/CUDA/cuDNN 依赖
- 当前模板: `config/ASTS-HTTP-001/v1/template.json`
- 当前配置: `config/ASTS-HTTP-001/v1/config.json`

## 2. 批量 OCR 验证

### 输入

- 数据集: `/Volumes/wdata/work/tech/OMRChecker/docs/assets/自制模板1/正常填涂测试答题卡归档`
- PDF 数量: 56

### 输出

- 输出目录: `outputs/ASTS-HTTP-001-ocr-full-current/`
- 主结果 CSV: `outputs/ASTS-HTTP-001-ocr-full-current/Results/Results_08PM.csv`
- OCR 明细 CSV: `outputs/ASTS-HTTP-001-ocr-full-current/Results/OcrResults.csv`
- CheckedOMRs: `outputs/ASTS-HTTP-001-ocr-full-current/CheckedOMRs/`
- CheckedOMR 图片数: 56
- OCR 明细行数: 336

备注: 当前 `config.json` 中 `outputs.save_image_level=0`，因此本次未生成 `RegionArtifacts` 裁剪图。CSV 识别结果完整。如需人工审核大图裁剪归档，可将保存级别调高后单独跑一次归档产物。

### OCR 字段统计，正常填涂 56 份

| 字段 | 非空 | 空值 | 主要识别值分布 | 置信度均值 |
|---|---:|---:|---|---:|
| `fill_blank_score_text` | 40 | 16 | 14×9, 13×7, 12×4, 15×3, 11×3, 8×3, 5×2, 9×2, 3×1, 7/×1, 16×1, B×1, 6×1, 7×1, 10×1 | 0.694030 |
| `q14_score_text` | 40 | 16 | 18×7, 17×6, 15×5, 19×4, 14×4, 16×3, 12×3, 13×2, 11×1, 1×1, 7×1, 9×1, 10×1, 20×1 | 0.711752 |
| `fill_q12_answer_text` | 0 | 56 | 无 | 0.000000 |
| `fill_q13_answer_text` | 0 | 56 | 无 | 0.000000 |
| `fill_q14_answer_text` | 0 | 56 | 无 | 0.000000 |
| `solution_q14_answer_text` | 0 | 56 | 无 | 0.000000 |

结论:

- 分数类小框识别效果稳定，正常填涂 56 份中 `fill_blank_score_text` 和 `q14_score_text` 均有 40 份非空。
- 主观答案文本区域在当前样本集全部为空，和人工观察一致，样本区域没有明显手写答案内容。
- 发现少量待人工复核值: `fill_blank_score_text` 中有 `7/` 和 `B`。建议业务侧对分数字段加数字白名单或人工复核规则。

## 3. OMR 回归验证

本次使用当前 ASTS 模板对四类真实归档执行识别。由于旧脚本默认查找 `docs/assets/淡涂答题卡归档`，而当前仓库实际路径为 `docs/assets/自制模板1/淡涂答题卡归档`，已改用实际可用路径手动补跑，不修改业务代码。

### 场景汇总

| 场景 | 输入 PDF | 输出目录 | 结果行数 | CheckedOMRs | OMR 单元格 | 空 OMR 单元格 | 非空率 |
|---|---:|---|---:|---:|---:|---:|---:|
| 正常填涂 | 56 | `outputs/ASTS-HTTP-001-ocr-full-current/` | 56 | 56 | 1064 | 0 | 100.00% |
| 淡涂 | 10 | `outputs/ASTS-HTTP-001-reg-weak-current/` | 10 | 10 | 190 | 3 | 98.42% |
| 没涂满 | 4 | `outputs/ASTS-HTTP-001-reg-underfill-current/` | 4 | 4 | 76 | 8 | 89.47% |
| 涂超出 | 4 | `outputs/ASTS-HTTP-001-reg-overflow-current/` | 4 | 4 | 76 | 0 | 100.00% |

说明:

- OMR 单元格统计范围: `id1` 到 `id8`，`q1` 到 `q11`。
- OCR 字段不计入 OMR 回归空值率。
- 正常填涂和涂超出场景 OMR 字段无空值。
- 淡涂、没涂满场景出现少量空值符合弱填涂/未涂满样本的业务属性，日志也显示弱填涂候选被拒绝或 fallback 复核事件。

## 4. 目标测试与静态检查

已执行命令:

```bash
.venv-ocr-prod/bin/python -m pytest src/tests/test_ocr_engine.py src/tests/test_region_artifacts.py src/tests/test_template_engine_blocks.py -q
rtk git diff --check
rtk git status --short
```

结果:

- 命令 exit code: 0
- 目标测试通过: 22 个测试通过
- `git diff --check`: 通过
- `git status --short`: 无未提交改动

## 5. 综合结论

1. 56 份正常填涂 ASTS 批量 OCR 处理完成，主结果和 OCR 明细 CSV 均已生成。
2. CPU-only PaddleOCR 3.7.0 在真实 PDF 批量处理链路中运行稳定。
3. 小框分数字段识别结果质量好，`fill_blank_score_text` 和 `q14_score_text` 是当前最有业务价值的 OCR 输出。
4. 主观答案字段在当前样本集中为空，属于样本内容问题，不是批处理失败。
5. OMR 回归四场景共 74 份完成，其中正常填涂与涂超出 OMR 非空率 100%，淡涂与没涂满保留弱填涂业务行为。
6. 当前 OCR 是 additive，不覆盖 OMR 区域，不使用 `regions.json`，顶层 `archiveRegions` 仅用于追加归档区域设计。
