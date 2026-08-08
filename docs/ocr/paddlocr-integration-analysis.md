# PaddleOCR 集成可行性分析与设计方案

日期：2026-08-08
分支：`paddlocr-integration`
项目：OMRChecker

## 1. 第一版目标

在当前 OMRChecker 答题卡模板机制上扩展 OCR 识别能力。模板中可以同时指定 OMR 区域和 OCR 区域。OCR 引擎使用 PaddleOCR。

第一版的硬性前提：**新增 OCR 不能影响现有 OMR 流程和功能**。

具体含义：

1. 纯 OMR 模板的识别流程不变。
2. 纯 OMR 模板的 Results CSV 不变。
3. 纯 OMR 模板的 checked image 归档和 COS 上传链路不变。
4. 现有 OMR 字段仍按当前字符串结果输出，不把 OMR 结果整体改成新对象结构。
5. OCR 只在模板区域显式声明 `engine: "paddleocr"` 时启用。
6. OCR 的截图归档复用现有 region artifact/COS 归档思路，不另起一套和现有业务割裂的上传流程。

第一版 OCR 重点支持三类答题卡区域：

1. **填空题得分区域**
   - 模板提供区域坐标。
   - `engine` 为 `paddleocr`。
   - OCR 返回识别出的分数文本和置信度。

2. **解答题得分区域**
   - 模板提供区域坐标。
   - `engine` 为 `paddleocr`。
   - OCR 返回识别出的得分文本和置信度。

3. **解答题解答区域**
   - 模板提供区域坐标。
   - `engine` 为 `paddleocr`。
   - OCR 返回识别出的解答文本和置信度。
   - 区域截图需要归档，并为后续上传 COS 保留 artifact 元数据。

第一版推荐规则：**一个 OCR block 对应一个业务字段**。例如 `blankScore1`、`solutionScore2`、`solutionAnswer2` 分别定义为三个独立 OCR block。这样字段边界清晰，截图归档可追溯，结果聚合也能尽量保持和 OMR 一致。

## 2. 当前实现分析

### 2.1 OMR 主流程

相关文件：

- `src/entry.py`
- `src/core.py`
- `src/template.py`
- `src/utils/file.py`
- `src/utils/parsing.py`

当前 OMR 单张图片核心流程在 `src/entry.py::_process_single_image()`：

```python
response_dict, final_marked, multi_marked, _ = template.image_instance_ops.read_omr_response(
    template, image=in_omr, name=file_id, save_dir=save_dir
)

omr_response = get_concatenated_response(response_dict, template)
```

随后按 `template.output_columns` 写入 Results CSV：

```python
resp_array = []
for k in template.output_columns:
    resp_array.append(omr_response[k])
```

这说明现有 OMR 结果核心是扁平字典：

```python
response_dict[field_label] = field_value
```

第一版 OCR 集成不应把这条 OMR 主链路整体改成结构化对象，否则会影响 CSV、evaluation、customLabels 和历史调用方。

### 2.2 模板解析

相关文件：

- `src/template.py`
- `src/constants/common.py`
- `src/schemas/template_schema.py`
- `src/utils/parsing.py`

当前模板通过 `Template` 读取 `template.json`：

```python
json_object = open_template_with_defaults(template_path)
# 中间省略默认值读取和字段解包。
self.setup_field_blocks(field_blocks_object)
```

`fieldBlocks` 中的每个 block 会被解析成 `FieldBlock`。

当前 `FieldBlock` 假设 block 是 OMR 气泡区域，核心字段包括：

- `origin`
- `fieldLabels`
- `fieldType` 或 `bubbleValues`
- `bubbleDimensions`
- `bubblesGap`
- `labelsGap`
- `direction`
- `multiSelect`

然后通过 `generate_bubble_grid()` 生成 `traverse_bubbles`，供后续 OMR 阈值识别使用。

### 2.3 现有归档截图和 COS 链路

当前项目已经有区域截图 artifact 生成与上传机制。

相关文件：

- `src/services/region_artifacts.py`
- `src/services/batch_service.py`
- `src/services/service_config.py`
- `src/services/cos_client.py`

`region_artifacts.py` 中的 `generate_region_artifacts()` 会从 checked image 裁剪配置区域，并返回 `ArtifactPayload`：

