import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from supply_engine import compute_replenishment, monitor_supply_risk, score_suppliers


class SupplyEngineTests(unittest.TestCase):
    def test_score_suppliers_ranks_and_tiers(self):
        suppliers = [
            {"name": "A供应商", "on_time_rate": 95, "quality_rate": 98, "price_index": 0.95, "service_score": 90},
            {"name": "B供应商", "on_time_rate": 50, "quality_rate": 60, "price_index": 1.5, "service_score": 50},
        ]
        result = score_suppliers(suppliers)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["suppliers"][0]["name"], "A供应商")
        self.assertEqual(result["suppliers"][0]["tier"], "A")
        self.assertEqual(result["suppliers"][1]["tier"], "D")
        self.assertTrue(result["suppliers"][1]["issues"])

    def test_replenishment_orders_when_below_reorder_point(self):
        item = {"name": "压铸件", "annual_demand": 3650, "lead_time_days": 7, "safety_days": 5,
                "on_hand": 5, "on_order": 0, "order_cost": 50, "unit_cost": 10, "holding_rate": 0.2}
        result = compute_replenishment(item)
        self.assertIn(result["status"], ("建议补货", "紧急补货"))
        self.assertGreater(result["suggested_quantity"], 0)
        self.assertGreaterEqual(result["safety_stock"], 0)

    def test_replenishment_sufficient_no_order(self):
        item = {"name": "外壳", "annual_demand": 365, "lead_time_days": 3, "safety_days": 2,
                "on_hand": 50, "on_order": 20, "order_cost": 50, "unit_cost": 5, "holding_rate": 0.2}
        result = compute_replenishment(item)
        self.assertEqual(result["status"], "库存充足")
        self.assertEqual(result["suggested_quantity"], 0)

    def test_monitor_risk_assigns_severity(self):
        records = [
            {"order_no": "PO123", "supplier": "A供应商", "status": "已延期", "risk_note": "物流停滞，存在交期风险"},
            {"order_no": "PO456", "supplier": "B供应商", "status": "正常生产", "risk_note": ""},
        ]
        result = monitor_supply_risk(records)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["records"][0]["order_no"], "PO123")
        self.assertTrue(result["records"][0]["risk_score"] > result["records"][1]["risk_score"])
        self.assertIn(result["records"][0]["severity"], ("high", "medium"))


if __name__ == "__main__":
    unittest.main()
