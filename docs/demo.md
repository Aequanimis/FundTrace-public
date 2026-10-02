# 面试演示与源码浏览

本公开仓库选择“真实截图和结果展示”方式，不包含原始研究数据，也不提供虚构的 161005 示例数据库。

## 三个展示区域

1. **产品工作流**：从业务信息空窗到输入、分析和报告。讲清用户是谁、什么时候需要。
2. **Dashboard 行业暴露与趋势**：打开 assets/dashboard.png，说明近期变化只是进一步核查的线索。
3. **模型诊断**：打开 assets/model_diagnostics.png，解释模型质量 A、结果可信度 C，展示评价与边界管理。

截图来自实际运行，基金161005、周频标签2026-08-07、模型v4-a2.1-stable。输入行业指数截至2026-08-05。图中页脚v1.2是历史UI文字，Build 075fc12对应V1.4产品源码。截图没有重画或合成。

## 可选：浏览本地实现

有 Python 3.12 和 Node.js 的开发者可运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
cd frontend
npm ci
npm run build
cd ..
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m api.server
```

打开 http://127.0.0.1:8765。安装依赖需要网络；没有研究数据时可以查看入口与实现，不能直接重算161005。完整分析需用户自行准备有权使用的输入；面试默认采用截图展示，不需要现场抓数。

Public源码不提供内置数据下载承诺。抓取脚本作为实现保留，其可用性和数据许可需使用者自行确认，不等于本仓库获准再分发数据。

## 讲述顺序

30秒：为什么低频披露无法满足持续研究。  
2分钟：用户操作、数据流程、结果呈现。  
5分钟：窗口、衰减与约束的取舍，可信度分级及待验证问题。

不要将截图称为在线SaaS，不将R²当准确率，不宣称真实持仓还原或收益增益。

