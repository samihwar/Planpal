from typing import Any

from pydantic import BaseModel, Field


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


class ApplyFollowUpRequest(BaseModel):
    task: dict[str, Any]
    answers: dict[str, Any]
    user_id: str = "default"


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    date: str | None = None
    time: str | None = None
    duration: float | None = None
    completed: bool | None = None
    archived: bool | None = None
    project: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    app: str
