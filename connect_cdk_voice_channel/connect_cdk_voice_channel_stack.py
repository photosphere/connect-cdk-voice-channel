from aws_cdk import (
    # Duration,
    Stack,
    CfnTag
    # aws_sqs as sqs,
)
from constructs import Construct
from aws_cdk import aws_connect as connect
import os
import subprocess
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
import pandas as pd
import boto3
import time
import json
import shutil
from datetime import datetime

# 工具函数


def copy_file(source, destination):
    """复制文件的通用函数"""
    if not os.path.exists(destination):
        shutil.copyfile(source, destination)


def load_json_file(file_path):
    """加载JSON文件的通用函数"""
    with open(file_path, 'r') as f:
        return json.load(f)


def save_json_file(data, file_path):
    """保存JSON文件的通用函数"""
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)


def create_message_input_section(label, value):
    """创建消息输入区域的通用函数"""
    return st.text_area(label, value=value)


def create_file_uploader_section(title, file_type, accept_multiple=False):
    """创建文件上传区域的通用函数"""
    return st.file_uploader(
        f"Choose a {file_type.upper()} file of {title}",
        accept_multiple_files=accept_multiple,
        type=file_type
    )


def create_inbound_flow(tab1_button, tab2_button, tab3_button):
    """创建入站流程文件"""

    # 根据选择的功能复制相应的流程文件
    flow_configs = [
        (tab1_button and tab2_button and tab3_button,
         'examples/flows/ivr_survey_screenpop_flow.json', 'inbound_flow.json'),
        (tab1_button and tab2_button,
         'examples/flows/ivr_survey_flow.json', 'inbound_flow.json'),
        (tab1_button and tab3_button,
         'examples/flows/ivr_screenpop_flow.json', 'inbound_flow.json'),
        (tab1_button, 'examples/flows/welcome_message_flow/welcome_message_flow.json',
         'inbound_flow.json')
    ]

    additional_files = [
        (tab2_button,
         'examples/flows/survey_message_flow/survey_message_flow.json', 'survey_message_flow.json'),
        (tab3_button, 'examples/flows/screenpop_message_flow/screenpop_message_flow.json',
         'screenpop_message_flow.json')
    ]

    # 复制主流程文件
    for condition, source, dest in flow_configs:
        if condition:
            print(source)
            copy_file(source, dest)
            break

    # 复制附加文件
    for condition, source, dest in additional_files:
        if condition:
            copy_file(source, dest)


def handle_agent_configuration():
    """处理代理配置"""
    with st.expander("Agent Configuration", expanded=False):
        uploaded_file = create_file_uploader_section("Agents", "csv")
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            st.write(df)
            df.to_csv("agents.csv", index=False)


def handle_hours_operation_configuration():
    """处理营业时间配置"""
    with st.expander("Hours of Operation Configuration", expanded=False):
        uploaded_file = create_file_uploader_section("Operation", "json")
        if uploaded_file is not None:
            hop_data = json.load(uploaded_file)
            st.write("Timezone:", hop_data['timeZone'])
            hop_df = pd.DataFrame(hop_data['timeslices'])
            st.write(hop_df)
            save_json_file(hop_data, 'hours_of_operation.json')


def setup_language_voice_selection():
    """设置语言和语音选择"""
    lan_df = pd.read_csv('examples/languages/languages_neural.csv')
    lan_vals = lan_df.iloc[:, 0].unique()
    default_language_index = 13  # English language as default
    lan_selected = st.selectbox(
        'IVR languages', lan_vals, index=default_language_index)

    lan_df['VoiceDisplay'] = lan_df['Voice'] + ',' + lan_df['Gender']
    lan_filter = lan_df['LanguageName'] == lan_selected
    voice_vals = lan_df.loc[lan_filter, 'VoiceDisplay'].str.replace("*", "")
    default_voice_index = 0  # Danielle voice as default
    voice_selected = st.selectbox(
        'IVR language voices', voice_vals, index=default_voice_index)

    return voice_selected.split(",")[0]


