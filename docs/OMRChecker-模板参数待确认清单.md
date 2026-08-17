# OMRChecker 模板参数待确认清单

本文档用于前端答题卡设计器与 OMRChecker 服务对齐模板参数语义，并作为前端把现有模板数据转换为 OMRChecker 可稳定识别参数的修改清单。

参考文档：

- `docs/omr-recognition-parameters.md`
- `docs/robyn-web-service.md`

## 1. 当前已确认的 OMRChecker 参数语义

以下结论来自 OMRChecker 当前代码和本地识别复现。

### 1.1 坐标系

| 参数 | OMRChecker 需要的语义 | 单位 | 前端需要确认/修改 |
| --- | --- | --- | --- |
| `pageDimensions` | `[pageWidth, pageHeight]`，模板坐标所在页面尺寸 | px | 必须等于 PDF 按 `pdfDpi` 渲染后、识别 resize 到的尺寸。 |
| `config.dimensions.processing_width` / `processing_height` | 识别前统一处理尺寸 | px | 必须和 `pageDimensions` 一致。 |
| `fieldBlocks.*.origin` | 第一个气泡采样框左上角，不是中心点 | px | 如果前端保存的是气泡中心点，需要转换为左上角。 |
| `fieldBlockOcrs.*.origin` | OCR 裁剪区域左上角 | px | 确认前端传的是区域左上角。 |
| `regions[].bbox` | 归档区域 `[x, y, width, height]` | px | 确认来自同一 PDF 渲染坐标系。 |
| `markerConfig.bbox` | marker 裁剪区域 `[x, y, width, height]` | px | 确认来自模板 PDF 按 `markerConfig.pdfDpi` 渲染后的坐标系。 |

坐标原点是页面左上角，`x` 向右增加，`y` 向下增加。

### 1.2 fieldBlocks 气泡网格语义

OMRChecker 会把 `origin` 直接作为第一个气泡采样框左上角，然后按 `fieldType` 的方向展开。

相关代码语义：

```text
QTYPE_INT      direction = vertical
QTYPE_MCQ4     direction = horizontal

bubble_point starts at origin
for each fieldLabel:
  for each bubbleValue:
    add Bubble at bubble_point
    bubble_point[direction_axis] += bubblesGap
  lead_point[cross_axis] += labelsGap
```

| fieldType | `bubbleValues` | 展开方向 | `bubblesGap` 含义 | `labelsGap` 含义 |
| --- | --- | --- | --- | --- |
| `QTYPE_MCQ4` | `A,B,C,D` | horizontal | A/B/C/D 相邻采样框左上角的水平间距 | 多个题号之间的垂直间距。单题单 `fieldLabel` 时不生效。 |
| `QTYPE_INT` | `0,1,2,3,4,5,6,7,8,9` | vertical | 同一号码列内相邻数字采样框左上角的垂直间距 | 相邻号码列采样框左上角的水平间距。 |
| `QTYPE_INT_FROM_1` | `1,2,3,4,5,6,7,8,9,0` | vertical | 同上 | 同上 |

> 重点：准考证号 `QTYPE_INT` 中，`bubblesGap` 是数字行垂直间距，`labelsGap` 是号码列水平间距。前端如果把二者传反，会导致准考证号采样框串列或落空白。

### 1.3 bubbleDimensions 语义

| 参数 | OMRChecker 需要的语义 | 单位 | 说明 |
| --- | --- | --- | --- |
| `bubbleDimensions` | 每个气泡采样框 `[width, height]` | px | 识别时直接裁取 `[x:x+width, y:y+height]` 计算灰度和密度。 |

OMRChecker 的部分弱识别特征会再看中心区域密度，但基础采样框仍由 `origin + bubbleDimensions` 决定。

前端建议：

- 如果前端保存的是气泡视觉外接框，可以先按外接框传。
- 如果边框线或文字干扰明显，可以将采样框适当向内收缩，但收缩后 `origin` 也要同步调整。
- 不要把 `origin` 当中心点传。否则采样框会整体右下偏移半个气泡尺寸。

### 1.4 pdf_page 语义

