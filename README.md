# 合同风险审查台

面向中文商务合同的**条款级风险审查工具**。上传合同，输出带法条依据的风险清单、修改建议和可导出的审查意见书。

不是又一个"法律问答机器人"，而是把审查这件事做成**确定性的流水线**：原文定位 → 规则判定 → 法条溯源 → 意见书。

```
上传 .docx/.txt  →  分段并记录字符偏移  →  20 个审查点逐条判定
                                              ├─ 命中 → 回填法条 + 修改建议
                                              └─ 未命中 → 记录「缺失型」风险
                                        →  评分/分级  →  导出 Word 意见书
```

## 关键指标

| 项目 | 数值 |
|---|---|
| 法条库 | 34 条（民法典合同编核心条文，逐字取自公开仓库） |
| 审查点 | 31 项，分 10 类：违约责任、担保、租赁、建设工程、争议解决、履行验收、合同要素等 |
| 样例·技术服务合同 | 命中 14 项（高 5 / 中 6 / 低 3），评分 14/100 |
| 样例·商铺租赁合同 | 命中 9 项（高 2 / 中 4 / 低 3），评分 54/100 |
| 干净合同（负样本） | 命中 0 项，评分 100/100，无误报 |
| 评测（种子集） | 3 份合同 / 23 个标注点，Precision 100% / Recall 100% / F1 100%（**样本量不足，见下文**） |
| 大模型复核（deepseek-chat） | 12 项全部返回合法 JSON，确认 12 项，单次审查 5.3–6.5 s（并发 4） |

## 快速开始

**双击 `run.bat`**，浏览器打开 <http://127.0.0.1:8765>，点「载入技术服务样例」或「载入租赁样例」即可看到完整效果——两类合同会走不同的审查点。

> 为什么是 `.bat` 不是 `.ps1`：Windows 默认执行策略会拦截未签名脚本（报「禁止运行脚本」）。`run.ps1` / `check.ps1` 保留了，但如果被拦就改用 `.bat`，或执行 `powershell -ExecutionPolicy Bypass -File .\run.ps1`。

手动方式：

```powershell
python -m pip install python-docx
python main.py --port 8765
```

**想支持 PDF 的话**，再装一个库（约 46 MB，装在项目内 `vendor/`，不污染系统 Python）：

```powershell
python -m pip install --target vendor pymupdf
# 国内网络慢或超时就加镜像：
# python -m pip install --target vendor pymupdf -i https://pypi.tuna.tsinghua.edu.cn/simple
```

不装也能用，只是上传 PDF 时会提示缺少解析库。

**不需要任何 API Key 也能跑完整个流程。** 大模型是可选增强，未配置时自动降级为规则模式，界面上会标注「大模型未配置 · 规则模式」。

### 接入 API Key

**双击 `set_key.bat`**，按提示粘贴 key（粘贴后不显示字符是正常的），回车。

它会自动完成两件事：把 key 写进 `.env`，然后立刻发一次真实请求检测。看到「✓ 调用成功」就通了。

手动方式：双击 `edit_env.bat` 用记事本打开 `.env`，把 `LLM_API_KEY=sk-your-key-here` 那一行换成真实 key，保存，再双击 `verify.bat`。

> 注意：`.env` 的文件名就是 `.env`，不是 `.env.txt`。Windows 默认隐藏扩展名，手动改名容易出错——用 `set_key.bat` 可以完全避开这个问题。

如果服务已经在跑，**改完 `.env` 只需刷新页面**，不用重启。

下文是手动配置方式，供参考：

```powershell
Copy-Item .env.example .env
notepad .env
```

填三行：

```ini
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-你的key
LLM_MODEL=deepseek-chat
```

**保存后直接刷新页面即可**，不必重启服务——`/api/meta` 每次都会重读 `.env`。右上角 chip 变成「大模型已启用 · deepseek-chat」就算接通。

常见端点对照：

| 供应商 | LLM_BASE_URL | LLM_MODEL |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里云百炼（通义） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| 火山方舟（豆包） | `https://ark.cn-beijing.volces.com/api/v3` | 推理接入点 ID（`ep-xxx`） |

模型名会随平台更新，以官方文档为准。`LLM_BASE_URL` 只写到版本段（如 `/v1`），不要带 `/chat/completions`。

**排障顺序：**

