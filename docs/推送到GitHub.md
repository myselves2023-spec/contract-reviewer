# 推到 GitHub

两条路，任选其一。**方式 A 需要装 git，方式 B 不用。**

---

## 方式 A：本地建仓后推送（推荐）

### 1. 装 git（如果还没有）

```powershell
winget install --id Git.Git -e
```

装完**关掉当前终端再开一个新的**，否则 `git` 不在 PATH 里。

验证：

```powershell
git --version
```

### 2. 建仓并提交

在 `contract-reviewer` 目录下执行：

```powershell
git init
git add .
git commit -m "feat: 合同风险审查台 v1.0

- 31 项审查点 + 34 条民法典条文，支持 docx/pdf/txt/md
- 规则层确定性检测 + LLM 逐条复核（可否决误报）
- 条款级定位高亮、法条溯源、审查意见书导出
- PWA 可安装，Docker/Render 部署配置"
git branch -M main
```

### 3. 在 GitHub 上建空仓库

网页操作：GitHub → New repository → 名字填 `contract-reviewer` → **不要**勾选 "Add a README" / "Add .gitignore" / "Choose a license"（本地已有）→ Create。

### 4. 关联并推送

```powershell
git remote add origin https://github.com/你的用户名/contract-reviewer.git
git push -u origin main
```

**第一次推送会要求登录。** GitHub 已经禁用密码认证，要填 Personal Access Token：

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token → 勾选 `repo` → 生成
3. 复制那串 `ghp_xxx`，在终端的密码提示处粘贴（**输入时不显示字符，正常**）
4. 用户名填 GitHub 用户名，不是邮箱

> Token 只显示一次。存到密码管理器里。

---

## 方式 B：网页上传（不装 git）

1. 把 `contract-reviewer` 整个文件夹解压到桌面（如果拿到的是 zip）
2. GitHub → New repository → 建空仓库
3. 进入仓库 → **Add file → Upload files**
4. 把**文件夹里的内容**（不是文件夹本身）拖进去
   - 关键：`.gitignore` 和 `.gitattributes` 是隐藏文件，Windows 资源管理器默认看不见，但**拖整个文件夹时会被一起复制**
5. 填提交信息 → Commit changes

**缺点**：以后每次改代码都要重新上传。只适合一次性上线、后续不再改的情况。

---

## 推送前必须确认的三件事

### 1. `.env` 没有进仓库

```powershell
git status --short | Select-String "\.env"
```

**必须没有任何输出。** 如果看到 `.env`，立刻：

```powershell
git rm --cached .env
git commit -m "chore: 移除误提交的 .env"
```

`.env` 里有你的 DeepSeek key，一旦推到公开仓库就等同于泄露——GitHub 上有机器人专门扫这个。

### 2. `vendor/` 没有进仓库

那是 46 MB 的 PDF 解析库，别人 `pip install` 就能装，不必进版本库。

```powershell
git status --short | Select-String "vendor"
```

### 3. 生成的 docx 没有进仓库

审查意见书是运行产物，不该提交。`.gitignore` 已经处理。

---

## 仓库里应该有什么

推到 GitHub 后，仓库首页应该长这样（约 60 个文件、0.5 MB）：

```
app/       8 个 py    后端：解析 / 规则 / LLM / 报告 / 服务
data/      2 个 json  法条库 + 审查点定义
data/prompts/          prompt 模板
web/       9 个       前端（含 manifest、sw、图标）
docs/                 参考来源说明
eval/                 评测集与标注
samples/              演示合同（docx/pdf/txt）
tools/     15 个      测试、评测、标注、图标生成
Dockerfile / render.yaml / requirements.txt
LICENSE / README.md / .gitignore / .gitattributes
```

---

## 提交信息怎么写（简历项目尤其重要）

别用 `update` / `fix` / `提交`。好的提交信息能让面试官看出你是在做工程，不是在凑数。

```
feat: 新增买卖合同与租赁合同审查点，覆盖 20→31 项
fix: 修正 CP19 正则把年份误判为租期的问题
refactor: 将逐条 LLM 复核的上下文改为跨条款拼接
docs: 补充评测方法与样本量说明
```

前缀用 `feat` / `fix` / `refactor` / `docs` / `test` / `chore` 里的一个。

---

## 下一步

推上去之后：

1. 确认 README 在网页上能正常渲染（表格、代码块）
2. 按 `README.md` 里的「方案 A」在 Render 上部署
3. 拿到公网地址后，回到仓库 → 右侧 About → 填 Website
4. 简历里放这个地址

**别急着公开传播。** 这个 demo 没有登录功能，任何人拿到链接都能用你的 key 花钱。要公开的话先加访问令牌。