```python
ArtifactPayload(
    artifact_type="region_screenshot",
    osskey=str(local_path),
    metadata={
        "localPath": str(local_path),
        "regionCode": region.region_code,
        "regionName": region.region_name,
        "regionType": region.type,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "sheetId": sheet_id,
        "taskId": task_id,
    },
)
```

`BatchRecognitionService.process_batch()` 已经有上传 checked image 和 region artifacts 的逻辑：

- checked image 上传到：`checked/<task_id>/<sheet_id>/<filename>`
- region artifact 上传到：`artifacts/<task_id>/<sheet_id>/<filename>`
- 上传成功后写入 store artifact 表。
- 上传失败不会导致识别失败，只记录 artifact error。

因此 OCR 区域截图归档不应该另起一套 COS 上传机制。建议复用或扩展现有 `region_artifacts` 思路。

### 2.4 服务聚合结果

相关文件：`src/services/omr_service.py`

`read_results_csv()` 会把 Results CSV 转成服务返回 JSON。当前 `_normalize_result_row()` 已经把答案组织成：

```json
{
  "file_id": "...",
  "answers": [
    {
      "regionCode": "singleChoice",
      "regionName": "单选题区域",
      "type": "SINGLE_CHOICE",
      "items": [
        {"field": "q1", "value": "A", "confidence": 1.0}
      ]
    }
  ],
  "answers_flat": {"q1": "A"}
}
```

这对 OCR 扩展有利，但需要一个明确改动：当前 `_normalize_result_row()` 只把 `id\d+` 和 `q\d+` 字段纳入 `answers` / `answers_flat`，因此 OCR 字段虽然可以先写入 Results CSV，但还需要扩展 `omr_service.py` 的聚合逻辑，让带有模板区域元数据的 OCR 字段也能进入服务结果，并带上 OCR 置信度和 artifact 引用。

## 3. 可行性结论

结论：**可行，但设计边界必须是 OCR 扩展，不是 OMR 重构。**

推荐方案：

1. `fieldBlocks` 增加统一 `engine` 字段。
2. 未配置 `engine` 的旧 block 默认 `omr`。
3. OMR block 继续走现有 OMR 识别和输出流程。
4. OCR block 走新增 OCR 分支。
5. OCR 的值可以进入同一个扁平 response，使主 Results CSV 能输出 OCR 字段值。
6. 返回结构沿用当前 OMR 已实现的 `answers` / `answers_flat` 风格，只在区域或 item 上扩展 `engine`。
7. OCR 截图归档复用现有 region artifact/COS 上传链路，方便后续审查。

## 4. 推荐模板规范

### 4.1 统一 `fieldBlocks`，新增 `engine`

每个 `fieldBlock` 可以显式配置：

`"engine": "omr"`

或：

`"engine": "paddleocr"`

兼容策略：如果未配置 `engine`，默认视为 `"omr"`。

这样现有模板不需要修改。

### 4.2 OMR block 保持现有规范

现有 OMR block 继续使用当前字段：

```json
{
  "engine": "omr",
  "fieldType": "QTYPE_MCQ4",
  "origin": [100, 300],
  "fieldLabels": ["q1..q50"],
  "bubbleDimensions": [20, 20],
  "bubblesGap": 40,
  "labelsGap": 30
}
```

其中 `engine` 可省略，省略时仍为 OMR。

### 4.3 OCR block 通用格式

OCR block 建议统一使用以下结构：

```json
{
  "engine": "paddleocr",
  "fieldLabels": ["blankScore1"],
  "origin": [120, 80],
  "dimensions": [160, 60],
  "regionCode": "blankScore",
  "regionName": "填空题得分区域",
  "type": "BLANK_SCORE",
  "ocr": {
    "lang": "ch",
    "det": false,
    "rec": true,
    "cls": true,
    "returnConfidence": true,
    "archiveRegion": true
  }
}
```

字段说明：

- `engine`: 固定为 `paddleocr`，表示该区域由 PaddleOCR 识别。
- `fieldLabels`: 第一版必须只有一个字段。
- `origin`: 区域左上角坐标，基于模板 `pageDimensions`。
- `dimensions`: 区域宽高。
- `regionCode`: 服务聚合和 artifact 元数据使用。
- `regionName`: 人类可读区域名称。
- `type`: 业务区域类型。
- `ocr`: 保留 OCR 细节配置，例如语言、检测、方向分类和置信度策略，不再重复配置引擎名称。
- `ocr.returnConfidence`: 必须开启。OCR 结果必须带置信度。
- `ocr.archiveRegion`: 是否归档区域截图。三类目标区域第一版建议默认开启。

