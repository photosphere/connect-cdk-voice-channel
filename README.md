# Amazon Connect Voice Channel CLI 部署指南

本文档介绍如何使用 `deploy_cli.py` 命令行工具，以交互式分步确认的方式将 Amazon Connect 语音通道资源部署到您的 AWS 账户。

---

## 前置条件

| 依赖 | 版本要求 | 安装方式 |
|------|---------|---------|
| Python | 3.8+ | — |
| Node.js | 14.x+ | [下载](https://nodejs.org/en/download/) |
| AWS CDK CLI | 2.x | `npm install -g aws-cdk` |
| AWS CLI | 已配置凭证 | `aws configure` |
| boto3 | — | `pip install -r requirements.txt` |

### 环境准备

```bash
# 克隆项目
git clone https://github.com/photosphere/connect-cdk-voice-channel.git
cd connect-cdk-voice-channel

# 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate   # macOS / Linux

# 安装依赖
pip install -r requirements.txt

# 首次使用需要 bootstrap CDK（每个 AWS 账户/区域只需执行一次）
cdk bootstrap
```

---

## 命令一览

```bash
python deploy_cli.py            # 交互式部署（默认）
python deploy_cli.py destroy    # 销毁已部署的 Stack
python deploy_cli.py clean      # 清理本地临时文件
python deploy_cli.py help       # 显示帮助信息
```

---

## 交互式部署流程

运行 `python deploy_cli.py` 后，工具将引导您完成以下 4 个步骤，每步确认后才会进入下一步。

### 步骤 1：确认 Amazon Connect 实例

工具会提示您输入 Amazon Connect 实例的 ARN：

```
============================================================
  步骤 1: 确认 Amazon Connect 实例
============================================================

请输入 Amazon Connect 实例 ARN: arn:aws:connect:us-east-1:123456789012:instance/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**获取 ARN 的方法：**
1. 登录 AWS 控制台 → Amazon Connect → 选择您的实例
2. 在实例概览页面复制 **实例 ARN**

**此步骤自动完成的操作：**
- 调用 `describe_instance` 验证实例是否存在
- 获取 Agent 安全配置文件（Security Profile）的 ARN
- 更新 Agent 安全配置文件权限（添加 CustomerProfiles、CustomViews 等权限）
- 生成 `connect.json` 和 `security_profile.json` 配置文件

确认信息无误后输入 `y` 继续。

---

### 步骤 2：选择 IVR 语言和语音

工具会列出所有可用的语言类别供您选择：

```
============================================================
  步骤 2: 选择 IVR 语言和语音
============================================================

  可选语言类别:
    1. 英语 (English (Australian), English (British), English (Indian)...)
    2. 中文 (Chinese (Cantonese), Chinese (Mandarin))
    3. 日语 (Japanese)
    4. 韩语 (Korean)
    5. 法语 (French (Belgian), French (Canadian), French)
    6. 德语 (German, German (Austrian))
    7. 西班牙语 (Spanish (European), Spanish (Mexican), Spanish (US))
    8. 阿拉伯语 (Arabic (Gulf))
    9. 葡萄牙语 (Portuguese (Brazilian), Portuguese (European))
    10. 意大利语 (Italian)
    其他: Belgian Dutch (Flemish), Catalan, Danish, ...

  请输入语言编号或直接输入语言名称（如 'English (US)', 'Chinese (Mandarin)'）
  语言选择: 2
```

**两种输入方式：**
- 输入编号（如 `1` 代表英语），若该类别有多个变体会进一步让您选择
- 直接输入语言名称（如 `Chinese (Mandarin)`）

**语音选择逻辑：**
- 工具自动选取该语言下 `languages_neural.csv` 中的第一个 Neural 语音
- 语音数据来源：`examples/languages/languages_neural.csv`

**语言与区域的关联：**

IVR 消息和 Survey 消息分别整合在两个 JSON 文件中，通过 `language` 属性区分：
- `examples/flows/welcome_message_flow/ivr_messages.json`
- `examples/flows/survey_message_flow/survey_messages.json`

| 语言 | language key | 营业时间文件 |
|------|-------------|-------------|
| English 系列 | `us` | `hours_of_operation_us.json` |
| Chinese (Mandarin) | `cn` | `hours_of_operation_hk.json` |
| Chinese (Cantonese) | `hk` | `hours_of_operation_hk.json` |
| Japanese | `jp` | `hours_of_operation_us.json` |
| Korean | `ko` | `hours_of_operation_us.json` |
| French 系列 | `fr` | `hours_of_operation_us.json` |
| German 系列 | `de` | `hours_of_operation_de.json` |
| Spanish 系列 | `es` | `hours_of_operation_us.json` |
| Arabic 系列 | `ar` | `hours_of_operation_dubai.json` |
| Portuguese 系列 | `pt` | `hours_of_operation_us.json` |
| Italian | `it` | `hours_of_operation_us.json` |

确认语言和语音后输入 `y` 继续。

---

### 步骤 3：确认弹屏（ScreenPop）功能

```
============================================================
  步骤 3: 确认弹屏 (ScreenPop) 功能
============================================================

  弹屏功能可以在座席接听电话时自动显示客户信息，
  包括客户姓名、电话、邮箱、历史通话记录等。
  需要启用 Amazon Connect Customer Profiles 服务。

  是否启用弹屏功能? (Y/n): y
```

**启用后将额外部署：**
- `screenpop_message_flow.json` → ScreenPop 联系流
- 主 IVR 流程中会添加 `DefaultAgentUI` 事件钩子，指向 ScreenPop 流

**前置要求：**
- 需要在 Amazon Connect 实例中启用 **Customer Profiles** 功能
- 需要配置 Calculated Attributes（如 `_last_agent_id`、`_last_channel` 等）

---

### 步骤 4：确认满意度评价（Survey）功能

```
============================================================
  步骤 4: 确认满意度评价 (Survey) 功能
============================================================

  满意度评价功能会在通话结束后自动播放评价语音，
  客户可以按 1-3 键进行评分（1=非常满意, 2=满意, 3=不满意）。

  是否启用满意度评价功能? (Y/n): y
```

**启用后将额外部署：**
- `survey_message_flow.json` → Survey 联系流
- 主 IVR 流程中会添加 `CustomerRemaining` 事件钩子，指向 Survey 流
- Survey 消息内容根据步骤 2 选择的语言自动匹配（支持 11 种语言）

**评分逻辑：**
- 按 `1` → 非常满意
- 按 `2` → 满意
- 按 `3` → 不满意
- 超时未按键 → 记录为 `-1`

---

### 部署确认与执行

四个步骤完成后，工具会显示完整的配置总览，并要求您输入租户名称：

```
============================================================
  部署配置总览
============================================================

  请输入租户名称 (Tenant Name) [MyTenant]: DemoTenant
  请输入租户描述 (可选) [Voice channel deployment]: Demo deployment

  ✓ Connect 实例 ARN: arn:aws:connect:us-east-1:123456789012:instance/xxxxx
  ✓ TTS 语音: Zhiyu
  ✓ 弹屏功能: 启用
  ✓ 满意度评价: 启用
  ✓ 租户名称: DemoTenant
  ✓ 座席文件: examples/agents/agents.csv
  ✓ 欢迎消息: 感谢您致电亚马逊客服中心。我们的客服代表正在接通中，请您耐心等待...
  ✓ 非工作时间消息: 感谢您致电亚马逊客服中心。我们的办公时间为周一至周五上午9点至...
  ✓ 营业时间: Basic Hours (Asia/Hong_Kong)

  确认以上配置，开始部署? (Y/n): y
```

确认后，工具将：

1. 设置所有环境变量（`tenant_name`、`tts_voice` 等）
2. 复制 `agents.csv` 到工作目录
3. 根据功能选择生成对应的 IVR 流程模板
4. 执行 `cdk deploy --require-approval never`

**CDK 部署创建的 AWS 资源：**

| 资源类型 | 命名规则 | 说明 |
|---------|---------|------|
| Hours of Operation | `{租户名} Basic Hours` | 营业时间配置 |
| Queue | `{租户名} Queue` | 联系队列 |
| Contact Flow (IVR) | `{租户名} Inbound Flow` | 主 IVR 入站流程 |
| Contact Flow (ScreenPop) | `{租户名} ScreenPop Flow` | 弹屏流程（可选） |
| Contact Flow (Survey) | `{租户名} Survey Flow` | 满意度评价流程（可选） |
| Routing Profile | `{租户名} Routing Profile` | 路由配置（VOICE + CHAT） |
| Users | 来自 `agents.csv` | 座席账号（SOFT_PHONE 模式） |

---

## 消息配置文件

所有语言的 IVR 消息和 Survey 消息分别整合在两个 JSON 文件中，通过顶层 key 区分语言，每个语言条目包含一个 `language` 属性标识语言名称。

### IVR 消息 — `examples/flows/welcome_message_flow/ivr_messages.json`

```json
{
  "us": {
    "language": "English",
    "welcomeMessage": "Thanks for calling Amazon Connect. ",
    "openHourMessage": "Thanks for calling Amazon Connect. Our office hours are ...",
    "errorMessage": "Thanks for calling Amazon Connect. We are currently ..."
  },
  "cn": {
    "language": "Chinese (Mandarin)",
    "welcomeMessage": "感谢您的来电。...",
    "openHourMessage": "感谢您的来电。我们的办公时间为...",
    "errorMessage": "感谢您的来电。我们目前的通话流量很大。..."
  }
}
```

### Survey 消息 — `examples/flows/survey_message_flow/survey_messages.json`

```json
{
  "us": {
    "language": "English",
    "surveyMessage": "Please rate your call experience from 1 to 3. ...",
    "surveyMessageFeedback": "Thanks for your feedback. Have a good day. Bye."
  },
  "cn": {
    "language": "Chinese (Mandarin)",
    "surveyMessage": "请对我们的服务进行评价。非常满意请按1，...",
    "surveyMessageFeedback": "感谢您的评价。祝您生活愉快，再见。"
  }
}
```

目前支持的 language key：`us`、`cn`、`hk`、`jp`、`ko`、`fr`、`de`、`es`、`ar`、`pt`、`it`（共 11 种语言）。

---

## 座席数据格式

座席信息从 `examples/agents/agents.csv` 读取，CSV 格式如下：

```csv
FirstName,LastName,Username,Password,Email,Mobile,Secondary_Email
Agent01,Test,Agent01_Test,Aa12345678.,,,
Agent02,Test,Agent02_Test,Aa12345678.,,,
```

如需修改座席列表，直接编辑该文件即可。密码需满足 Amazon Connect 的密码策略要求。

---

## 销毁资源

```bash
python deploy_cli.py destroy
```

输入部署时使用的租户名称（即 CloudFormation Stack 名称），确认后执行 `cdk destroy --force`。

---

## 清理临时文件

```bash
python deploy_cli.py clean
```

清理部署过程中在项目根目录生成的临时文件：
`connect.json`、`security_profile.json`、`environment_config.json`、`hours_of_operation.json`、`ivr_messages.json`、`survey_message.json`、`inbound_flow.json`、`agents.csv` 等。

---

## 常见问题

**Q: 部署失败提示 "未找到 cdk 命令"**
> 请确认已全局安装 AWS CDK CLI：`npm install -g aws-cdk`

**Q: 验证 Connect 实例失败**
> 请检查：1) ARN 格式是否正确；2) AWS CLI 凭证是否有 `connect:DescribeInstance` 权限；3) 区域是否匹配。

**Q: 部署后在 Connect 控制台看不到资源**
> 请确认您查看的是正确的 Connect 实例。资源名称均以您输入的租户名称为前缀。

**Q: 如何自定义 IVR 消息内容**
> 编辑 `examples/flows/welcome_message_flow/ivr_messages.json`，找到对应的 language key（如 `us`、`cn`、`jp`），修改其中的 `welcomeMessage`、`openHourMessage`、`errorMessage` 字段。

**Q: 如何自定义 Survey 消息内容**
> 编辑 `examples/flows/survey_message_flow/survey_messages.json`，找到对应的 language key，修改 `surveyMessage` 和 `surveyMessageFeedback` 字段。

**Q: 如何添加新语言的 IVR/Survey 消息**
> 在 `ivr_messages.json` 和 `survey_messages.json` 中新增一个 language key 及其消息内容，然后在 `deploy_cli.py` 的 `LANGUAGE_REGION_MAP` 中添加语言名称到该 key 的映射。

**Q: 如何添加新的营业时间配置**
> 在 `examples/hoursofoperation/` 目录下新建 JSON 文件，参考现有文件格式，然后在 `deploy_cli.py` 的 `HOP_REGION_MAP` 中添加映射。
