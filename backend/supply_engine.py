# -*- coding: utf-8 -*-
"""Supplier scoring, replenishment planning and supply risk monitoring."""

from __future__ import annotations

import math
from typing import Any

# Weighted dimensions used when scoring a supplier.
WEIGHTS = {"delivery": 0.30, "quality": 0.35, "price": 0.25, "service": 0.10}


def _bounded(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _price_score(price_index: float) -> float:
    """Convert a relative price index to a 0-100 score (1.0 is market benchmark)."""
    if price_index <= 0:
        return 60.0
    # Below benchmark is cheaper -> higher score; above is penalised.
    return _bounded(100.0 - (price_index - 1.0) * 120.0)


def score_supplier(supplier: dict[str, Any]) -> dict[str, Any]:
    """Score a single supplier and assign an A/B/C/D tier."""
    on_time = _bounded(float(supplier.get("on_time_rate", 0) or 0))
    quality = _bounded(float(supplier.get("quality_rate", 0) or 0))
    price_index = float(supplier.get("price_index", 1.0) or 1.0)
    delivery = _bounded(float(supplier.get("delivery_score", on_time) or on_time))
    service = _bounded(float(supplier.get("service_score", 80) or 80))
    price = _price_score(price_index)

    score = (
        delivery * WEIGHTS["delivery"]
        + quality * WEIGHTS["quality"]
        + price * WEIGHTS["price"]
        + service * WEIGHTS["service"]
    )
    score = _bounded(score)
    if score >= 85:
        tier, level = "A", "high"
    elif score >= 70:
        tier, level = "B", "medium"
    elif score >= 55:
        tier, level = "C", "low"
    else:
        tier, level = "D", "critical"

    issues = []
    if on_time < 80:
        issues.append("准时交付率偏低")
    if quality < 85:
        issues.append("来料合格率偏低")
    if price_index > 1.15:
        issues.append("价格高于市场基准")
    if service < 70:
        issues.append("响应与服务评分偏低")

    return {
        **supplier,
        "on_time_rate": round(on_time, 2),
        "quality_rate": round(quality, 2),
        "price_index": round(price_index, 3),
        "score": round(score, 2),
        "tier": tier,
        "level": level,
        "issues": issues,
        "method": "weighted-score-v1",
    }


def score_suppliers(suppliers: list[dict[str, Any]]) -> dict[str, Any]:
    """Score many suppliers and rank them from best to worst."""
    if len(suppliers) > 2000:
        raise ValueError("单次最多评估2000家供应商")
    scored = [score_supplier(supplier) for supplier in suppliers]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"suppliers": scored, "count": len(scored), "method": "weighted-score-v1"}


def compute_replenishment(series: dict[str, Any]) -> dict[str, Any]:
    """Compute safety stock, reorder point, EOQ and suggested order quantity."""
    demand = float(series.get("annual_demand", 0) or 0)
    lead_time = max(1.0, float(series.get("lead_time_days", 1) or 1))
    safety_days = max(0.0, float(series.get("safety_days", 3) or 0))
    on_hand = float(series.get("on_hand", 0) or 0)
    on_order = float(series.get("on_order", 0) or 0)
    order_cost = float(series.get("order_cost", 50) or 0)
    unit_cost = float(series.get("unit_cost", 1) or 1)
    holding_rate = float(series.get("holding_rate", 0.2) or 0.2)

    avg_daily = demand / 365.0 if demand > 0 else 0.0
    safety_stock = avg_daily * safety_days if safety_days else avg_daily * lead_time * 0.5
    lead_time_demand = avg_daily * lead_time
    reorder_point = lead_time_demand + safety_stock
    net_position = on_hand + on_order

    if unit_cost > 0 and holding_rate > 0 and order_cost > 0:
        eoq = math.sqrt(2 * demand * order_cost / (unit_cost * holding_rate))
    else:
        eoq = 0.0

    if net_position <= reorder_point:
        suggested = max(eoq, reorder_point - net_position)
        status = "紧急补货" if net_position <= safety_stock else "建议补货"
    else:
        suggested = 0.0
        status = "库存充足"

    return {
        **series,
        "avg_daily_demand": round(avg_daily, 3),
        "lead_time_days": lead_time,
        "safety_days": safety_days,
        "safety_stock": round(safety_stock, 2),
        "reorder_point": round(reorder_point, 2),
        "on_hand": on_hand,
        "on_order": on_order,
        "net_position": round(net_position, 2),
        "eoq": round(eoq, 2),
        "suggested_quantity": round(suggested, 2),
        "status": status,
        "method": "safety-stock-eoq-v1",
    }


