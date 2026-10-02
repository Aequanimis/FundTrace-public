# FundTrace 技术产品事实核验

核验日期：2026-10-03。基于 Public 仓库提交 `7e01948750fcaeba6ca81cda331ee5bbb7dfb980` 的源码、依赖配置、测试定义及现有文档；本次不修改或重新运行研究模型。事实优先级为代码、配置、实际测试记录、文档、历史陈述。测试中写有断言不等于本次执行通过；截图可证明历史展示内容，不能替代原始数据重算。

## 1. Data Input Layer

| 数据 | 来源与获取入口 | 格式 | 用途 |
|---|---|---|---|
| 基金身份 | `fetch_fund_manual.py` 解析东方财富 `pingzhongdata` 中的名称；`api/fund_metadata.py` 读取本地缓存 | `metadata.json`、manifest 或原始 JS | 基金名称与代码展示，不参与回归 |
| 净值与分红 | 东方财富净值 JS 和分红页面；也可指定已有 JS 文件 | `nav.csv`：date、nav_unit、nav_cum、nav_adj | 基金日收益目标 |
| 持股披露 | AkShare 的 `fund_portfolio_hold_em`，逐年抓取 | `holdings.csv`：原始字段经解析得到代码、占比、报告期 | 季度模拟行业组合 |
| 行业配置披露 | AkShare 的 `fund_portfolio_industry_allocation_em` | `industry_alloc.csv` | 组合补全、披露行业配置总量参照；分析加载器允许缺失，抓取流程仍尝试获取 |
| 申万行业指数日线 | `fetch_data.py` 调用 `index_hist_sw` | `sw_industry_index.csv`：date、industry_name、close 等 | 默认行业收益特征 |
| 股票行业映射 | `stock_industry_clf_hist_sw`；失败时用当前行业成分股拼接 | `stock_industry_map.csv`，列名经适配 | 将股票映射到申万一级行业；分析时压缩成静态字典，不是逐日期历史分类查询 |
| 可选个股行情 | `fetch_stock_klines.py` 中的腾讯行情接口 | `stock_klines.csv`：date、code、close | 仅可选 stock_level 路径；默认产品流程使用 index_proxy，历史验收未验证个股路径 |

完整分析入口要求净值、持股、行业指数、股票行业映射。行业配置缺失会降低结构及总量核查能力。抓取脚本可保存基准权重，但默认 `run_analysis.py` 不使用它。Public 仓库不附研究输入；接口可用性和数据再分发许可不因源码存在而得到保证。

## 2. Data Processing Layer

- 抓取路径：解析净值日期与数值，删除缺失记录，按日期排序并保留同日最后记录；CSV/JSON 先写临时文件再替换目标。网络重试、分阶段错误和部分超时机制存在，但不是所有外部数据都能自动补齐的承诺。
- 持股清洗：六位股票代码、比例与报告期格式统一；删除代码、占比或报告期缺失行，排除非正占比，按报告期与股票代码去重。行业映射表匹配可识别列名并限制到代码内的行业分类。
- 季度模拟组合：使用持股、行业配置与历史结构估计未披露部分。`FULL` 以某期持股数超过 15 判断，不能据此确认真实完整披露。
- 基金收益：`nav_to_returns` 优先选有效记录超过 10 的 nav_adj，其次 nav_unit，保留 nav_cum 警告兜底。抓取复权处理把分红加回日收益后累乘；分红未取得时退化为单位净值收益。
- 行业收益：`index_to_returns` 以日期、行业为索引透视收盘价，重复单元取最后值，排序后 `pct_change()`。该调用未显式设置 fill_method，内部缺值行为依赖锁定 Pandas 版本；不能描述为所有缺失一律删除。
- 日期与交易日：取基金收益和行业收益日期交集，不补齐一个独立交易日历；`W-FRI` 生成周标签，每个标签取不晚于它的最近样本。窗口长度与 age 按对齐后观测计数，不按自然日计数。
- 缺失与筛选：有效非空记录超过共同日期总数一半的行业列被保留，其余列丢弃；保留列残余缺失填零。窗口内 y 的 NaN 行再剔除，少于 60 条则不计算该窗口。行业列筛选使用全段输入可用性，不能视为严格逐时点筛选。
- 披露滞后：`disclosure_align` 后移 45 个周一至周五工作日，`_latest_sim_row` 再要求距该时点至少 30 个自然日。不是实际公告日，也未处理交易所节假日。
- 标准化：存在字段、比例格式整理，求解时将时间权重归一化为合计 1，对 X/y 做加权中心化；**没有 z-score、除以标准差或 Min-Max 特征缩放**。

