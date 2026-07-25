#!/usr/bin/env python3
"""
Amazon Connect Voice Channel CLI Deployment Tool
分步骤交互式部署，功能等同于 connect_cdk_voice_channel_stack.py
"""

import os
import sys
import csv
import json
import shutil
import subprocess
import time
from datetime import datetime

import boto3

# ─── 常量 ───────────────────────────────────────────────────────────────────

EXAMPLES_DIR = "examples"
AGENTS_CSV = os.path.join(EXAMPLES_DIR, "agents", "agents.csv")
LANGUAGES_CSV = os.path.join(EXAMPLES_DIR, "languages", "languages_neural.csv")
FLOWS_DIR = os.path.join(EXAMPLES_DIR, "flows")
HOP_DIR = os.path.join(EXAMPLES_DIR, "hoursofoperation")

IVR_MESSAGES_FILE = os.path.join(FLOWS_DIR, "welcome_message_flow", "ivr_messages.json")
SURVEY_MESSAGES_FILE = os.path.join(FLOWS_DIR, "survey_message_flow", "survey_messages.json")
SCREENPOP_TRANSLATIONS_FILE = os.path.join(FLOWS_DIR, "screenpop_message_flow", "screenpop_translations.json")

# 语言名称到区域 key 的映射（用于选取 IVR/Survey 消息和营业时间文件）
LANGUAGE_REGION_MAP = {
    "English": "us",
    "Chinese (Cantonese)": "hk",
    "Chinese (Mandarin)": "cn",
    "Chinese": "cn",
    "German": "de",
    "Japanese": "jp",
    "Korean": "ko",
    "French": "fr",
    "Spanish": "es",
    "Arabic": "ar",
    "Portuguese": "pt",
    "Italian": "it",
}

HOP_REGION_MAP = {
    "us": os.path.join(HOP_DIR, "hours_of_operation_us.json"),
    "cn": os.path.join(HOP_DIR, "hours_of_operation_hk.json"),
    "hk": os.path.join(HOP_DIR, "hours_of_operation_hk.json"),
    "de": os.path.join(HOP_DIR, "hours_of_operation_de.json"),
    "jp": os.path.join(HOP_DIR, "hours_of_operation_us.json"),
    "ko": os.path.join(HOP_DIR, "hours_of_operation_us.json"),
    "fr": os.path.join(HOP_DIR, "hours_of_operation_us.json"),
    "es": os.path.join(HOP_DIR, "hours_of_operation_us.json"),
    "ar": os.path.join(HOP_DIR, "hours_of_operation_dubai.json"),
    "pt": os.path.join(HOP_DIR, "hours_of_operation_us.json"),
    "it": os.path.join(HOP_DIR, "hours_of_operation_us.json"),
}


# ─── 工具函数 ────────────────────────────────────────────────────────────────

def get_cdk_command():
    """返回可用的 CDK CLI 命令。

    优先使用项目本地安装的 CLI（node_modules/.bin/cdk），其版本已固定为
    与 aws-cdk-lib 兼容（>= 2.1133.0），避免因全局/npx 缓存中的旧版 CLI
    导致 "Cloud assembly schema version mismatch" 部署失败。
    若本地未安装则回退到 PATH 中的 cdk。
    """
    project_dir = os.path.dirname(os.path.abspath(__file__))
    local_cdk = os.path.join(project_dir, "node_modules", ".bin", "cdk")
    if os.path.isfile(local_cdk) and os.access(local_cdk, os.X_OK):
        return local_cdk
    return "cdk"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def copy_file(src, dst):
    shutil.copyfile(src, dst)


