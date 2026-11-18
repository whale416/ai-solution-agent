# 企业采购 AI 售前 Copilot

基于公开招标需求的独立 PoC。售前人员输入模拟客户需求后，三个智能体依次完成需求澄清、方案设计和用例验证，输出带公告出处的验收报告。

## 项目来源

本项目参考并接入 `lalala613lys/ai-solution-copilot`。上游提供 FastAPI、React、LangGraph 和模型接入，本项目新增采购案例、澄清分支、公告查询、验收和报告。这里发布采购 PoC 的新增源码和接入补丁。组装脚本从上游获取验证过的版本 `16934a4`。[上游仓库](https://github.com/lalala613lys/ai-solution-copilot) · [验证基线](https://github.com/lalala613lys/ai-solution-copilot/tree/16934a4ebf844b12720c97e6f41add46da4415da)

## 采购案例

案例来自南方电网供应链集团的「采购 AI 数字员工建设项目」，采购编号 `CG2700022002374581`。公告与候选人公示来自官方平台，客户对话为模拟输入。公开阶段按北京时间查询指定日期前已发布的公告。[招标公告](https://www.bidding.csg.cn/zbgg/1200442355.jhtml) · [中标候选人公示](https://www.bidding.csg.cn/zbhxrgs/1200446532.jhtml)

| 模拟答复 | PoC 输出 |
| --- | --- |
| 一期只查公开进度 | 执行公开验收，核对原公告截标时间、候选人公示阶段、历史时点和未知采购编号。 |
| 公开进度和内部审批都要查 | 执行相同的公开用例。内部审批标为「待联调／未执行」，附接口、采购编号映射、状态字段和权限的联调用例。 |
| 先做个能看的版本 | 继续追问，等待确认范围。 |

## 本地启动

准备 Git、Python 3.12 和 Node.js。在 PowerShell 中组装项目。

```powershell
git clone https://github.com/whale416/ai-solution-agent.git
cd ai-solution-agent
python setup_workspace.py
```

组装后，在仓库根目录打开两个终端。

```powershell
# 后端终端
cd workspace/backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# 前端终端
cd workspace/frontend
npm ci
npm run dev -- --host 127.0.0.1
```

macOS 和 Linux 可将后端命令中的 `.\.venv\Scripts\python.exe` 换成 `.venv/bin/python`。

打开 [本地采购 PoC](http://127.0.0.1:5173/procurement)，先点「开始澄清」，再选择模拟答复。完成后可以展开工具记录、查看官方出处，或下载 Markdown 验收报告。

默认规则模式无需模型密钥，公告查询和验收照常执行。配置 `workspace/backend/.env` 中的 `DEEPSEEK_API_KEY` 等参数后，新会话可使用模型辅助澄清和方案设计。验证结果由工具执行和校验程序产生。

## 验证

两条路径均在本地 Chrome 完成验证，每条路径的 4 个公开用例全部通过。14 条后端回归测试及前端生产构建通过，另实测后端重启后可继续原有澄清会话。浏览器使用规则模式，DeepSeek 接入使用测试替身覆盖。

```powershell
cd workspace/backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_procurement.py -v
```

## 目录结构

```text
ai-solution-agent/
├─ setup_workspace.py       # 获取上游版本并组装本地工作区
├─ integration.patch        # 路由、依赖和界面的接入改动
└─ overlay/
   ├─ backend/              # 采购工作流、公告数据与回归测试
   ├─ frontend/             # 采购 PoC 页面
   └─ docs/                 # 演示与实现说明
```

会话检查点保存在本地 `workspace/backend/data/procurement.sqlite`。完整演示顺序、API 和代码位置见[采购 PoC 实现说明](overlay/docs/PROCUREMENT_POC.md)。