def create_message_configuration(file_path, output_file, message_fields, button_text, success_message):
    """创建消息配置区域的通用函数"""
    message_data = load_json_file(file_path)
    save_json_file(message_data, output_file)

    # 创建输入字段
    updated_values = {}
    for field_key, field_label in message_fields.items():
        updated_values[field_key] = create_message_input_section(
            field_label, message_data[field_key])

    # 保存按钮
    if st.button(button_text):
        save_json_file(updated_values, output_file)
        st.success(success_message)

    return updated_values


def get_default_connect_instance_id():
    """获取默认的Connect实例ID"""
    if os.path.exists('connect.json'):
        json_data = load_json_file('connect.json')
        return json_data['Id']
    return ''


def load_connect_configuration(connect_client, connect_instance_id):
    """加载Connect配置"""
    try:
        # 获取实例信息
        res = connect_client.describe_instance(InstanceId=connect_instance_id)
        connect_filtered = {k: v for k, v in res['Instance'].items() if k in [
            'Id', 'Arn']}
        save_json_file(connect_filtered, 'connect.json')
        connect_instance_arn_val = res['Instance']['Arn']

        # 获取安全配置文件
        res = connect_client.list_security_profiles(
            InstanceId=connect_instance_id)
        security_profile_arn_val = None
        security_profile_id = None

        for item in res['SecurityProfileSummaryList']:
            if item['Name'] == 'Agent':
                security_profile_arn_val = item['Arn']
                security_profile_id = item['Id']
                item_filtered = {k: v for k, v in item.items() if k in [
                    'Id', 'Arn', 'Name']}
                save_json_file(item_filtered, 'security_profile.json')
                break

        # 更新Agent安全配置文件权限
        if security_profile_id:
            additional_permissions = [
                'BasicAgentAccess',
                'OutboundCallAccess',
                'CustomerProfiles.Create',
                'CustomerProfiles.Edit', 
                'CustomerProfiles.View',
                'CustomViews.Access'
            ]
            
            try:
                connect_client.update_security_profile(
                    SecurityProfileId=security_profile_id,
                    InstanceId=connect_instance_id,
                    Permissions=additional_permissions
                )
            except Exception as perm_error:
                st.warning(f"Failed to update security profile permissions: {perm_error}")

        # 保存ARN值到session state
        if 'connect_instance_arn' not in st.session_state:
            st.session_state['connect_instance_arn'] = connect_instance_arn_val
        if 'security_profile_arn' not in st.session_state:
            st.session_state['security_profile_arn'] = security_profile_arn_val
            
        st.success("Connect instance has been loaded")

    except Exception as e:
        st.error('Load Connect instance failed')
        st.error(e)


def save_environment_configuration(tenant_name, tenant_description, tts_voice, tab2_button, tab3_button):
    """保存环境配置"""
    config_data = {
        "tenant_name": tenant_name,
        "tenant_description": tenant_description,
        "tts_voice": tts_voice,
        "deploy_survey_flow": str(tab2_button),
        "deploy_screen_flow": str(tab3_button)
    }

    # 设置环境变量
    for key, value in config_data.items():
        os.environ[key] = value

    # 保存配置文件
    save_json_file(config_data, 'environment_config.json')
   


def monitor_stack_status(cfm_client, stack_name, operation_type):
    """监控CloudFormation堆栈状态"""
    try:
        while True:
            time.sleep(5)
            res = cfm_client.describe_stacks()
            stacks = [i['StackName'] for i in res['Stacks']]

            if operation_type == 'deploy':
                if stack_name in stacks:
                    res = cfm_client.describe_stacks(StackName=stack_name)
                    status = res['Stacks'][0]['StackStatus']
                    if status == 'CREATE_COMPLETE':
                        st.success('Deploy complete!')
                        break
                    elif status in ['CREATE_FAILED', 'ROLLBACK_COMPLETE']:
                        st.error(
                            'Deploy failed, please check CloudFormation event for detailed messages.')
                        break
            elif operation_type == 'destroy':
                if stack_name not in stacks:
                    st.success('Destroy complete!')
                    break
                else:
                    res = cfm_client.describe_stacks(StackName=stack_name)
                    status = res['Stacks'][0]['StackStatus']
                    if status == 'DELETE_FAILED':
                        st.error(
                            'Destroy failed, please check CloudFormation event for detailed messages.')
                        break
    except Exception as e:
        st.error('Failed')


