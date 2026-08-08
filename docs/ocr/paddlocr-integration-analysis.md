# PaddleOCR 集成方案分析

日期：2026-08-08  
分支：`paddlocr-integration`  
目标：在当前 OMRChecker 项目中集成 PaddleOCR 能力，同时保证现有 OMR 识别业务、接口和输出默认不受影响。

## 1. 当前项目识别链路梳理

### 1.1 OMR 核心 CLI 链路

当前 OMR 核心入口是 `src/entry.py`：

- `entry_point(input_dir, args)` 校验输入目录后调用 `process_dir`。
- `process_dir(...)` 递归扫描目录，读取 `config.json`、`template.json`、`evaluation.json`。
- 对图片和 PDF 执行预处理、模板定位、填涂识别、评分和 CSV 输出。
- 结果文件由 `setup_outputs_for_template` 管理，典型输出包括：
  - `Results/Results_*.csv`
  - `CheckedOMRs/*.png`
  - `Errors/*.csv`
  - `WeakFillReview.csv`

这条链路是现有 OMR 识别的事实来源，不应直接混入 OCR 逻辑。

### 1.2 服务层 OMR 封装

`src/services/omr_service.py` 将 CLI 识别封装成框架无关 API：

- `prepare_upload_input_dir(...)` 为上传文件创建隔离输入和输出目录。
- `run_omr_directory(input_dir, output_dir, template_dir=None, auto_align=False, debug=False)` 调用 `entry_point` 或 `process_dir`。
- `read_results_csv(...)` 将 OMR CSV 转换为 Java/Robyn 接口友好的 JSON。
- `get_checked_image_path(...)` 从输出目录中定位 checked image。

Web 服务和测试都应继续通过该层调用 OMR，避免绕过既有稳定行为。

### 1.3 Robyn Web 服务链路

`web/robyn_app.py` 提供两类接口：

1. 单任务接口：`/api/omr/tasks`
   - 接收上传文件或内部输入目录。
   - 使用线程池调用 `run_omr_directory`。
   - 返回异步任务状态和结果。

2. 批量接口：`/api/omr/batches` 和 `/api/omr/batch-tasks`
   - 解析 `BatchRecognitionRequest`。
   - 通过 `BatchRecognitionService` 保存任务、下载 COS 文件、执行识别、上传 artifacts、回调业务系统。
   - 当前 Robyn 默认 wiring 中注入 `_run_batch_omr` 作为 `recognition_runner`。

### 1.4 批量识别扩展点

`src/services/batch_service.py` 已经有较好的扩展边界：

- `RecognitionRunner = Callable[[RecognitionContext], RecognitionOutput]`
- `BatchRecognitionService(..., recognition_runner=...)`
- `RecognitionContext` 提供：
  - `task_id`
  - `sheet`
  - `source_path`
  - `workdir`
  - `request`
  - `template_dir`
- `RecognitionOutput` 提供：
  - `result`
  - `checked_image_path`

这意味着 PaddleOCR 可以作为 runner 的增强步骤接入，而不需要修改 `BatchRecognitionService.process_batch` 的核心状态机。

## 2. PaddleOCR 集成目标与非目标

### 2.1 目标

1. 在需要时对答题卡中的文本区域执行 OCR，例如姓名、班级、学校、主观题文字、条码旁文本等。
2. OCR 结果以独立字段或独立 artifacts 形式返回，不改变现有 OMR 判题字段语义。
3. OCR 默认关闭，未显式启用时，所有 CLI、Web 和批量 OMR 行为与当前完全一致。
4. OCR 失败不导致 OMR 失败。OCR 错误应作为附加错误或警告记录。
5. 支持按模板或请求指定 OCR 区域，避免全图 OCR 造成性能和误识别风险。

### 2.2 非目标

1. 不用 OCR 替代现有填涂识别算法。
2. 不改变 `Results_*.csv` 的既有列和含义。
3. 不把 PaddleOCR 作为基础运行依赖强制安装到默认 OMR 环境。
4. 不在第一阶段做复杂版面分析或主观题自动评分。
5. 不要求所有接口立即返回 OCR 结果。可优先支持 batch 服务，再扩展单任务接口。

## 3. 不影响现有 OMR 的核心原则

### 3.1 默认关闭

新增配置必须默认禁用：

```json
{
  "recognition": {
    "debugArtifacts": false,
    "ocr": {
      "enabled": false,
      "provider": "paddleocr"
    }
  }
}
```

