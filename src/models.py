from datetime import date, time
from typing import Any, Literal
import re

from pydantic import BaseModel, Field, field_validator


class ParseTaskRequest(BaseModel):
    user_input: str = Field(..., min_length=1)
    user_id: str = "default"


class ParsedTaskResponse(BaseModel):
    task: dict[str, Any]
    missing_info: list[str] = []
    follow_up_questions: list[dict[str, str]] = []


class ConfirmTaskRequest(BaseModel):
    task: dict[str, Any]
    user_id: str = "default"

    @field_validator("task")
    @classmethod
    def validate_task(cls, task: dict[str, Any]) -> dict[str, Any]:
        validated = UpdateTaskRequest.model_validate(task)
        if not validated.title:
            raise ValueError("A task title is required")
        return {**task, **validated.model_dump(exclude_unset=True)}


class ApplyFollowUpRequest(BaseModel):
    task: dict[str, Any]
    answers: dict[str, Any]
    user_id: str = "default"


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    date: str | None = None
    time: str | None = None
    time_mode: Literal["timed", "none"] | None = None
    duration: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    all_day: bool | None = None
    completed: bool | None = None
    archived: bool | None = None
    project: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("A task title is required")
        return value.strip()

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Date must use YYYY-MM-DD")
        return date.fromisoformat(value).isoformat()

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"\d{2}:\d{2}", value):
            raise ValueError("Time must use HH:MM")
        return time.fromisoformat(value).strftime("%H:%M")


class HealthResponse(BaseModel):
    ok: bool
    app: str