### 4.4 填空题得分区域示例

```json
{
  "fieldBlocks": {
    "blankScore1": {
      "engine": "paddleocr",
      "fieldLabels": ["blankScore1"],
      "origin": [980, 320],
      "dimensions": [120, 48],
      "regionCode": "blankScore",
      "regionName": "填空题得分区域",
      "type": "BLANK_SCORE",
      "ocr": {
        "lang": "ch",
        "returnConfidence": true,
        "archiveRegion": true
      }
    }
  }
}
```

### 4.5 解答题得分区域示例

```json
{
  "fieldBlocks": {
    "solutionScore2": {
      "engine": "paddleocr",
      "fieldLabels": ["solutionScore2"],
      "origin": [1010, 780],
      "dimensions": [120, 56],
      "regionCode": "solutionScore",
      "regionName": "解答题得分区域",
      "type": "SOLUTION_SCORE",
      "ocr": {
        "lang": "ch",
        "returnConfidence": true,
        "archiveRegion": true
      }
    }
  }
}
```

### 4.6 解答题解答区域示例

```json
{
  "fieldBlocks": {
    "solutionAnswer2": {
      "engine": "paddleocr",
      "fieldLabels": ["solutionAnswer2"],
      "origin": [120, 840],
      "dimensions": [860, 420],
      "regionCode": "solutionAnswer",
      "regionName": "解答题解答区域",
      "type": "SOLUTION_ANSWER",
      "ocr": {
        "lang": "ch",
        "det": true,
        "rec": true,
        "cls": true,
        "returnConfidence": true,
        "archiveRegion": true
      }
    }
  }
}
```

## 5. 结果结构设计

### 5.1 OMR 结果保持不变

这是第一版设计约束。

当前 OMR 识别结果继续保持：

```python
response_dict[field_label] = field_value
```

例如：

```python
response_dict["q1"] = "A"
response_dict["id1"] = "3"
```

不把 OMR 字段改成：

```python
response_dict["q1"] = {"value": "A", "confidence": 1.0}
```

原因：这会影响现有 CSV 输出、evaluation、customLabels、服务解析和历史调用方。

### 5.2 OCR 值进入 flat response

OCR 字段为了尽量和 OMR 结果格式一致，也应向主 response 写入字符串值：

```python
response_dict["blankScore1"] = "5"
response_dict["solutionScore2"] = "12"
response_dict["solutionAnswer2"] = "解：根据题意..."
```

这样：

1. `outputColumns` 可以直接输出 OCR 字段值。
2. `customLabels` 可以复用。
3. Results CSV 仍然是字段值表。
4. OMR 原有字段不受影响。

### 5.3 OCR 识别信息沿用当前 OMR 聚合结构扩展

核心原则是：**结构和当前 OMR 已实现的返回保持一致，只扩展必要字段**。

主 response 仍保持扁平字段值，服务聚合结果继续使用当前 `answers` / `answers_flat` 结构。实现时需要把 `omr_service.py` 当前仅收集 `q\d+` / `id\d+` 的逻辑扩展为：除了历史 OMR 字段，也收集模板元数据中标记为 OCR 的字段。OCR 的`engine` 信息不改变结果层级，只作为区域或 item 的附加字段返回：

```json
{
  "field": "blankScore1",
  "value": "5",
  "confidence": 0.96,
  "engine": "paddleocr",
  "artifactOsskey": "artifacts/task-1/sheet-1/001_sheet-1_blankScore1_填空题得分区域.png"
}
```

输出建议：

1. 主 Results CSV：只写字段值，保持 OMR 风格。
2. 服务 result：沿用现有 `answers` / `answers_flat`，给 OCR item 补充 `engine`、`confidence`、`artifactOsskey`。
3. Batch artifacts：写入 region screenshot artifact，后续由现有 COS 链路处理。

### 5.4 服务聚合返回

服务聚合结果建议延续当前 `answers` / `answers_flat` 风格，不改 OMR 字段含义。

示例：