同时支持请求级开关：

```json
{
  "recognitionConfig": {
    "ocr": {
      "enabled": true
    }
  }
}
```

若服务配置和请求配置都未启用 OCR，则不导入 PaddleOCR，不初始化模型，不产生任何 OCR 输出。

### 3.2 旁路增强，不进入 OMR 核心

PaddleOCR 应放在服务增强层，而不是 `src/entry.py` 或模板填涂识别内部。推荐位置：

```text
Robyn batch request
  -> BatchRecognitionService.process_batch
    -> injected recognition_runner
      -> run_omr_directory(...)      # 现有 OMR
      -> optional OCR enhancer       # 新增旁路
      -> merged JSON result          # OMR 原字段保持不变，OCR 放新增字段
```

### 3.3 OMR 输出兼容

现有结果字段应保持稳定：

- `file_id`
- `input_path`
- `output_path`
- `score`
- `exam_id`
- `answers`
- `answers_flat`
- `weak_marks`
- `review_required`
- `checkedImagePath`
- `checkedImageOsskey`
- `regionImages`

OCR 只能追加，例如：

```json
{
  "ocr": {
    "enabled": true,
    "provider": "paddleocr",
    "status": "completed",
    "regions": [
      {
        "regionCode": "studentName",
        "regionName": "姓名区域",
        "type": "TEXT",
        "text": "张三",
        "confidence": 0.982,
        "bbox": [120, 80, 260, 130]
      }
    ],
    "errors": []
  }
}
```

### 3.4 OCR 异常隔离

推荐状态策略：

- OMR 成功，OCR 成功：sheet `completed`，结果包含 `ocr.status=completed`。
- OMR 成功，OCR 失败：sheet 仍为 `completed`，结果包含 `ocr.status=failed` 和 `ocr.errors`。
- OMR 失败：保持当前 sheet `failed` 逻辑，不额外运行 OCR，除非后续明确需要“失败图像 OCR 诊断”。

这样不会因为 PaddleOCR 模型、GPU、依赖、文本区域配置问题影响现有填涂识别业务。

## 4. 推荐架构

### 4.1 新增模块边界

建议新增独立包：

```text
src/services/ocr/
  __init__.py
  models.py
  config.py
  paddle_provider.py
  region_resolver.py
  enhancer.py
```

职责划分：

- `models.py`
  - 定义 `OcrRegion`, `OcrResult`, `OcrError` 等 dataclass。
- `config.py`
  - 从 `ServiceConfig.recognition` 和 `BatchRecognitionRequest.recognition_config` 合并 OCR 配置。
- `paddle_provider.py`
  - 延迟导入 PaddleOCR。
  - 封装模型初始化和推理。
  - 将 PaddleOCR 原始输出转换为内部稳定结构。
- `region_resolver.py`
  - 从模板配置、服务配置或请求配置解析 OCR 区域。
  - 验证 bbox 合法性。
- `enhancer.py`
  - 接收 `RecognitionContext`、OMR result、checked/source image。
  - 判断是否启用 OCR。
  - 调用 provider 后把 OCR 结果追加到 result。

### 4.2 Runner 组合方式

保留现有 `_run_batch_omr(context)`，新增组合 runner：

```python
def _run_batch_recognition(context: RecognitionContext) -> RecognitionOutput:
    omr_output = _run_batch_omr(context)
    return enhance_with_ocr_if_enabled(
        context=context,
        output=omr_output,
        service_config=_BATCH_SERVICE.config,
    )
```

`_build_batch_service()` 中只替换注入对象：

```python
recognition_runner=_run_batch_recognition
```

关键点：

- 当 OCR 未启用时，`enhance_with_ocr_if_enabled` 直接返回原 `RecognitionOutput`，不复制、不改写。
- 当 OCR 启用时，只对 `dict` 类型 result 追加 `ocr` 字段。
- 不修改 `BatchRecognitionService.process_batch` 的任务状态、artifact 上传、callback 流程。

### 4.3 单任务接口接入顺序

第一阶段建议只接入 batch runner，因为 batch 已经有 `recognitionConfig`、模板依赖、COS、callback 和 artifact 体系。

第二阶段再扩展 `/api/omr/tasks`：

- 接收 `recognitionConfig.ocr`。
- 复用同一个 `enhance_with_ocr_if_enabled`。
- 保持旧请求不带 `recognitionConfig` 时结果不变。

