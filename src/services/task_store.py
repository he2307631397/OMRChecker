from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None

_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "canceled"}


class TaskStore:
    """SQLite-backed persistent state store for COS batch orchestration."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                create table if not exists batches (
                    task_id text primary key,
                    exam_id text,
                    external_batch_id text,
                    status text not null,
                    callback_url text,
                    request_json text,
                    response_json text,
                    result_json text,
                    error text,
                    created_at text not null,
                    updated_at text not null,
                    completed_at text
                );

                create index if not exists idx_batches_exam_id on batches(exam_id);
                create index if not exists idx_batches_external_batch_id on batches(external_batch_id);
                create index if not exists idx_batches_status on batches(status);
                create index if not exists idx_batches_created_at on batches(created_at);

                create table if not exists sheets (
                    task_id text not null,
                    sheet_id text not null,
                    source_osskey text not null,
                    status text not null,
                    result_json text,
                    error text,
                    created_at text not null,
                    updated_at text not null,
                    primary key (task_id, sheet_id),
                    foreign key (task_id) references batches(task_id) on delete cascade
                );

                create index if not exists idx_sheets_task_id on sheets(task_id);

                create table if not exists artifacts (
                    id integer primary key autoincrement,
                    task_id text not null,
                    sheet_id text,
                    artifact_type text not null,
                    osskey text not null,
                    local_path text,
                    metadata_json text,
                    created_at text not null,
                    foreign key (task_id) references batches(task_id) on delete cascade,
                    foreign key (task_id, sheet_id) references sheets(task_id, sheet_id) on delete cascade
                );

                create index if not exists idx_artifacts_task_sheet on artifacts(task_id, sheet_id);

                create table if not exists callback_attempts (
                    id integer primary key autoincrement,
                    task_id text not null,
                    target_url text not null,
                    status_code integer,
                    success integer not null,
                    error text,
                    request_json text,
                    response_text text,
                    created_at text not null,
                    foreign key (task_id) references batches(task_id) on delete cascade
                );

                create index if not exists idx_callback_attempts_task_id on callback_attempts(task_id);
                """
            )

    def create_batch(
        self,
        *,
        task_id: str,
        exam_id: str | None = None,
        external_batch_id: str | None = None,
        status: str = "queued",
        callback_url: str | None = None,
        request_json: JsonValue = None,
        response_json: JsonValue = None,
        result_json: JsonValue = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        completed_at = now if status in _TERMINAL_STATUSES else None
        with self._connect() as conn:
            conn.execute(
                """
                insert into batches (
                    task_id, exam_id, external_batch_id, status, callback_url,
                    request_json, response_json, result_json, error,
                    created_at, updated_at, completed_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    exam_id,
                    external_batch_id,
                    status,
                    callback_url,
                    _json_dumps(request_json),
                    _json_dumps(response_json),
                    _json_dumps(result_json),
                    error,
                    now,
                    now,
                    completed_at,
                ),
            )
        batch = self.get_batch(task_id)
        if batch is None:
            raise RuntimeError(f"failed to create batch {task_id}")
        return batch

    def get_batch(self, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("select * from batches where task_id = ?", (task_id,)).fetchone()
        return _batch_from_row(row) if row else None

    def list_batches(
        self,
        *,
        status: str | None = None,
        exam_id: str | None = None,
        external_batch_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = []
        params: list[Any] = []
        if status is not None:
            where.append("status = ?")
            params.append(status)
        if exam_id is not None:
            where.append("exam_id = ?")
            params.append(exam_id)
        if external_batch_id is not None:
            where.append("external_batch_id = ?")
            params.append(external_batch_id)

        query = "select * from batches"
        if where:
            query += " where " + " and ".join(where)
        query += " order by created_at asc, task_id asc"
        if limit is not None:
            query += " limit ? offset ?"
            params.extend([limit, offset])
        elif offset:
            query += " limit -1 offset ?"
            params.append(offset)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_batch_from_row(row) for row in rows]

    def update_batch_status(
        self,
        task_id: str,
        status: str,
        *,
        response_json: JsonValue = None,
        result_json: JsonValue = None,
        error: str | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        terminal_completed_at = completed_at if completed_at is not None else (now if status in _TERMINAL_STATUSES else None)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                update batches
                set status = ?, response_json = ?, result_json = ?, error = ?, updated_at = ?, completed_at = ?
                where task_id = ?
                """,
                (
                    status,
                    _json_dumps(response_json),
                    _json_dumps(result_json),
                    error,
                    now,
                    terminal_completed_at,
                    task_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"batch not found: {task_id}")
        batch = self.get_batch(task_id)
        if batch is None:
            raise KeyError(f"batch not found: {task_id}")
        return batch

    def upsert_sheet(
        self,
        *,
        task_id: str,
        sheet_id: str,
        source_osskey: str,
        status: str,
        result_json: JsonValue = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                insert into sheets (
                    task_id, sheet_id, source_osskey, status, result_json, error, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(task_id, sheet_id) do update set
                    source_osskey = excluded.source_osskey,
                    status = excluded.status,
                    result_json = excluded.result_json,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (task_id, sheet_id, source_osskey, status, _json_dumps(result_json), error, now, now),
            )
            row = conn.execute(
                "select * from sheets where task_id = ? and sheet_id = ?",
                (task_id, sheet_id),
            ).fetchone()
        return _sheet_from_row(row)

    def create_sheet(
        self,
        *,
        task_id: str,
        sheet_id: str,
        source_osskey: str,
        status: str,
        result_json: JsonValue = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                insert into sheets (
                    task_id, sheet_id, source_osskey, status, result_json, error, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, sheet_id, source_osskey, status, _json_dumps(result_json), error, now, now),
            )
            row = conn.execute(
                "select * from sheets where task_id = ? and sheet_id = ?",
                (task_id, sheet_id),
            ).fetchone()
        return _sheet_from_row(row)

    def update_sheet(
        self,
        *,
        task_id: str,
        sheet_id: str,
        source_osskey: str,
        status: str,
        result_json: JsonValue = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                update sheets
                set source_osskey = ?, status = ?, result_json = ?, error = ?, updated_at = ?
                where task_id = ? and sheet_id = ?
                """,
                (source_osskey, status, _json_dumps(result_json), error, now, task_id, sheet_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"sheet not found: {task_id}/{sheet_id}")
            row = conn.execute(
                "select * from sheets where task_id = ? and sheet_id = ?",
                (task_id, sheet_id),
            ).fetchone()
        return _sheet_from_row(row)

    def list_sheets(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "select * from sheets where task_id = ? order by created_at asc, sheet_id asc",
                (task_id,),
            ).fetchall()
        return [_sheet_from_row(row) for row in rows]

    def add_artifact(
        self,
        *,
        task_id: str,
        sheet_id: str | None = None,
        artifact_type: str,
        osskey: str,
        local_path: str | None = None,
        metadata_json: JsonValue = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                insert into artifacts (task_id, sheet_id, artifact_type, osskey, local_path, metadata_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, sheet_id, artifact_type, osskey, local_path, _json_dumps(metadata_json), now),
            )
            row = conn.execute("select * from artifacts where id = ?", (cursor.lastrowid,)).fetchone()
        return _artifact_from_row(row)

    def list_artifacts(self, task_id: str, sheet_id: str | None = None) -> list[dict[str, Any]]:
        query = "select * from artifacts where task_id = ?"
        params: list[Any] = [task_id]
        if sheet_id is not None:
            query += " and sheet_id = ?"
            params.append(sheet_id)
        query += " order by created_at asc, id asc"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_artifact_from_row(row) for row in rows]

    def add_callback_attempt(
        self,
        *,
        task_id: str,
        target_url: str,
        status_code: int | None = None,
        success: bool,
        error: str | None = None,
        request_json: JsonValue = None,
        response_text: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                insert into callback_attempts (
                    task_id, target_url, status_code, success, error, request_json, response_text, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, target_url, status_code, 1 if success else 0, error, _json_dumps(request_json), response_text, now),
            )
            row = conn.execute("select * from callback_attempts where id = ?", (cursor.lastrowid,)).fetchone()
        return _callback_attempt_from_row(row)

    def list_callback_attempts(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "select * from callback_attempts where task_id = ? order by created_at asc, id asc",
                (task_id,),
            ).fetchall()
        return [_callback_attempt_from_row(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json_dumps(value: JsonValue) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None) -> JsonValue:
    if value is None:
        return None
    return json.loads(value)


def _batch_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "exam_id": row["exam_id"],
        "external_batch_id": row["external_batch_id"],
        "status": row["status"],
        "callback_url": row["callback_url"],
        "request_json": _json_loads(row["request_json"]),
        "response_json": _json_loads(row["response_json"]),
        "result_json": _json_loads(row["result_json"]),
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


def _sheet_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "sheet_id": row["sheet_id"],
        "source_osskey": row["source_osskey"],
        "status": row["status"],
        "result_json": _json_loads(row["result_json"]),
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _artifact_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "sheet_id": row["sheet_id"],
        "artifact_type": row["artifact_type"],
        "osskey": row["osskey"],
        "local_path": row["local_path"],
        "metadata_json": _json_loads(row["metadata_json"]),
        "created_at": row["created_at"],
    }


def _callback_attempt_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "target_url": row["target_url"],
        "status_code": row["status_code"],
        "success": bool(row["success"]),
        "error": row["error"],
        "request_json": _json_loads(row["request_json"]),
        "response_text": row["response_text"],
        "created_at": row["created_at"],
    }
