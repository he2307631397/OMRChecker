# fieldBlockOcrs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate `fieldBlockOcrs` template section for OCR blocks while keeping `fieldBlocks` strict for OMR blocks.

**Architecture:** Extend the template JSON schema with a top-level optional `fieldBlockOcrs` object. Update `Template` parsing so OMR blocks and OCR blocks are read from separate sections, then merged into the existing `Template.field_blocks` runtime list. Preserve existing OCR-in-`fieldBlocks` compatibility unless a later product decision removes it.

**Tech Stack:** Python, jsonschema, pytest, existing OMRChecker `Template` and `FieldBlock` classes.

---

## File Structure

- Modify: `src/schemas/template_schema.py`
  - Responsibility: Template JSON schema. Add `fieldBlockOcrs` and keep `fieldBlocks` validation strict for OMR.
- Modify: `src/template.py`
  - Responsibility: Runtime template parsing. Load and parse OMR and OCR sections separately while reusing `FieldBlock` and current label/overflow validation.
- Modify: `src/tests/test_template_engine_blocks.py`
  - Responsibility: Focused unit tests for OMR/OCR block schema and parser behavior.
- Reference only: `docs/superpowers/specs/2026-08-09-field-block-ocrs-design.md`
  - Responsibility: Approved design spec.

---

### Task 1: Add failing parser tests for `fieldBlockOcrs`

**Files:**
- Modify: `src/tests/test_template_engine_blocks.py`

- [ ] **Step 1: Update the test helper to accept `fieldBlockOcrs`**

Replace the helper at the top of `src/tests/test_template_engine_blocks.py` with:

```python
def _write_template(
    path: Path,
    field_blocks: str,
    output_columns: str = '[]',
    field_block_ocrs: str | None = None,
) -> None:
    field_block_ocrs_json = (
        f',\n          "fieldBlockOcrs": {field_block_ocrs}'
        if field_block_ocrs is not None
        else ""
    )
    path.write_text(
        f"""
        {{
          "pageDimensions": [1000, 1000],
          "bubbleDimensions": [20, 20],
          "emptyValue": "",
          "preProcessors": [],
          "fieldBlocks": {field_blocks}{field_block_ocrs_json},
          "outputColumns": {output_columns},
          "customLabels": {{}}
        }}
        """,
        encoding="utf-8",
    )
```

- [ ] **Step 2: Add a failing test for parsing separate OCR blocks**

Append this test to `src/tests/test_template_engine_blocks.py`:

```python
def test_field_block_ocrs_parse_as_paddleocr_blocks(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "choice_area_1": {
            "fieldType": "QTYPE_MCQ4",
            "fieldLabels": ["q1"],
            "origin": [100, 100],
            "bubblesGap": 40,
            "labelsGap": 30
          }
        }
        """,
        '["q1", "blankScore1"]',
        """
        {
          "blank_score_1": {
            "fieldLabels": ["blankScore1"],
            "origin": [300, 100],
            "dimensions": [160, 60],
            "regionCode": "blankScore",
            "regionName": "填空题得分区域",
            "type": "BLANK_SCORE",
            "ocr": {"lang": "ch", "archiveRegion": true}
          }
        }
        """,
    )

    template = Template(template_path, CONFIG_DEFAULTS)

    assert len(template.field_blocks) == 2
    omr_block = template.field_blocks[0]
    ocr_block = template.field_blocks[1]
    assert omr_block.engine == "omr"
    assert ocr_block.engine == "paddleocr"
    assert ocr_block.parsed_field_labels == ["blankScore1"]
    assert ocr_block.origin == [300, 100]
    assert ocr_block.dimensions == [160, 60]
    assert ocr_block.region_code == "blankScore"
    assert ocr_block.region_name == "填空题得分区域"
    assert ocr_block.region_type == "BLANK_SCORE"
    assert ocr_block.ocr_options == {
        "returnConfidence": True,
        "archiveRegion": True,
        "lang": "ch",
    }
    assert ocr_block.traverse_bubbles == []
```

- [ ] **Step 3: Run the new parser test and verify it fails**

Run:

```bash
rtk pytest src/tests/test_template_engine_blocks.py::test_field_block_ocrs_parse_as_paddleocr_blocks -q
```

Expected: FAIL because `fieldBlockOcrs` is rejected by the schema as an additional top-level property or ignored by the parser.

- [ ] **Step 4: Commit the failing tests**

Run:

```bash
rtk git add src/tests/test_template_engine_blocks.py
rtk git commit -m "test: cover separate OCR field blocks"
```

---

### Task 2: Add schema support for `fieldBlockOcrs`

**Files:**
- Modify: `src/schemas/template_schema.py`
- Test: `src/tests/test_template_engine_blocks.py`

- [ ] **Step 1: Run the failing test from Task 1 again**

Run:

```bash
rtk pytest src/tests/test_template_engine_blocks.py::test_field_block_ocrs_parse_as_paddleocr_blocks -q
```

Expected: FAIL before schema and parser implementation.

- [ ] **Step 2: Add OCR block schema definitions**