## 5. OCR 区域配置方案

### 5.1 推荐区域来源优先级

从高到低：

1. 请求级 `recognitionConfig.ocr.regions`
2. 模板目录中的 `template.json` 扩展字段
3. 服务级 `config/robyn-service.json` 的默认 OCR 区域

请求级适合临时实验和不同批次定制。模板级适合生产稳定配置。服务级仅适合全局默认或兜底。

### 5.2 区域配置格式建议

```json
{
  "recognitionConfig": {
    "ocr": {
      "enabled": true,
      "regions": [
        {
          "regionCode": "studentName",
          "regionName": "姓名区域",
          "type": "TEXT",
          "bbox": [120, 80, 260, 130],
          "language": "ch"
        }
      ]
    }
  }
}
```

字段说明：

- `regionCode`：业务稳定编码。
- `regionName`：显示名称。
- `type`：建议先支持 `TEXT`，后续可扩展 `NUMBER`、`HANDWRITING`。
- `bbox`：基于 checked image 或 source image 坐标，格式 `[x1, y1, x2, y2]`。
- `language`：传给 PaddleOCR provider 的语言或模型选择参数。

### 5.3 坐标基准

推荐第一阶段使用 checked image 坐标：

- OMR 已经完成预处理、旋转、对齐和模板匹配。
- checked image 与现有归档区域截图逻辑更接近。
- 可复用 `archiveRegions` 的思路进行区域裁剪。

如果 checked image 不存在，可降级到 source image，但需要在结果中标明 `coordinateSpace=source`，避免业务侧误用。

## 6. 依赖与部署策略

### 6.1 可选依赖

当前 `requirements.txt` 没有 PaddleOCR 相关依赖。建议不要直接加入默认运行依赖，而是新增可选文件：

```text
requirements.ocr.txt
```

内容示例：

```text
-r requirements.txt
paddleocr>=2.7.0
paddlepaddle>=2.6.0
```

如部署 GPU 版本，应通过部署文档选择对应 PaddlePaddle 包，不要在通用 requirements 中固定 GPU 包。

### 6.2 延迟导入

`paddle_provider.py` 应在实际启用 OCR 时才执行：

```python
try:
    from paddleocr import PaddleOCR
except ImportError as exc:
    raise OcrProviderUnavailableError(...)
```

这样默认 OMR 服务启动不依赖 PaddleOCR。

### 6.3 模型初始化

PaddleOCR 初始化开销较大，建议 provider 单例缓存：

- 按 `(language, use_angle_cls, model_dir, device)` 作为缓存 key。
- 服务启动时不预热，除非显式配置 `ocr.preload=true`。
- 并发安全需要用 lock 保护首次初始化。

## 7. API 返回结构建议

### 7.1 Sheet result 增量字段

OCR 结果放在 sheet result 内的 `ocr` 字段：

```json
{
  "sheetId": "sheet-1",
  "status": "completed",
  "result": {
    "file_id": "source.png",
    "answers": [],
    "ocr": {
      "enabled": true,
      "provider": "paddleocr",
      "status": "completed",
      "regions": [],
      "errors": []
    }
  }
}
```

因为 `SheetRecognitionResult.to_callback_dict()` 会把 result dict 的顶层 key 透出到 sheet payload，业务侧也能直接读取 `sheet.ocr`。

### 7.2 OCR artifacts

若需要保存 OCR 区域截图，可复用 artifact 思路，新增 artifact type：

- `ocr_region_screenshot`
- `ocr_debug_image`
- `ocr_raw_output`

第一阶段建议只返回结构化文本，不上传 OCR debug artifacts，除非 `debugArtifacts=true`。

## 8. 错误处理策略

### 8.1 配置错误

请求显式启用 OCR 但配置非法时，建议在请求解析或 runner 开始阶段失败：

- `bbox` 不是四个数字。
- `regionCode` 为空。
- `regions` 不是数组。

这属于调用方请求错误，可让该 sheet 失败或让 batch 提交返回 `ValueError`。为减少对 OMR 的影响，建议第一阶段在 batch 提交解析阶段只做类型校验，在单 sheet 处理阶段把 OCR 配置错误写入 `ocr.errors`，不影响 OMR 成功状态。

### 8.2 Provider 不可用

当 `ocr.enabled=true` 但环境未安装 PaddleOCR：

