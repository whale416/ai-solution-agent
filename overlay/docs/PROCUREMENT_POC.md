# 企业采购 AI 售前 Copilot｜本地演示

本案例基于 AI Solution Copilot 的 FastAPI、React、LangGraph 和 DeepSeek Provider 扩展。工作台新增「采购 PoC」入口。[上游仓库与改造基线 16934a4](https://github.com/lalala613lys/ai-solution-copilot/tree/16934a4)

## 启动

在 `ai-solution-agent/workspace` 打开两个 PowerShell 终端。已安装依赖时，直接执行各终端的最后一条启动命令。

```powershell
# 后端终端
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# 前端终端
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

打开 [采购 PoC](http://127.0.0.1:5173/procurement)，也可从原工作台的侧栏进入。无密钥时采用规则演示，实际查询公告快照并运行校验。配置 `backend/.env` 中的 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL=deepseek-flash` 和 `DEEPSEEK_BASE_URL=https://api.deepseek.com`，重启后端再新建会话可启用模型辅助。DeepSeek 官方接口的结构化输出请求关闭思考模式以支持指定工具。模型异常时执行轨迹会记录当次回退。[DeepSeek 中文接入文档](https://api-docs.deepseek.com/zh-cn/) · [对话补全接口](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)

## 演示两条路径

1. 使用预填的模拟客户需求，点击「开始澄清」。需求澄清 Agent 会先问进度是否包含内部审批。
2. 选择「只查公开进度」。查看四条公开用例的实际结果，展开某条用例核对采购编号、查询时点、预期值和执行记录。下载这次的 Markdown 报告。
3. 点击「用同一需求再演示」，重新提交需求，再选「公开进度＋内部审批」。公开用例继续执行，报告同时列出接口、编号映射、字段和权限的联调条件与拟验收用例。
4. 如需展示补问，先输入「先做个能看的版本」。如需展示断点恢复，在等待答复时重启后端，再打开原会话地址。

案例固定使用采购编号 `CG2700022002374581`。查询时点按北京时间日期筛选公告发布时间。原公告的截标时间为 2026 年 10 月 13 日 09:00。按此快照，截至 10 月 22 日可以核实已发布中标候选人公示，截至 10 月 20 日可核实的最近记录为招标公告。[官方招标公告](https://www.bidding.csg.cn/zbgg/1200442355.jhtml) · [官方中标候选人公示](https://www.bidding.csg.cn/zbhxrgs/1200446532.jhtml)

公告依据来自两份公开页面。客户答复为模拟输入。内部审批功能处于「待联调／未执行」，需要企业提供接口和授权测试环境。

## 实现与验证

| 环节 | 代码 |
| --- | --- |
| 需求澄清、范围判断、验证方案 | `backend/app/agents/procurement_agents.py` |
| LangGraph 分支、澄清断点、验证节点 | `backend/app/graph/procurement_workflow.py` |
| 公告快照与人工标注的预期答案 | `backend/data/procurement/` |
| 公告查询、证据校验与失败复核 | `backend/app/services/procurement_sources.py`、`backend/app/agents/procurement_verifier.py` |
| 会话与报告 | `backend/app/routes/procurement.py`、`backend/app/services/procurement_sessions.py`、`backend/app/services/procurement_report.py` |
| 工作台页面 | `frontend/src/pages/Procurement.tsx` |

运行时 SQLite 检查点写入 `backend/data/procurement.sqlite`，会话通过 URL 中的 ID 恢复。当前启动方式使用单进程服务。公告问答工具只接收问题、采购编号和查询日期，预期答案由独立的用例文件提供。模型可调整验证顺序，事实、出处和验收结果由执行记录决定。

可在 [本地 API 文档](http://127.0.0.1:8000/docs#/procurement-poc) 试用采购接口。`POST /api/procurement/query` 接收 `question`、`project_id`、`as_of`，可独立验证公开问答工具。

```powershell
# 后端回归测试
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_procurement.py -v
```

```powershell
# 前端生产构建
cd frontend
npm run build
```

15 条回归覆盖 A/B 路径、含糊答复、公告日期截断、未知采购编号、引用错误、工具超时、重启恢复、独立报告和 DeepSeek 结构化请求参数。真实 `deepseek-flash` 已在公开进度与内部审批路径完成澄清和方案设计，四条公开用例通过。
