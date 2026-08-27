# -*- coding: utf-8 -*-
"""Supply Studio HTTP and Agent entrypoint."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from qwenpaw.plugins.api import PluginApi

import httpx
from uuid import uuid4
from fastapi.responses import StreamingResponse

try:
    from .supply_engine import compute_replenishment, monitor_supply_risk, score_suppliers
    from .supply_workflow import SupplyWorkflowStore
except ImportError:
    backend_dir = str(Path(__file__).resolve().parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from supply_engine import compute_replenishment, monitor_supply_risk, score_suppliers
    from supply_workflow import SupplyWorkflowStore



# ==== 统一登录鉴权：与 zhiyun-auth 相同的 HMAC Token 本地校验（PRD §15 / §17.16） ====
try:
    from .auth_guard import _verify_token_user
except ImportError:  # pragma: no cover
    from auth_guard import _verify_token_user


def require_auth(authorization: str = Header(default="")) -> None:
    """所有业务端点统一要求有效登录令牌；/health 保持开放供探活。"""
    if _verify_token_user(authorization) is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")


router = APIRouter()
PLUGIN_VERSION = "0.4.0"


def _store() -> SupplyWorkflowStore:
    try:
        return SupplyWorkflowStore()
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


class SuppliersRequest(BaseModel):
    suppliers: list[dict[str, Any]] = Field(max_length=2000)


class ReplenishmentRequest(BaseModel):
    items: list[dict[str, Any]] = Field(max_length=2000)


class RiskRequest(BaseModel):
    records: list[dict[str, Any]] = Field(max_length=5000)


class ArtifactReviewRequest(BaseModel):
    action: str
    reviewer: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "available", "version": PLUGIN_VERSION}


@router.post("/suppliers/score", dependencies=[Depends(require_auth)])
async def score(request: SuppliersRequest) -> dict[str, Any]:
    try:
        return score_suppliers(request.suppliers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/replenishment/calc", dependencies=[Depends(require_auth)])
async def replenishment(request: ReplenishmentRequest) -> dict[str, Any]:
    try:
        return {"items": [compute_replenishment(item) for item in request.items], "method": "safety-stock-eoq-v1"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/risk/monitor", dependencies=[Depends(require_auth)])
async def risk(request: RiskRequest) -> dict[str, Any]:
    try:
        return monitor_supply_risk(request.records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/artifacts/supplier", dependencies=[Depends(require_auth)])
async def create_supplier_artifact(request: SuppliersRequest) -> dict[str, Any]:
    try:
        payload = score_suppliers(request.suppliers)
        title = "供应商评估结果"
        return _store().create_artifact("supplier", title, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.post("/artifacts/replenishment", dependencies=[Depends(require_auth)])
async def create_replenishment_artifact(request: ReplenishmentRequest) -> dict[str, Any]:
    try:
        payload = {"items": [compute_replenishment(item) for item in request.items], "method": "safety-stock-eoq-v1"}
        return _store().create_artifact("replenishment", "补货建议", payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.post("/artifacts/risk", dependencies=[Depends(require_auth)])
async def create_risk_artifact(request: RiskRequest) -> dict[str, Any]:
    try:
        payload = monitor_supply_risk(request.records)
        return _store().create_artifact("risk", "供应链风险监控", payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.get("/artifacts", dependencies=[Depends(require_auth)])
async def list_artifacts(kind: str | None = None, limit: int = 100) -> dict[str, Any]:
    try:
        return _store().list_artifacts(kind, limit)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.get("/artifacts/{artifact_id}", dependencies=[Depends(require_auth)])
async def get_artifact(artifact_id: str) -> dict[str, Any]:
    try:
        return _store().get_artifact(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="供应链工件不存在") from exc


@router.post("/artifacts/{artifact_id}/reviews", dependencies=[Depends(require_auth)])
async def review_artifact(artifact_id: str, request: ArtifactReviewRequest) -> dict[str, Any]:
    try:
        return _store().review_artifact(artifact_id, request.action, request.reviewer, request.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="供应链工件不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/artifacts/{artifact_id}/export", dependencies=[Depends(require_auth)])
async def export_artifact(artifact_id: str) -> Response:
    try:
        content, media_type = _store().export_artifact(artifact_id)
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": 'attachment; filename="supply-artifact.json"'})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="供应链工件不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def evaluate_and_review_suppliers(suppliers: list[dict[str, Any]]) -> dict[str, Any]:
    """Score real supplier data and persist a reviewable artifact."""
    payload = score_suppliers(suppliers)
    return _store().create_artifact("supplier", "供应商评估结果", payload)


def recommend_replenishment(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute safety stock, reorder point and suggested quantity for real SKUs."""
    payload = {"items": [compute_replenishment(item) for item in items], "method": "safety-stock-eoq-v1"}
    return _store().create_artifact("replenishment", "补货建议", payload)


