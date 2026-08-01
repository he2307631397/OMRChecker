# inputs PDF 识别配置说明

本目录已按当前 A4 单页 PDF 答题卡配置 OMRChecker。

## 覆盖范围

当前 `template.json` 识别以下涂卡区域：

- 准考证号：8 位数字，输出列 `id1` 到 `id8`
- 单选题：`q1` 到 `q8`，选项 A-D
- 多选题：`q9` 到 `q11`，选项 A-D，输出可能为组合值，例如 `AC`、`BD`

以下区域不是标准涂卡区，当前未配置自动识别：

- 姓名、班级手写内容
- 填空题手写答案
- 解答题手写答案
- 手写得分

## PDF 参数

`config.json` 中使用：

```json
"pdf_params": {
  "pdf_dpi": 144,
  "pdf_page": 1
}
```

当前 PDF 均为单页 A4，未加密，因此只处理第 1 页。

## 浅涂补救

当前 `config.json` 已启用 `weak_mark_params`，用于补救单选题中明显比其他选项更深、但没有达到常规阈值的浅涂。

当前策略：

- 只对 `QTYPE_MCQ4` 单选题生效
- 只在原识别结果为空时尝试补救
- 最深选项必须比次深选项至少深 `10` 个灰度点
- 最深选项均值必须不高于 `215`
- `q9`、`q10`、`q11` 是多选题，不使用单选弱判
- `q9`、`q10`、`q11` 已启用多选弱填涂补救，会基于本题空白基线追加明显更深的弱填涂选项

## 运行命令

在项目根目录执行：

```bash
python main.py --inputDir inputs --outputDir outputs_inputs_pdf
```

结果文件位于：

```text
outputs_inputs_pdf/Results/Results_*.csv
```

标注后的检测图位于：

```text
outputs_inputs_pdf/CheckedOMRs/
```

## 注意事项

1. 本模板基于当前 PDF 版式和 144 DPI 渲染尺寸 `1190x1682` 配置。
2. 如果后续扫描版式、缩放比例或题目位置变化，需要重新校准 `template.json` 中的坐标。
3. 若要计算分数，需要另外提供 `evaluation.json` 或答案配置。