| 参数 | OMRChecker 需要的语义 | 单位/类型 | 前端需要确认/修改 |
| --- | --- | --- | --- |
| `config.pdf_params.pdf_page` | 要识别的 PDF 页码 | 1-based 页码 | 不等于模板总页数。单页传 `1`。 |
| `markerConfig.pdfPage` | 用于生成 marker/reference 的模板 PDF 页码 | 1-based 页码 | 应与模板坐标所在页一致。 |
| `referenceConfig.pdfPage` | 用于生成 reference 的模板 PDF 页码 | 1-based 页码 | 应与模板坐标所在页一致。 |

> 当前如果前端把 `pageCount` 写入 `pdf_page`，多页模板会有风险。`pdf_page=2` 表示识别第 2 页，不表示总页数为 2。

### 1.5 marker/reference 和 CropOnMarkers

| 参数 | 当前 OMRChecker 行为 | 前端需要确认/修改 |
| --- | --- | --- |
| `markerConfig` | 生成 `marker.png`。如果没有 `referenceConfig`，也会同页生成 `reference.png`。 | 可以继续传。 |
| `markerConfig.enableCropOnMarkers` | 默认 `false`。只有显式 `true` 才把 marker 接入 `CropOnMarkers`。 | 当前阶段保持 `false` 或不传。 |
| `FeatureBasedAlignment` | 使用 `reference.png` 对齐，输出尺寸为 reference resize 到 `processing_width/height` 后的尺寸。 | 推荐默认使用。 |
| `CropOnMarkers` | 会根据四角 marker 做透视裁切，输出页面坐标系会变化。 | 当前前端坐标来自原始 PDF 页面时不要启用。 |

当前推荐：前端只提供左上 marker bbox 和模板 PDF key，由 OMRChecker 生成 `marker.png/reference.png`。不要让前端上传 `marker.png/reference.png`。

## 2. 前端需要确认并修改的清单

### 2.1 坐标单位和 DPI

- [ ] 前端所有导出的 `x/y/width/height` 是否都是 PDF 按 `pdfDpi` 渲染后的 px。
- [ ] 前端生成 `pageDimensions` 时是否使用 `[renderedPdfWidthPx, renderedPdfHeightPx]`。
- [ ] `config.dimensions.processingWidth/processingHeight` 是否与 `templateConfig.pageDimensions` 完全一致。
- [ ] `markerConfig.bbox` 是否和 `templateConfig.fieldBlocks` 使用同一个 DPI 下的坐标。
- [ ] 非 144 DPI 模板是否显式传 `markerConfig.pdfDpi` 和 `referenceConfig.pdfDpi`。

### 2.2 fieldBlocks.origin

OMRChecker 需要：

```json
"origin": [firstBubbleLeft, firstBubbleTop]
```

如果前端当前保存的是气泡中心：

```js
origin = [centerX, centerY]
```

需要改为：

```js
origin = [
  Math.round(centerX - bubbleWidth / 2),
  Math.round(centerY - bubbleHeight / 2)
]
```

需要确认：

- [ ] 选择题 `QTYPE_MCQ4` 的 `origin` 是否已从中心点改为左上角。
- [ ] 准考证号 `QTYPE_INT` 的 `origin` 是否已从中心点改为第一列数字 0 采样框左上角。
- [ ] 如果前端保存的是外接框左上角，则不要重复减半个气泡尺寸。

### 2.3 选择题 QTYPE_MCQ4

OMRChecker 需要：

```json
{
  "fieldType": "QTYPE_MCQ4",
  "fieldLabels": ["q1"],
  "origin": [firstOptionLeft, firstOptionTop],
  "bubbleDimensions": [bubbleWidth, bubbleHeight],
  "bubblesGap": optionHorizontalGap,
  "labelsGap": 0,
  "multiSelect": false
}
```

前端需要确认：

- [ ] `origin` 是 A 选项采样框左上角。
- [ ] `bubblesGap` 是 A 到 B 采样框左上角的水平间距，不是题块间距。
- [ ] 单题单 `fieldLabel` 时 `labelsGap` 可以传 `0` 或小值，不参与识别。
- [ ] 多选题设置 `multiSelect: true`。
- [ ] 多选题仍可用 `QTYPE_MCQ4`，只是 `multiSelect` 为 true。

### 2.4 准考证号 QTYPE_INT