| 现象 | 检查 |
|---|---|
| chip 仍显示「未配置」 | 文件名是不是真的叫 `.env`（Windows 默认隐藏扩展名，容易存成 `.env.txt`）；key 是否还是占位符 `sk-your-key-here`（代码会把占位符判定为未配置） |
| chip 变绿但审查报错 | 看响应里的 `engine.llm_error`，或执行 `python tools/prompt_probe.py --id CP02 --raw` 单条调试 |
| 400 / 不认 `response_format` | 代码会自动去掉该参数重试一次；若仍 400，多半是模型名或 key 不对 |
| 返回不是 JSON | 换 `deepseek-chat` 这类指令遵循较好的模型，或把 `LLM_TEMPERATURE` 调到 0 |

## 目录结构

```
contract-reviewer/
├─ app/
│  ├─ parsing.py      文档解析：.docx/.txt → 文本 + 分段偏移
│  ├─ checklist.py    规则层：审查点加载、法条查询、确定性扫描
│  ├─ llm.py          LLM 层：OpenAI 兼容端点，失败自动降级
│  ├─ review.py       编排：扫描 → 评分 → 结构化结果
│  ├─ report.py       导出：Word 版审查意见书
│  └─ server.py       HTTP 服务（标准库实现）
├─ data/
│  ├─ statutes.json   法条库
│  ├─ checklist.json  审查点定义（含正则、法条映射、整改动作推断）
│  └─ prompts/        prompt 模板（版本化，改文案不用动代码）
├─ docs/              参考来源与借鉴边界说明
├─ vendor/            PDF 解析库（可选，pip 安装，已 gitignore）
├─ web/               单页前端（原生 JS，无构建）
├─ eval/              评测集：cases/ + labels.json
├─ samples/           样例合同（txt + docx）与示例意见书
└─ tools/             冒烟测试 / 接口测试 / 评测 / 法条抓取
```

## 设计说明

### 为什么分「规则层」和「LLM 层」

规则层做确定性检测：同样的合同永远得到同样的结果，可以写回归测试，可以算精确率召回率。它的短板是只能匹配表述，理解不了语义。

LLM 层补语义：结合本合同的具体措辞解释风险、生成可直接替换的条款文本。它的短板是不稳定、不可复现、会编法条。

**分工是刻意的**：法条引用只由规则层给出（`checklist.json` 里写死映射），LLM 永远不负责"引用法条"，从架构上消除幻觉引用。LLM 只做两件事——解释和改写。

### 为什么是条款级定位

很多合同审查工具输出"整篇总结"。这类输出没法核对，也没法改。

这里的做法是：解析时记录每个段落的 `start/end` 字符偏移，规则命中后把偏移**扩展到整个条款行**，前端据此在原文上高亮。返回结果里每个风险点都带 `evidence: [{start, end, text}]`，前端切原文验证，`tools/smoke_test.py` 里有一条断言专门校验这个不越界：

```python
assert result["contract"]["text"][ev["start"]:ev["end"]] == ev["text"], "偏移错位"
```

`normalize()` 把所有换行替换为等长空格，保证正则匹配位置与原始偏移一一对应——这是整套定位能成立的前提，改动时不要破坏这个不变量。

### 为什么零依赖

目标环境往往装不了包（内网、离线评审机、服务器无 pip）。除 `python-docx` 外全部用标准库，包括 HTTP 服务（`http.server`）、BM25 类检索、JSON 处理。

代价是要自己写路由和 base64 文件传输；收益是 `git clone` 之后 `python main.py` 就能跑，部署只需一个 Python 进程。

## 法条数据

