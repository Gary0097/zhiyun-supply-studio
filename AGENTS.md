# AGENTS.md

## Purpose

智造云采购与供应链中心：供应商评分、安全库存补货测算和供应链风险实时监控。

## Conventions

- Python 引擎放在 `backend/`，每个纯函数可独立测试，不依赖网络。
- 审阅类结果必须持久化到本地 SQLite 等待具名人员 `accept`/`reject`，不允许自动执行。
- UI 使用 `window.QwenPaw` + `Q.host.React` + `Q.host.antd`，路由走 `Q.registerRoutes`。
- 版本号在 `plugin.json` 与 `backend/main.py` 的 `PLUGIN_VERSION` 保持一致。
- 新增/修改功能后运行 `python scripts/verify_release.py`。

## Commands

```bash
python -m unittest discover -s tests -v
node --check ui/index.js
python scripts/verify_release.py
```