In `src/schemas/template_schema.py`, immediately before `TEMPLATE_SCHEMA = {`, add:

```python
ocr_options_schema = {
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
}

field_block_ocrs_schema = {
    "description": "OCR recognition regions parsed with PaddleOCR",
    "type": "object",
    "patternProperties": {
        "^.*$": {
            "type": "object",
            "additionalProperties": False,
            "required": ["origin", "dimensions", "fieldLabels"],
            "properties": {
                "fieldLabels": {"type": "array", "items": FIELD_STRING_TYPE},
                "origin": two_positive_integers,
                "dimensions": two_positive_integers,
                "regionCode": {"type": "string"},
                "regionName": {"type": "string"},
                "type": {"type": "string"},
                "ocr": ocr_options_schema,
            },
        }
    },
}
```

- [ ] **Step 3: Reuse the OCR options schema inside existing `fieldBlocks`**

In the existing `fieldBlocks` property, replace the inline `"ocr": { ... }` schema with:

```python
"ocr": ocr_options_schema,
```

- [ ] **Step 4: Add `fieldBlockOcrs` to top-level properties**

Immediately after the existing `fieldBlocks` property block, add:

```python
"fieldBlockOcrs": field_block_ocrs_schema,
```

Make sure the top-level schema still has `additionalProperties: False` and does not add `fieldBlockOcrs` to the top-level `required` list.

- [ ] **Step 5: Run the parser test and verify the failure changed**

Run:

```bash
rtk pytest src/tests/test_template_engine_blocks.py::test_field_block_ocrs_parse_as_paddleocr_blocks -q
```

Expected: FAIL because schema accepts the property, but the parser still does not load `fieldBlockOcrs` into `Template.field_blocks`.

- [ ] **Step 6: Commit schema support**

Run:

```bash
rtk git add src/schemas/template_schema.py
rtk git commit -m "feat: add fieldBlockOcrs schema"
```

---

### Task 3: Implement parser support for `fieldBlockOcrs`

**Files:**
- Modify: `src/template.py`
- Test: `src/tests/test_template_engine_blocks.py`

- [ ] **Step 1: Update `Template.__init__` to read `fieldBlockOcrs`**

In `src/template.py`, replace the tuple assignment in `Template.__init__` with:

```python
(
    custom_labels_object,
    field_blocks_object,
    field_block_ocrs_object,
    output_columns_array,
    pre_processors_object,
    self.bubble_dimensions,
    self.global_empty_val,
    self.options,
    self.page_dimensions,
) = map(
    json_object.get,
    [
        "customLabels",
        "fieldBlocks",
        "fieldBlockOcrs",
        "outputColumns",
        "preProcessors",
        "bubbleDimensions",
        "emptyValue",
        "options",
        "pageDimensions",
    ],
)
```

Then replace the field-block setup call with:

```python
self.setup_field_blocks(field_blocks_object, field_block_ocrs_object or {})
```

- [ ] **Step 2: Update `setup_field_blocks` to parse both collections**

Replace `setup_field_blocks` with:

```python
def setup_field_blocks(self, field_blocks_object, field_block_ocrs_object=None):
    # Add field_blocks
    self.field_blocks = []
    self.all_parsed_labels = set()
    for block_name, field_block_object in field_blocks_object.items():
        self.parse_and_add_field_block(block_name, field_block_object)

    for block_name, field_block_object in (field_block_ocrs_object or {}).items():
        self.parse_and_add_ocr_field_block(block_name, field_block_object)
```

- [ ] **Step 3: Add an OCR-specific parser helper**

Immediately after `parse_and_add_field_block`, add:

```python
def parse_and_add_ocr_field_block(self, block_name, field_block_object):
    field_block_object = {
        "engine": "paddleocr",
        "ocr": {},
        **field_block_object,
    }
    block_instance = FieldBlock(block_name, field_block_object)
    self.field_blocks.append(block_instance)
    self.validate_parsed_labels(field_block_object["fieldLabels"], block_instance)
```

- [ ] **Step 4: Run the new parser test and verify it passes**

Run:

```bash
rtk pytest src/tests/test_template_engine_blocks.py::test_field_block_ocrs_parse_as_paddleocr_blocks -q
```

Expected: PASS.

- [ ] **Step 5: Run existing engine block tests**

Run:

```bash
rtk pytest src/tests/test_template_engine_blocks.py -q
```

Expected: PASS for all tests in the file.

- [ ] **Step 6: Commit parser support**

Run:

```bash
rtk git add src/template.py
rtk git commit -m "feat: parse separate OCR field blocks"
```

---

### Task 4: Add validation and regression tests

**Files:**
- Modify: `src/tests/test_template_engine_blocks.py`

- [ ] **Step 1: Add a schema failure test for missing OCR dimensions**

Append this test:

```python
def test_field_block_ocrs_require_dimensions(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "choice_area_1": {
            "fieldType": "QTYPE_MCQ4",
            "fieldLabels": ["q1"],
            "origin": [100, 100],
            "bubblesGap": 40,
            "labelsGap": 30
          }
        }
        """,
        '["q1", "blankScore1"]',
        """
        {
          "blank_score_1": {
            "fieldLabels": ["blankScore1"],
            "origin": [300, 100]
          }
        }
        """,
    )

    with pytest.raises(Exception):
        Template(template_path, CONFIG_DEFAULTS)
```

