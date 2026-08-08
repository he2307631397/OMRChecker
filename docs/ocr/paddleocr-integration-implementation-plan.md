# PaddleOCR 集成具体实现方案

日期：2026-08-08  
分支：`paddlocr-integration`  
项目：OMRChecker  
前置设计文档：`docs/ocr/paddlocr-integration-analysis.md`  

## 1. 目标和边界

本实现方案基于当前设计方案，目标是在 OMRChecker 现有模板和识别流程中增加 PaddleOCR 区域识别能力，并保持现有 OMR 行为默认不变。

第一版只实现显式 OCR 区域：

1. 填空题得分区域。
2. 解答题得分区域。
3. 解答题解答区域。

核心边界：

1. 统一使用 `engine` 字段区分识别引擎。
   - 默认：`engine: "omr"`。
   - OCR：`engine: "paddleocr"`。
2. 不引入第二套识别类型字段，统一只使用 `engine`。
3. 未声明 `engine` 的旧模板必须继续按 OMR 模板解析和识别。
4. 纯 OMR 模板的 Results CSV 字段、checked image、COS 上传、region artifact 上传行为保持不变。
5. OCR block 的识别值进入现有扁平 response，使 Results CSV 可以输出 OCR 字段。
6. OCR 置信度和 OCR 区域元数据通过新增辅助产物和服务聚合扩展返回，不改变 OMR 字段的基础字符串输出。
7. OCR 区域截图复用现有 region artifact/COS 上传链路。

## 2. 总体架构

### 2.1 识别流程

当前主流程保持不变：

```text
entry.py::_process_single_image()
  -> template.image_instance_ops.read_omr_response(template, image, name, save_dir)
  -> get_concatenated_response(response_dict, template)
  -> 按 template.output_columns 写 Results CSV
```

新增 OCR 后，`read_omr_response()` 内部对 `template.field_blocks` 做分流：

```text
FieldBlock.engine == "omr"
  -> 现有 bubble 阈值识别逻辑
  -> response_dict[field] = 字符串值

FieldBlock.engine == "paddleocr"
  -> 裁剪该 block 的图像区域
  -> 调用 PaddleOCR 引擎适配器
  -> response_dict[field] = OCR 文本
  -> 记录 field 级置信度和区域 artifact 元数据
```

对外仍返回现有四元组：

```python
response_dict, final_marked, multi_marked, multi_roll = read_omr_response(...)
```

OCR 额外信息保存在 `ImageInstanceOps` 实例的运行期属性中，并在 `entry.py` 写出辅助 CSV/JSON。这样避免重构现有调用方。

### 2.2 模板结构

OMR block 示例，兼容旧模板，`engine` 可省略：

```json
{
  "engine": "omr",
  "fieldType": "QTYPE_MCQ4",
  "fieldLabels": ["q1..50"],
  "origin": [100, 300],
  "bubbleDimensions": [20, 20],
  "bubblesGap": 40,
  "labelsGap": 30
}
```

OCR block 示例：

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

第一版约束：

1. OCR block 必须 `engine: "paddleocr"`。
2. OCR block 必须只有一个 `fieldLabels` 解析后的业务字段。
3. OCR block 必须提供 `origin` 和 `dimensions`。
4. OCR block 不需要 `fieldType`、`bubbleValues`、`bubblesGap`、`labelsGap`。
5. `ocr.returnConfidence` 默认为 `true`，输出必须保留置信度。
6. `ocr.archiveRegion` 默认为 `true`，三类目标区域建议开启。

## 3. 文件级改动清单

### 3.1 新增文件

| 文件 | 职责 |
| --- | --- |
| `src/ocr/__init__.py` | OCR 子包入口。 |
| `src/ocr/engine.py` | OCR 引擎协议、结果数据结构、PaddleOCR 延迟加载适配器、测试用 fake 注入点。 |
| `src/ocr/region.py` | OCR block 图像裁剪、边界检查、结果规范化。 |
| `src/tests/test_ocr_engine.py` | OCR 适配器和结果规范化单元测试，不依赖真实 PaddleOCR 模型。 |
| `src/tests/test_template_engine_blocks.py` | 模板 schema 和 `FieldBlock.engine` 解析测试。 |
| `src/tests/test_core_ocr_dispatch.py` | `read_omr_response()` OMR/OCR 分流测试，使用 fake OCR 引擎。 |

### 3.2 修改文件

| 文件 | 改动 |
| --- | --- |
| `src/schemas/template_schema.py` | `fieldBlocks` schema 增加 `engine` 分支，支持 OMR 和 PaddleOCR 两类 block。 |
| `src/template.py` | `FieldBlock` 增加 `engine`、OCR 元数据字段；OMR block 保持原解析；OCR block 跳过 bubble grid 生成。 |
| `src/core.py` | `ImageInstanceOps` 增加 OCR 引擎注入；`read_omr_response()` 只对 OMR block 执行现有 bubble 逻辑，对 OCR block 调用新增 OCR 分支。 |
| `src/entry.py` | 单张处理后写出 OCR 辅助结果文件，并继续写现有 Results CSV。 |
| `src/utils/file.py` | 如当前 CSV 写出逻辑集中在此文件，增加 OCR 辅助 CSV 写出函数。若 `entry.py` 已有合适写点，则只新增轻量 helper。 |
| `src/services/omr_service.py` | 聚合逻辑从只纳入 `id\d+`/`q\d+` 扩展为纳入模板元数据中的 OCR 字段，并读取 OCR 置信度。 |
| `src/services/region_artifacts.py` | 从模板派生归档区域时纳入 `engine: "paddleocr"` 且 `ocr.archiveRegion` 开启的 block。 |
| `src/services/batch_service.py` | 保持上传链路，必要时把 OCR artifact metadata 透传到任务结果。 |
| `docs/ocr/paddlocr-integration-analysis.md` | 如实现中发现设计文档例子需要同步，只做术语或字段一致性修正。 |