```json
{
  "file_id": "001.png",
  "answers": [
    {
      "regionCode": "singleChoice",
      "regionName": "单选题区域",
      "type": "SINGLE_CHOICE",
      "items": [
        {"field": "q1", "value": "A", "confidence": 1.0}
      ]
    },
    {
      "regionCode": "blankScore",
      "regionName": "填空题得分区域",
      "type": "BLANK_SCORE",
      "items": [
        {
          "field": "blankScore1",
          "value": "5",
          "confidence": 0.96,
          "engine": "paddleocr",
          "artifactOsskey": "artifacts/task-1/sheet-1/001_sheet-1_blankScore1_填空题得分区域.png"
        }
      ]
    }
  ],
  "answers_flat": {
    "q1": "A",
    "blankScore1": "5"
  }
}
```

关键点：

- OMR 字段仍然按当前逻辑进入 `answers` 和 `answers_flat`。
- OMR 字段仍可按当前逻辑返回，不强制增加新字段。
- OCR 字段在 item 上补充 `engine`，表示该区域使用 OCR 引擎识别。
- `answers_flat` 仍是简单字段值字典。
- artifact 上传成功后可补充 `artifactOsskey`，用于后续审查。

## 6. OCR 截图归档设计

### 6.1 复用现有 artifact/COS 链路

当前已有 `generate_region_artifacts()` 和 `_upload_region_artifacts()`。OCR 截图归档应复用这个模式。

推荐做法：

1. OCR block 识别时可以从预处理后的图像裁剪区域，用于 OCR 识别。
2. OCR block 的归档截图作为 `ArtifactPayload` 交给 batch artifact 上传链路。
3. 上传到现有远端 key 规则：

```text
artifacts/<task_id>/<sheet_id>/<filename>.png
```

4. artifact metadata 中增加 OCR 相关字段：

```json
{
  "localPath": "...",
  "regionCode": "blankScore",
  "regionName": "填空题得分区域",
  "regionType": "BLANK_SCORE",
  "engine": "paddleocr",
  "field": "blankScore1",
  "confidence": 0.96,
  "value": "5",
  "bbox": {"x": 980, "y": 320, "width": 120, "height": 48},
  "sheetId": "sheet-1",
  "taskId": "task-1"
}
```

### 6.2 不建议第一版新增独立 COS 上传流程

不建议 OCR 自己直接调用 COS client。原因：

1. 现有 batch service 已经处理 artifact 上传和错误隔离。
2. 现有上传失败是非致命错误，符合识别业务稳定性。
3. 现有 store artifact 表可以统一查询 artifact。
4. 独立上传会造成 checked image、OMR region screenshot、OCR screenshot 三套行为不一致。

### 6.3 本地归档目录

本地目录可以继续使用 batch workdir 下的 artifact 目录，例如：

```text
<workdir>/region_artifacts/
  001_sheet-1_blankScore1_填空题得分区域.png
  002_sheet-1_solutionScore2_解答题得分区域.png
  003_sheet-1_solutionAnswer2_解答题解答区域.png
```

是否在 OMR CLI 输出目录下额外生成 `OCRCrops`，应作为可选 debug 行为，而不是第一版必须业务链路。第一版业务归档应以 artifact/COS 链路为准。

## 7. 推荐架构设计

### 7.1 新增识别引擎边界

引入两个识别引擎标识：

- `engine = "omr"`
- `engine = "paddleocr"`

`FieldBlock` 保留为模板区域对象，但内部按类型处理：

- OMR block：继续生成 bubble grid。
- OCR block：保存 `origin`、`dimensions`、`fieldLabels`、`regionCode`、`regionName`、`type`、`ocr_options`，不生成 bubble grid。

### 7.2 识别流程调整

推荐最小改造流程：

1. 加载图片。
2. 应用现有 preProcessors。
3. resize 到 `pageDimensions`。
4. 执行现有 auto alignment。
5. 根据区域指定的 `engine` 分发识别：
   - `omr` 区域走现有阈值识别逻辑。
   - `paddleocr` 区域裁剪后调用 PaddleOCR。
6. 每个区域识别完成后按当前 OMR 已实现的结果结构聚合：
   - 将 `value` 写入现有 flat response。
   - OCR item 额外带上 `engine: "paddleocr"` 和 `confidence`。
   - OCR 区域截图生成 region artifact，交给现有 COS 上传链路。