RISK_RULES: list[tuple[str, list[str]]] = [
    ("交期风险", ["交期", "延期", "delay", "晚点", "交付"]),
    ("质量风险", ["质量", "不合格", "退货", "品质", "索赔"]),
    ("物流风险", ["物流", "停滞", "运输", "滞留", "签收", "海运", "空运"]),
    ("价格风险", ["涨价", "调价", "价格上浮", "汇率"]),
    ("产能风险", ["产能", "缺货", "停产", "检修", "断供"]),
    ("合规风险", ["环保", "认证", "合规", "海关"]),
]


def _extract_risk(text: str) -> tuple[list[str], str]:
    hits = [label for label, keywords in RISK_RULES if any(keyword in text for keyword in keywords)]
    if hits:
        return hits, hits[0]
    return [], "异常"


def monitor_risk(record: dict[str, Any]) -> dict[str, Any]:
    """Monitor one supply order/logistics record and assign a risk level."""
    text = " ".join(str(record.get(key, "")) for key in ("risk_note", "order_no", "supplier", "status"))
    hits, category = _extract_risk(text)
    base = {
        "交期风险": 30,
        "质量风险": 35,
        "物流风险": 25,
        "价格风险": 20,
        "产能风险": 35,
        "合规风险": 40,
    }
    score = min(100, 15 + sum(base.get(hit, 25) for hit in hits))
    severity = "high" if score >= 70 else "medium" if score >= 45 else "low"
    return {
        **record,
        "risk_category": category,
        "matched_keywords": hits,
        "risk_score": score,
        "severity": severity,
        "recommended_action": _recommend(category, severity),
        "method": "rule-based-risk-v1",
    }


def monitor_supply_risk(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Monitor a batch of supply records and rank by risk score."""
    if len(records) > 5000:
        raise ValueError("单次最多监控5000条记录")
    monitored = [monitor_risk(record) for record in records]
    monitored.sort(key=lambda item: item["risk_score"], reverse=True)
    high = sum(1 for item in monitored if item["severity"] == "high")
    medium = sum(1 for item in monitored if item["severity"] == "medium")
    return {
        "records": monitored,
        "count": len(monitored),
        "high_count": high,
        "medium_count": medium,
        "method": "rule-based-risk-v1",
    }


def _recommend(category: str, severity: str) -> str:
    if severity != "high":
        return "纳入观察清单，关注后续轨迹与质量抽查。"
    table = {
        "交期风险": "立即确认是否影响生产排程，必要时切换备选供应商并调整交期承诺。",
        "质量风险": "安排来料复检或驻厂质检，暂停该批次验收入库，评估索赔与退货。",
        "物流风险": "联系物流承运方定位货物，必要时启用应急运输或改走备选路线。",
        "价格风险": "启动议价或换供应商评估，复核采购合同的价格联动条款。",
        "产能风险": "确认供应缺口，启用安全库存并同步采购、生产和销售侧预警。",
        "合规风险": "暂停合作评估，要求供应商提供合规材料并复核准入档案。",
        "异常": "补充真实风险描述后重新评估。",
    }
    return table.get(category, table["异常"])