## 4. 数据结构设计

### 4.1 `FieldBlock` 新增属性

`src/template.py::FieldBlock` 增加以下运行期属性：

```python
self.engine: str  # "omr" 或 "paddleocr"
self.region_code: str | None
self.region_name: str | None
self.region_type: str | None
self.ocr_options: dict
self.dimensions: list[int]
```

OMR block：

```python
engine = field_block_object.get("engine", "omr")
```

OCR block：

```python
engine = "paddleocr"
parsed_field_labels = parse_fields(...)
origin = field_block_object["origin"]
dimensions = field_block_object["dimensions"]
region_code = field_block_object.get("regionCode") or block_name
region_name = field_block_object.get("regionName") or block_name
region_type = field_block_object.get("type") or "OCR"
ocr_options = {"returnConfidence": True, "archiveRegion": True, **field_block_object.get("ocr", {})}
traverse_bubbles = []
```

### 4.2 OCR 结果对象

新增 `src/ocr/engine.py`：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float
    raw: object | None = None
```

置信度规则：

1. PaddleOCR 原始结果中可能有多个文本片段。
2. 第一版将多个片段按从上到下、从左到右顺序拼接。
3. 空结果输出 `text=""`、`confidence=0.0`。
4. 多片段置信度使用平均值，四舍五入在服务返回层处理。
5. 如果 OCR adapter 发现 PaddleOCR 返回结构无法解析，输出空结果并记录 warning，不让整张 OMR 失败。

### 4.3 OCR 辅助结果文件

新增文件写到 Results 目录：

```text
Results/OcrResults.csv
```

字段：

```csv
file_id,input_path,output_path,field,value,confidence,engine,regionCode,regionName,type,bbox,artifactLocalPath
```

说明：

1. Results CSV 继续只输出 `template.output_columns` 中的字段值。
2. `OcrResults.csv` 只存 OCR 字段的置信度和区域信息。
3. 服务聚合读取 `OcrResults.csv` 为 OCR 字段补充 confidence、engine、artifactLocalPath。
4. 没有 OCR block 时不生成 `OcrResults.csv`，避免影响纯 OMR 输出目录。

### 4.4 服务返回结构

现有服务返回继续保留：

```json
{
  "answers_flat": {"q1": "A"},
  "answers": []
}
```

有 OCR 字段时扩展为：

```json
{
  "answers_flat": {
    "q1": "A",
    "blankScore1": "5"
  },
  "answers": [
    {
      "regionCode": "blankScore",
      "regionName": "填空题得分区域",
      "type": "BLANK_SCORE",
      "engine": "paddleocr",
      "items": [
        {
          "field": "blankScore1",
          "value": "5",
          "confidence": 0.982,
          "artifactLocalPath": ".../001_sheet_blankScore.png"
        }
      ]
    }
  ]
}
```

兼容性规则：

1. OMR region 不强制增加 `engine`，避免改变旧契约。OCR region 添加区域级 `engine`。
2. `items[]` 不重复返回 `engine`，因为同一区域内的 OCR items 继承区域级 `engine`。
3. OMR 字段默认 confidence 仍按现有逻辑：非空为 `1.0`，空为 `0.0`，weak fill review 覆盖。
4. OCR 字段 confidence 优先来自 `OcrResults.csv`。
5. OCR 字段进入 `answers_flat`，前提是模板元数据确认该字段属于 OCR block。

## 5. 分阶段 TDD 实施任务

### 阶段 1：模板 schema 和 FieldBlock 解析

目标：旧 OMR 模板无感兼容，新 OCR block 可通过 schema 和模板解析。

#### 任务 1.1：增加模板 schema 测试

测试文件：`src/tests/test_template_engine_blocks.py`

新增测试点：

1. 旧 OMR block 不写 `engine` 仍通过模板解析。
2. OMR block 写 `engine: "omr"` 仍通过模板解析。
3. OCR block 写 `engine: "paddleocr"`、`origin`、`dimensions`、单字段 `fieldLabels` 时通过模板解析。
4. OCR block 缺少 `dimensions` 时 schema 校验失败。
5. OCR block 如果同时缺失 `origin` 或 `fieldLabels` 时 schema 校验失败。
6. OCR block 如果写了多个解析后字段，`Template` 解析阶段抛出明确异常。

建议测试样例：

```python
def test_paddleocr_block_parses_with_engine_and_dimensions(tmp_path):
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [20, 20],
          "emptyValue": "",
          "preProcessors": [],
          "fieldBlocks": {
            "blank_score_1": {
              "engine": "paddleocr",
              "fieldLabels": ["blankScore1"],
              "origin": [100, 100],
              "dimensions": [160, 60],
              "regionCode": "blankScore",
              "regionName": "填空题得分区域",
              "type": "BLANK_SCORE",
              "ocr": {"lang": "ch", "archiveRegion": true}
            }
          },
          "outputColumns": ["blankScore1"],
          "customLabels": {}
        }
        """,
        encoding="utf-8",
    )

    template = Template(template_path, CONFIG_DEFAULTS)

    block = template.field_blocks[0]
    assert block.engine == "paddleocr"
    assert block.parsed_field_labels == ["blankScore1"]
    assert block.dimensions == [160, 60]
    assert block.region_code == "blankScore"
    assert block.region_name == "填空题得分区域"
    assert block.region_type == "BLANK_SCORE"
    assert block.ocr_options["archiveRegion"] is True
    assert block.ocr_options["returnConfidence"] is True
    assert block.traverse_bubbles == []
```

执行命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_template_engine_blocks.py -q
```

预期：先失败，原因是 schema 和 `FieldBlock.engine` 尚未实现。

#### 任务 1.2：修改 `src/schemas/template_schema.py`

当前 `fieldBlocks` schema 只适合 OMR block：

```python
"required": ["origin", "bubblesGap", "labelsGap", "fieldLabels"],
"oneOf": [
    {"required": ["fieldType"]},
    {"required": ["bubbleValues", "direction"]},
],
```

改为 engine 分支：

1. block 通用字段包含：
   - `engine`: enum `['omr', 'paddleocr']`。
   - `fieldLabels`。
   - `origin`。
   - `regionCode`。
   - `regionName`。
   - `type`。
2. `engine` 不 required，默认由 `Template` 处理。
3. `engine` 为 `omr` 或缺省时，继续要求 OMR 字段。
4. `engine` 为 `paddleocr` 时，要求 `origin`、`dimensions`、`fieldLabels`。
5. `ocr` 对象允许以下属性并禁止其他属性：
   - `lang`: string。
   - `det`: boolean。
   - `rec`: boolean。
   - `cls`: boolean。
   - `returnConfidence`: boolean。
   - `archiveRegion`: boolean。

建议 schema 结构：

```python
"fieldBlocks": {
    "description": "The fieldBlocks denote small groups of adjacent fields",
    "type": "object",
    "patternProperties": {
        "^.*$": {
            "type": "object",
            "properties": {
                "engine": {"type": "string", "enum": ["omr", "paddleocr"]},
                "bubbleDimensions": two_positive_numbers,
                "bubblesGap": positive_number,
                "bubbleValues": ARRAY_OF_STRINGS,
                "direction": {"type": "string", "enum": ["horizontal", "vertical"]},
                "emptyValue": {"type": "string"},
                "fieldLabels": {"type": "array", "items": FIELD_STRING_TYPE},
                "labelsGap": positive_number,
                "multiSelect": {"type": "boolean"},
                "origin": two_positive_integers,
                "dimensions": two_positive_integers,
                "regionCode": {"type": "string"},
                "regionName": {"type": "string"},
                "type": {"type": "string"},
                "fieldType": {"type": "string", "enum": list(FIELD_TYPES.keys())},
                "ocr": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "lang": {"type": "string"},
                        "det": {"type": "boolean"},
                        "rec": {"type": "boolean"},
                        "cls": {"type": "boolean"},
                        "returnConfidence": {"type": "boolean"},
                        "archiveRegion": {"type": "boolean"},
                    },
                },
            },
            "required": ["origin", "fieldLabels"],
            "allOf": [
                {
                    "if": {"properties": {"engine": {"const": "paddleocr"}}, "required": ["engine"]},
                    "then": {"required": ["dimensions"]},
                    "else": {
                        "required": ["bubblesGap", "labelsGap"],
                        "oneOf": [
                            {"required": ["fieldType"]},
                            {"required": ["bubbleValues", "direction"]},
                        ],
                    },
                }
            ],
        }
    },
},
```

注意：旧模板没有 `engine`，会走 `else`，因此继续按 OMR 校验。

#### 任务 1.3：修改 `src/template.py`

在 `Template.pre_fill_field_block()` 中按 engine 分流：

```python
def pre_fill_field_block(self, field_block_object):
    engine = field_block_object.get("engine", "omr")
    if engine == "paddleocr":
        return {
            "engine": "paddleocr",
            "ocr": {},
            **field_block_object,
        }

    if "fieldType" in field_block_object:
        field_block_object = {
            **FIELD_TYPES[field_block_object["fieldType"]],
            **field_block_object,
        }
    else:
        field_block_object = {**field_block_object, "fieldType": "__CUSTOM__"}

    return {
        "engine": "omr",
        "direction": "vertical",
        "emptyValue": self.global_empty_val,
        "bubbleDimensions": self.bubble_dimensions,
        **field_block_object,
    }
```

在 `FieldBlock.setup_field_block()` 开头增加 OCR 分支：

```python
self.engine = field_block_object.get("engine", "omr")
if self.engine == "paddleocr":
    self.setup_ocr_field_block(field_block_object)
    return
```

新增方法：

```python
def setup_ocr_field_block(self, field_block_object):
    field_labels = field_block_object.get("fieldLabels")
    self.parsed_field_labels = parse_fields(
        f"Field Block Labels: {self.name}", field_labels
    )
    if len(self.parsed_field_labels) != 1:
        raise Exception(
            f"PaddleOCR field block '{self.name}' must resolve to exactly one field label, got {self.parsed_field_labels}"
        )
    self.origin = field_block_object.get("origin")
    self.dimensions = field_block_object.get("dimensions")
    self.bubble_dimensions = None
    self.field_type = "__OCR__"
    self.direction = None
    self.multi_select = False
    self.empty_val = ""
    self.region_code = field_block_object.get("regionCode") or self.name
    self.region_name = field_block_object.get("regionName") or self.name
    self.region_type = field_block_object.get("type") or "OCR"
    self.ocr_options = {
        "returnConfidence": True,
        "archiveRegion": True,
        **(field_block_object.get("ocr") or {}),
    }
    self.traverse_bubbles = []
```

在 OMR 分支补充默认属性，便于下游统一读取：

```python
self.region_code = field_block_object.get("regionCode")
self.region_name = field_block_object.get("regionName")
self.region_type = field_block_object.get("type")
self.ocr_options = {}
```

执行命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_template_engine_blocks.py -q
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_region_artifacts.py::test_derives_archive_regions_from_template_field_blocks -q
```

预期：新增模板测试通过，现有 region artifact OMR 派生测试通过。

建议提交：

```bash
git add src/schemas/template_schema.py src/template.py src/tests/test_template_engine_blocks.py
git commit -m "feat: parse engine-based OCR field blocks"
```

### 阶段 2：OCR 引擎适配层

目标：封装 PaddleOCR 依赖，实现可测试、可延迟加载、可 fake 的 OCR 调用接口。

#### 任务 2.1：新增 OCR engine 单元测试

测试文件：`src/tests/test_ocr_engine.py`

测试点：

1. 空 PaddleOCR 输出规范化为空文本和 `0.0` 置信度。
2. 单片段输出返回该文本和置信度。
3. 多片段输出按顺序拼接，并取平均置信度。
4. 未安装 PaddleOCR 时实例化真实适配器不应在 import 阶段失败，只在调用或显式加载时报错，错误消息提示安装依赖。

建议测试核心：

```python
def test_normalize_paddleocr_empty_result():
    assert normalize_paddleocr_result([]) == OcrResult(text="", confidence=0.0, raw=[])


def test_normalize_paddleocr_single_line_result():
    raw = [[[[0, 0], [10, 0], [10, 10], [0, 10]], ("5", 0.98)]]]

    result = normalize_paddleocr_result(raw)

    assert result.text == "5"
    assert result.confidence == 0.98


def test_normalize_paddleocr_multiple_lines_average_confidence():
    raw = [
        [
            [[[0, 0], [10, 0], [10, 10], [0, 10]], ("解", 0.9)],
            [[[0, 20], [10, 20], [10, 30], [0, 30]], ("答", 0.8)],
        ]
    ]

    result = normalize_paddleocr_result(raw)

    assert result.text == "解答"
    assert result.confidence == 0.85
```

#### 任务 2.2：实现 `src/ocr/engine.py`

建议接口：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float
    raw: Any | None = None


class OcrEngine(Protocol):
    def recognize(self, image, options: dict[str, Any] | None = None) -> OcrResult:
        ...
```

真实适配器：

```python
class PaddleOcrEngine:
    def __init__(self):
        self._instances = {}

    def recognize(self, image, options=None):
        options = options or {}
        paddle = self._get_instance(options)
        raw = paddle.ocr(image, det=options.get("det", True), rec=options.get("rec", True), cls=options.get("cls", True))
        return normalize_paddleocr_result(raw)

    def _get_instance(self, options):
        lang = options.get("lang", "ch")
        key = (lang, bool(options.get("cls", True)))
        if key not in self._instances:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise RuntimeError(
                    "PaddleOCR is required for fieldBlocks with engine='paddleocr'. Install paddleocr to enable OCR recognition."
                ) from exc
            self._instances[key] = PaddleOCR(lang=lang, use_angle_cls=key[1])
        return self._instances[key]
```

规范化函数：

```python
def normalize_paddleocr_result(raw):
    lines = []
    for page in raw or []:
        for item in page or []:
            if not item or len(item) < 2:
                continue
            text_conf = item[1]
            if not text_conf or len(text_conf) < 2:
                continue
            text, confidence = text_conf[0], text_conf[1]
            if text is None:
                continue
            try:
                conf = float(confidence)
            except (TypeError, ValueError):
                conf = 0.0
            lines.append((str(text), conf))
    if not lines:
        return OcrResult(text="", confidence=0.0, raw=raw)
    text = "".join(line[0] for line in lines).strip()
    confidence = sum(line[1] for line in lines) / len(lines)
    return OcrResult(text=text, confidence=confidence, raw=raw)
```

执行命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_ocr_engine.py -q
```

建议提交：

```bash
git add src/ocr/__init__.py src/ocr/engine.py src/tests/test_ocr_engine.py
git commit -m "feat: add PaddleOCR engine adapter"
```

### 阶段 3：OCR 区域裁剪与 core 分流

目标：在单张识别流程中让 OCR block 被识别，并且 OMR block 仍走原逻辑。

#### 任务 3.1：新增 OCR 裁剪测试

新增文件：`src/ocr/region.py`  
测试文件：`src/tests/test_core_ocr_dispatch.py`

测试点：

1. 给定灰度图和 OCR block，裁剪区域尺寸等于 `dimensions`。
2. OCR block 越界时抛出明确异常，包含 block 名称和 bbox。
3. fake OCR engine 返回 `OcrResult("5", 0.91)` 时，`read_omr_response()` 的 response 包含 `blankScore1: "5"`。
4. fake OCR engine 被调用的 image shape 等于 OCR block 裁剪尺寸。
5. 纯 OMR 模板不调用 OCR engine。

建议 fake：

```python
class FakeOcrEngine:
    def __init__(self):
        self.calls = []

    def recognize(self, image, options=None):
        self.calls.append((image.copy(), dict(options or {})))
        return OcrResult(text="5", confidence=0.91, raw={"fake": True})
```

#### 任务 3.2：实现 OCR 裁剪 helper

`src/ocr/region.py`：

```python
def crop_ocr_region(image, field_block):
    x, y = field_block.origin
    width, height = field_block.dimensions
    image_height, image_width = image.shape[:2]
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > image_width or y + height > image_height:
        raise ValueError(
            f"OCR field block '{field_block.name}' bbox {[x, y, width, height]} is outside image bounds {[image_width, image_height]}"
        )
    return image[y : y + height, x : x + width].copy()
```

#### 任务 3.3：修改 `src/core.py::ImageInstanceOps`

在 `ImageInstanceOps.__init__()` 增加可注入 OCR engine：

```python
from src.ocr.engine import PaddleOcrEngine

class ImageInstanceOps:
    def __init__(self, tuning_config, ocr_engine=None):
        self.tuning_config = tuning_config
        self.ocr_engine = ocr_engine or PaddleOcrEngine()
        self.last_ocr_results = []
```

如果当前 `__init__` 已有其他初始化逻辑，保留原逻辑，只追加属性。

在 `read_omr_response()` 开始处重置：

```python
self.last_ocr_results = []
```

在遍历 `template.field_blocks` 的 OMR 识别循环前或循环内分流：

```python
omr_field_blocks = [block for block in template.field_blocks if block.engine == "omr"]
ocr_field_blocks = [block for block in template.field_blocks if block.engine == "paddleocr"]
```

现有 bubble 阈值识别循环只遍历 `omr_field_blocks`。

新增 OCR 处理函数：

```python
def read_ocr_response(self, image, field_blocks, file_id):
    from src.ocr.region import crop_ocr_region

    response = {}
    for field_block in field_blocks:
        field = field_block.parsed_field_labels[0]
        crop = crop_ocr_region(image, field_block)
        result = self.ocr_engine.recognize(crop, field_block.ocr_options)
        response[field] = result.text
        x, y = field_block.origin
        width, height = field_block.dimensions
        self.last_ocr_results.append(
            {
                "file_id": file_id,
                "field": field,
                "value": result.text,
                "confidence": float(result.confidence),
                "engine": "paddleocr",
                "regionCode": field_block.region_code,
                "regionName": field_block.region_name,
                "type": field_block.region_type,
                "bbox": {"x": x, "y": y, "width": width, "height": height},
                "artifactLocalPath": "",
            }
        )
    return response
```

在 `read_omr_response()` 中完成 OMR 后合并：

```python
ocr_response = self.read_ocr_response(img, ocr_field_blocks, name)
omr_response.update(ocr_response)
```

注意事项：

1. OCR 使用 resize/normalize 后的 `img`，坐标和模板 `pageDimensions` 保持一致。
2. OCR 不参与 auto align 的 field block shift 第一版处理。若后续要支持，需在 OCR 裁剪时应用 `field_block.shift`，但第一版不做，避免改变现有 OMR 对齐逻辑。
3. OMR 绘制 checked image 时不要要求 OCR block 有 `traverse_bubbles`。
4. 如果当前 `draw_template_layout()` 遍历所有 block 并假设 bubble grid 存在，需要跳过 `engine != "omr"` 或为 OCR block 画矩形框。第一版建议跳过或画矩形但不影响 OMR。

执行命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_core_ocr_dispatch.py -q
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_all_samples.py::test_run_sample1 -q
```

建议提交：

```bash
git add src/core.py src/ocr/region.py src/tests/test_core_ocr_dispatch.py
git commit -m "feat: dispatch PaddleOCR field blocks in core recognition"
```

### 阶段 4：OCR 辅助结果文件写出

目标：在不改变纯 OMR Results CSV 的前提下保存 OCR 置信度和区域元数据。

#### 任务 4.1：新增 entry 或 file helper 测试

测试文件可新增：`src/tests/test_ocr_results_output.py`

测试点：

1. `last_ocr_results` 为空时不创建 `OcrResults.csv`。
2. 有一条 OCR 结果时创建 `Results/OcrResults.csv`。
3. CSV 包含固定表头。
4. `bbox` 序列化为稳定 JSON 字符串。
5. 多张图片追加写入同一个 `OcrResults.csv`。

建议表头：

```python
OCR_RESULTS_COLUMNS = [
    "file_id",
    "input_path",
    "output_path",
    "field",
    "value",
    "confidence",
    "engine",
    "regionCode",
    "regionName",
    "type",
    "bbox",
    "artifactLocalPath",
]
```

#### 任务 4.2：实现 OCR CSV 写出

优先在 `src/utils/file.py` 增加小函数：

```python
def append_ocr_results_csv(results_dir, rows):
    if not rows:
        return None
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "OcrResults.csv"
    write_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OCR_RESULTS_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            serialized = {column: row.get(column, "") for column in OCR_RESULTS_COLUMNS}
            if isinstance(serialized.get("bbox"), dict):
                serialized["bbox"] = json.dumps(serialized["bbox"], ensure_ascii=False, sort_keys=True)
            writer.writerow(serialized)
    return csv_path
```

在 `src/entry.py::_process_single_image()` 单张处理结束、Results 目录已确定时调用：

```python
ocr_rows = getattr(template.image_instance_ops, "last_ocr_results", [])
for row in ocr_rows:
    row["input_path"] = str(in_omr_path)
    row["output_path"] = str(checked_omr_path)
append_ocr_results_csv(results_dir, ocr_rows)
```

实际变量名以 `entry.py` 现状为准。实现时必须就近读取现有 Results CSV 写入路径，不能新增独立输出根目录。

执行命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_ocr_results_output.py -q
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_all_samples.py::test_run_sample1 -q
```

建议提交：

```bash
git add src/entry.py src/utils/file.py src/tests/test_ocr_results_output.py
git commit -m "feat: write OCR confidence results"
```

### 阶段 5：服务聚合扩展

目标：`omr_service.read_results_csv()` 能把 OCR 字段纳入 `answers` 和 `answers_flat`，并带上置信度和区域元数据。

#### 任务 5.1：扩展服务聚合测试

修改测试文件：`src/tests/test_omr_service.py`

新增测试：

```python
def test_read_results_csv_includes_template_paddleocr_fields_with_confidence(tmp_path):
    results_dir = tmp_path / "output" / "Results"
    results_dir.mkdir(parents=True)
    results_csv = results_dir / "Results_001.csv"
    results_csv.write_text(
        "file_id,input_path,output_path,score,id1,q1,blankScore1,solutionAnswer2\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,2,3,A,5,过程文本\n",
        encoding="utf-8",
    )
    (results_dir / "OcrResults.csv").write_text(
        "file_id,input_path,output_path,field,value,confidence,engine,regionCode,regionName,type,bbox,artifactLocalPath\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,blankScore1,5,0.982,paddleocr,blankScore,填空题得分区域,BLANK_SCORE,\"{\"\"height\"\": 60, \"\"width\"\": 160, \"\"x\"\": 120, \"\"y\"\": 80}\",artifacts/sheet-1/blankScore1.png\n"
        "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,solutionAnswer2,过程文本,0.876,paddleocr,solutionAnswer,解答题解答区域,SOLUTION_ANSWER,\"{\"\"height\"\": 220, \"\"width\"\": 500, \"\"x\"\": 100, \"\"y\"\": 200}\",artifacts/sheet-1/solutionAnswer2.png\n",
        encoding="utf-8",
    )
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "template.json").write_text(
        """
        {
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [10, 10],
          "emptyValue": "",
          "preProcessors": [],
          "fieldBlocks": {
            "student_id_area": {"fieldType": "QTYPE_INT", "fieldLabels": ["id1"], "origin": [0, 20], "bubblesGap": 10, "labelsGap": 10},
            "choice_area_1": {"fieldType": "QTYPE_MCQ4", "fieldLabels": ["q1"], "origin": [0, 0], "bubblesGap": 10, "labelsGap": 10},
            "blank_score_1": {"engine": "paddleocr", "fieldLabels": ["blankScore1"], "origin": [120, 80], "dimensions": [160, 60], "regionCode": "blankScore", "regionName": "填空题得分区域", "type": "BLANK_SCORE", "ocr": {"archiveRegion": true}},
            "solution_answer_2": {"engine": "paddleocr", "fieldLabels": ["solutionAnswer2"], "origin": [100, 200], "dimensions": [500, 220], "regionCode": "solutionAnswer", "regionName": "解答题解答区域", "type": "SOLUTION_ANSWER", "ocr": {"archiveRegion": true}}
          },
          "outputColumns": ["id1", "q1", "blankScore1", "solutionAnswer2"],
          "customLabels": {}
        }
        """,
        encoding="utf-8",
    )

    rows = omr_service.read_results_csv(results_csv, template_dir=template_dir)

    assert rows[0]["answers_flat"] == {
        "q1": "A",
        "blankScore1": "5",
        "solutionAnswer2": "过程文本",
    }
    blank_region = next(region for region in rows[0]["answers"] if region["regionCode"] == "blankScore")
    assert blank_region["engine"] == "paddleocr"
    assert blank_region["items"] == [
        {
            "field": "blankScore1",
            "value": "5",
            "confidence": 0.982,
            "artifactLocalPath": "artifacts/sheet-1/blankScore1.png",
        }
    ]
```

同时保留现有测试 `test_read_results_csv_groups_answers_by_business_region_with_confidence()` 不变，确保 OMR-only 返回不被破坏。

#### 任务 5.2：实现 OCR 聚合读取

修改 `src/services/omr_service.py`。

新增 helper：

```python
def _load_ocr_results(results_csv: Path) -> dict[str, dict[str, dict[str, Any]]]:
    ocr_csv = results_csv.parent / "OcrResults.csv"
    if not ocr_csv.exists():
        return {}
    results: dict[str, dict[str, dict[str, Any]]] = {}
    try:
        with ocr_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
            for row in csv.DictReader(csv_file):
                file_id = row.get("file_id", "")
                field = row.get("field", "")
                if not file_id or not field:
                    continue
                try:
                    confidence = float(row.get("confidence", ""))
                except ValueError:
                    confidence = 0.0
                results.setdefault(file_id, {})[field] = {
                    "confidence": confidence,
                    "engine": row.get("engine") or "paddleocr",
                    "regionCode": row.get("regionCode") or "other",
                    "regionName": row.get("regionName") or "其他识别区域",
                    "type": row.get("type") or "OCR",
                    "artifactLocalPath": row.get("artifactLocalPath") or "",
                }
    except Exception:
        return {}
    return results
```

修改 `read_results_csv()`：

```python
ocr_results = _load_ocr_results(results_csv)
return [
    _normalize_result_row(
        row,
        field_regions=field_regions,
        review_confidences=review_confidences.get(row.get("file_id", ""), {}),
        ocr_results=ocr_results.get(row.get("file_id", ""), {}),
    )
    for row in rows
]
```

修改 `_normalize_result_row()` 签名并扩展 recognized fields：

```python
def _normalize_result_row(row, *, field_regions=None, review_confidences=None, ocr_results=None):
    ocr_results = ocr_results or {}
    id_keys = sorted((key for key in row if re.fullmatch(r"id\d+", key)), key=lambda key: int(key[2:]))
    id_digits = [row[key] for key in id_keys]
    omr_answers = {key: value for key, value in row.items() if re.fullmatch(r"q\d+", key)}
    ocr_answers = {key: row.get(key, "") for key in ocr_results if key in row}
    flat_answers = {**omr_answers, **ocr_answers}
    recognized_fields = {**{key: row[key] for key in id_keys}, **flat_answers}
```

修改 `_group_answers_by_region_type()` 支持 OCR metadata：

```python
def _group_answers_by_region_type(flat_answers, *, field_regions, review_confidences, ocr_results=None):
    ocr_results = ocr_results or {}
    grouped = {}
    for field, value in flat_answers.items():
        ocr_metadata = ocr_results.get(field, {})
        metadata = {**field_regions.get(field, {}), **ocr_metadata}
        fallback_region = _infer_business_region(field)
        region_code = metadata.get("regionCode") or fallback_region["regionCode"]
        region = grouped.setdefault(
            region_code,
            {
                "regionCode": region_code,
                "regionName": metadata.get("regionName") or fallback_region["regionName"],
                "type": metadata.get("type") or fallback_region["type"],
                "items": [],
            },
        )
        if metadata.get("engine") == "paddleocr":
            region["engine"] = "paddleocr"
        confidence = metadata.get("confidence")
        if confidence is None:
            confidence = review_confidences.get(field)
        if confidence is None:
            confidence = 1.0 if value != "" else 0.0
        item = {"field": field, "value": value, "confidence": round(float(confidence), 3)}
        if metadata.get("engine") == "paddleocr" and metadata.get("artifactLocalPath"):
            item["artifactLocalPath"] = metadata["artifactLocalPath"]
        region["items"].append(item)
    return list(grouped.values())
```

修改 `_load_field_region_metadata()`：

1. 对 OCR block 不要合并 `FIELD_TYPES`。
2. `engine` 写入 metadata。
3. OCR block 的 `regionName` 优先使用 `regionName`，不要只用 `name`。

建议逻辑：

```python
engine = field_block.get("engine", "omr")
if engine == "paddleocr":
    merged = field_block
    default_region = {"regionCode": field_block.get("regionCode") or region_code, "regionName": field_block.get("regionName") or region_code, "type": field_block.get("type") or "OCR"}
else:
    field_type = field_block.get("fieldType") or "__CUSTOM__"
    merged = {**FIELD_TYPES.get(field_type, {}), **field_block}
    default_region = _default_business_region_for_field_block(field_type, merged)
```

执行命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_omr_service.py -q
```

建议提交：

```bash
git add src/services/omr_service.py src/tests/test_omr_service.py
git commit -m "feat: aggregate PaddleOCR fields in service results"
```

### 阶段 6：OCR 区域截图归档

目标：OCR block 可以参与现有 region artifact 派生和 COS 上传，不新增上传链路。

#### 任务 6.1：扩展 region artifact 测试

修改 `src/tests/test_region_artifacts.py`。

新增测试：

```python
def test_derives_archive_regions_from_paddleocr_template_blocks(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(
        """
        {
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [29, 18],
          "fieldBlocks": {
            "BlankScore1": {"engine": "paddleocr", "fieldLabels": ["blankScore1"], "origin": [120, 80], "dimensions": [160, 60], "regionCode": "blankScore", "regionName": "填空题得分区域", "type": "BLANK_SCORE", "ocr": {"archiveRegion": true}},
            "SolutionAnswer2": {"engine": "paddleocr", "fieldLabels": ["solutionAnswer2"], "origin": [100, 200], "dimensions": [500, 220], "regionCode": "solutionAnswer", "regionName": "解答题解答区域", "type": "SOLUTION_ANSWER", "ocr": {"archiveRegion": true}},
            "NoArchive": {"engine": "paddleocr", "fieldLabels": ["internalOcr"], "origin": [10, 10], "dimensions": [20, 20], "regionCode": "internal", "regionName": "内部区域", "type": "INTERNAL", "ocr": {"archiveRegion": false}}
          }
        }
        """,
        encoding="utf-8",
    )

    regions = derive_archive_regions_from_template(template_path, margin=10)

    assert [(region.region_code, region.region_name, region.type, region.bbox) for region in regions] == [
        ("blankScore", "填空题得分区域", "BLANK_SCORE", [110, 70, 180, 80]),
        ("solutionAnswer", "解答题解答区域", "SOLUTION_ANSWER", [90, 190, 520, 240]),
    ]
```

#### 任务 6.2：修改 `src/services/region_artifacts.py`

当前 `derive_archive_regions_from_template()` 会从 OMR field block 类型推导大区域。新增 OCR block 分支：

```python
for block_name, field_block in field_blocks.items():
    engine = field_block.get("engine", "omr")
    if engine == "paddleocr":
        ocr_options = field_block.get("ocr") or {}
        if ocr_options.get("archiveRegion", True) is False:
            continue
        x, y = field_block["origin"]
        width, height = field_block["dimensions"]
        regions.append(
            RegionSpec(
                region_code=field_block.get("regionCode") or block_name,
                region_name=field_block.get("regionName") or block_name,
                type=field_block.get("type") or "OCR",
                bbox=_apply_margin([x, y, width, height], margin=margin, page_dimensions=page_dimensions),
            )
        )
        continue
```

如果当前文件没有 `_apply_margin()`，就把现有 OMR bbox margin 逻辑抽成小函数，确保 OMR 现有测试仍通过。

执行命令：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_region_artifacts.py -q
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_batch_service.py::test_artifact_upload_failure_is_non_fatal_and_reflected_in_result_metadata -q
```

建议提交：

```bash
git add src/services/region_artifacts.py src/tests/test_region_artifacts.py
git commit -m "feat: archive PaddleOCR template regions"
```

### 阶段 7：依赖和运行配置

目标：不让未安装 PaddleOCR 的环境因为 import 失败影响纯 OMR。

#### 任务 7.1：PaddleOCR 依赖策略

当前仓库没有明确 requirements 文件，只有 `pyproject.toml` 里的 black 配置。因此第一版不要强制把 `paddleocr` 加入默认安装依赖，避免 CI 和纯 OMR 使用者被大型依赖阻塞。

实现策略：

1. `src/ocr/engine.py` 中延迟 import `paddleocr`。
2. 只有模板实际包含 `engine: "paddleocr"` 并调用识别时才加载 PaddleOCR。
3. 第一版明确选择 CPU-only 运行时，不集成 GPU 版，不安装 `paddlepaddle-gpu`，不要求 CUDA/cuDNN/NVIDIA 驱动。
4. 按当前 PaddleOCR 3.x 生态，推荐最小运行时为 CPU 版 PaddlePaddle 加 PaddleOCR 默认包：

```bash
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install paddleocr
```

5. 不默认使用 `paddleocr[all]`，因为第一版只需要通用 OCR，不需要文档解析、KIE、翻译等额外能力。
6. 如果后续固定依赖文件，建议新增可选依赖清单，例如 `requirements-ocr-cpu.txt`，内容固定为 CPU 版。按当前 PaddleOCR 3.x 生态和 PyPI 稳定发布，第一版推荐锁定：

```text
paddlepaddle==3.2.0
paddleocr==3.7.0
```

7. 依赖提交前必须用 CPU 环境做一次 smoke test，确认 `PaddleOCR` 可初始化并对一张小图执行通用 OCR。命令示例：

```bash
python - <<'PY'
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
print(type(ocr).__name__)
PY
```

8. 未安装 PaddleOCR 且模板使用 OCR 时抛出明确错误：

```text
PaddleOCR is required for fieldBlocks with engine='paddleocr'. Install paddleocr to enable OCR recognition.
```

9. 纯 OMR 模板测试必须在未安装 PaddleOCR 环境继续通过。

#### 任务 7.2：可选文档更新

如需要给部署方说明安装方式，新增或更新：

```text
docs/ocr/paddleocr-runtime.md
```

内容只包含 CPU-only 运行时说明，不作为第一版代码必要任务：

```bash
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install paddleocr
```

文档中明确不使用 `paddlepaddle-gpu`，不提供 GPU/CUDA 安装步骤，避免部署方误装 GPU 版本。

## 6. 回归测试矩阵

### 6.1 单元测试

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  src/tests/test_template_engine_blocks.py \
  src/tests/test_ocr_engine.py \
  src/tests/test_core_ocr_dispatch.py \
  src/tests/test_ocr_results_output.py \
  src/tests/test_omr_service.py \
  src/tests/test_region_artifacts.py \
  -q
```

### 6.2 现有 OMR 样例回归

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_all_samples.py::test_run_sample1 -q
```

如果本地样例数据完整，再运行：

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests/test_all_samples.py -q
```

### 6.3 服务和批处理回归

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  src/tests/test_batch_service.py \
  src/tests/test_omr_service.py \
  -q
```

### 6.4 全量测试

```bash
PYTHONPATH=. .venv/bin/python -m pytest src/tests -q
```

### 6.5 静态和格式检查

```bash
git diff --check
```

如果项目当前 black 可用：

```bash
PYTHONPATH=. .venv/bin/python -m black src/ocr src/tests/test_ocr_engine.py src/tests/test_template_engine_blocks.py src/tests/test_core_ocr_dispatch.py src/tests/test_ocr_results_output.py
```

## 7. 验收标准

### 7.1 兼容性验收

1. 不含 `engine` 的旧模板可以正常解析和识别。
2. 纯 OMR 模板不 import PaddleOCR，不要求安装 PaddleOCR。
3. 纯 OMR 模板的 Results CSV 表头和字段值不变。
4. 纯 OMR 模板的 checked image 生成路径不变。
5. 纯 OMR 模板的 region artifact 派生结果不变。
6. 现有 `test_read_results_csv_groups_answers_by_business_region_with_confidence()` 预期不需要修改。

### 7.2 OCR 功能验收

1. 模板中显式 `engine: "paddleocr"` 的 block 会被 OCR 识别。
2. OCR block 的字段值写入 Results CSV 的对应 output column。
3. OCR 置信度写入 `Results/OcrResults.csv`。
4. `omr_service.read_results_csv()` 返回中，OCR 字段进入 `answers_flat`。
5. `answers` 中 OCR region 包含 `regionCode`、`regionName`、`type`、区域级 `engine`，items 只包含 field/value/confidence/artifactLocalPath，不重复返回 `engine`。
6. OCR block 可派生 region screenshot artifact。
7. OCR artifact 上传失败仍不导致整批识别失败，沿用现有 artifact error 记录策略。

### 7.3 错误处理验收

1. OCR block 缺少 `dimensions` 时模板 schema 校验失败。
2. OCR block 解析出多个 field label 时 `Template` 抛出明确异常。
3. OCR bbox 越界时抛出包含 block name 和 bbox 的 `ValueError`。
4. 模板使用 OCR 但未安装 PaddleOCR 时，错误消息指向安装 PaddleOCR，而不是 `ModuleNotFoundError` 泄漏。

## 8. 实施顺序和提交建议

建议按以下顺序实施，每个阶段单独提交：

1. `feat: parse engine-based OCR field blocks`
2. `feat: add PaddleOCR engine adapter`
3. `feat: dispatch PaddleOCR field blocks in core recognition`
4. `feat: write OCR confidence results`
5. `feat: aggregate PaddleOCR fields in service results`
6. `feat: archive PaddleOCR template regions`
7. `docs: document PaddleOCR runtime setup`，可选。

每个提交前至少运行该阶段测试和一个 OMR-only 回归测试。

## 9. 风险和控制措施

| 风险 | 控制措施 |
| --- | --- |
| OCR 改动影响旧 OMR 模板 schema | `engine` 缺省走 OMR `else` 分支，旧模板测试固定覆盖。 |
| PaddleOCR 大依赖影响 CI | 延迟 import，不加入默认依赖，fake engine 覆盖单元测试。OCR 可选依赖固定 CPU-only，不集成 GPU 版。 |
| `read_omr_response()` 现有循环假设所有 block 都有 bubbles | 先拆分 `omr_field_blocks` 和 `ocr_field_blocks`，现有 bubble 逻辑只看 OMR block。 |
| 服务聚合只识别 `id\d+` 和 `q\d+` | 新增 `_load_ocr_results()`，只把模板/OCR 辅助文件确认过的 OCR 字段纳入 answers。 |
| OCR artifact 和现有 artifact 重复或路径不一致 | 不新增上传链路，只扩展 `derive_archive_regions_from_template()`。 |
| OCR confidence 与 weak fill confidence 混淆 | OCR confidence 只来自 `OcrResults.csv`，OMR weak fill 继续来自 `WeakFillReview.csv`。 |
| 多字段 OCR block 后续需求复杂 | 第一版强制单 OCR block 单字段，后续如要多字段必须另写设计。 |

## 10. 非目标

第一版不做以下事项：

1. 不训练 OCR 模型。
2. 不自动检测 OCR 区域位置。
3. 不改变现有 OMR 评分逻辑。
4. 不把所有 OMR response 改成结构化对象。
5. 不把 PaddleOCR 加为默认强依赖，也不集成 PaddleOCR GPU 运行时。
6. 不支持一个 OCR block 输出多个业务字段。
7. 不实现 OCR 结果人工复核界面。
8. 不改变现有 COS 上传目录结构。

## 11. 审查重点

请优先审查以下设计点：

1. `engine` 字段分支是否满足现有模板兼容要求。
2. OCR 辅助结果使用 `OcrResults.csv` 是否符合服务侧消费方式。
3. OCR 字段进入 `answers_flat` 的条件是否足够保守。
4. OCR artifact 复用 `region_artifacts.py` 是否符合当前批处理归档模型。
5. PaddleOCR 不作为默认依赖是否符合部署预期。
6. 第一版单 OCR block 单字段的约束是否符合业务模板制作方式。