OMRChecker 需要：

```json
{
  "fieldType": "QTYPE_INT",
  "fieldLabels": ["id1..8"],
  "origin": [firstColumnDigit0Left, firstColumnDigit0Top],
  "bubbleDimensions": [bubbleWidth, bubbleHeight],
  "bubblesGap": digitVerticalGap,
  "labelsGap": columnHorizontalGap
}
```

前端需要确认：

- [ ] `origin` 是第一列数字 `0` 的采样框左上角。
- [ ] `bubblesGap` 是同一列数字 `0 -> 1` 的垂直间距。
- [ ] `labelsGap` 是相邻准考证号列 `id1 -> id2` 的水平间距。
- [ ] `fieldLabels` 使用 `id1..8` 时，OMRChecker 会按 `labelsGap` 展开 8 列。
- [ ] 如果模板视觉顺序是 1 到 9 再 0，可使用 `QTYPE_INT_FROM_1`，否则使用 `QTYPE_INT`。

如果当前前端逻辑是：

```js
bubblesGap = colGap
labelsGap = rowGap
```

需要改为：

```js
bubblesGap = rowGap
labelsGap = colGap
```

### 2.5 OCR 区域 fieldBlockOcrs

前端需要确认：

- [ ] `origin` 是 OCR 区域左上角。
- [ ] `dimensions` 是 OCR 区域宽高，单位 px。
- [ ] `fieldLabels` 中每个 OCR block 只对应一个输出字段。
- [ ] `regionCode`、`regionName`、`type` 能满足业务归档和结果展示。
- [ ] 需要归档裁图的区域设置 `ocr.archiveRegion: true`。

### 2.6 regions 归档区域

前端需要确认：

- [ ] `regions[].bbox` 为 `[x, y, width, height]`，单位 px。
- [ ] bbox 坐标和 `pageDimensions` 使用同一坐标系。
- [ ] 不要把中心点或右下角坐标误传成 width/height。
- [ ] `regionCode` 能和题号/业务字段稳定对应。

### 2.7 markerConfig

推荐前端输出：

```json
{
  "markerConfig": {
    "sourcePdfOsskey": "template-assets/sheet-template.pdf",
    "pdfPage": 1,
    "pdfDpi": 144,
    "bbox": [48, 52, 36, 28],
    "outputName": "marker.png",
    "enableCropOnMarkers": false
  }
}
```

前端需要确认：

- [ ] `sourcePdfOsskey` 最终传到 OMRChecker 时不能为空。
- [ ] `pdfPage` 是模板坐标所在页，单页为 `1`。
- [ ] `pdfDpi` 和前端导出坐标 DPI 一致。
- [ ] `bbox` 只框住 marker 本体和少量白边，不包含题干、长横线、表格线。
- [ ] 当前阶段 `enableCropOnMarkers` 不传或传 `false`。

### 2.8 preProcessors

当前推荐由 OMRChecker 根据 `markerConfig` 自动生成/补齐：

```json
{
  "name": "FeatureBasedAlignment",
  "options": {
    "reference": "reference.png",
    "2d": true,
    "goodMatchPercent": 0.25,
    "maxFeatures": 2000
  }
}
```

前端需要确认：

- [ ] 不再直接上传或指定 `reference.png` URL，除非特殊模板需要覆盖。
- [ ] 不主动写入 `CropOnMarkers`。
- [ ] 如果历史模板中已有 `CropOnMarkers`，需要移除或确保 `enableCropOnMarkers=false` 时不会生成。
- [ ] 如果历史模板中已有 `FeatureBasedAlignment.reference` 指向远程 URL，确认 OMRChecker 会生成并覆盖为本地 `reference.png`。

## 3. 建议前端转换规则

### 3.1 通用坐标转换

如果设计器内部保存的是中心点：

```ts
type CenterBubble = {
  centerX: number
  centerY: number
  width: number
  height: number
}

function toOmrTopLeft(b: CenterBubble): [number, number] {
  return [
    Math.round(b.centerX - b.width / 2),
    Math.round(b.centerY - b.height / 2)
  ]
}
```

如果设计器内部保存的是左上角，直接传左上角，不要再转换。

### 3.2 QTYPE_MCQ4 转换

