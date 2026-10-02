# 验收记录与公开版边界

公开版不是带研究数据库的完整分发包。以下两组结果分别记录，不能相互替代。

## V1.4 原开发环境：已完成的产品验收

版本：`feat/v1.4-credibility-regrade`，源代码提交 `075fc12d9d7f8f84f1325777884e9c1571532a04`。

- React / FastAPI 实际启动，浏览器 Dashboard 正常。
- 基金 161005 使用已有本地数据、关闭更新后完成分析；本次记录用时 14.84 秒，不是性能承诺。
- 行业暴露、趋势、拟合与可信度诊断实际展示；报告及 CSV 下载验证成功。
- Python：71 passed，1 warning；Frontend：25 passed，1 skipped；前端构建成功。
- 1,044 周 × 27 行业的周频结果与稳定生产基线一致，最大绝对数值差为 0；这验证复现，不验证持仓真值。
- 最新窗口 R² 约 0.831；Dashboard 模型质量 A、结果可信度 C。
- 四张公开图片中，Dashboard 和诊断来自真实运行截图，结果曲线来自实际分析输出，workflow 是说明图。

以上为此前完整开发环境的验收记录。本轮没有重新开发模型或重复全部基金分析，也没有把缺失数据复制到公开仓库。

## 无研究数据的 Public 版本：2026-10-02 实际检查

| 检查 | 结果 |
|---|---|
| Python 3.12 / pytest | **66 passed，5 skipped，1 warning**，14.51 秒 |
| Frontend / Vitest | **25 passed，1 skipped** |
| npm ci | 成功安装锁定依赖 |
| npm run build | 成功，Vite 6.4.3 |
| FastAPI 实际启动 | 成功；根页面及 OpenAPI 返回 HTTP 200，根页面包含 React 挂载点 |
| 核心数学实现 | lib 下 Python 文件及 run_analysis.py 与 V1.4 来源逐文件一致 |

首次公开版 Python 运行发现两项额外的数据依赖测试失败，原因是有意排除了研究数据。保留测试内容，添加明确缺数据跳过条件后重新运行，得到上表结果。未通过修改模型来使测试通过。

跳过的五项 Python 测试：三项研究 CSV 基线回归，两项真实研究样本求解器比较。代码内的合成样本测试仍执行。前端一项既有集成测试仍跳过；不把它算作通过。

运行命令：

```text
python -m pytest -q
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npm test -- --reporter=dot
```

## 已知问题及不承诺的能力

- Vite 提示 charts chunk 超过 500 kB；构建成功，后续可按需拆分。
- jsdom 图表测试有零宽高警告；这不是完整浏览器端到端覆盖。
- FastAPI TestClient 依赖产生弃用警告；测试未失败。
- 真实截图页脚保留旧 UI 版本 v1.2，Build 075fc12 对应本次 V1.4 产品来源。
- 老报告中的历史模型等级与 V1.4 Dashboard 可信度不完全一致，应结合诊断阅读。
- Public 版未附研究输入或输出 CSV，不能 clone 后立即重算 161005；不提供在线分析服务。
- 没有完成多基金泛化、严格公告时点回测、完整持仓真值检验或用户业务价值实验。

模型与可信度局限详见 [methodology.md](methodology.md)，公开范围详见 [PUBLIC_SCOPE.md](../PUBLIC_SCOPE.md)。