def monitor_review_supply_risk(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Monitor real supply records for risk and persist a reviewable artifact."""
    payload = monitor_supply_risk(records)
    return _store().create_artifact("risk", "供应链风险监控", payload)




# ==== 应用内默认智能体（真实模型对话，SSE 流式） ====
CONSOLE_CHAT_URL = "http://127.0.0.1:8088/api/console/chat"
CHAT_TIMEOUT_SECONDS = 300

APP_CONTEXT = (
    "你是「制造云 AI-OS」智能供应中心的智能助手。你可以调用 evaluate_and_review_suppliers、recommend_replenishment、monitor_review_supply_risk 等工具，"
    "基于用户工作台的真实业务数据回答问题；涉及分析结论时先调用对应工具再回答，不要凭空编造数据。"
)


class AgentChatRequest(BaseModel):
    """Client payload for the streaming in-app agent chat."""

    text: str = Field(min_length=1, max_length=4000, description="User message")
    session_id: str | None = Field(default=None, description="Persistent conversation id")
    user_id: str | None = Field(default="default", description="Calling user id")
    app_id: str | None = Field(default="zhiyun-supply-studio", description="Owning app id")
    context: str | None = Field(default=None, description="Extra system context from the UI")
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prior turns [{role, text}] for multi-turn context",
    )


def _build_input(body: AgentChatRequest) -> list[dict[str, Any]]:
    """Build the console ``input`` message list from the dock payload."""
    context = APP_CONTEXT + ("\n" + body.context if body.context else "")
    input_messages: list[dict[str, Any]] = []
    if context:
        input_messages.append({"role": "system", "content": [{"type": "text", "text": context}]})
    for turn in body.history:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        text = turn.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        mapped_role = "assistant" if role in ("bot", "assistant") else "user"
        input_messages.append({"role": mapped_role, "content": [{"type": "text", "text": text}]})
    input_messages.append({"role": "user", "content": [{"type": "text", "text": body.text}]})
    return input_messages


@router.post("/agent/chat", dependencies=[Depends(require_auth)])
async def agent_chat(body: AgentChatRequest) -> StreamingResponse:
    """Proxy a user message to the real console chat and stream its SSE reply."""
    session_id = body.session_id or f"zhiyun-supply-studio-{uuid4().hex}"
    payload = {
        "input": _build_input(body),
        "session_id": session_id,
        "user_id": body.user_id or "default",
        "stream": True,
        "metadata": {
            "app_id": body.app_id or "zhiyun-supply-studio",
            "source_kind": "agent_dock",
            "data_mode": "real",
        },
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async with httpx.AsyncClient(timeout=CHAT_TIMEOUT_SECONDS) as client:
                async with client.stream("POST", CONSOLE_CHAT_URL, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        text = err_body.decode("utf-8", errors="replace")
                        yield f"data: {json.dumps({'error': text})}\n\n"
                        return
                    async for line in response.aiter_lines():
                        yield ("\n" if line == "" else line + "\n")
        except httpx.TimeoutException:
            yield f"data: {json.dumps({'error': '智能体响应超时，请稍后重试'})}\n\n"
        except Exception as exc:  # pragma: no cover - defensive
            yield f"data: {json.dumps({'error': f'调用智能体失败: {exc}'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


class SupplyStudioPlugin:
    def register(self, api: PluginApi) -> None:
        api.register_http_router(router, prefix="/zhiyun-supply-studio", tags=["zhiyun-supply-studio"])
        api.register_tool(
            tool_name="evaluate_and_review_suppliers",
            tool_func=evaluate_and_review_suppliers,
            description="对真实供应商的准时交付率、来料合格率、价格与服务评分进行加权打分，生成 A/B/C/D 分级并等待具名审阅。",
            icon="🏭",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="recommend_replenishment",
            tool_func=recommend_replenishment,
            description="基于年需求、交期与在库/在途数量计算安全库存、再订货点与建议补货量，结果等待人工确认。",
            icon="📦",
            tool_type="internal",
        )
        api.register_tool(
            tool_name="monitor_review_supply_risk",
            tool_func=monitor_review_supply_risk,
            description="对真实订单与物流记录做交期、质量、物流、价格、产能和合规风险监控并生成可审阅风险工件。",
            icon="🚨",
            tool_type="internal",
        )


plugin = SupplyStudioPlugin()
