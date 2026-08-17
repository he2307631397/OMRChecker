# OMRChecker 识别参数说明

本文说明批量识别接口和 OMRChecker 模板中常用的识别参数。目标读者是前端、后端网关和 OMRChecker 服务维护者。

## 1. 参数来源和坐标系

一次批量识别通常会合并三类参数：

| 来源 | 文件或字段 | 作用 |
| --- | --- | --- |
| 批量任务请求 | `recognitionConfig`、`markerConfig`、`referenceConfig` | 运行时覆盖模板、识别阈值、生成 `marker.png` / `reference.png`。 |
| 模板目录 | `config/<templateCode>/<schemaVersion>/template.json` | 答题卡页面尺寸、气泡区域、OCR 区域、预处理器。 |
| 模板目录 | `config/<templateCode>/<schemaVersion>/config.json` | PDF 渲染、阈值、弱填涂、输出、尺寸等运行参数。 |

所有前端提供的坐标默认都应处在同一个坐标系：**模板 PDF 按 `pdfDpi` 渲染后的像素坐标系**。

### 1.1 单位约定

除特别说明外，本文档中的长度、坐标、尺寸都使用 **像素 px**，坐标原点为处理图像左上角。

| 参数类型 | 单位 | 取值说明 |
| --- | --- | --- |
| 坐标 `x`、`y` | px | 从页面左上角开始计数，`x` 向右递增，`y` 向下递增。 |
| 区域宽高 `width`、`height` | px | 矩形区域尺寸，必须为正数。 |
| `origin` | px | `[x, y]`，字段或 OCR 区域左上角。 |
| `bbox` | px | `[x, y, width, height]`，左上角加宽高。 |
| `pageDimensions` | px | `[width, height]`，模板坐标对应页面尺寸。 |
| `processing_width` / `processing_height` | px | OMRChecker 识别前统一 resize 后的图像尺寸。 |
| `display_width` / `display_height` | px | 调试显示目标尺寸。 |
| `bubbleDimensions` | px | `[width, height]`，单个气泡采样框尺寸。 |
| `bubblesGap` | px | 同一字段内相邻气泡采样框起点之间的间距。 |
| `labelsGap` | px | 多个字段标签之间采样框起点的间距。 |
| `dimensions`，OCR 区域 | px | `[width, height]`，OCR 裁剪区域尺寸。 |
| `pdfDpi` / `pdf_dpi` | DPI | PDF 渲染分辨率，dots per inch。必须和前端坐标生成 DPI 一致。 |
| `pdfPage` / `pdf_page` | 页码 | 1-based 页码，第 1 页写 `1`。 |
| 灰度均值，例如 `max_mean` | 0-255 灰度值 | `0` 为黑，`255` 为白。数值越小表示越深。 |
| 灰度差，例如 `min_gap`、`min_delta_from_blank` | 0-255 灰度差 | 两个灰度均值之间的差。数值越大要求填涂越明显。 |
| 匹配比例，例如 `goodMatchPercent` | 比例 | 0 到 1 的小数，`0.25` 表示保留 25% 匹配点。 |
| 匹配分，例如 `min_matching_threshold` | 归一化分数 | 通常 0 到 1，越高表示模板匹配越严格。 |
| 数量，例如 `maxFeatures`、`max_marks` | 个 | 整数计数。 |
| 布尔开关 | boolean | `true` 或 `false`。 |

例如当前常见 A4 144 DPI 模板：

```json
{
  "pageDimensions": [1190, 1682],
  "pdfParams": {
    "pdfDpi": 144,
    "pdfPage": 1
  }
}
```

如果启用会裁切或透视页面的预处理器，例如 `CropOnMarkers`，处理后的页面坐标系会变化。此时模板中的所有气泡和 OCR 坐标也必须同步基于处理后的页面重新校准。否则会出现 marker 截图准确，但气泡识别区域整体偏移的问题。

## 2. 批量接口参数

批量接口见 `docs/robyn-web-service.md`。识别相关参数主要在 `recognitionConfig`、顶层 `markerConfig` 和顶层 `referenceConfig` 中。

### 2.1 markerConfig

`markerConfig` 可以放在请求顶层，也可以放在 `recognitionConfig.markerConfig`。

