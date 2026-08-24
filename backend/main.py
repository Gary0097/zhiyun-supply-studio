# -*- coding: utf-8 -*-
"""Supply Studio HTTP and Agent entrypoint."""

from __future__ import annotations

import json
import sys
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from qwenpaw.plugins.api import PluginApi

try:
    from .supply_engine import compute_replenishment, monitor_supply_risk, score_suppliers
    from .supply_workflow import SupplyWorkflowStore
except ImportError:
    backend_dir = str(Path(__file__).resolve().parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from supply_engine import compute_replenishment, monitor_supply_risk, score_suppliers
    from supply_workflow import SupplyWorkflowStore

router = APIRouter()
PLUGIN_VERSION = "0.2.0"


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


@router.post("/suppliers/score")
async def score(request: SuppliersRequest) -> dict[str, Any]:
    try:
        return score_suppliers(request.suppliers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/replenishment/calc")
async def replenishment(request: ReplenishmentRequest) -> dict[str, Any]:
    try:
        return {"items": [compute_replenishment(item) for item in request.items], "method": "safety-stock-eoq-v1"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/risk/monitor")
async def risk(request: RiskRequest) -> dict[str, Any]:
    try:
        return monitor_supply_risk(request.records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/artifacts/supplier")
async def create_supplier_artifact(request: SuppliersRequest) -> dict[str, Any]:
    try:
        payload = score_suppliers(request.suppliers)
        title = "供应商评估结果"
        return _store().create_artifact("supplier", title, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.post("/artifacts/replenishment")
async def create_replenishment_artifact(request: ReplenishmentRequest) -> dict[str, Any]:
    try:
        payload = {"items": [compute_replenishment(item) for item in request.items], "method": "safety-stock-eoq-v1"}
        return _store().create_artifact("replenishment", "补货建议", payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.post("/artifacts/risk")
async def create_risk_artifact(request: RiskRequest) -> dict[str, Any]:
    try:
        payload = monitor_supply_risk(request.records)
        return _store().create_artifact("risk", "供应链风险监控", payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.get("/artifacts")
async def list_artifacts(kind: str | None = None, limit: int = 100) -> dict[str, Any]:
    try:
        return _store().list_artifacts(kind, limit)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail=f"供应链持久化依赖不可用：{exc}") from exc


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str) -> dict[str, Any]:
    try:
        return _store().get_artifact(artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="供应链工件不存在") from exc


@router.post("/artifacts/{artifact_id}/reviews")
async def review_artifact(artifact_id: str, request: ArtifactReviewRequest) -> dict[str, Any]:
    try:
        return _store().review_artifact(artifact_id, request.action, request.reviewer, request.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="供应链工件不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/artifacts/{artifact_id}/export")
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
