(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React, antd = Q.host.antd, h = React.createElement;
  function request(path, body) {
    return Q.host.fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) }).then(function (response) {
      return response.json().then(function (data) { if (!response.ok) throw new Error(data.detail || "操作失败"); return data; });
    });
  }
  function SupplyStudio() {
    var supplierTextState = React.useState(""), supplierText = supplierTextState[0], setSupplierText = supplierTextState[1];
    var supplierResultState = React.useState(null), supplierResult = supplierResultState[0], setSupplierResult = supplierResultState[1];
    var replenishTextState = React.useState(""), replenishText = replenishTextState[0], setReplenishText = replenishTextState[1];
    var replenishResultState = React.useState(null), replenishResult = replenishResultState[0], setReplenishResult = replenishResultState[1];
    var riskTextState = React.useState(""), riskText = riskTextState[0], setRiskText = riskTextState[1];
    var riskResultState = React.useState(null), riskResult = riskResultState[0], setRiskResult = riskResultState[1];
    var reviewerState = React.useState(""), reviewer = reviewerState[0], setReviewer = reviewerState[1];
    var recentState = React.useState([]), recent = recentState[0], setRecent = recentState[1];
    var loadingState = React.useState(false), loading = loadingState[0], setLoading = loadingState[1];
    var message = antd.App.useApp().message;
    function parseJson(text, label) {
      var parsed;
      try { parsed = JSON.parse(text); } catch (err) { message.error(label + "必须是JSON数组"); return null; }
      if (!Array.isArray(parsed) || !parsed.length) { message.warning("请提供至少一条" + label); return null; }
      return parsed;
    }
    function loadRecent() {
      return Q.host.fetch("/zhiyun-supply-studio/artifacts").then(function (response) { return response.json(); })
        .then(function (data) { setRecent(data.artifacts || []); }).catch(function () {});
    }
    function runSupplier() {
      var suppliers = parseJson(supplierText, "供应商数据");
      if (!suppliers) return;
      setLoading(true);
      request("/zhiyun-supply-studio/artifacts/supplier", { suppliers: suppliers }).then(function (data) { setSupplierResult(data); message.success("已生成供应商评估工件，等待审阅"); loadRecent(); })
        .catch(function (e) { message.error(e.message); }).finally(function () { setLoading(false); });
    }
    function runReplenishment() {
      var items = parseJson(replenishText, "补货物料");
      if (!items) return;
      setLoading(true);
      request("/zhiyun-supply-studio/artifacts/replenishment", { items: items }).then(function (data) { setReplenishResult(data); message.success("已生成补货建议工件，等待审阅"); loadRecent(); })
        .catch(function (e) { message.error(e.message); }).finally(function () { setLoading(false); });
    }
    function runRisk() {
      var records = parseJson(riskText, "供应链记录");
      if (!records) return;
      setLoading(true);
      request("/zhiyun-supply-studio/artifacts/risk", { records: records }).then(function (data) { setRiskResult(data); message.success("已生成风险监控工件，等待审阅"); loadRecent(); })
        .catch(function (e) { message.error(e.message); }).finally(function () { setLoading(false); });
    }
    function decide(kind, action) {
      if (!reviewer.trim()) { message.warning("请输入审阅人"); return; }
      var result = kind === "supplier" ? supplierResult : kind === "replenishment" ? replenishResult : riskResult;
      if (!result) { message.warning("请先生成工件"); return; }
      request("/zhiyun-supply-studio/artifacts/" + result.id + "/reviews", { action: action, reviewer: reviewer }).then(function (data) {
        if (kind === "supplier") setSupplierResult(data); else if (kind === "replenishment") setReplenishResult(data); else setRiskResult(data);
        message.success(action === "accept" ? "工件已接受" : "工件已驳回"); loadRecent();
      }).catch(function (e) { message.error(e.message); });
    }
    function exportArtifact(result) {
      if (!result) return;
      window.open("/zhiyun-supply-studio/artifacts/" + result.id + "/export", "_blank");
    }
    var supplierExample = '[{"name":"华南五金","on_time_rate":92,"quality_rate":96,"price_index":1.05,"service_score":85},{"name":"明达包装","on_time_rate":74,"quality_rate":82,"price_index":1.2,"service_score":66}]';
    var replenishExample = '[{"sku":"AB123","name":"铝合金型材","annual_demand":12000,"lead_time_days":9,"safety_days":5,"on_hand":120,"on_order":80,"order_cost":60,"unit_cost":18,"holding_rate":0.22}]';
    var riskExample = '[{"order_no":"PO-S-20260801","supplier":"深圳精工","risk_note":"交期可能延期，物流在海运途中停滞","status":"在途"},{"order_no":"PO-S-20260802","supplier":"东江五金","risk_note":"来料抽检不合格比例升高","status":"待验收"}]';
    var intents = [
      { key: "supplier", label: "供应商评估" },
      { key: "replenishment", label: "补货建议" },
      { key: "risk", label: "风险监控" }
    ];
    var activeState = React.useState("supplier"), active = activeState[0], setActive = activeState[1];
    React.useEffect(function () { loadRecent(); }, []);
    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } }, h("div", { style: { maxWidth: 1080, margin: "0 auto" } },
      h("h2", null, "智能供应链中心"), h("p", { style: { color: "#667085" } }, "供应商多维打分、安全库存与再订货点建议、供应链风险实时监控。"),
      h(antd.Tabs, { activeKey: active, onChange: setActive, items: intents.map(function (item) {
        return { key: item.key, label: item.label, children: item.key === "supplier" ? (
          h("div", null,
            h(antd.Alert, { type: "info", showIcon: true, message: "评估供应商", description: "粘贴JSON数组，每项含 name、on_time_rate(准时交付)、quality_rate(来料合格)、price_index(价格指数)、service_score(服务)。" }),
            h(antd.Input.TextArea, { style: { marginTop: 12 }, value: supplierText, rows: 8, onChange: function (e) { setSupplierText(e.target.value); }, placeholder: supplierExample }),
            h(antd.Button, { type: "primary", loading: loading, style: { marginTop: 12 }, onClick: runSupplier }, "评估并生成工件"),
            supplierResult ? h(antd.Card, { size: "small", title: "评估结果（" + supplierResult.payload.count + " 家）", style: { marginTop: 16 }, extra: h(antd.Tag, { color: supplierResult.status === "accepted" ? "green" : supplierResult.status === "rejected" ? "red" : "orange" }, supplierResult.status) },
              h(antd.Table, { size: "small", rowKey: "name", dataSource: supplierResult.payload.suppliers, pagination: false, columns: [
                { title: "供应商", dataIndex: "name" },
                { title: "评分", dataIndex: "score", render: function (v) { return h("span", { style: { fontWeight: 600 } }, v); } },
                { title: "分级", dataIndex: "tier", render: function (v) { return h(antd.Tag, { color: v === "A" ? "green" : v === "B" ? "blue" : v === "C" ? "orange" : "red" }, v); } },
                { title: "准时率", dataIndex: "on_time_rate" }, { title: "合格率", dataIndex: "quality_rate" },
                { title: "风险点", dataIndex: "issues", render: function (v) { return (v || []).join("、") || "无"; } }
              ] }),
              h("div", { style: { display: "flex", gap: 8, marginTop: 12 } },
                h(antd.Input, { value: reviewer, onChange: function (e) { setReviewer(e.target.value); }, placeholder: "审阅人", style: { width: 180 } }),
                h(antd.Button, { type: "primary", onClick: function () { decide("supplier", "accept"); } }, "接受"),
                h(antd.Button, { danger: true, onClick: function () { decide("supplier", "reject"); } }, "驳回"),
                h(antd.Button, { disabled: supplierResult.status !== "accepted", onClick: function () { exportArtifact(supplierResult); } }, "导出")
              )
            ) : null
          )
        ) : item.key === "replenishment" ? (
          h("div", null,
            h(antd.Alert, { type: "info", showIcon: true, message: "计算补货", description: "每项含 sku、annual_demand(年需求)、lead_time_days(交期)、safety_days、on_hand、on_order、order_cost、unit_cost、holding_rate。" }),
            h(antd.Input.TextArea, { style: { marginTop: 12 }, value: replenishText, rows: 8, onChange: function (e) { setReplenishText(e.target.value); }, placeholder: replenishExample }),
            h(antd.Button, { type: "primary", loading: loading, style: { marginTop: 12 }, onClick: runReplenishment }, "计算并生成工件"),
            replenishResult ? h(antd.Card, { size: "small", title: "补货建议（" + replenishResult.payload.items.length + " 项）", style: { marginTop: 16 }, extra: h(antd.Tag, { color: replenishResult.status === "accepted" ? "green" : replenishResult.status === "rejected" ? "red" : "orange" }, replenishResult.status) },
              h(antd.Table, { size: "small", rowKey: "sku", dataSource: replenishResult.payload.items, pagination: false, columns: [
                { title: "物料", dataIndex: "sku" }, { title: "年需求", dataIndex: "annual_demand" },
                { title: "安全库存", dataIndex: "safety_stock" }, { title: "再订货点", dataIndex: "reorder_point" },
                { title: "建议补货", dataIndex: "suggested_quantity" },
                { title: "状态", dataIndex: "status", render: function (v) { return h(antd.Tag, { color: v === "库存充足" ? "green" : v === "紧急补货" ? "red" : "orange" }, v); } }
              ] }),
              h("div", { style: { display: "flex", gap: 8, marginTop: 12 } },
                h(antd.Input, { value: reviewer, onChange: function (e) { setReviewer(e.target.value); }, placeholder: "审阅人", style: { width: 180 } }),
                h(antd.Button, { type: "primary", onClick: function () { decide("replenishment", "accept"); } }, "接受"),
                h(antd.Button, { danger: true, onClick: function () { decide("replenishment", "reject"); } }, "驳回"),
                h(antd.Button, { disabled: replenishResult.status !== "accepted", onClick: function () { exportArtifact(replenishResult); } }, "导出")
              )
            ) : null
          )
        ) : (
          h("div", null,
            h(antd.Alert, { type: "info", showIcon: true, message: "监控风险", description: "每项含 order_no、supplier、risk_note、status，引擎自动识别交期/质量/物流/价格/产能/合规风险。" }),
            h(antd.Input.TextArea, { style: { marginTop: 12 }, value: riskText, rows: 8, onChange: function (e) { setRiskText(e.target.value); }, placeholder: riskExample }),
            h(antd.Button, { type: "primary", loading: loading, style: { marginTop: 12 }, onClick: runRisk }, "监控并生成工件"),
            riskResult ? h(antd.Card, { size: "small", title: "风险监控（" + riskResult.payload.count + " 条，高风险 " + riskResult.payload.high_count + " 条）", style: { marginTop: 16 }, extra: h(antd.Tag, { color: riskResult.status === "accepted" ? "green" : riskResult.status === "rejected" ? "red" : "orange" }, riskResult.status) },
              h(antd.Table, { size: "small", rowKey: "order_no", dataSource: riskResult.payload.records, pagination: false, columns: [
                { title: "订单", dataIndex: "order_no" }, { title: "供应商", dataIndex: "supplier" },
                { title: "风险类型", dataIndex: "risk_category" },
                { title: "分数", dataIndex: "risk_score", render: function (v) { return h("span", { style: { fontWeight: 600 } }, v); } },
                { title: "级别", dataIndex: "severity", render: function (v) { return h(antd.Tag, { color: v === "high" ? "red" : v === "medium" ? "orange" : "green" }, v); } },
                { title: "建议措施", dataIndex: "recommended_action", ellipsis: true }
              ] }),
              h("div", { style: { display: "flex", gap: 8, marginTop: 12 } },
                h(antd.Input, { value: reviewer, onChange: function (e) { setReviewer(e.target.value); }, placeholder: "审阅人", style: { width: 180 } }),
                h(antd.Button, { type: "primary", onClick: function () { decide("risk", "accept"); } }, "接受"),
                h(antd.Button, { danger: true, onClick: function () { decide("risk", "reject"); } }, "驳回"),
                h(antd.Button, { disabled: riskResult.status !== "accepted", onClick: function () { exportArtifact(riskResult); } }, "导出")
              )
            ) : null
          )
        )};
      }) }
    )));
  }
  Q.registerRoutes("zhiyun-supply-studio", [{ path: "/apps/zhiyun-supply-studio", component: SupplyStudio, label: "智能供应链中心", icon: "🚚", priority: 82 }]);
})();