def load_languages_csv():
    """加载语言 CSV，返回 [{LanguageName, LanguageCode, Voice, Gender}, ...]"""
    rows = []
    with open(LANGUAGES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def get_ivr_messages(region_key):
    """从整合的 ivr_messages.json 中按 language key 获取 IVR 消息"""
    all_msgs = load_json(IVR_MESSAGES_FILE)
    return all_msgs.get(region_key, all_msgs["us"])


def get_survey_messages(region_key):
    """从整合的 survey_messages.json 中按 language key 获取 Survey 消息"""
    all_msgs = load_json(SURVEY_MESSAGES_FILE)
    return all_msgs.get(region_key, all_msgs["us"])


def get_screenpop_translations(region_key):
    """从 screenpop_translations.json 中按 language key 获取弹屏界面翻译"""
    all_translations = load_json(SCREENPOP_TRANSLATIONS_FILE)
    return all_translations.get(region_key, all_translations["us"])


def get_arn_prefix(arn):
    """从 Connect 实例 ARN 中提取前缀 (arn:aws:connect:region:account)"""
    return arn.rsplit(":", 2)[0]


def sanitize_username_token(name):
    """将租户名转换为合法的用户名片段（Connect Username 允许 [A-Za-z0-9_@.-]）。"""
    import re
    token = re.sub(r"[^A-Za-z0-9_@.\-]", "", name.replace(" ", ""))
    return token or "Tenant"


def prepare_agents_csv(tenant_name):
    """复制 agents.csv 到工作目录，并将 LastName / Username 中的 'Test' 替换为租户名。

    这样不同租户或多次部署之间座席用户名不会重复（Connect 实例内用户名必须唯一），
    避免创建座席时因重名而失败。返回处理后的用户名列表（供重名协调使用）。
    """
    if not os.path.exists(AGENTS_CSV):
        return []

    username_token = sanitize_username_token(tenant_name)
    rows = []
    usernames = []
    with open(AGENTS_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row.get("LastName"):
                row["LastName"] = row["LastName"].replace("Test", tenant_name)
            if row.get("Username"):
                row["Username"] = row["Username"].replace("Test", username_token)
            rows.append(row)
            if row.get("Username"):
                usernames.append(row["Username"])

    with open("agents.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return usernames


def get_stack_managed_arns(stack_name):
    """获取当前 CloudFormation Stack 已管理的资源物理 ID（Connect 资源为 ARN）。

    用于在重名协调时区分：由本 Stack 管理的同名资源交给 CloudFormation 就地更新，
    不属于本 Stack 的同名资源才需要删除后重建。
    """
    cfn = boto3.client("cloudformation")
    managed = set()
    try:
        paginator = cfn.get_paginator("list_stack_resources")
        for page in paginator.paginate(StackName=stack_name):
            for r in page.get("StackResourceSummaries", []):
                pid = r.get("PhysicalResourceId")
                if pid:
                    managed.add(pid)
    except Exception:
        # Stack 尚不存在（首次部署）——返回空集合
        pass
    return managed


def reconcile_existing_resources(connect_instance_arn, stack_name, tenant_name, agent_usernames):
    """删除与目标资源同名、但不由当前 Stack 管理的 Connect 资源。

    - 由当前 Stack 管理的同名资源会跳过：CloudFormation 会对其执行就地更新。
    - 不属于当前 Stack 的同名资源（例如手动创建或历史遗留）会被删除，
      以便 cdk deploy 顺利创建，实现「有重名则更新、无重名则创建」的效果。

    删除顺序遵循依赖关系：座席 → 路由配置 → 队列 → 营业时间 → 联系流 → Lambda。
    整个过程为尽力而为（best-effort），单个失败不会中断部署。
    """
    instance_id = connect_instance_arn.split("/")[-1]
    connect_client = boto3.client("connect")
    managed = get_stack_managed_arns(stack_name)

    prefix = f"{tenant_name} "
    queue_name = f"{tenant_name} Queue"
    routing_profile_name = f"{tenant_name} Routing Profile"
    flow_names = {
        f"{tenant_name} Inbound Flow",
        f"{tenant_name} ScreenPop Flow",
        f"{tenant_name} Survey Flow",
    }
    lambda_name = f"{tenant_name}-GetAgentNameByAgentId"

    print("\n  正在检查并清理同名的历史资源（不影响本 Stack 管理的资源）...")

    # 1. 座席（Users）——必须先于路由配置删除
    try:
        paginator = connect_client.get_paginator("list_users")
        for page in paginator.paginate(InstanceId=instance_id):
            for u in page.get("UserSummaryList", []):
                if u.get("Username") in agent_usernames and u.get("Arn") not in managed:
                    try:
                        connect_client.delete_user(InstanceId=instance_id, UserId=u["Id"])
                        print(f"    ↻ 已删除同名座席: {u['Username']}")
                    except Exception as e:
                        print(f"    ⚠ 删除座席 {u.get('Username')} 失败: {e}")
    except Exception as e:
        print(f"    ⚠ 列举座席失败: {e}")

    # 2. 路由配置（Routing Profile）——引用队列，需先于队列删除
    try:
        paginator = connect_client.get_paginator("list_routing_profiles")
        for page in paginator.paginate(InstanceId=instance_id):
            for rp in page.get("RoutingProfileSummaryList", []):
                if rp.get("Name") == routing_profile_name and rp.get("Arn") not in managed:
                    try:
                        connect_client.delete_routing_profile(
                            InstanceId=instance_id, RoutingProfileId=rp["Id"])
                        print(f"    ↻ 已删除同名路由配置: {rp['Name']}")
                    except Exception as e:
                        print(f"    ⚠ 删除路由配置失败: {e}")
    except Exception as e:
        print(f"    ⚠ 列举路由配置失败: {e}")

    # 3. 队列（Queue）——引用营业时间，需先于营业时间删除
    try:
        paginator = connect_client.get_paginator("list_queues")
        for page in paginator.paginate(InstanceId=instance_id, QueueTypes=["STANDARD"]):
            for q in page.get("QueueSummaryList", []):
                if q.get("Name") == queue_name and q.get("Arn") not in managed:
                    try:
                        connect_client.delete_queue(InstanceId=instance_id, QueueId=q["Id"])
                        print(f"    ↻ 已删除同名队列: {q['Name']}")
                    except Exception as e:
                        print(f"    ⚠ 删除队列失败: {e}")
    except Exception as e:
        print(f"    ⚠ 列举队列失败: {e}")

    # 4. 营业时间（Hours of Operation）
    try:
        paginator = connect_client.get_paginator("list_hours_of_operations")
        for page in paginator.paginate(InstanceId=instance_id):
            for h in page.get("HoursOfOperationSummaryList", []):
                if h.get("Name", "").startswith(prefix) and h.get("Arn") not in managed:
                    try:
                        connect_client.delete_hours_of_operation(
                            InstanceId=instance_id, HoursOfOperationId=h["Id"])
                        print(f"    ↻ 已删除同名营业时间: {h['Name']}")
                    except Exception as e:
                        print(f"    ⚠ 删除营业时间失败: {e}")
    except Exception as e:
        print(f"    ⚠ 列举营业时间失败: {e}")

    # 5. 联系流（Contact Flows）——入站流引用其它流，需最先删除
    try:
        flows_to_delete = []
        paginator = connect_client.get_paginator("list_contact_flows")
        for page in paginator.paginate(InstanceId=instance_id):
            for cf in page.get("ContactFlowSummaryList", []):
                if cf.get("Name") in flow_names and cf.get("Arn") not in managed:
                    flows_to_delete.append(cf)
        flows_to_delete.sort(key=lambda c: 0 if c["Name"].endswith("Inbound Flow") else 1)
        for cf in flows_to_delete:
            try:
                connect_client.delete_contact_flow(
                    InstanceId=instance_id, ContactFlowId=cf["Id"])
                print(f"    ↻ 已删除同名联系流: {cf['Name']}")
            except Exception as e:
                print(f"    ⚠ 删除联系流 {cf.get('Name')} 失败: {e}")
    except Exception as e:
        print(f"    ⚠ 列举联系流失败: {e}")

    # 6. Lambda 函数（先解除与 Connect 实例的关联，再删除）
    try:
        lambda_client = boto3.client("lambda")
        fn = lambda_client.get_function(FunctionName=lambda_name)
        fn_arn = fn["Configuration"]["FunctionArn"]
        if fn_arn not in managed:
            try:
                assoc = connect_client.list_lambda_functions(InstanceId=instance_id)
                for arn in assoc.get("LambdaFunctions", []):
                    if arn == fn_arn:
                        connect_client.disassociate_lambda_function(
                            InstanceId=instance_id, FunctionArn=fn_arn)
            except Exception:
                pass
            try:
                lambda_client.delete_function(FunctionName=lambda_name)
                print(f"    ↻ 已删除同名 Lambda 函数: {lambda_name}")
            except Exception as e:
                print(f"    ⚠ 删除 Lambda 函数失败: {e}")
    except Exception:
        # Lambda 不存在——无需处理
        pass


def prompt_input(msg, default=None):
    """带默认值的输入提示"""
    if default:
        val = input(f"{msg} [{default}]: ").strip()
        return val if val else default
    while True:
        val = input(f"{msg}: ").strip()
        if val:
            return val
        print("  ⚠ 不能为空，请重新输入。")


def sanitize_stack_name(name):
    """将任意名称转换为合法的 CDK Stack 名称。
    规则: /^[A-Za-z][A-Za-z0-9-]*$/
    尽量保持与原始名称接近。
    """
    import re
    sanitized = name.replace("_", "-").replace(" ", "-")
    sanitized = re.sub(r"[^A-Za-z0-9-]", "", sanitized)
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    sanitized = sanitized.strip("-")
    # 数字开头时加最小前缀 "S"
    if sanitized and not sanitized[0].isalpha():
        sanitized = "S" + sanitized
    return sanitized if sanitized else "MyTenant"


def prompt_tenant_name(msg, default=None):
    """输入租户名称，自动生成合法的 CDK Stack 名称。
    tenant_name: 用户原始输入，用于 Connect 资源命名（Queue、Flow 等前缀）
    stack_name:  符合 CDK 规则的名称，仅用于 CloudFormation Stack ID
    返回 (tenant_name, stack_name)
    """
    import re
    pattern = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
    tenant_name = prompt_input(msg, default)
    if pattern.match(tenant_name):
        return tenant_name, tenant_name
    stack_name = sanitize_stack_name(tenant_name)
    print(f"  ℹ CDK Stack 名称自动设为: {stack_name}（原始租户名 '{tenant_name}' 用于 Connect 资源命名）")
    return tenant_name, stack_name


def prompt_yes_no(msg, default="y"):
    """是/否确认"""
    hint = "Y/n" if default == "y" else "y/N"
    val = input(f"{msg} ({hint}): ").strip().lower()
    if not val:
        val = default
    return val in ("y", "yes", "是")


def print_header(step, title):
    print(f"\n{'='*60}")
    print(f"  步骤 {step}: {title}")
    print(f"{'='*60}")


def print_summary(label, value):
    print(f"  ✓ {label}: {value}")


# ─── 步骤 1: 确认 Amazon Connect 实例 ────────────────────────────────────────

def step1_connect_instance():
    print_header(1, "确认 Amazon Connect 实例")
    print()

    connect_instance_arn = prompt_input("请输入 Amazon Connect 实例 ARN")

    # 从 ARN 中提取 Instance ID
    # ARN 格式: arn:aws:connect:region:account:instance/instance-id
    try:
        instance_id = connect_instance_arn.split("/")[-1]
    except Exception:
        print("  ✗ ARN 格式不正确，请检查后重试。")
        sys.exit(1)

    print(f"\n  正在验证 Connect 实例...")
    connect_client = boto3.client("connect")

    try:
        res = connect_client.describe_instance(InstanceId=instance_id)
        instance_arn = res["Instance"]["Arn"]
        print(f"  ✓ 实例验证成功")
        print(f"    Instance ID: {instance_id}")
        print(f"    Instance ARN: {instance_arn}")

        # 保存 connect.json
        save_json({"Id": instance_id, "Arn": instance_arn}, "connect.json")

        # 获取 Agent 安全配置文件
        res = connect_client.list_security_profiles(InstanceId=instance_id)
        security_profile_arn = None
        security_profile_id = None
        for item in res["SecurityProfileSummaryList"]:
            if item["Name"] == "Agent":
                security_profile_arn = item["Arn"]
                security_profile_id = item["Id"]
                save_json(
                    {"Id": item["Id"], "Arn": item["Arn"], "Name": item["Name"]},
                    "security_profile.json",
                )
                break

        if not security_profile_arn:
            print("  ✗ 未找到 Agent 安全配置文件")
            sys.exit(1)

        print(f"    Security Profile ARN: {security_profile_arn}")

        # 更新安全配置文件权限
        try:
            connect_client.update_security_profile(
                SecurityProfileId=security_profile_id,
                InstanceId=instance_id,
                Permissions=[
                    "BasicAgentAccess",
                    "OutboundCallAccess",
                    "CustomerProfiles.Create",
                    "CustomerProfiles.Edit",
                    "CustomerProfiles.View",
                    "CustomViews.Access",
                ],
            )
            print("  ✓ Agent 安全配置文件权限已更新")
        except Exception as e:
            print(f"  ⚠ 更新安全配置文件权限失败: {e}")

    except Exception as e:
        print(f"  ✗ 验证 Connect 实例失败: {e}")
        sys.exit(1)

    if not prompt_yes_no("\n  确认使用此 Connect 实例继续?"):
        print("  已取消。")
        sys.exit(0)

    return instance_arn, security_profile_arn


# ─── 步骤 2: 选择语言和语音 ──────────────────────────────────────────────────

def step2_language_voice():
    print_header(2, "选择 IVR 语言和语音")
    print()

    languages = load_languages_csv()

    # 获取唯一语言名称列表
    lang_names = []
    seen = set()
    for row in languages:
        name = row["LanguageName"].strip()
        if name not in seen:
            lang_names.append(name)
            seen.add(name)

    # 构建语言分类提示
    language_categories = {
        "英语": [n for n in lang_names if "English" in n],
        "中文": [n for n in lang_names if "Chinese" in n],
        "日语": [n for n in lang_names if "Japanese" in n],
        "韩语": [n for n in lang_names if "Korean" in n],
        "法语": [n for n in lang_names if "French" in n],
        "德语": [n for n in lang_names if "German" in n],
        "西班牙语": [n for n in lang_names if "Spanish" in n],
        "阿拉伯语": [n for n in lang_names if "Arabic" in n],
        "葡萄牙语": [n for n in lang_names if "Portuguese" in n],
        "意大利语": [n for n in lang_names if "Italian" in n],
    }

    print("  可选语言类别:")
    for i, (zh_name, variants) in enumerate(language_categories.items(), 1):
        if variants:
            print(f"    {i}. {zh_name} ({', '.join(variants[:3])}{'...' if len(variants) > 3 else ''})")

    # 也列出其他语言
    categorized = set()
    for variants in language_categories.values():
        categorized.update(variants)
    others = [n for n in lang_names if n not in categorized]
    if others:
        print(f"    其他: {', '.join(others)}")

    print()
    print("  请输入语言编号或直接输入语言名称（如 'English (US)', 'Chinese (Mandarin)'）")
    lang_input = prompt_input("  语言选择")

    # 解析输入
    selected_lang = None
    try:
        idx = int(lang_input) - 1
        category_keys = list(language_categories.keys())
        if 0 <= idx < len(category_keys):
            variants = language_categories[category_keys[idx]]
            if len(variants) == 1:
                selected_lang = variants[0]
            else:
                print(f"\n  该类别下有多个变体:")
                for j, v in enumerate(variants, 1):
                    print(f"    {j}. {v}")
                v_input = prompt_input("  请选择变体编号", "1")
                v_idx = int(v_input) - 1
                selected_lang = variants[v_idx] if 0 <= v_idx < len(variants) else variants[0]
    except ValueError:
        # 直接输入了语言名称
        for name in lang_names:
            if lang_input.lower() in name.lower():
                selected_lang = name
                break

    if not selected_lang:
        print("  ⚠ 未匹配到语言，使用默认 English (US)")
        selected_lang = "English (US)"

    # 筛选该语言的语音
    voices = [r for r in languages if r["LanguageName"].strip() == selected_lang]
    if not voices:
        print(f"  ✗ 未找到 {selected_lang} 的语音")
        sys.exit(1)

    # 选择第一个语音（去掉 * 号）
    first_voice = voices[0]["Voice"].replace("*", "").strip()
    print(f"\n  已选择语言: {selected_lang}")
    print(f"  使用语音: {first_voice} ({voices[0]['Gender'].strip()})")

    # 确定区域映射 — 优先匹配更具体的名称（如 "Chinese (Mandarin)" 优先于 "Chinese"）
    region_key = "us"  # 默认
    best_match_len = 0
    for key, value in LANGUAGE_REGION_MAP.items():
        if key.lower() in selected_lang.lower() and len(key) > best_match_len:
            region_key = value
            best_match_len = len(key)

    if not prompt_yes_no(f"\n  确认使用 {selected_lang} / {first_voice}?"):
        print("  已取消。")
        sys.exit(0)

    return first_voice, selected_lang, region_key


# ─── 步骤 3: 确认弹屏功能 ────────────────────────────────────────────────────

def step3_screenpop():
    print_header(3, "确认弹屏 (ScreenPop) 功能")
    print()
    print("  弹屏功能可以在座席接听电话时自动显示客户信息，")
    print("  包括客户姓名、电话、邮箱、历史通话记录等。")
    print("  需要启用 Amazon Connect Customer Profiles 服务。")
    print()

    enable = prompt_yes_no("  是否启用弹屏功能?", "y")
    if enable:
        print("  ✓ 将部署 ScreenPop 联系流")
    else:
        print("  ✓ 跳过 ScreenPop 部署")

    return enable


# ─── 步骤 4: 确认满意度评价功能 ──────────────────────────────────────────────

def step4_survey(region_key):
    print_header(4, "确认满意度评价 (Survey) 功能")
    print()
    print("  满意度评价功能会在通话结束后自动播放评价语音，")
    print("  客户可以按 1-3 键进行评分（1=非常满意, 2=满意, 3=不满意）。")
    print()

    enable = prompt_yes_no("  是否启用满意度评价功能?", "y")
    survey_message = ""
    survey_feedback = ""

    if enable:
        # 从整合的 survey_messages.json 中按 language key 获取消息
        survey_data = get_survey_messages(region_key)
        survey_message = survey_data.get("surveyMessage", "")
        survey_feedback = survey_data.get("surveyMessageFeedback", "")

        print(f"  ✓ 将部署 Survey 联系流")
        print(f"    评价提示: {survey_message[:50]}...")
        print(f"    反馈消息: {survey_feedback[:50]}...")

        save_json(
            {"surveyMessage": survey_message, "surveyMessageFeedback": survey_feedback},
            "survey_message.json",
        )
    else:
        print("  ✓ 跳过 Survey 部署")

    return enable, survey_message, survey_feedback


# ─── 准备流程文件 ─────────────────────────────────────────────────────────────

def prepare_flow_files(enable_screenpop, enable_survey):
    """根据功能选择复制对应的流程模板文件"""
    if enable_screenpop and enable_survey:
        src = os.path.join(FLOWS_DIR, "ivr_survey_screenpop_flow.json")
    elif enable_survey:
        src = os.path.join(FLOWS_DIR, "ivr_survey_flow.json")
    elif enable_screenpop:
        src = os.path.join(FLOWS_DIR, "ivr_screenpop_flow.json")
    else:
        src = os.path.join(FLOWS_DIR, "welcome_message_flow", "welcome_message_flow.json")

    copy_file(src, "inbound_flow.json")

    if enable_survey:
        copy_file(
            os.path.join(FLOWS_DIR, "survey_message_flow", "survey_message_flow.json"),
            "survey_message_flow.json",
        )

    if enable_screenpop:
        copy_file(
            os.path.join(FLOWS_DIR, "screenpop_message_flow", "screenpop_message_flow.json"),
            "screenpop_message_flow.json",
        )


# ─── 部署确认和执行 ──────────────────────────────────────────────────────────

def deploy(
    connect_instance_arn,
    security_profile_arn,
    tts_voice,
    selected_lang,
    region_key,
    enable_screenpop,
    enable_survey,
    survey_message,
    survey_feedback,
):
    print(f"\n{'='*60}")
    print("  部署配置总览")
    print(f"{'='*60}")

    # 获取租户名称
    tenant_name, stack_name = prompt_tenant_name("\n  请输入租户名称 (Tenant Name)", "MyTenant")
    tenant_description = prompt_input("  请输入租户描述 (可选)", "Voice channel deployment")

    print()
    print_summary("Connect 实例 ARN", connect_instance_arn)
    print_summary("TTS 语音", tts_voice)
    print_summary("弹屏功能", "启用" if enable_screenpop else "禁用")
    print_summary("满意度评价", "启用" if enable_survey else "禁用")
    print_summary("租户名称", tenant_name)
    if stack_name != tenant_name:
        print_summary("CDK Stack 名称", stack_name)
    print_summary("座席文件", AGENTS_CSV)

    # 加载 IVR 消息
    ivr_data = get_ivr_messages(region_key)

    welcome_msg = ivr_data.get("welcomeMessage", "")
    open_hour_msg = ivr_data.get("openHourMessage", "")
    error_msg = ivr_data.get("errorMessage", "")

    save_json(
        {"welcomeMessage": welcome_msg, "openHourMessage": open_hour_msg, "errorMessage": error_msg},
        "ivr_messages.json",
    )

    print_summary("欢迎消息", welcome_msg[:40] + "...")
    print_summary("非工作时间消息", open_hour_msg[:40] + "...")

    # 加载弹屏翻译
    if enable_screenpop:
        screenpop_translations = get_screenpop_translations(region_key)
        save_json(screenpop_translations, "screenpop_translations.json")
        print_summary("弹屏界面语言", f"已设置为 {region_key} 区域语言")

    # 加载 HOP
    hop_file = HOP_REGION_MAP.get(region_key, HOP_REGION_MAP["us"])
    if os.path.exists(hop_file):
        copy_file(hop_file, "hours_of_operation.json")
    else:
        copy_file(HOP_REGION_MAP["us"], "hours_of_operation.json")

    hop_data = load_json("hours_of_operation.json")
    print_summary("营业时间", f"{hop_data['name']} ({hop_data['timeZone']})")

    # 准备流程文件
    prepare_flow_files(enable_screenpop, enable_survey)

    print()
    if not prompt_yes_no("  确认以上配置，开始部署?"):
        print("  已取消部署。")
        sys.exit(0)

    # 设置环境变量
    os.environ["tenant_name"] = tenant_name
    os.environ["stack_name"] = stack_name
    os.environ["tenant_description"] = tenant_description
    os.environ["tts_voice"] = tts_voice
    os.environ["deploy_survey_flow"] = str(enable_survey)
    os.environ["deploy_screen_flow"] = str(enable_screenpop)
    os.environ["ivr_welcome_message"] = welcome_msg
    os.environ["ivr_open_hour_message"] = open_hour_msg
    os.environ["ivr_error_message"] = error_msg
    os.environ["language_region_key"] = region_key
    os.environ["selected_language"] = selected_lang

    if enable_survey:
        os.environ["survey_message"] = survey_message
        os.environ["survey_message_feedback"] = survey_feedback

    # 保存环境配置
    save_json(
        {
            "tenant_name": tenant_name,
            "stack_name": stack_name,
            "tenant_description": tenant_description,
            "tts_voice": tts_voice,
            "deploy_survey_flow": str(enable_survey),
            "deploy_screen_flow": str(enable_screenpop),
            "language_region_key": region_key,
            "selected_language": selected_lang,
        },
        "environment_config.json",
    )

    # 复制并处理 agents.csv（将 LastName / Username 中的 'Test' 替换为租户名）
    agent_usernames = prepare_agents_csv(tenant_name)

    # 重名协调：删除不由本 Stack 管理的同名资源，使部署实现「有重名则更新、无重名则创建」
    reconcile_existing_resources(
        connect_instance_arn, stack_name, tenant_name, agent_usernames)

    # 执行 CDK 部署
    print(f"\n{'='*60}")
    print("  开始 CDK 部署...")
    print(f"{'='*60}\n")

    try:
        result = subprocess.run(
            [get_cdk_command(), "deploy", "--require-approval", "never"],
            capture_output=False,
        )
        if result.returncode == 0:
            print(f"\n  ✓ CDK 部署完成!")
        else:
            print(f"\n  ✗ CDK 部署失败，请检查 CloudFormation 控制台获取详细信息。")
            sys.exit(1)
    except FileNotFoundError:
        print("  ✗ 未找到 cdk 命令，请在项目根目录安装本地 AWS CDK CLI:")
        print("    npm install")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  部署已被用户中断。")
        sys.exit(1)


# ─── 清理临时文件 ─────────────────────────────────────────────────────────────

def cleanup():
    """清理部署过程中生成的临时文件"""
    files = [
        "connect.json",
        "security_profile.json",
        "environment_config.json",
        "hours_of_operation.json",
        "ivr_messages.json",
        "survey_message.json",
        "screenpop_translations.json",
        "inbound_flow.json",
        "inbound_flow_updated.json",
        "survey_message_flow.json",
        "screenpop_message_flow.json",
        "connect_flow_screenpop_updated.json",
        "connect_flow_survey_updated.json",
        "agents.csv",
    ]
    removed = 0
    for f in files:
        if os.path.exists(f):
            os.remove(f)
            removed += 1
    if removed:
        print(f"  已清理 {removed} 个临时文件。")


# ─── 销毁 CDK Stack ──────────────────────────────────────────────────────────

def destroy():
    """销毁已部署的 CDK Stack"""
    tenant_name, stack_name = prompt_tenant_name("请输入要销毁的租户名称 (Tenant Name)")

    print(f"\n  ⚠ 即将销毁 Stack: {stack_name}" + (f"（租户名: {tenant_name}）" if stack_name != tenant_name else ""))
    if not prompt_yes_no("  确认销毁?", "n"):
        print("  已取消。")
        return

    os.environ["tenant_name"] = tenant_name
    os.environ["stack_name"] = stack_name
    os.environ["tenant_description"] = ""
    os.environ["tts_voice"] = "Joanna"
    os.environ["deploy_survey_flow"] = "False"
    os.environ["deploy_screen_flow"] = "False"
    os.environ["ivr_welcome_message"] = ""
    os.environ["ivr_open_hour_message"] = ""
    os.environ["ivr_error_message"] = ""
    os.environ["survey_message"] = ""
    os.environ["survey_message_feedback"] = ""

    # Stack 初始化还会读取 connect.json / security_profile.json / hours_of_operation.json 等文件。
    # 如果本地已被清理，需要生成占位文件让 synth 能跑通。
    placeholder_files = {
        "connect.json": {"Id": "placeholder", "Arn": "arn:aws:connect:us-east-1:000000000000:instance/placeholder"},
        "security_profile.json": {"Id": "placeholder", "Arn": "arn:aws:connect:us-east-1:000000000000:instance/placeholder/security-profile/placeholder", "Name": "Agent"},
        "environment_config.json": {
            "tenant_name": tenant_name,
            "tenant_description": "",
            "tts_voice": "Joanna",
            "deploy_survey_flow": "False",
            "deploy_screen_flow": "False",
        },
    }

    created_placeholders = []
    for fname, content in placeholder_files.items():
        if not os.path.exists(fname):
            save_json(content, fname)
            created_placeholders.append(fname)

    if not os.path.exists("hours_of_operation.json"):
        hop_default = os.path.join(HOP_DIR, "hours_of_operation_us.json")
        if os.path.exists(hop_default):
            copy_file(hop_default, "hours_of_operation.json")
            created_placeholders.append("hours_of_operation.json")

    # 确保 inbound_flow.json 存在（Stack 初始化时 load_flows() 会写入，但以防万一）
    if not os.path.exists("inbound_flow.json"):
        default_flow = os.path.join(FLOWS_DIR, "welcome_message_flow", "welcome_message_flow.json")
        if os.path.exists(default_flow):
            copy_file(default_flow, "inbound_flow.json")
            created_placeholders.append("inbound_flow.json")

    # 确保 ivr_messages.json 存在
    if not os.path.exists("ivr_messages.json"):
        ivr_default = get_ivr_messages("us")
        save_json(
            {"welcomeMessage": ivr_default["welcomeMessage"],
             "openHourMessage": ivr_default["openHourMessage"],
             "errorMessage": ivr_default["errorMessage"]},
            "ivr_messages.json",
        )
        created_placeholders.append("ivr_messages.json")

    # 确保 screenpop_translations.json 存在
    if not os.path.exists("screenpop_translations.json"):
        screenpop_default = get_screenpop_translations("us")
        save_json(screenpop_default, "screenpop_translations.json")
        created_placeholders.append("screenpop_translations.json")

    try:
        result = subprocess.run(
            [get_cdk_command(), "destroy", "--force"],
            capture_output=False,
        )
        if result.returncode == 0:
            print(f"\n  ✓ Stack {stack_name} 已销毁!")
        else:
            print(f"\n  ✗ 销毁失败，请检查 CloudFormation 控制台。")
    except FileNotFoundError:
        print("  ✗ 未找到 cdk 命令，请在项目根目录运行 'npm install' 安装本地 CDK CLI。")
    finally:
        # 清理本次为 destroy 生成的占位文件
        for fname in created_placeholders:
            if os.path.exists(fname):
                os.remove(fname)


# ─── 磁盘/缓存检查 ────────────────────────────────────────────────────────────

# CloudShell 的持久化家目录仅有约 1GB，缓存过大时会导致 CDK/jsii 解压
# aws-cdk-lib 时报 "ENOSPC: no space left on device"。部署前检查缓存目录，
# 超过阈值则自动清空以释放空间。
CACHE_DIR = os.path.expanduser("~/.cache")
CACHE_SIZE_LIMIT_BYTES = 100 * 1024 * 1024  # 100MB


def get_dir_size(path):
    """递归计算目录占用的字节数（无法访问的文件将被跳过）。"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path, onerror=lambda e: None):
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                # 使用 lstat 避免跟随符号链接重复统计
                total += os.lstat(fp).st_size
            except (OSError, FileNotFoundError):
                continue
    return total


def check_and_clear_cache():
    """检查缓存目录大小，超过 100MB 时清空其内容以释放磁盘空间。"""
    if not os.path.isdir(CACHE_DIR):
        return

    size = get_dir_size(CACHE_DIR)
    size_mb = size / (1024 * 1024)

    if size <= CACHE_SIZE_LIMIT_BYTES:
        print(f"  缓存目录 {CACHE_DIR} 当前占用 {size_mb:.1f}MB，未超过 100MB 限制。")
        return

    print(f"\n  ⚠ 缓存目录 {CACHE_DIR} 占用 {size_mb:.1f}MB，已超过 100MB，正在清空 ...")
    cleared = 0
    for entry in os.listdir(CACHE_DIR):
        target = os.path.join(CACHE_DIR, entry)
        try:
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target, ignore_errors=True)
            else:
                os.remove(target)
            cleared += 1
        except OSError as e:
            print(f"    ⚠ 无法删除 {target}: {e}")

    freed_mb = (size - get_dir_size(CACHE_DIR)) / (1024 * 1024)
    print(f"  ✓ 已清理 {cleared} 项缓存，释放约 {freed_mb:.1f}MB 空间。")


# ─── 依赖检查 ────────────────────────────────────────────────────────────────

def ensure_dependencies():
    """确保 CDK 部署所需的 Python 依赖已安装。

    CDK 会以子进程运行 `python3 app.py`，该文件需要 aws_cdk / constructs。
    在 Homebrew / Debian 等「externally-managed」环境中，pip 会依据 PEP 668
    拒绝全局或 --user 安装。为兼容这些环境，这里在项目目录下创建独立的虚拟环境
    .venv，将依赖安装其中，并用该虚拟环境的解释器重新执行本脚本，
    从而避免 ModuleNotFoundError: No module named 'aws_cdk'。
    """
    import importlib.util

    required_modules = ["aws_cdk", "constructs"]
    missing = [m for m in required_modules if importlib.util.find_spec(m) is None]
    if not missing:
        return

    project_dir = os.path.dirname(os.path.abspath(__file__))
    req_file = os.path.join(project_dir, "requirements.txt")
    if not os.path.exists(req_file):
        print(f"  ⚠ 缺少依赖 {missing}，但未找到 requirements.txt，请手动安装。")
        return

    in_virtualenv = sys.prefix != sys.base_prefix

    # 已处于虚拟环境：pip 允许直接安装。
    if in_virtualenv:
        print(f"\n  检测到缺少依赖 {missing}，正在安装 requirements.txt ...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], check=True)
            print("  ✓ 依赖安装完成")
            return
        except subprocess.CalledProcessError as e:
            print(f"  ✗ 依赖安装失败: {e}")
            print("    请手动运行: pip install -r requirements.txt")
            sys.exit(1)

    # 非虚拟环境（常见于 Homebrew/系统 Python，受 PEP 668 限制）：
    # 创建并使用项目本地 .venv，再用其解释器重新执行本脚本。
    venv_dir = os.path.join(project_dir, ".venv")
    if os.name == "nt":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        venv_bin = os.path.join(venv_dir, "Scripts")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")
        venv_bin = os.path.join(venv_dir, "bin")

    if not os.path.exists(venv_python):
        print(f"\n  检测到缺少依赖 {missing}，正在创建虚拟环境 .venv ...")
        try:
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
        except subprocess.CalledProcessError as e:
            print(f"  ✗ 创建虚拟环境失败: {e}")
            print("    请手动运行: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt")
            sys.exit(1)

    print("  正在安装 requirements.txt 到 .venv ...")
    try:
        subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([venv_python, "-m", "pip", "install", "-r", req_file], check=True)
        print("  ✓ 依赖安装完成")
    except subprocess.CalledProcessError as e:
        print(f"  ✗ 依赖安装失败: {e}")
        print("    请手动运行: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt")
        sys.exit(1)

    # 将 .venv 提前加入 PATH，确保后续 CDK 子进程中的 `python3 app.py` 也使用该环境；
    # 然后用 .venv 的解释器重新执行本脚本（再次进入时依赖已就绪，会直接跳过）。
    os.environ["VIRTUAL_ENV"] = venv_dir
    os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")
    print("  ✓ 已切换到 .venv，重新启动部署脚本 ...\n")
    os.execv(venv_python, [venv_python] + sys.argv)


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Amazon Connect Voice Channel CLI Deployment Tool      ║")
    print("╚══════════════════════════════════════════════════════════╝")

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "destroy":
            ensure_dependencies()
            destroy()
            return
        elif cmd == "clean":
            cleanup()
            return
        elif cmd == "help":
            print("\n用法:")
            print("  python deploy_cli.py          交互式部署")
            print("  python deploy_cli.py destroy   销毁已部署的 Stack")
            print("  python deploy_cli.py clean     清理临时文件")
            print("  python deploy_cli.py help      显示帮助")
            return

    # 部署前检查缓存目录大小，必要时清空以避免磁盘空间不足
    check_and_clear_cache()

    # 部署前确保 CDK 依赖已安装
    ensure_dependencies()

    # 步骤 1: 确认 Connect 实例
    connect_instance_arn, security_profile_arn = step1_connect_instance()

    # 步骤 2: 选择语言和语音
    tts_voice, selected_lang, region_key = step2_language_voice()

    # 步骤 3: 确认弹屏功能
    enable_screenpop = step3_screenpop()

    # 步骤 4: 确认满意度评价
    enable_survey, survey_message, survey_feedback = step4_survey(region_key)

    # 部署
    deploy(
        connect_instance_arn,
        security_profile_arn,
        tts_voice,
        selected_lang,
        region_key,
        enable_screenpop,
        enable_survey,
        survey_message,
        survey_feedback,
    )


if __name__ == "__main__":
    main()
