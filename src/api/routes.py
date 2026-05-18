import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from models import (
    ApplyFollowUpRequest,
    ConfirmTaskRequest,
    HealthResponse,
    ParseTaskRequest,
    ParsedTaskResponse,
    UpdateTaskRequest,
)
from storage import TaskStorage
from task_handler import apply_follow_up_answer, parse_task_with_missing_info


router = APIRouter()
storage = TaskStorage("data/tasks.json")


def _parser_config() -> dict[str, Any]:
    config: dict[str, Any] = {}
    base_url = os.getenv("OLLAMA_BASE_URL")
    model = os.getenv("OLLAMA_MODEL")
    if base_url:
        config["base_url"] = base_url
    if model:
        config["model"] = model
    return config


def _clean_project(value: Any) -> str | None:
    if value is None:
        return "project"
    project = str(value).strip()
    return project or "project"


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id"),
        "user_id": task.get("user_id", "default"),
        "title": task.get("title") or "",
        "description": task.get("description") or "",
        "date": task.get("date"),
        "time": task.get("time"),
        "time_mode": task.get("time_mode"),
        "duration": task.get("duration"),
        "all_day": bool(task.get("all_day", False)),
        "completed": bool(task.get("completed", False)),
        "archived": bool(task.get("archived", False)),
        "project": _clean_project(task.get("project")),
        "missing_info": task.get("missing_info", []),
        "follow_up_questions": task.get("follow_up_questions", []),
    }


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, app="PlanPal")


@router.post("/api/tasks/parse", response_model=ParsedTaskResponse)
def parse_task_endpoint(request: ParseTaskRequest) -> ParsedTaskResponse:
    try:
        parsed = parse_task_with_missing_info(
            request.user_input,
            backend=os.getenv("LLM_BACKEND", "ollama"),
            user_id=request.user_id,
            **_parser_config(),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ParsedTaskResponse(
        task=parsed,
        missing_info=parsed.get("missing_info", []),
        follow_up_questions=parsed.get("follow_up_questions", []),
    )


@router.post("/api/tasks/follow-up", response_model=ParsedTaskResponse)
def apply_follow_up_endpoint(request: ApplyFollowUpRequest) -> ParsedTaskResponse:
    task = dict(request.task)
    followup_preference = task.get("user_profile", {}).get("followup_preference", "ask_when_ambiguous")

    try:
        for field, answer in request.answers.items():
            task = apply_follow_up_answer(
                task,
                field,
                answer,
                backend=os.getenv("LLM_BACKEND", "ollama"),
                followup_preference=followup_preference,
                user_profile=task.get("user_profile"),
                adaptive_rules=task.get("adaptive_rules"),
                **_parser_config(),
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task["user_id"] = request.user_id
    return ParsedTaskResponse(
        task=task,
        missing_info=task.get("missing_info", []),
        follow_up_questions=task.get("follow_up_questions", []),
    )


@router.post("/api/tasks/confirm")
def confirm_task_endpoint(request: ConfirmTaskRequest) -> dict[str, Any]:
    task = dict(request.task)
    task["user_id"] = request.user_id
    task.setdefault("completed", False)
    task.setdefault("archived", False)
    task["project"] = _clean_project(task.get("project"))
    saved_task = storage.add_task(task)
    return {"task": _public_task(saved_task)}


@router.get("/api/tasks")
def list_tasks_endpoint(user_id: str = Query("default")) -> dict[str, list[dict[str, Any]]]:
    tasks = [_public_task(task) for task in storage.load_tasks() if task.get("user_id", "default") == user_id]
    return {"tasks": tasks}


@router.patch("/api/tasks/{task_id}")
def update_task_endpoint(task_id: str, request: UpdateTaskRequest) -> dict[str, Any]:
    request_data = request.model_dump()
    updates = {key: request_data[key] for key in request.model_fields_set}
    if "project" in updates:
        updates["project"] = _clean_project(updates["project"])
    updated_task = storage.update_task(task_id, updates)
    if updated_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": _public_task(updated_task)}


@router.delete("/api/tasks/{task_id}")
def delete_task_endpoint(task_id: str) -> dict[str, bool]:
    deleted = storage.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}