来源：`fetch_fund_manual.py`、`fetch_data.py`、`run_analysis.py:load_base/load_fund`、`lib/simulate.py`、`lib/regress.py`、`lib/solver.py`。相关测试包括 `test_fetch_fund_manual.py`、`test_disclosure_align.py` 和 `test_e2e_synthetic.py`；它们不证明外部数据完整性。

## 3. Feature Construction

`y` 是长度 T 的基金日收益向量；`X` 是 T×K 的行业日收益矩阵。默认每列来自一个申万行业指数，K 由实际输入及有效性筛选决定，既不固定 31，也不固定 27。

季度模拟行业组合不直接作为默认 X 的特征列，而是生成滞后的总暴露先验。默认逐行业锚定关闭。基金名称不是特征；净值水平也不是直接回归目标。

## 4. Modeling Layer

基金日收益近似为行业日收益加权组合、截距和未解释项之和。β 是收益口径的隐含暴露。

```math
\min_{\beta,c}\sum_t\widetilde w_t(y_t-X_t\beta-c)^2+\alpha\sum_j\beta_j,
\qquad\beta_j\ge0,\quad\sum_j\beta_j\le B.
```

- 滚动：默认最多 120 个对齐日观测，最少 60；按 W-FRI 标签逐周重算，每窗重新初始化，不沿用前一窗系数。
- 时间衰减：`w=0.5^(age/40)`，最新观测 age=0；默认半衰期 40，非正半衰期使用等权。权重在求解器内归一化。
- Lasso：默认 alpha=1e-6；非负条件下 L1 等于系数之和，因此梯度中加入常数 alpha。它控制系数收缩，可能带来稀疏性，但不保证正确识别行业或彻底解决共线性。
- 非负：适配多头权益行业解释假设，不是所有基金或衍生品策略的普遍真理。
- 总量上限：`min(prior.sum()*1.05, 0.98)`，缺先验为 0.95。`anchor_mult=None` 默认不设逐行业上限。

这些设计是响应速度、稳定性与经济解释之间的取舍，不是已经证明的全市场最优参数。FastAPI 快速分析不覆写命令行默认值；可选标定候选不自动进入正式分析。

## 5. Solver Implementation

实际调用为 `rolling_positions → _solve_with_caps → solve_weighted_lasso`。同文件保留的 legacy 求解器不是当前默认调用。

1. X、y 转为浮点数组，时间权重归一化。计算加权均值 xbar、ybar，中心化得到 Xc、yc。
2. 构造 `A=Xc.T @ diag(w) @ Xc`、`b=Xc.T @ diag(w) @ yc`。以 A 最大特征值估计梯度 Lipschitz 常数 `L=2*max(lambda_max,1e-12)`；特征值求解失败则用 trace 兜底，步长为 1/L。
3. β 从零向量投影开始，辅助点 z=β，初始动量为 1。不是从季度持仓或上周结果初始化。
4. 在 z 处计算 `2*(A@z-b)+alpha`，执行梯度步后投影到非负且系数合计不超过 B 的集合。默认无单行业上限时使用非负截断或排序阈值投影；有单行业上限的可选路径使用二分阈值投影。
5. 在新 β 处再做一次投影梯度检查，计算 `max(abs(beta_new-project(beta_new-step*gradient)))`。该投影残差不大于 1e-10 时标记收敛；否则 FISTA 更新动量，并在代码定义的点积条件下重启以抑制震荡。最多 2000 次迭代，到上限未达条件则保留 converged=false。
6. 最后清理小于 1e-12 的系数并重新投影，恢复截距 `c=ybar-xbar@beta`，计算时间加权 R²、残差和暴露合计。

求解器返回 n_iter 和 kkt_residual，但当前周频 diagnostics.csv 没有保存这两个字段。不能从公开诊断表格式推出某一次运行迭代了 176 次。