def handle_cdk_operation(operation, command, initial_message, spinner_message):
    """处理CDK操作的通用函数"""
    subprocess.Popen(command)
    st.write(initial_message)
    time.sleep(5)
    with st.spinner(spinner_message):
        cfm_client = boto3.client("cloudformation")
        monitor_stack_status(cfm_client, os.environ["tenant_name"], operation)


# Streamlit UI 代码仅在 Streamlit 运行环境下执行，
# 避免 CDK synth 导入模块时覆盖 CLI 已准备好的配置文件（如 ivr_messages.json）
if get_script_run_ctx() is not None:
    st.set_page_config(
        page_title="Amazon Connect Voice Channel Deployment Tool!", layout="wide")

    # app title
    header = f"Amazon Connect Voice Channel Deployment Tool!"
    st.write(f"<h3 class='main-header'>{header}</h3>", unsafe_allow_html=True)

    # 配置区域
    handle_agent_configuration()
    handle_hours_operation_configuration()

    tab1_button = st.checkbox('Deploy IVR Flow', value=True, disabled=True)
    tab2_button = st.checkbox('Deploy Survey Flow')
    tab3_button = st.checkbox('Deploy Screen Flow')

    tab1, tab2 = st.tabs(
        ["IVR Flow", "Survey Flow"])

    if tab1_button:
        with tab1:
            with st.expander("IVR Configuration", expanded=True):
                # 语言和语音选择
                tts_voice = setup_language_voice_selection()

                # IVR消息配置
                ivr_message_fields = {
                    "welcomeMessage": "IVR welcome message",
                    "openHourMessage": "IVR open hour message",
                    "errorMessage": "IVR error message"
                }

                create_message_configuration(
                    'examples/flows/welcome_message_flow/welcome_messages/ivr_messages_us.json',
                    'ivr_messages.json',
                    ivr_message_fields,
                    'Update IVR Messages',
                    "IVR messages have been updated"
                )

    if tab2_button:
        with tab2:
            with st.expander("Survey Configuration", expanded=True):
                # 调查消息配置
                survey_message_fields = {
                    "surveyMessage": "Survey Message",
                    "surveyMessageFeedback": "Survey Message Feedback"
                }

                create_message_configuration(
                    'examples/flows/survey_message_flow/survey_messages/survey_messages_us.json',
                    'survey_message.json',
                    survey_message_fields,
                    'Update Survey Message',
                    "Survey message have been updated"
                )

    with st.sidebar:
        # connect instance configuration
        st.subheader('Connect Parameters', divider="rainbow")

        # connect configuration
        default_connect_instance_id = get_default_connect_instance_id()
        connect_instance_id = st.text_input(
            'Connect Instance Id', default_connect_instance_id)

        # load env
        if st.button('Load Configuration'):
            connect_client = boto3.client("connect")
            load_connect_configuration(connect_client, connect_instance_id)
        
        # 显示ARN值（从session state获取）
        if 'connect_instance_arn' in st.session_state:
            st.text_input('Amazon Connect instance ARN',
                          value=st.session_state['connect_instance_arn'],
                          disabled=True)
        if 'security_profile_arn' in st.session_state:
            st.text_input('Security profile ARN (Agent Role)',
                          value=st.session_state['security_profile_arn'],
                          disabled=True)

        # tenant configuration
        tenant_name = st.text_input('Tenant Name (Required)')
        tenant_description = st.text_area('Tenant Description (Optional)')
        st.write('*You must click follow button to load and save configuration*')

        # save env
        col1, col2 = st.columns(2)
        with col1:
            btn_Save=st.button('Save')
            if btn_Save:
                save_environment_configuration(
                    tenant_name, tenant_description, tts_voice, tab2_button, tab3_button)
        
        with col2:
            btn_Clear=st.button('Clear')
            if btn_Clear:
                files_to_remove = [
                    'environment_config.json',
                    'hours_of_operation.json',
                    'inbound_flow_updated.json',
                    'inbound_flow.json',
                    'ivr_messages.json',
                    'security_profile.json'
                ]
                
                for file_path in files_to_remove:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        
                # 清除session state中的ARN值
                if 'connect_instance_arn' in st.session_state:
                    del st.session_state['connect_instance_arn']
                if 'security_profile_arn' in st.session_state:
                    del st.session_state['security_profile_arn']
                    
                st.success('Configuration files have been cleared')
                st.experimental_rerun()

        if(btn_Save):
            st.success('Configuration have been saved')
        if(btn_Clear):
            st.success('Configuration have been cleared')
        
        # deploy cdk
        st.subheader('CDK Deployment', divider="rainbow")
        if st.button('Deploy CDK Stack'):
            handle_cdk_operation(
                'deploy',
                ['cdk', 'deploy'],
                'CDK stack initialized...........',
                'Deploying......'
            )

        # destroy cdk
        st.subheader('Clean Resources', divider="rainbow")
        if st.button('Destroy CDK Stack'):
            handle_cdk_operation(
                'destroy',
                ['cdk', 'destroy', '--force'],
                'Destroying CDK stack...........',
                'Destroying......'
            )


