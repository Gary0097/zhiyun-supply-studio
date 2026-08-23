# 智造云采购与供应链中心

独立 PawApp。基于真实供应商、需求与订单物流数据完成供应商加权评分、安全库存/再订货点/EOQ 补货测算与供应链风险实时监控，所有结果进入可审阅工件等待人工确认。

## 验证

```bash
python -m unittest discover -s tests -v
python -m py_compile backend/main.py backend/supply_engine.py backend/supply_workflow.py
node --check ui/index.js
```