## 6. Output Layer

- 分析产物：weekly_positions.csv、diagnostics.csv、sim_portfolio.csv、report.md、positions.png（绘图成功时）。诊断表包含 r2、sum_beta、converged、n_obs、n_active。
- `api/presentation.py` 将结果组织为当前暴露、近四周变化、过去一年趋势与披露基座比较；`api/credibility.py` 评价已有结果，不重算或改变 β。
- Model Quality：未收敛或缺 R² 为 D；收敛时 R²≥0.8 为 A、≥0.6 为 B、≥0.35 为 C，否则 D；既有更低的报告等级可限制基础等级。
- Result Credibility：在基础等级上结合暴露合计差、结构距离、主要行业异常、近期总量变化、噪声与已保存合同范围等规则降级或告警。比如总量差达到 30 个百分点会把等级限制到 C；缺失参照时对应规则不可用。
- API：POST `/api/analyze` 创建任务，GET `/api/jobs/{job_id}` 查状态，GET `/api/results/{fund_code}` 读取结果，GET `/api/downloads/{fund_code}/{filename}` 下载允许的报告/周频/诊断文件。健康检查与本地静态前端服务亦存在。
- React 消费上述结果并展示风险和下载入口。工具目录负责启动日志、端口身份、环境锁定及回归比对，不是额外的数据智能模型。

## 历史数字核验表

| 内容 | 是否代码验证 | 来源文件 / 证据 | 是否可以写入 README |
|---|---|---|---|
| 161005 案例 | 是：代码支持基金代码输入；具体历史运行由截图与既有记录支持，本轮未重跑 | api/server.py；assets/model_diagnostics.png；docs/validation.md | 可以，限定为已留存的历史示例 |
| 5000+ 净值数据 | 否：Public 不包含 nav.csv，无法清点本例记录数 | run_analysis.py 加载逻辑不保证数量 | 不写；描述为可用历史净值序列，不用“约5000”替代证据 |
| 31 个申万一级行业 | 是：分类字典包含 31 项；不等于每次取得或使用 31 列 | lib/taxonomy.py:SW_L1 | 可以，仅描述内置分类范围 |
| 27 个最终行业 | 部分：测试断言及既有验收记录为 27，但研究基线不在 Public，相关测试缺数据跳过 | tests/test_production_regression.py；docs/validation.md | 不写成固定维度；首页采用“实际可用行业”，历史记录注明证据边界 |
| 120 交易日窗口 | 是：CLI 和函数默认定义 | run_analysis.py；lib/regress.py:rolling_positions | 可以，解释最多 120 个对齐观测 |
| 半衰期 40 日 | 是 | 同上；lib/solver.py:exp_decay_weights | 可以，单位为日观测而非自然日 |
| alpha=1e-6 | 是 | run_analysis.py；lib/regress.py | 可以，作为默认参数 |
| 最小 60 有效观测 | 是 | lib/regress.py:rolling_positions | 可以 |
| 176 次迭代 | 否：不是固定参数，未找到本例可核对的运行产物 | lib/solver.py 返回 n_iter；lib/regress.py 不将它写入诊断表 | 不写具体次数；说明自适应停止、上限2000 |
| R²=0.831 | 公式可由代码确认；具体数字仅能确认历史截图显示值，本轮不能独立重算 | lib/solver.py；assets/model_diagnostics.png；docs/validation.md | 可以写“历史截图显示约0.831”，不能宣称本轮重算验证 |
| Model Quality A | 规则可核对；本例等级在截图中可见 | api/credibility.py:_model_quality；诊断截图 | 可以，作为历史示例，不是全局质量保证 |
| Result Credibility C | 降级规则可核对；本例等级在截图中可见 | api/credibility.py:assess_result_credibility；诊断截图 | 可以，作为历史示例，不是统计置信概率 |

## 验证范围与后续缺口

本次重新检查源码、配置与测试定义，未重新运行 161005 分析、未抓取新数据、未重跑既有测试。测试通过数量沿用已明确标记的历史验收记录。真实市场准确性、多基金泛化、严格公告时点回测、置信区间覆盖率及业务效率增益仍缺充分证据。源码中的注释若与执行逻辑不一致，以执行逻辑为准。