7. 后续 Results CSV、checked image、evaluation 尽量使用现有流程。

重要约束：OMR block 的阈值统计、冲突处理、弱填涂处理、多选处理不能因为 OCR block 存在而改变。

### 7.3 新增 OCR 引擎封装

建议新增模块：

```text
src/ocr/
  __init__.py
  engine.py
  paddleocr_engine.py
```

建议接口：

```python
class OCRResult:
    text: str
    confidence: float
    raw: object | None

class OCREngine:
    def recognize(self, image, options) -> OCRResult:
        raise NotImplementedError
```

设计要求：

1. 懒加载 PaddleOCR，只在模板中存在 OCR block 时初始化。
2. OCR 依赖作为 optional dependency，避免纯 OMR 用户被迫安装 PaddleOCR。
3. OCR 返回文本和置信度，置信度为必填。
4. PaddleOCR 原始结果如需保留，只作为调试信息或 artifact metadata 的可选字段，不改变主返回结构。

### 7.4 OCR 坐标定义

OCR block 坐标应与 OMR block 保持一致：

- 坐标基于模板的 `pageDimensions`。
- 坐标作用于 resize 和 preProcessors 之后的图像。
- OCR block 默认不参与 OMR 气泡阈值统计。
- OCR block 的稳定性优先依赖全局 preProcessor，例如 `CropOnMarkers`、`FeatureBasedAlignment`。

## 8. 不推荐第一版支持“一块 OCR 区域拆成多个字段”

例如下面这种能力不建议第一版实现：

```json
{
  "engine": "paddleocr",
  "origin": [100, 100],
  "dimensions": [500, 200],
  "fieldLabels": ["blankScore1", "blankScore2", "blankScore3"],
  "split": {
    "mode": "lines"
  }
}
```

原因：

1. OCR 本身会有检测框顺序问题。
2. 多行文本和字段标签之间需要额外映射规则。
3. 表格、空行、印刷文本干扰会让拆分规则复杂化。
4. 错误来源会变成 OCR 错误加拆分错误，不利于验证。
5. 当前目标可以通过多个规范一致的 OCR block 达成。

## 9. 可选方案对比

### 9.1 方案 A：在 `fieldBlocks` 中扩展统一 `engine`

推荐。

优点：

- 最大程度复用当前模板结构。
- 最大程度复用当前输出流程。
- OMR 和 OCR 都是答题卡上的字段区域，语义统一。
- 填空题得分、解答题得分、解答题解答区域可以使用同一规范。
- 可以通过默认 `engine = "omr"` 保持历史模板兼容。
- 可复用现有 region artifact/COS 归档链路。

缺点：

- `FieldBlock` 需要支持 OMR/OCR 两种结构。
- `template_schema.py` 需要使用条件 schema 区分 OMR block 和 OCR block。
- `read_omr_response()` 需要分流识别逻辑，但不能破坏 OMR 分支。

### 9.2 方案 B：新增顶层 `ocrBlocks`

不推荐第一版采用。

缺点：

- 输出列需要同时收集 `fieldBlocks` 和 `ocrBlocks`。
- `customLabels` 校验需要跨两个来源。
- 模板结构变成两套字段定义，长期维护成本更高。
- 不符合“区域已经可以通过统一 `engine` 指定识别方式”的设计方向。

### 9.3 方案 C：把 OCR 做成 preProcessor

不推荐。

缺点：

- preProcessor 的职责是图像预处理，不适合产出字段识别结果。
- OCR 结果难以进入统一 flat response。
- 会破坏当前架构中“预处理”和“识别”的边界。

## 10. 需要修改的文件

### 10.1 必改

- `src/schemas/template_schema.py`
  - 扩展 `fieldBlocks` 条件校验。
  - 支持统一 `engine` 字段。
  - OMR block 保持现有字段要求。
  - OCR block 要求 `origin`、`dimensions`、`fieldLabels`。
  - OCR block 限制 `fieldLabels` 第一版只能有一个字段。
  - OCR block 不要求 `bubbleDimensions`、`bubblesGap`、`labelsGap`、`bubbleValues`。