def get_config_value(file_path, key, default=''):
    """从配置文件获取值的通用函数"""
    if os.path.exists(file_path):
        json_data = load_json_file(file_path)
        return json_data.get(key, default)
    return default


def load_flows():
    """清理未使用的文件"""
    os_data = load_json_file('environment_config.json')

    create_inbound_flow(
        True, eval(os_data['deploy_survey_flow']), eval(os_data['deploy_screen_flow']))

def get_arn_prefix(arn):
    return arn.rsplit(':', 2)[0]

def create_screenpop_contact_flow(self, file_path, output_file, flow_name, description, connect_instance_arn, formatted_now):
    """创建联系流程的通用函数"""
    if os.path.exists(file_path):
        flow_data = load_json_file(file_path)
        flow_content = json.dumps(flow_data)

        # 替换消息内容
        replacements = {
            "arn_prefix": get_arn_prefix(connect_instance_arn),
            "contact_queue_name": f"{os.environ['tenant_name']} Queue"
        }

        for old_text, new_text in replacements.items():
            flow_content = flow_content.replace(old_text, new_text)
            
        with open(output_file, 'w') as f:
            f.write(flow_content)

        return connect.CfnContactFlow(
            self,
            f"CfnContactFlow{flow_name}{formatted_now}",
            content=flow_content,
            instance_arn=connect_instance_arn,
            description=description,
            name=f"{os.environ['tenant_name']} {flow_name}",
            type="CONTACT_FLOW"
        )
    return None


def create_survey_contact_flow(self, connect_instance_arn, formatted_now):
    """创建调查联系流程"""
    if os.path.exists('survey_message.json') and os.path.exists('survey_message_flow.json'):
        message_data = load_json_file('survey_message.json')
        os.environ["survey_message"] = message_data['surveyMessage']
        os.environ["survey_message_feedback"] = message_data['surveyMessageFeedback']

        flow_data = load_json_file('survey_message_flow.json')
        flow_content = json.dumps(flow_data)

        # 替换消息内容
        replacements = {
            "Joanna": os.environ["tts_voice"],
            "survey_message": os.environ["survey_message"],
            "survey_feedback": os.environ["survey_message_feedback"]
        }

        for old_text, new_text in replacements.items():
            flow_content = flow_content.replace(old_text, new_text)

        with open('connect_flow_survey_updated.json', 'w') as f:
            f.write(flow_content)

        return connect.CfnContactFlow(
            self,
            f"CfnContactFlowSurvey{formatted_now}",
            content=flow_content,
            instance_arn=connect_instance_arn,
            description="Survey flow created using cfn",
            name=f"{os.environ['tenant_name']} Survey Flow",
            type="CONTACT_FLOW"
        )
    return None


