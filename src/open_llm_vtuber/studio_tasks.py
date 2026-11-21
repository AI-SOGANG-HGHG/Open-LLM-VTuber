"""Current task state derived from user statements in a Studio history."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
)

TASK_METADATA = "studio_tasks_v1"
MAX_TASKS = 12
TaskTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
TaskEvidence = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)
]
TaskStatus = Literal["not_started", "in_progress", "completed"]


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str | None
    title: TaskTitle
    status: TaskStatus
    evidence: TaskEvidence


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    title: TaskTitle
    status: TaskStatus
    evidence: TaskEvidence
    source_event_id: str
    updated_at: AwareDatetime


def stored_tasks(metadata: dict) -> dict[str, TaskRecord]:
    records = metadata.get(TASK_METADATA)
    if not isinstance(records, list):
        return {}
    tasks = {}
    for record in records[-MAX_TASKS:]:
        try:
            task = TaskRecord.model_validate(record)
        except ValidationError:
            continue
        tasks[task.id] = task
    return tasks


def task_with_title(tasks: dict[str, TaskRecord], title: str) -> TaskRecord | None:
    return next(
        (task for task in tasks.values() if task.title.casefold() == title.casefold()),
        None,
    )


def resolve_task_update(
    tasks: dict[str, TaskRecord],
    update: TaskUpdate,
    text: str,
    event_id: str,
    occurred_at: datetime,
) -> TaskRecord | None:
    if update.evidence not in text:
        return None
    if update.task_id is not None:
        existing = tasks.get(update.task_id)
        if existing is None:
            return None
    else:
        existing = task_with_title(tasks, update.title)
    return TaskRecord(
        id=existing.id if existing else event_id,
        title=existing.title if existing else update.title,
        status=update.status,
        evidence=update.evidence,
        source_event_id=event_id,
        updated_at=occurred_at,
    )


def merge_task_update(
    tasks: dict[str, TaskRecord], update: TaskRecord
) -> list[dict] | None:
    existing = tasks.get(update.id) or task_with_title(tasks, update.title)
    if existing:
        if existing.updated_at >= update.updated_at:
            return None
        update = update.model_copy(update={"id": existing.id})
    records = sorted(
        {**tasks, update.id: update}.values(), key=lambda task: task.updated_at
    )
    return [task.model_dump(mode="json") for task in records[-MAX_TASKS:]]