- `src/template.py`
  - `FieldBlock` 增加 `engine`。
  - OMR block 走现有 `calculate_block_dimensions()` 和 `generate_bubble_grid()`。
  - OCR block 直接读取 `dimensions`，保存 `regionCode`、`regionName`、`type`、`ocr_options`。
  - `validate_parsed_labels()` 对 OCR block 继续检查重名和越界。

- `src/core.py`
  - 在 `read_omr_response()` 中区分 OMR/OCR block。
  - OMR 阈值统计只遍历 OMR block。
  - OCR block 单独裁剪并调用 OCR 引擎。
  - OCR `value` 写入现有 flat response。
  - OCR `confidence`、`engine` 和 artifact 引用写入当前服务结果结构的扩展字段。

- `src/services/region_artifacts.py`
  - 扩展从 template 派生 archive regions 的能力，使 OCR block 可派生为 region artifact。
  - 或新增 helper，将 OCR block 结果转成 `ArtifactPayload`。
  - 保持现有 `ArtifactPayload` 和上传链路兼容。

- `src/services/batch_service.py`
  - 复用现有 `_upload_region_artifacts()` 上传 OCR region artifact。
  - 将上传后的 `artifactOsskey` 回填到 OCR 元数据或服务聚合结果。
  - 不改变 checked image 上传逻辑。

- `src/services/omr_service.py`
  - 聚合返回时兼容 OCR 字段区域元数据和置信度。
  - 扩展 `_normalize_result_row()` 当前只纳入 `id\d+` / `q\d+` 的 recognized fields 规则，允许模板元数据声明的 OCR 字段进入 `answers` 和 `answers_flat`。
  - 保持 `answers_flat` 为简单字段值字典。

- `src/defaults/config.py` 和 `src/schemas/config_schema.py`
  - 增加 OCR 默认配置和 schema。

### 10.2 建议新增

- `src/ocr/__init__.py`
- `src/ocr/engine.py`
- `src/ocr/paddleocr_engine.py`
- `src/tests/test_ocr_template_schema.py`
- `src/tests/test_ocr_field_block.py`
- `src/tests/test_ocr_processing.py`
- `src/tests/test_ocr_artifacts.py`
- `src/tests/test_ocr_does_not_change_omr.py`

## 11. 测试策略

### 11.1 OMR 不变性测试

这是第一优先级。

覆盖点：

- 现有纯 OMR sample 的 Results CSV 不变。
- 现有纯 OMR sample 的 checked image 路径规则不变。
- 现有 `read_results_csv()` 对纯 OMR 的返回结构不变。
- 现有弱填涂、多选、错误文件流程不受 OCR 代码影响。
- 未安装 PaddleOCR 时，纯 OMR 流程仍可运行。

### 11.2 模板兼容性测试

覆盖点：

- 没有 `engine` 的旧 block 默认是 OMR。
- 旧的 `QTYPE_MCQ4`、`QTYPE_INT` 模板继续解析成功。
- OCR block 有 `origin`、`dimensions`、单个 `fieldLabels` 时通过。
- OCR block 多个 `fieldLabels` 时失败。
- OCR block 缺少 `dimensions` 时失败。

### 11.3 OCR 处理测试

覆盖点：

- 用 fake OCR engine 代替 PaddleOCR，避免测试依赖重模型。
- 验证裁剪区域尺寸正确。
- 验证 OCR 结果必须包含置信度。
- 验证 OCR `value` 写入 flat response。
- 验证 OCR 置信度、`engine` 按当前服务结果结构返回。
- 验证 PaddleOCR 未安装时，只有模板使用 OCR 才报出清晰错误。

### 11.4 artifact/COS 归档测试

覆盖点：

- OCR block 可生成 `region_screenshot` artifact。
- artifact metadata 包含 field、engine、confidence、value、bbox。
- `_upload_region_artifacts()` 能上传 OCR artifact。
- 上传失败不影响识别完成，只记录 artifact error。
- 回调 payload 中可以看到 artifact 列表或对应 osskey。

### 11.5 端到端回归测试

覆盖点：

- 纯 OMR 样例结果不变。
- OMR + OCR 混合模板能输出主 Results CSV。
- OCR 字段出现在 `outputColumns` 中时，主 CSV 输出 OCR 文本值。
- OCR 字段在服务结果中带置信度。
- OCR artifact 进入现有 artifacts/COS 链路。

## 12. 风险与应对