def create_ivr_contact_flow(cfn_queue, cfn_contact_flow_screenpop=None, cfn_contact_flow_survey=None):
    """创建IVR联系流程"""
    flow_data = load_json_file('inbound_flow.json')
    flow_content = json.dumps(flow_data)

    # 基本替换
    basic_replacements = {
        "contact_queue_name": f"{os.environ['tenant_name']} Queue",
        "contact_name": os.environ["tenant_name"],
        "Joanna": os.environ["tts_voice"],
        "welcome-message": os.environ["ivr_welcome_message"],
        "open-hour-message": os.environ["ivr_open_hour_message"],
        "error-message": os.environ["ivr_error_message"],
        "queue-arn": cfn_queue.attr_queue_arn
    }

    # 执行基本替换
    for old_text, new_text in basic_replacements.items():
        flow_content = flow_content.replace(old_text, new_text)

    # 条件替换
    if cfn_contact_flow_screenpop and os.path.exists('screenpop_message_flow.json'):
        screenpop_replacements = {
            "contact_screenpop_flow_name": cfn_contact_flow_screenpop.name,
            "contact_screenpop_flow_id": cfn_contact_flow_screenpop.attr_contact_flow_arn
        }
        for old_text, new_text in screenpop_replacements.items():
            flow_content = flow_content.replace(old_text, new_text)

    if cfn_contact_flow_survey and os.path.exists('survey_message.json'):
        survey_replacements = {
            "contact_survey_flow_name": cfn_contact_flow_survey.name,
            "contact_survey_flow_id": cfn_contact_flow_survey.attr_contact_flow_arn
        }
        for old_text, new_text in survey_replacements.items():
            flow_content = flow_content.replace(old_text, new_text)

    with open('inbound_flow_updated.json', 'w') as f:
        f.write(flow_content)

    return flow_content


class ConnectCdkVoiceChannelStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        try:
            # 初始化配置
            config = self._initialize_config()

            # 创建核心资源
            hours_of_operation = self._create_hours_of_operation(config)
            queue = self._create_queue(config, hours_of_operation)

            # 创建联系流程
            contact_flows = self._create_contact_flows(config)
            ivr_flow = self._create_ivr_flow(config, queue, contact_flows)

            # 创建路由配置文件
            routing_profile = self._create_routing_profile(config, queue)

            # 创建代理用户
            self._create_agents(config, routing_profile)

        except Exception as e:
            print(f"Error initializing ConnectCdkVoiceChannelStack: {e}")
            raise

    def _initialize_config(self):
        """初始化配置参数"""
        config = {
            'connect_instance_arn': get_config_value('connect.json', 'Arn'),
            'security_profile_arn': get_config_value('security_profile.json', 'Arn'),
            'timestamp': datetime.now().strftime("%Y%m%d%H%M%S"),
            'tenant_name': os.environ.get('tenant_name', 'DefaultTenant')
        }

        if not config['connect_instance_arn']:
            raise ValueError("Connect instance ARN not found in configuration")

        load_flows()
        return config

    def _create_hours_of_operation(self, config):
        """创建营业时间配置"""
        if not os.path.exists('hours_of_operation.json'):
            copy_file('examples/hoursofoperation/hours_of_operation_hk.json',
                      'hours_of_operation.json')

        hop_data = load_json_file('hours_of_operation.json')
        hop_df = pd.DataFrame(hop_data['timeslices'])

        hop_props = [
            connect.CfnHoursOfOperation.HoursOfOperationConfigProperty(
                day=row['day'],
                end_time=connect.CfnHoursOfOperation.HoursOfOperationTimeSliceProperty(
                    hours=row['endH'], minutes=row['endM']
                ),
                start_time=connect.CfnHoursOfOperation.HoursOfOperationTimeSliceProperty(
                    hours=row['startH'], minutes=row['startM']
                )
            ) for _, row in hop_df.iterrows()
        ]

        return connect.CfnHoursOfOperation(
            self, f"CfnHoursOfOperation{config['timestamp']}",
            config=hop_props,
            instance_arn=config['connect_instance_arn'],
            name=f"{config['tenant_name']} {hop_data['name']}",
            time_zone=hop_data['timeZone'],
            description=hop_data['description']
        )

    def _create_queue(self, config, hours_of_operation):
        """创建队列"""
        return connect.CfnQueue(
            self, f"CfnQueue{config['timestamp']}",
            hours_of_operation_arn=hours_of_operation.attr_hours_of_operation_arn,
            instance_arn=config['connect_instance_arn'],
            description="Queue created using cfn",
            name=f"{config['tenant_name']} Queue"
        )

    def _create_contact_flows(self, config):
        """创建联系流程"""
        flows = {}

        # ScreenPop流程
        flows['screenpop'] = create_screenpop_contact_flow(
            self, 'screenpop_message_flow.json', 'connect_flow_screenpop_updated.json',
            'ScreenPop Flow', 'ScreenPop flow created using cfn',
            config['connect_instance_arn'], config['timestamp']
        )

        # Survey流程
        flows['survey'] = create_survey_contact_flow(
            self, config['connect_instance_arn'], config['timestamp']
        )

        return flows

    def _create_ivr_flow(self, config, queue, contact_flows):
        """创建IVR流程"""
        # 加载IVR消息
        if os.path.exists('ivr_messages.json'):
            message_data = load_json_file('ivr_messages.json')
            for key, env_key in [('welcomeMessage', 'ivr_welcome_message'),
                                 ('openHourMessage', 'ivr_open_hour_message'),
                                 ('errorMessage', 'ivr_error_message')]:
                os.environ[env_key] = message_data.get(key, '')

        flow_content = create_ivr_contact_flow(
            queue, contact_flows.get('screenpop'), contact_flows.get('survey')
        )

        return connect.CfnContactFlow(
            self, f"CfnContactFlowIVR{config['timestamp']}",
            content=flow_content,
            instance_arn=config['connect_instance_arn'],
            description="IVR flow created using cfn",
            name=f"{config['tenant_name']} Inbound Flow",
            type="CONTACT_FLOW"
        )

    def _create_routing_profile(self, config, queue):
        """创建路由配置文件"""
        return connect.CfnRoutingProfile(
            self, f"CfnRoutingProfile{config['timestamp']}",
            default_outbound_queue_arn=queue.attr_queue_arn,
            description="Routing profile created using cfn",
            instance_arn=config['connect_instance_arn'],
            media_concurrencies=[
                connect.CfnRoutingProfile.MediaConcurrencyProperty(
                    channel="VOICE", concurrency=1),
                connect.CfnRoutingProfile.MediaConcurrencyProperty(
                    channel="CHAT", concurrency=1)
            ],
            queue_configs=[connect.CfnRoutingProfile.RoutingProfileQueueConfigProperty(
                delay=0, priority=1,
                queue_reference=connect.CfnRoutingProfile.RoutingProfileQueueReferenceProperty(
                    channel="VOICE", queue_arn=queue.attr_queue_arn
                )
            )],
            name=f"{config['tenant_name']} Routing Profile"
        )

    def _create_agents(self, config, routing_profile):
        """创建代理用户"""
        if not os.path.exists("agents.csv"):
            return

        try:
            agent_df = pd.read_csv("agents.csv")
            for index, row in agent_df.iterrows():
                connect.CfnUser(
                    self, f"CfnUser{config['timestamp']}{index}",
                    instance_arn=config['connect_instance_arn'],
                    phone_config=connect.CfnUser.UserPhoneConfigProperty(
                        phone_type="SOFT_PHONE", auto_accept=False
                    ),
                    routing_profile_arn=routing_profile.attr_routing_profile_arn,
                    security_profile_arns=[config['security_profile_arn']],
                    username=row["Username"],
                    identity_info=connect.CfnUser.UserIdentityInfoProperty(
                        first_name=row["FirstName"], last_name=row["LastName"]
                    ),
                    password=row["Password"]
                )
        except Exception as e:
            print(f"Error creating agents: {e}")