```ts
const fieldBlock = {
  fieldType: 'QTYPE_MCQ4',
  fieldLabels: [`q${questionNo}`],
  origin: toOmrTopLeft(firstOptionBubble),
  bubbleDimensions: [bubbleWidthPx, bubbleHeightPx],
  bubblesGap: optionB.left - optionA.left,
  labelsGap: 0,
  multiSelect: isMultiSelect
}
```

如果 `optionB.left` 不可直接获得，但有中心点：

```ts
bubblesGap = optionB.centerX - optionA.centerX
```

前提是 A/B/C/D 气泡尺寸一致。中心距等于左上角距。

### 3.3 QTYPE_INT 转换

```ts
const fieldBlock = {
  fieldType: 'QTYPE_INT',
  fieldLabels: [`id1..${digits}`],
  origin: toOmrTopLeft(firstColumnDigit0Bubble),
  bubbleDimensions: [bubbleWidthPx, bubbleHeightPx],
  bubblesGap: digit1.top - digit0.top,
  labelsGap: column2.left - column1.left
}
```

如果只有中心点：

```ts
bubblesGap = digit1.centerY - digit0.centerY
labelsGap = column2.centerX - column1.centerX
```

前提是所有数字气泡尺寸一致。

## 4. 前端需要给 OMRChecker 的最终结构示例

```json
{
  "templateCode": "exam_sheet_template_101",
  "schemaVersion": "v1",
  "recognitionConfig": {
    "debugArtifacts": false,
    "config": {
      "dimensions": {
        "processingWidth": 1190,
        "processingHeight": 1682,
        "displayWidth": 1190,
        "displayHeight": 1682
      },
      "pdfParams": {
        "pdfDpi": 144,
        "pdfPage": 1
      },
      "alignmentParams": {
        "autoAlign": false
      }
    },
    "templateConfig": {
      "pageDimensions": [1190, 1682],
      "fieldBlocks": {
        "ExamId": {
          "fieldType": "QTYPE_INT",
          "fieldLabels": ["id1..8"],
          "origin": [833, 385],
          "bubbleDimensions": [28, 16],
          "bubblesGap": 26,
          "labelsGap": 38
        },
        "Q1": {
          "fieldType": "QTYPE_MCQ4",
          "fieldLabels": ["q1"],
          "origin": [132, 717],
          "bubbleDimensions": [28, 16],
          "bubblesGap": 36,
          "labelsGap": 0
        }
      }
    }
  },
  "markerConfig": {
    "sourcePdfOsskey": "template-assets/sheet-template.pdf",
    "pdfPage": 1,
    "pdfDpi": 144,
    "bbox": [48, 52, 36, 28],
    "outputName": "marker.png",
    "enableCropOnMarkers": false
  }
}
```

## 5. 验收标准

前端修改完成后，应满足：

- [ ] 随机抽一题选择题，OMRChecker 的采样框覆盖 A/B/C/D 气泡本体。
- [ ] 随机抽一列准考证号，10 个数字采样框沿垂直方向排列。
- [ ] 准考证号相邻列沿水平方向排列，列间距等于 `labelsGap`。
- [ ] `CheckedOMR` 中 q1/q2/q3/q4 不再落到纯白区域。
- [ ] 日志中不再大量出现同一题 `darkest_mean=255, density=0`。
- [ ] 单页 PDF 的 `pdf_page` 为 `1`。
- [ ] `reference.png`、`pageDimensions`、`processingWidth/Height` 尺寸一致或仅存在 OMRChecker 可接受的 1 到 2 px resize 差异。
- [ ] 批量识别不产生 `ErrorFiles` 和 `MultiMarkedFiles`。

## 6. 当前优先级

前端优先修改顺序：

1. 把 `fieldBlocks.origin` 统一为采样框左上角。
2. 修正 `QTYPE_INT.bubblesGap` 和 `QTYPE_INT.labelsGap` 方向。
3. 修正 `pdf_params.pdf_page`，不要传总页数。
4. 确保 `markerConfig.pdfPage/pdfDpi/sourcePdfOsskey` 完整。
5. 保持 `enableCropOnMarkers=false`。
6. 坐标修正后再考虑弱识别阈值。