### 12.1 OMR 流程被误改

风险：为了支持 OCR，把 OMR 结果整体改成结构化对象，破坏已有行为。

应对：

- 明确 OMR 结果保持字符串 flat response。
- OCR 识别信息使用当前服务结果结构的扩展字段。
- 建立 OMR 不变性回归测试。

### 12.2 `read_omr_response()` 过长且耦合较重

风险：直接把 OCR 逻辑塞进去会让函数更难维护，并增加 OMR 回归风险。

应对：第一版建议抽出私有方法：

- `_read_omr_blocks(...)`
- `_read_ocr_blocks(...)`
- `_build_ocr_artifacts(...)`
- `_draw_ocr_result(...)`

### 12.3 PaddleOCR 依赖重

风险：安装慢，平台差异大，模型首次下载慢。

应对：

- OCR 作为 optional dependency。
- 懒加载 PaddleOCR。
- 未安装时纯 OMR 不受影响。
- 未安装且模板使用 OCR 时给出明确错误。

### 12.4 OCR 坐标稳定性

风险：扫描图偏移时，OCR 裁剪区域可能错位。

应对：

- 推荐配合 `CropOnMarkers` 或 `FeatureBasedAlignment` 使用。
- 文档明确 OCR 坐标基于预处理后的模板坐标。
- 后续可增加 OCR block 独立 padding 或局部对齐能力。

### 12.5 artifact 上传一致性

风险：OCR 自行上传 COS，和现有 checked image / region artifact 行为不一致。

应对：

- OCR 截图归档复用现有 artifact payload 和 `_upload_region_artifacts()`。
- 上传失败保持非致命。
- artifact 元数据统一进入 store。

## 13. 推荐第一版范围

第一版建议做：

1. `fieldBlocks` 支持统一 `engine` 字段。
2. OCR block 一块区域对应一个字段。
3. 支持填空题得分区域、解答题得分区域、解答题解答区域，三者模板规范保持一致。
4. OMR block 流程和输出保持不变。
5. PaddleOCR 懒加载封装。
6. OCR 结果必须包含 `value` 和 `confidence`。
7. OCR `value` 写入现有 flat response。
8. OCR item 在当前服务结果结构上扩展 `engine`、`confidence` 和 artifact 引用。
9. OCR 截图归档复用现有 region artifact/COS 链路。
10. 主 Results CSV 继续只输出字段值。
11. 纯 OMR 模板完全兼容。
12. 支持 fake OCR engine 测试。
13. `final_marked` 可标注 OCR 区域和识别文本，但不改变 checked image 上传规则。

第一版不做：

1. 一块 OCR 区域拆多个字段。
2. 表格 OCR。
3. 复杂正则字段映射。
4. OCR 参与自动评分的复杂规则。
5. PaddleOCR GPU 配置自动管理。
6. OCR 区域自动检测。
7. 独立于现有 artifacts 的 OCR COS 上传流程。
8. 将所有 OMR 字段改成结构化对象。

## 14. 后续扩展方向

如果第一版稳定，可以再扩展：

1. 多行 OCR 拆字段：`split.mode = "lines"`。
2. 正则拆字段：`split.mode = "regex"`。
3. OCR 置信度输出到主 CSV 的可选列。
4. OCR 区域独立预处理。
5. OCR block 局部定位或锚点对齐。
6. 支持更多 OCR 引擎。
7. 解答题文本结构化分析。

## 15. 最终建议

建议采用：**方案 A，在现有 `fieldBlocks` 中新增统一 `engine` 字段，第一版 OCR block 强制一块区域对应一个字段。**

第一版应明确支持填空题得分区域、解答题得分区域和解答题解答区域。三类区域使用同一套模板规范：模板提供 `origin` 和 `dimensions`，识别引擎为 `paddleocr`，OCR 引擎返回 `value` 和必填 `confidence`。

最重要的设计边界是：**OMR 流程和结果不变，识别时按区域指定的 `engine` 分流。** OCR 字段值进入现有 flat response，服务返回结构沿用当前 OMR 已实现的 `answers` / `answers_flat` 风格，只在 OCR item 上补充 `engine`、`confidence` 和截图 artifact 引用。OCR 截图归档复用现有 region artifact/COS 上传链路，方便后续审查，避免产生新的、不一致的归档业务流程。