- [ ] **Step 2: Add a duplicate-label test across OMR and OCR**

Append this test:

```python
def test_field_block_ocrs_labels_cannot_overlap_omr_labels(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "choice_area_1": {
            "fieldType": "QTYPE_MCQ4",
            "fieldLabels": ["q1"],
            "origin": [100, 100],
            "bubblesGap": 40,
            "labelsGap": 30
          }
        }
        """,
        '["q1"]',
        """
        {
          "blank_score_1": {
            "fieldLabels": ["q1"],
            "origin": [300, 100],
            "dimensions": [160, 60]
          }
        }
        """,
    )

    with pytest.raises(
        Exception,
        match="The field strings for field block blank_score_1 overlap with other existing fields",
    ):
        Template(template_path, CONFIG_DEFAULTS)
```

- [ ] **Step 3: Add an OCR overflow test**

Append this test:

```python
def test_field_block_ocrs_must_stay_inside_page_dimensions(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        "{}",
        '["blankScore1"]',
        """
        {
          "blank_score_1": {
            "fieldLabels": ["blankScore1"],
            "origin": [950, 950],
            "dimensions": [100, 100]
          }
        }
        """,
    )

    with pytest.raises(
        Exception,
        match="Overflowing field block 'blank_score_1' with origin \\[950, 950\\] and dimensions \\[100, 100\\] in template with dimensions \\[1000, 1000\\]",
    ):
        Template(template_path, CONFIG_DEFAULTS)
```

- [ ] **Step 4: Add an invalid OMR regression test**

Append this test:

```python
def test_field_blocks_remain_strict_omr_blocks(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        """
        {
          "choice_area_1": {
            "fieldLabels": ["q1"],
            "origin": [100, 100],
            "bubblesGap": null,
            "labelsGap": null,
            "fieldType": ""
          }
        }
        """,
        '["q1"]',
    )

    with pytest.raises(Exception):
        Template(template_path, CONFIG_DEFAULTS)
```

- [ ] **Step 5: Add a test proving OCR section ignores app-side OMR defaults outside it**

Append this test:

```python
def test_field_block_ocrs_are_not_polluted_by_empty_omr_defaults(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(
        template_path,
        "{}",
        '["blankScore1"]',
        """
        {
          "blank_score_1": {
            "fieldLabels": ["blankScore1"],
            "origin": [300, 100],
            "dimensions": [160, 60],
            "ocr": {"lang": "ch"}
          }
        }
        """,
    )

    template = Template(template_path, CONFIG_DEFAULTS)

    assert len(template.field_blocks) == 1
    assert template.field_blocks[0].engine == "paddleocr"
    assert template.field_blocks[0].ocr_options["lang"] == "ch"
```

- [ ] **Step 6: Run the full engine block test file**

Run:

```bash
rtk pytest src/tests/test_template_engine_blocks.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit validation tests**

Run:

```bash
rtk git add src/tests/test_template_engine_blocks.py
rtk git commit -m "test: cover OCR field block validation"
```

---

### Task 5: Run broader verification and update docs if implementation behavior differs

**Files:**
- Modify only if behavior differs from approved spec: `docs/superpowers/specs/2026-08-09-field-block-ocrs-design.md`
- Verify: `src/tests/test_template_engine_blocks.py`, `src/tests/test_template_validations.py`

- [ ] **Step 1: Run focused template tests**

Run:

```bash
rtk pytest src/tests/test_template_engine_blocks.py src/tests/test_template_validations.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full project tests**

Run:

```bash
rtk pytest -q
```

Expected: PASS. If unrelated environment tests fail, capture the exact failing test names and rerun the focused template tests to prove the changed area passes.

- [ ] **Step 3: Check git diff**

Run:

```bash
rtk git diff -- src/schemas/template_schema.py src/template.py src/tests/test_template_engine_blocks.py docs/superpowers/specs/2026-08-09-field-block-ocrs-design.md
```

Expected: Diff contains only schema, parser, tests, and any necessary spec correction.

- [ ] **Step 4: Commit final verification docs correction if needed**

If Step 3 shows a spec correction, run:

```bash
rtk git add docs/superpowers/specs/2026-08-09-field-block-ocrs-design.md
rtk git commit -m "docs: align OCR field block spec"
```

If there is no spec correction, do not create an empty commit.

- [ ] **Step 5: Report implementation result**

Final report must include:

```markdown
Implemented `fieldBlockOcrs` support.

Validation run:
- `rtk pytest src/tests/test_template_engine_blocks.py src/tests/test_template_validations.py -q`
- `rtk pytest -q`

Behavior:
- Existing `fieldBlocks` OMR templates remain strict.
- New `fieldBlockOcrs` OCR templates parse as `engine == "paddleocr"`.
- Duplicate labels and overflow checks apply across OMR and OCR blocks.
```