```json
{
  "markerConfig": {
    "sourcePdfOsskey": "template-assets/sheet-template.pdf",
    "pdfPage": 1,
    "pdfDpi": 144,
    "bbox": [40, 52, 40, 28],
    "outputName": "marker.png",
    "enableCropOnMarkers": false
  }
}
```

| 字段 | 必填 | 默认值 | 单位/类型 | 说明 |
| --- | --- | --- | --- | --- |
| `sourcePdfOsskey` | 是 | 无 | 字符串 | 模板 PDF 的 OSS key。OMRChecker 会下载并渲染此 PDF。 |
| `pdfPage` | 否 | `1` | 页码，1-based | 必须和答题卡模板实际识别页一致。 |
| `pdfDpi` | 否 | `144` | DPI | 渲染分辨率。必须和前端生成坐标时使用的 DPI 一致。 |
| `bbox` | 是 | 无 | px，`[x, y, width, height]` | 从渲染后的模板 PDF 中裁出 marker。 |
| `outputName` | 否 | `marker.png` | 字符串 | 生成的 marker 文件名。 |
| `enableCropOnMarkers` | 否 | `false` | boolean | 是否把生成的 marker 自动接入 `CropOnMarkers`。默认关闭。 |
| `preProcessorOptions` | 否 | `{}` | object | 传给 `CropOnMarkers` 的高级参数，仅在 `enableCropOnMarkers=true` 时有意义。 |

当前推荐：**前端传 `markerConfig`，OMRChecker 生成 `marker.png` 和 `reference.png`，但默认只接入 `FeatureBasedAlignment`，不启用 `CropOnMarkers`。**

`enableCropOnMarkers=true` 只适用于模板坐标已经基于 Crop 后页面重新校准的场景。

### 2.2 referenceConfig

`referenceConfig` 可以放在请求顶层，也可以放在 `recognitionConfig.referenceConfig`。如果不传，且传了 `markerConfig`，OMRChecker 会默认从 `markerConfig.sourcePdfOsskey` 同页生成 `reference.png`。

```json
{
  "referenceConfig": {
    "sourcePdfOsskey": "template-assets/sheet-template.pdf",
    "pdfPage": 1,
    "pdfDpi": 144,
    "outputName": "reference.png"
  }
}
```

| 字段 | 必填 | 默认值 | 单位/类型 | 说明 |
| --- | --- | --- | --- | --- |
| `sourcePdfOsskey` | 是 | 无 | 字符串 | 用于生成 reference 的 PDF OSS key。 |
| `pdfPage` | 否 | `1` | 页码，1-based | 第 1 页写 `1`。 |
| `pdfDpi` | 否 | `144` | DPI | PDF 渲染分辨率。 |
| `outputName` | 否 | `reference.png` | 字符串 | 生成的 reference 文件名。 |

`reference.png` 用于 `FeatureBasedAlignment`，它应表示和模板坐标一致的完整页面。不要用已经裁切或缩放过的图，除非模板坐标也是基于同样处理后的图生成的。

## 3. config.json 参数

`config.json` 控制 OMRChecker 运行时行为。通过 Java/HTTP 请求传入时可以使用 camelCase，OMRChecker 会归一化为 snake_case 运行配置。

### 3.1 dimensions

