import sqlite3

from src.services.task_store import TaskStore


def test_initialize_creates_schema_and_parent_dir(tmp_path):
    db_path = tmp_path / "nested" / "state" / "tasks.db"
    store = TaskStore(db_path)

    store.initialize()

    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        table_names = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table' order by name"
            )
        }
    assert {"batches", "sheets", "artifacts", "callback_attempts"}.issubset(table_names)


def test_create_get_and_list_batch_round_trips_business_fields_and_json(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    store.initialize()

    created = store.create_batch(
        task_id="task-1",
        exam_id="exam-1",
        external_batch_id="cos-batch-1",
        status="queued",
        callback_url="https://example.test/callback",
        request_json={"sheetKeys": ["a.jpg", "b.jpg"]},
        response_json={"accepted": True},
    )

    assert created["task_id"] == "task-1"
    assert created["request_json"] == {"sheetKeys": ["a.jpg", "b.jpg"]}
    assert created["response_json"] == {"accepted": True}
    assert created["result_json"] is None
    assert created["created_at"].endswith("Z")
    assert created["updated_at"] == created["created_at"]

    fetched = store.get_batch("task-1")
    assert fetched == created

    listed = store.list_batches()
    assert listed == [created]


def test_update_batch_status_sets_updated_and_completed_at_for_terminal_status(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    store.initialize()
    created = store.create_batch(task_id="task-1", exam_id="exam-1", status="queued")

    updated = store.update_batch_status(
        "task-1",
        "completed",
        result_json={"scoreFiles": 2},
        response_json={"delivered": True},
    )

    assert updated["status"] == "completed"
    assert updated["result_json"] == {"scoreFiles": 2}
    assert updated["response_json"] == {"delivered": True}
    assert updated["updated_at"] >= created["updated_at"]
    assert updated["completed_at"] is not None
    assert updated["completed_at"].endswith("Z")


def test_sheet_artifact_and_callback_attempt_persistence_and_list_ordering(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    store.initialize()
    store.create_batch(task_id="task-1", exam_id="exam-1", status="queued")

    first_sheet = store.upsert_sheet(
        task_id="task-1",
        sheet_id="sheet-1",
        source_osskey="input/sheet-1.jpg",
        status="processing",
    )
    second_sheet = store.upsert_sheet(
        task_id="task-1",
        sheet_id="sheet-2",
        source_osskey="input/sheet-2.jpg",
        status="completed",
        result_json={"answers": ["A", "B"]},
    )
    updated_first_sheet = store.upsert_sheet(
        task_id="task-1",
        sheet_id="sheet-1",
        source_osskey="input/sheet-1.jpg",
        status="failed",
        error="unreadable",
    )

    assert updated_first_sheet["created_at"] == first_sheet["created_at"]
    assert updated_first_sheet["updated_at"] >= first_sheet["updated_at"]
    assert store.list_sheets("task-1") == [updated_first_sheet, second_sheet]

    sheet_artifact = store.add_artifact(
        task_id="task-1",
        sheet_id="sheet-1",
        artifact_type="marked_image",
        osskey="outputs/sheet-1.png",
        local_path="/tmp/sheet-1.png",
        metadata_json={"width": 100},
    )
    batch_artifact = store.add_artifact(
        task_id="task-1",
        sheet_id=None,
        artifact_type="summary",
        osskey="outputs/summary.json",
        metadata_json={"count": 2},
    )

    assert store.list_artifacts("task-1") == [sheet_artifact, batch_artifact]
    assert store.list_artifacts("task-1", sheet_id="sheet-1") == [sheet_artifact]

    first_attempt = store.add_callback_attempt(
        task_id="task-1",
        target_url="https://example.test/callback",
        status_code=500,
        success=False,
        error="server error",
        request_json={"taskId": "task-1"},
        response_text="nope",
    )
    second_attempt = store.add_callback_attempt(
        task_id="task-1",
        target_url="https://example.test/callback",
        status_code=200,
        success=True,
        request_json={"taskId": "task-1"},
        response_text="ok",
    )

    assert store.list_callback_attempts("task-1") == [first_attempt, second_attempt]


def test_list_batches_filters_by_exam_status_external_batch_and_paginates(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    store.initialize()
    store.create_batch(task_id="task-1", exam_id="exam-1", external_batch_id="ext-1", status="queued")
    store.create_batch(task_id="task-2", exam_id="exam-1", external_batch_id="ext-2", status="completed")
    store.create_batch(task_id="task-3", exam_id="exam-2", external_batch_id="ext-3", status="completed")
    store.create_batch(task_id="task-4", exam_id="exam-1", external_batch_id="ext-4", status="completed")

    assert [batch["task_id"] for batch in store.list_batches(exam_id="exam-1", status="completed")] == [
        "task-2",
        "task-4",
    ]
    assert [batch["task_id"] for batch in store.list_batches(external_batch_id="ext-3")] == ["task-3"]
    assert [batch["task_id"] for batch in store.list_batches(status="completed", limit=1, offset=1)] == [
        "task-3"
    ]