条文正文逐字取自 [LawRefBook/Laws](https://github.com/LawRefBook/Laws)（民法典/合同编.md），未作改写，`data/statutes.json` 的 `meta` 字段记录了来源与生效日期。

目前只收录 25 条审查高频条文，不是全库。扩充方式：

```powershell
python tools/fetch_laws.py --books 总则 合同编
# 生成 data/statutes_full.json，确认无误后替换 data/statutes.json
```

**注意**：引用失效条文是法律工具最严重的事故。民法典 2021-01-01 施行，此前签订的合同可能适用原《合同法》，正式使用前必须核对合同的签订时间与法律适用。

## 评测

```powershell
python tools/eval.py --verbose
```

```
合同                          分数   命中   误报   漏报
sample_contract.txt           19    13     0     0
clean_service_contract.txt   100     0     0     0
TP=13  FP=0  FN=0
Precision = 100.0%   Recall = 100.0%   F1 = 100.0%
```

**这个数字不能直接写进简历。** 评测集只有 2 份合同、13 个标注点，而且是我自己标注、自己调规则，属于"训练集即测试集"，100% 只能说明规则没有写错，不说明泛化能力。

要拿到有意义的数字，需要：

1. 收集 30–50 份真实（脱敏）合同，覆盖买卖、服务、租赁、建设工程
2. 人工标注每个合同**确实存在**的风险点编号
3. 至少留 30% 作为测试集，调规则时不许看
4. 重跑评测，报测试集上的数字

`eval/labels.json` 加一条 case 就会自动纳入统计，脚本已经把 `expected: []` 当作负样本用来衡量误报。

## 如何提升精度（这不是「训练」）

这个系统里没有可训练的参数。三样东西各管一件事，混在一起会走错方向：

| 直觉上以为的 | 实际是什么 | 改法 | 对精度的影响 |
|---|---|---|---|
| 多喂法条，让它更懂法 | 静态查询表，只用于展示引用原文 | 改 `data/statutes.json` | **几乎为零**。法条不参与检索，扩库只让引用能显示更多条文 |
| 多喂案例，让它学着判 | 没有学习机制。案例只用于**测量**精度 | 放 `eval/cases/` 并标注 | 不直接提升，但让提升**可度量** |
| 训练模型 | 规则层是正则 + JSON；LLM 是调用现成 API | 改 `checklist.json` / prompt | 这才是真正提升精度的地方 |

正确的循环：

```
收集合同 → 标注 → 出指标 → 看误报还是漏报 → 改规则/prompt → 复跑对比
```

### 第 1 步：收集合同

脱敏后放进 `eval/cases/`，支持 `.txt` / `.md` / `.docx`。建议 30–50 份，覆盖买卖、服务、租赁、建设工程。

别用裁判文书网的判决书全文——合规风险和体积都不合适。

### 第 2 步：标注

```powershell
python tools/annotate.py      # 或双击 annotate.bat
```

逐条确认命中的风险点是否真实存在（`y` / `n`），再确认有没有规则漏掉的。每份约 3–5 分钟。

### 第 3 步：看指标

```powershell
python tools/eval.py --verbose
```

盯两个数：

- **误报（FP）**——规则层报了你标"不存在"的。改 `data/checklist.json` 里对应正则，收紧条件。
- **漏报（FN）**——你补进去但规则没命中的。要么新增检查点，要么放宽正则。

### 第 4 步：只在必要时改 prompt

规则层能解决的不要交给 LLM。LLM 只负责「解释」和「改写条款」，**不该决定"有没有这个风险"**——那部分必须确定性、可回归。

### 什么时候才需要扩法条

只有当你**新增一个审查点**、而这个审查点要引用新条文时。在 `data/statutes.json` 加一条，id 用 `mfd-条号`（如 `mfd-577`），然后在新检查点的 `statutes` 里引用它。

批量抓取：

```powershell
python tools/fetch_laws.py --books 总则 合同编
```

> 需要能访问 `raw.githubusercontent.com`。本机该域名 DNS 不通，所以这一步在当前环境跑不了；换网络或用 GitHub 网页下载 `民法典/合同编.md` 后本地解析。

### 如果你确实想做「训练」

那是微调（SFT）一个模型，和当前项目是两件不同的事，需要：GPU（本机没有）、数千条标注样本、以及独立评测集（否则无法判断微调后是变好还是变坏）。

代价大、收益不确定。这个场景当前的瓶颈是**审查点定义不全**，不是模型不够懂法。两周项目里不建议做。

## 审查意见书结构

导出的 docx 按律所交付物的顺序组织：

```
一、总体结论      评分 / 等级 / 风险分布 / 一句话判断
二、风险明细      每条含：整改动作 · 法律依据 · 命中原文 · 风险说明 · 复核结论 · 修改建议 · 建议条款
三、谈判顺序      按后果严重性排序的处理次序
四、签署前必检清单 能自动判定的打 ✓/✗，需人工的标 ○
五、免责声明
```

**整改动作**分为六种（借鉴 [contract-copilot](https://github.com/cat-xierluo/legal-skills) 的修订策略）：

| 动作 | 含义 |
|---|---|
| 局部删减 | 只需删掉一段风险表述 |
| 局部补入 | 只需补一句/一段（条款缺失时默认） |
| 局部替换 | 替换局部短语、数字、期限 |
| 整条重写 | 原条款逻辑已失效，局部改动无法修复 |
| 批注提示 | 只提示，不改正文 |
| 仅入意见书 | 不必留痕的优化建议 |

**涉及商务数值时不替客户拍板**：改动价格、比例、期限这类条款时，建议条款里的具体数字用 `【】` 占位（如「违约金按合同总额的【百分之X】计算」），并在分析里注明需商务确认。

借鉴明细与边界见 [docs/参考来源.md](docs/参考来源.md)。

## 大模型层

配置方式见上文「接入 API Key」。任何 OpenAI 兼容端点都行（DeepSeek / 通义 / 豆包 / 本地 vLLM）。

### 三个刻意的设计

**1. 逐条复核，不是整篇投喂。**
每个审查点单独发一次请求，上下文只有：该审查点命中的条款 + **规则层为判定该审查点而匹配到的其他条款** + 相关法条原文。相比把整份合同丢给模型，锚点明确、不会跑题，token 成本低一个数量级，而且某一条失败不影响其他条。

这里踩过一个坑，值得记录：最初上下文取的是「命中段前后各一段」，结果跨条款的审查点全错。模型看不到第三条的定金，就断言「全文未约定定金」；CP09 属于缺失型、没有命中文本，上下文是空的，模型直接编出「全文未检索到任何保证条款」——而合同 9.1 明明有保证人。

修法是让 `Checkpoint.evaluate` 同时返回 primary（用于高亮）和 related（用于上下文），把 `all` 条件命中的条款也带进 prompt；同时在 prompt 里加硬约束：**看不到相反约定时不许断言"全文未约定"，只能判 uncertain**。

**2. 允许模型否决规则层。**
规则层是高召回、低精度的，误报多。模型可以返回 `verdict: "dismiss"` 把这部分挡掉，界面上打「疑似误报」标签，报告里写「建议人工确认后忽略」。**被否决的项不会被删除**，保留可追溯性——审查工具最忌讳模型悄悄吞掉一条真实风险。

判定分布会写进 `engine.llm_verdicts`，界面和意见书都会显示"确认 10 项 / 排除 2 项 / 存疑 0 项"。

**3. 法条仍然只由规则层提供。**
prompt 里塞的是法条原文，模型被明确禁止引用未提供的条文。引用合法性由架构保证，不靠 prompt 求它别编。

### prompt 是数据，不是代码

`data/prompts/review_v1.system.txt` 和 `review_v1.user.txt`，改文案不用动 Python。换版本时新增 `review_v2.*`，用 `LLM_PROMPT=review_v2` 切换，历史版本保留即可对比效果。

### 失败如何处理

超时、429、5xx 会指数退避重试 2 次；仍失败则该条目跳过并记进 `engine.llm_error`，审查流程照常出结果。端点完全不可达时，整份报告降级为纯规则版，界面提示一次。

`LLM_API_KEY` 若是 `sk-your-key-here` 这类占位符，会被判定为未配置——避免照抄示例后每次都卡在超时上。

## 测试

```powershell
# 1. 后端逻辑（不需要网络/不需要起服务）
python tools/smoke_test.py

# 2. HTTP 接口 + 导出 + 三种文件格式
python main.py --port 8765
python tools/api_test.py 8765

# 3. 规则层指标
python tools/eval.py --verbose

# 3.5 标注新合同（提升精度的入口）
python tools/annotate.py

# 4. LLM 链路（用本地 mock 端点，无需外网）
python tools/mock_llm.py --port 8899
$env:LLM_BASE_URL="http://127.0.0.1:8899/v1"; $env:LLM_API_KEY="test-key"; $env:LLM_MODEL="mock-model"
python main.py --port 8768
python tools/llm_test.py 8768 8899

# 5. 重试：前两次请求故意返回 500
python tools/mock_llm.py --port 8898 --fail-first 2
python tools/llm_test.py 8769 8898

# 6. 降级：端点不可达时仍要出结果
$env:LLM_BASE_URL="http://127.0.0.1:9/v1"; $env:LLM_RETRIES="0"
python main.py --port 8770
python tools/degraded_test.py 8770
```

`tools/mock_llm.py` 不是空壳桩：它会解析程序真正发出的 prompt，按审查点编号返回不同的 `verdict`（含 `dismiss`），因此能覆盖"否决""字段归一化""并发合并""重试"这些分支。

**注意**：mock 端点用于回归测试（不花钱、可复现），验证的是链路正确性。真实模型已用 `deepseek-chat` 跑通：12 项全部返回合法 JSON，且据此发现并修掉了一个跨条款上下文缺陷（见上文「逐条复核」）。换模型或改 prompt 后仍需重跑 `verify.bat`，重点看两件事——JSON 是否稳定，以及 `revised_clause` 的措辞质量。

开发机的网络实测（用于排障参考）：`api.deepseek.com`、`dashscope.aliyuncs.com`、`github.com` 可直连；`pypi.org` 超时、`raw.githubusercontent.com` DNS 失败，所以 `pip install` 和 raw 直链在这个环境不可用。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/meta` | 法条数、审查点数、LLM 状态 |
| GET | `/api/sample` | 内置样例合同 |
| POST | `/api/review` | `{filename, content_b64}` 或 `{filename, text}` 或 `{sample: true}` |
| POST | `/api/export` | `{result}` → `{filename, content_b64}`（docx） |

文件用 base64 放在 JSON 里传，不上传磁盘、不落库，请求结束即释放。

## 装成 App（PWA）

页面已带 `manifest.json` 和 Service Worker，不用应用商店：

| 设备 | 操作 |
|---|---|
| 电脑（Chrome / Edge） | 地址栏右侧的「安装」图标，或菜单 → 应用 → 安装此站点 |
| iPhone | Safari 打开 → 分享 → 添加到主屏幕 |
| Android | Chrome 菜单 → 添加到主屏幕 |

装好后从桌面图标全屏打开，没有地址栏，和原生 App 一样。外壳已缓存，断网也能打开界面（审查本身仍需联网）。

> 安装要求 HTTPS。`127.0.0.1` 是例外，本地可以直接装。

## 部署（让别人也能打开）

单进程、无状态、不依赖数据库，任何能跑 Python 的地方都行。

### 方案 A：Render 免费部署（最省事）

1. 把代码推到 GitHub
2. 打开 [render.com](https://render.com) → New → Blueprint → 选仓库（会自动读 `render.yaml`）
3. 在 Environment 里填 `LLM_API_KEY`
4. 等 2–3 分钟，拿到 `https://xxx.onrender.com`

**代价**：免费实例闲置 15 分钟休眠，下次访问冷启动约 30 秒；国内访问速度一般。

### 方案 B：国内云服务器（访问快，要花钱）

阿里云 / 腾讯云轻量应用服务器，最低配约 ¥10–40/月：

```bash
python3 -m pip install -r requirements.txt
python3 main.py --host 0.0.0.0 --port 8000
```

用 systemd 或 nohup 常驻，Nginx 反代 + Let's Encrypt 证书。绑自己的域名需要 ICP 备案，用平台分配的域名不用。

### 方案 C：Docker

```bash
docker build -t contract-reviewer .
docker run -p 8000:8000 -e LLM_API_KEY=sk-xxx contract-reviewer
```

镜像只装 `python-docx` + `pymupdf`，约 200 MB。

### 部署前必读

- `LLM_API_KEY` 用平台的环境变量传，**不要**提交 `.env`（已在 `.gitignore`）。
- **这个 demo 没有登录功能**。公网部署后，任何拿到链接的人都能用你的 key 调用大模型并产生费用。自己演示可以接受，公开传播前请先加访问控制。

## 已知局限

- **扫描件不支持 OCR**。带文字层的 PDF 可以正常解析（实测与 txt 结果完全一致）；纯图片的扫描件会被明确拦截并提示，不做 OCR。
- **旧版 `.doc` 不支持**。请用 Word 另存为 `.docx`。
- **规则层是浅层匹配**。同义表述、跨条款矛盾（如违约金条款与责任限制条款冲突）检测不到，这部分要靠 LLM 层补。
- **评分是启发式**。权重来自严重度分级，没有经过真实案件校准，只适合做横向比较，不适合当绝对风险度量。
- **不是法律意见**。产品内所有输出都带免责声明，且不允许出现"胜诉""包赔"一类表述。

## 简历写法（数字待你补全后再填）

> **合同风险审查台**（个人项目）｜Python / 原生 JS / OpenAI 兼容 LLM
> - 设计「规则层 + LLM 层」双通道架构：规则层负责确定性检测与法条映射，LLM 层**逐条**复核（单条上下文 = 命中条款 + 相邻段 + 法条原文），从架构上消除模型编造法条引用的可能
> - 让 LLM 反向否决规则层误报（`dismiss` 分支），被否决项打标保留而非删除，兼顾精度与可追溯性
> - 实现条款级定位：解析阶段记录字符偏移，命中后扩展至整条条款并在前端原文高亮，正则可回归验证偏移不越界
> - 构建 XX 份中文合同的标注评测集，规则层在测试集上 Precision XX% / Recall XX%；LLM 复核后误报率从 XX% 降至 XX%
> - 全链路失败可控：超时/限流指数退避重试，端点不可达时自动降级为纯规则报告，单进程零第三方依赖部署

**不要写**："自研法律大模型""微调 ChatLaw"——没做，一问就穿。