```json
{
  "dimensions": {
    "display_width": 1190,
    "display_height": 1682,
    "processing_width": 1190,
    "processing_height": 1682
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `processing_width` / `processing_height` | px | 实际识别前统一 resize 到的尺寸。模板坐标必须匹配这个尺寸。 |
| `display_width` / `display_height` | px | 调试显示尺寸。通常与 processing 尺寸一致。 |

如果输入 PDF 渲染尺寸和 `processing_*` 不一致，OMRChecker 会 resize。小于 1 到 2 像素的差异通常可接受，但模板坐标最好和最终 processing 尺寸严格一致。

### 3.2 pdf_params

```json
{
  "pdf_params": {
    "pdf_dpi": 144,
    "pdf_page": 1
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `pdf_dpi` | DPI | 输入 PDF 转图片的分辨率。必须和模板坐标、marker bbox、reference 生成 DPI 一致。 |
| `pdf_page` | 页码，1-based | 识别 PDF 的页码。单页 PDF 应为 `1`。 |

常见问题：模板 PDF 和学生答题 PDF 不是同一页，或者 `pdf_page=2` 但输入 PDF 只有 1 页，会导致识别内容完全错位或失败。

### 3.3 alignment_params

```json
{
  "alignment_params": {
    "auto_align": false
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `auto_align` | boolean | 旧的自动对齐开关。当前批量任务建议依赖 `preProcessors` 中的 `FeatureBasedAlignment`。 |

## 4. template.json 参数

`template.json` 描述页面上每个字段的位置和类型。

### 4.1 pageDimensions

```json
{
  "pageDimensions": [1190, 1682]
}
```

表示模板坐标使用的页面宽高。应与 `config.json.dimensions.processing_width/height` 一致。

### 4.2 fieldBlocks

客观题和准考证号等气泡区域使用 `fieldBlocks`。

```json
{
  "fieldBlocks": {
    "Q1": {
      "origin": [132, 717],
      "bubbleDimensions": [28, 16],
      "bubblesGap": 36,
      "labelsGap": 2,
      "fieldLabels": ["q1"],
      "fieldType": "QTYPE_MCQ4"
    }
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `origin` | px，`[x, y]` | 第一个识别单元左上角坐标。不是题干坐标，也不是气泡中心点。 |
| `bubbleDimensions` | px，`[width, height]` | 每个气泡检测框的尺寸。 |
| `bubblesGap` | px | 同一个字段内相邻选项气泡采样框起点之间的间距。通常是横向 A/B/C/D 间距。 |
| `labelsGap` | px | 多个 fieldLabel 之间采样框起点的间距。准考证号多列识别时尤其关键。 |
| `fieldLabels` | string[] | 输出字段名。支持范围写法，例如 `id1..8`。 |
| `fieldType` | string | 识别类型，例如 `QTYPE_MCQ4`、`QTYPE_INT`。 |
| `multiSelect` | boolean | 是否允许多选。多选题应为 `true`。 |

常见 fieldType：

| 类型 | 用途 |
| --- | --- |
| `QTYPE_MCQ4` | A/B/C/D 四选项。 |
| `QTYPE_INT` | 0-9 数字列，常用于准考证号。 |

准考证号识别不稳定时，优先检查：

1. `origin` 是否落在第一列第一个数字气泡左上角。
2. `bubbleDimensions` 是否覆盖气泡主体且不要过大。
3. `bubblesGap` 是否等于同列 0 到 1、1 到 2 的垂直间距或对应模板定义方向的选项间距。
4. `labelsGap` 是否等于相邻号码列的水平间距。

如果 `labelsGap` 太小，会出现多列采样框挤在一起，导致准考证号弱识别或串列。

### 4.3 fieldBlockOcrs

主观题、填空题、分数框等 OCR 区域使用 `fieldBlockOcrs`。

```json
{
  "fieldBlockOcrs": {
    "FillQ12AnswerOcr": {
      "origin": [92, 1041],
      "dimensions": [322, 56],
      "fieldLabels": ["fill_q12_answer_text"],
      "type": "answer",
      "regionCode": "Q12",
      "regionName": "第12题填空题",
      "ocr": {
        "lang": "ch",
        "archiveRegion": true
      }
    }
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `origin` | px，`[x, y]` | OCR 区域左上角。 |
| `dimensions` | px，`[width, height]` | OCR 区域宽高。 |
| `fieldLabels` | string[] | OCR 输出字段名。 |
| `type` | string | 业务类型，例如 `answer`、`score`。 |
| `regionCode` / `regionName` | string | 归档和业务展示用区域信息。 |
| `ocr.lang` | string | OCR 语言，例如 `ch`。 |
| `ocr.archiveRegion` | boolean | 是否把该区域裁图作为 artifact 归档。 |

### 4.4 outputColumns

```json
{
  "outputColumns": ["id1", "id2", "q1", "q2"]
}
```

控制 CSV 输出列顺序。若字段存在但不在 `outputColumns` 中，可能不会出现在结果 CSV 中。

## 5. preProcessors 参数

`preProcessors` 是识别前对整页图像的处理流水线，顺序很重要。

### 5.1 FeatureBasedAlignment

推荐默认使用。

```json
{
  "name": "FeatureBasedAlignment",
  "options": {
    "reference": "reference.png",
    "2d": true,
    "maxFeatures": 2000,
    "goodMatchPercent": 0.25
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `reference` | 字符串 | 参考图文件名或可被下载重写的 OSS key。 |
| `2d` | boolean | `true` 使用仿射变换，通常更稳，不做强透视扭曲。 |
| `maxFeatures` | 个，整数 | ORB 特征点数量上限。图文复杂模板可适当增大。 |
| `goodMatchPercent` | 比例，0-1 | 保留匹配点比例。过低可能匹配不足，过高可能引入错误匹配。 |

当前代码已保护 RANSAC/仿射估计失败场景：特征不足、匹配不足、OpenCV 抛错时会跳过对齐并记录 warning，不会直接让任务崩溃。

### 5.2 CropOnMarkers

谨慎使用。它会在四个象限中匹配同一个 marker，然后用四个匹配中心点做透视变换。

```json
{
  "name": "CropOnMarkers",
  "options": {
    "relativePath": "marker.png",
    "min_matching_threshold": 0.3,
    "max_matching_variation": 0.41
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `relativePath` | 字符串 | marker 图片路径。 |
| `min_matching_threshold` | 归一化分数，通常 0-1 | 单个象限最低匹配分。 |
| `max_matching_variation` | 归一化分数差，通常 0-1 | 四个象限匹配分允许的最大差异。 |
| `marker_rescale_range` | 百分比整数区间 | marker 高度缩放搜索范围，例如 `[35, 100]` 表示 35% 到 100%。 |
| `marker_rescale_steps` | 个，整数 | 缩放搜索步数。 |
| `apply_erode_subtract` | boolean | 是否使用腐蚀差分增强线条。 |

使用条件：

1. 四角 marker 外形必须一致。
2. marker 图应只包含定位标记本体和少量白边。
3. 不要包含题干、横线、边框、表格线等容易误匹配的内容。
4. 模板坐标必须基于 Crop 后的页面重新校准，或者 OMRChecker 需要同步变换所有字段坐标。

如果前端坐标来自原始 PDF 页面，默认不要启用 `CropOnMarkers`。

## 6. 阈值和弱识别参数

### 6.1 threshold_params

```json
{
  "threshold_params": {
    "PAGE_TYPE_FOR_THRESHOLD": "white",
    "GAMMA_LOW": 0.7,
    "MIN_GAP": 30,
    "MIN_JUMP": 25,
    "JUMP_DELTA": 30,
    "CONFIDENT_SURPLUS": 5
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `PAGE_TYPE_FOR_THRESHOLD` | 字符串 | 页面背景类型。常用 `white`。 |
| `GAMMA_LOW` | 系数，小数 | 低亮度 gamma 调整参数。 |
| `MIN_GAP` | 灰度差，0-255 | 正常填涂判定中最深和次深选项的最小差距。 |
| `MIN_JUMP` | 灰度差，0-255 | 阈值跳变判断参数。 |
| `JUMP_DELTA` | 灰度差，0-255 | 阈值跳变差值。 |
| `CONFIDENT_SURPLUS` | 灰度差，0-255 | 置信冗余量。 |

这些参数影响正常填涂识别。若大面积空白被识别为填涂，或淡涂完全识别不到，需要结合 `WeakFillReview.csv` 调整。

### 6.2 weak_mark_params

用于单选题弱填涂兜底。

```json
{
  "weak_mark_params": {
    "enabled": true,
    "min_gap": 10,
    "max_mean": 215,
    "supported_field_types": ["QTYPE_MCQ4"],
    "exclude_labels": []
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `enabled` | boolean | 是否启用弱填涂兜底。 |
| `min_gap` | 灰度差，0-255 | 最深和次深候选的最小均值差。越小越容易接受弱填涂。 |
| `max_mean` | 灰度均值，0-255 | 最深候选的最大灰度均值。越大越宽松。 |
| `supported_field_types` | string[] | 生效题型。 |
| `exclude_labels` | string[] | 排除字段。 |

### 6.3 weak_identifier_params

用于准考证号等数字列弱识别。

```json
{
  "weak_identifier_params": {
    "enabled": true,
    "labels": [],
    "exclude_labels": [],
    "min_gap": 20,
    "min_delta_from_blank": 25,
    "max_mean": 205,
    "supported_field_types": ["QTYPE_INT"]
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `min_gap` | 灰度差，0-255 | 最深和次深数字候选的最小差距。 |
| `min_delta_from_blank` | 灰度差，0-255 | 候选和空白基线的最小差值。 |
| `max_mean` | 灰度均值，0-255 | 最深候选最大灰度均值。 |
| `labels` | string[] | 只对指定字段启用。为空表示不限制。 |
| `exclude_labels` | string[] | 排除字段。 |

准考证号弱识别多时，不要只调弱识别阈值。应先确认 `ExamId.origin`、`bubbleDimensions`、`bubblesGap`、`labelsGap` 是否准确。

### 6.4 weak_multi_mark_params

用于多选题弱填涂兜底。

```json
{
  "weak_multi_mark_params": {
    "enabled": true,
    "labels": [],
    "only_when_blank": true,
    "min_delta_from_blank": 10,
    "max_mean": 218,
    "max_marks": 4,
    "full_select_fallback_enabled": true,
    "full_select_max_mean": 170,
    "full_select_min_delta_from_blank": 35,
    "full_select_max_spread": 25
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `enabled` | boolean | 是否启用多选弱识别。 |
| `only_when_blank` | boolean | 仅当正常识别为空时才兜底。推荐 `true`。 |
| `min_delta_from_blank` | 灰度差，0-255 | 候选与空白基线最小差值。 |
| `max_mean` | 灰度均值，0-255 | 弱填涂候选最大灰度均值。 |
| `max_marks` | 个，整数 | 最多允许选项数。 |
| `full_select_fallback_enabled` | boolean | 是否启用“全选/接近全选”兜底。 |
| `full_select_max_mean` | 灰度均值，0-255 | 全选兜底候选最大灰度均值。 |
| `full_select_min_delta_from_blank` | 灰度差，0-255 | 全选兜底与空白基线最小差值。 |
| `full_select_max_spread` | 灰度差，0-255 | 全选候选之间最大均值跨度。 |

## 7. outputs 参数

```json
{
  "outputs": {
    "save_detections": true,
    "save_image_level": 0,
    "show_image_level": 0
  }
}
```

| 字段 | 单位/类型 | 说明 |
| --- | --- | --- |
| `save_detections` | boolean | 是否保存检测结果图。 |
| `save_image_level` | 级别，整数 | 保存调试图级别。值越大输出越多。 |
| `show_image_level` | 级别，整数 | 显示调试窗口级别。服务端非交互运行建议保持 `0`。 |

批量服务中如需保存临时 workdir，可设置 `recognitionConfig.debugArtifacts=true`，方便排查生成的 `template.json`、`marker.png`、`reference.png` 和 CheckedOMR。

## 8. 调参排查顺序

识别偏移或效果差时建议按以下顺序排查：

1. **PDF 页码和 DPI**：确认 `pdf_page`、`pdf_dpi`、`markerConfig.pdfPage`、`markerConfig.pdfDpi` 一致。
2. **页面尺寸**：确认 `pageDimensions`、`processing_width/height`、`reference.png` 尺寸一致。
3. **坐标系是否变化**：如果启用了 `CropOnMarkers`、`CropPage` 等裁切类预处理，确认模板坐标是否基于处理后的页面。
4. **CheckedOMR 可视化**：查看 `outputs/.../CheckedOMRs/*.png`，确认气泡框是否覆盖真实填涂区域。
5. **单点采样**：如果日志出现 `darkest_mean=255`、`density=0`，通常说明采样框落到纯白处，是坐标偏移，不是阈值问题。
6. **气泡网格参数**：客观题检查 `origin`、`bubbleDimensions`、`bubblesGap`；准考证号额外重点检查 `labelsGap`。
7. **弱识别阈值**：坐标准确后，再根据 `WeakFillReview.csv` 调 `weak_*` 参数。

## 9. 推荐默认配置

当前批量识别推荐：

```json
{
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
    }
  },
  "markerConfig": {
    "sourcePdfOsskey": "template-assets/sheet-template.pdf",
    "pdfPage": 1,
    "pdfDpi": 144,
    "bbox": [40, 52, 40, 28],
    "outputName": "marker.png",
    "enableCropOnMarkers": false
  }
}
```

这会让 OMRChecker：

1. 根据模板 PDF 生成 `marker.png`。
2. 根据同页模板 PDF 生成 `reference.png`。
3. 自动把 `reference.png` 接入 `FeatureBasedAlignment`。
4. 保持前端传入的气泡和 OCR 坐标仍处于原始 PDF 渲染页坐标系。

如果未来需要真正使用四角 marker 透视矫正，应在 OMRChecker 内部实现字段坐标同步变换，或要求模板坐标基于 Crop 后页面重新标定。
