# Morning Briefing — 晨间简报系统

一个 Bloomberg 风格的专业金融晨间简报自动化系统，每个工作日自动生成并通过邮件发送。

## 系统架构

```
morning_briefing/
├── morning_briefing.py    ← 核心脚本：采集数据 → 生成简报 → 发送邮件
├── config.json            ← 配置：邮箱、数据源、定时参数
├── setup_task.ps1         ← 一键注册 Windows 定时任务
├── briefing_YYYY-MM-DD.html  ← 每日生成的简报（自动归档）
└── run_elevated.ps1       ← 提权运行脚本（UAC）
```

## 快速开始

### 1️⃣ 配置 Gmail 应用密码

由于开启了两步验证，Gmail 需要使用**应用专用密码**：

1. 打开 https://myaccount.google.com/apppasswords
2. 选择「邮件」→「Windows 计算机」，生成 16 位密码
3. 编辑 `config.json`，填入密码：

```json
"sender_password": "xxxx xxxx xxxx xxxx"
```

### 2️⃣ 注册定时任务（管理员权限）

方式一：右键点击 `setup_task.ps1` → **以管理员身份运行**（PowerShell）
方式二：手动注册（管理员 PowerShell）：

```powershell
$Action = New-ScheduledTaskAction -Execute "C:\Users\ZhuanZ\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -Argument "`"C:\Users\ZhuanZ\Documents\Codex\2026-06-19\new-chat-2\outputs\morning_briefing\morning_briefing.py`"" -WorkingDirectory "C:\Users\ZhuanZ\Documents\Codex\2026-06-19\new-chat-2\outputs\morning_briefing"
$Trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName "MorningFinancialBriefing" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force
```

### 3️⃣ 手动测试

```powershell
python "C:\Users\ZhuanZ\Documents\Codex\2026-06-19\new-chat-2\outputs\morning_briefing\morning_briefing.py"
```

### 4️⃣ 查看今天的简报

已生成的简报以 HTML 格式保存在同目录下：
`briefing_2026-06-19.html`

直接用浏览器打开即可查看。

## Bloomberg 风格说明

简报采用 Bloomberg Terminal 标志性的深色主题（`#0a0a0a` 背景 + `#ffd700` 金色高亮），版面包含：

- **顶部**：金色边框标题 + 日期 / Daily Edition
- **Market Overview**：全球主要指数实时行情（▲/▼色标）
- **Currencies**：主要外汇对报价
- **Commodities & Crypto**：黄金、原油、比特币
- **Top Stories**：20 条精选全球金融新闻（带编号和摘要）
- **页脚**：免责声明

## 数据源

| 类别 | 来源 |
|------|------|
| 行情数据 | Yahoo Finance (unofficial API) |
| 金融新闻 | Yahoo Finance RSS, MarketWatch RSS, The Economist |

## 取消定时任务

```powershell
Unregister-ScheduledTask -TaskName "MorningFinancialBriefing" -Confirm:$false
```