```json
{
  "ocr": {
    "enabled": true,
    "provider": "paddleocr",
    "status": "failed",
    "regions": [],
    "errors": [
      {
        "code": "OCR_PROVIDER_UNAVAILABLE",
        "message": "PaddleOCR is not installed. Install requirements.ocr.txt to enable OCR."
      }
    ]
  }
}
```

OMR sheet 仍应保持 `completed`。

### 8.3 推理失败

单个区域推理失败不应影响其他区域：

- 成功区域进入 `regions`。
- 失败区域进入 `errors`，包含 `regionCode`。
- 整体 `ocr.status` 可为 `partial_failed`。

## 9. 测试策略

### 9.1 回归保护：OCR 默认关闭

必须添加测试证明默认行为不变：

1. 不带 `recognitionConfig.ocr` 的 batch 请求，结果不包含 `ocr` 字段。
2. `config/robyn-service.json` 默认未启用 OCR 时，不导入 PaddleOCR。
3. 现有 `test_default_batch_service_wires_real_omr_runner` 仍通过。
4. 现有 `test_batch_models.py` 对 `recognitionConfig` 的兼容行为仍通过。

### 9.2 OCR 启用但 provider 缺失

模拟未安装 PaddleOCR：

- 输入：`recognitionConfig.ocr.enabled=true`
- 期望：OMR runner 输出保留，`ocr.status=failed`，错误码为 `OCR_PROVIDER_UNAVAILABLE`。

### 9.3 OCR provider mock

不在单元测试中加载真实 PaddleOCR。使用 fake provider：

- 给定 checked image 和 bbox，返回固定文本。
- 验证结果追加到 `ocr.regions`。
- 验证 OMR 原字段完全不变。

### 9.4 区域配置解析

覆盖：

- 请求级 regions 优先。
- 模板级 regions 次之。
- 服务级 regions 兜底。
- 非法 bbox 被记录为 OCR 错误。

### 9.5 集成测试

在安装 PaddleOCR 的环境中单独运行慢测试：

- 标记为 `pytest.mark.ocr`。
- 默认 CI 不运行。
- 使用小图片或 fixture 验证真实 OCR provider 可以返回结果。

## 10. 推荐实施步骤

1. 增加文档和配置 schema 说明。
2. 增加 `src/services/ocr` 模块和 dataclass。
3. 实现 `resolve_ocr_config`，默认关闭。
4. 实现 `OcrProvider` 协议和 fake provider 测试。
5. 实现 `PaddleOcrProvider`，延迟导入 PaddleOCR。
6. 实现 `enhance_with_ocr_if_enabled`。
7. 在 `web/robyn_app.py` 中将 `_run_batch_omr` 包装为 `_run_batch_recognition`。
8. 添加单元测试，重点验证默认关闭不影响 OMR。
9. 增加 `requirements.ocr.txt` 和部署说明。
10. 如需支持单任务接口，再复用 enhancer 扩展 `/api/omr/tasks`。

## 11. 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| PaddleOCR 依赖重、安装复杂 | 默认服务无法启动或部署变慢 | 可选依赖、延迟导入、默认关闭 |
| OCR 推理慢 | batch 处理耗时增加 | 只对配置区域 OCR、限制区域数量、后续支持并发或队列 |
| OCR 错误影响 OMR | 现有业务失败 | 异常隔离，OCR 错误写入 `ocr.errors` |
| 坐标不一致 | OCR 区域裁剪错误 | 第一阶段统一 checked image 坐标，并在结果标注 coordinateSpace |
| 输出结构破坏业务兼容 | Java 侧解析失败 | 只追加 `ocr` 字段，不修改现有字段 |
| 真实模型测试不稳定 | CI flaky | 默认使用 fake provider，真实 PaddleOCR 测试单独标记 |

## 12. 结论

推荐采用“服务层旁路增强”方案：

- 不修改 `src/entry.py` 的 OMR 核心流程。
- 不修改既有 CSV 输出和 OMR 判题字段。
- 利用 `BatchRecognitionService` 已有 `recognition_runner` 注入点，在 Robyn batch runner 中组合 OMR 与可选 OCR。
- OCR 默认关闭、依赖可选、异常隔离。
- OCR 结果作为 `ocr` 增量字段返回。

该方案对现有 OMR 识别业务影响最小，同时为后续文本识别、主观题处理和 OCR artifacts 留出清晰扩展空间。
