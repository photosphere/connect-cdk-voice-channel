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
import pandas as pd
import boto3
import time
import json
import shutil
from datetime import datetime

# 工具函数
def copy_file(source, destination):
    """复制文件的通用函数"""
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

def create_inbound_flow():
    """创建入站流程文件"""
    # 复制基础文件
    copy_file('examples/agents/agents.csv', 'agents.csv')
    copy_file('examples/hoursofoperation/hours_of_operation_us.json', 'hours_of_operation.json')
    
    # 根据选择的功能复制相应的流程文件
    flow_configs = [
        (tab1_button, 'examples/flows/welcome_message_flow/welcome_message_flow.json', 'inbound_flow.json'),
        (tab1_button and tab2_button, 'examples/flows/ivr_survey_flow.json', 'inbound_flow.json'),
        (tab1_button and tab3_button, 'examples/flows/ivr_screenpop_flow.json', 'inbound_flow.json'),
        (tab1_button and tab2_button and tab3_button, 'examples/flows/ivr_survey_screenpop_flow.json', 'inbound_flow.json')
    ]
    
    additional_files = [
        (tab1_button and tab2_button, 'examples/flows/survey_message_flow/survey_message_flow.json', 'survey_message_flow.json'),
        (tab1_button and tab3_button, 'examples/flows/screenpop_message_flow/screenpop_message_flow.json', 'screenpop_message_flow.json'),
        (tab1_button and tab2_button and tab3_button, 'examples/flows/survey_message_flow/survey_message_flow.json', 'survey_message_flow.json'),
        (tab1_button and tab2_button and tab3_button, 'examples/flows/screenpop_message_flow/screenpop_message_flow.json', 'screenpop_message_flow.json')
    ]
    
    # 复制主流程文件
    for condition, source, dest in flow_configs:
        if condition:
            copy_file(source, dest)
            break
    
    # 复制附加文件
    for condition, source, dest in additional_files:
        if condition:
            copy_file(source, dest)

st.set_page_config(
    page_title="Amazon Connect Voice Channel Deployment Tool!", layout="wide")

# app title
header = f"Amazon Connect Voice Channel Deployment Tool!"
st.write(f"<h3 class='main-header'>{header}</h3>", unsafe_allow_html=True)

tab1_button = st.checkbox('Deploy IVR Flow', value=True, disabled=True)
tab2_button = st.checkbox('Deploy Survey Flow')
tab3_button = st.checkbox('Deploy Screen Flow')


tab1, tab2 = st.tabs(
    ["IVR Flow", "Survey Flow"])
 
create_inbound_flow()
 
def setup_language_voice_selection():
    """设置语言和语音选择"""
    lan_df = pd.read_csv('examples/languages/languages_neural.csv')
    lan_vals = lan_df.iloc[:, 0].unique()
    default_language_index = 13  # English language as default
    lan_selected = st.selectbox('IVR languages', lan_vals, index=default_language_index)
    
    lan_df['VoiceDisplay'] = lan_df['Voice'] + ',' + lan_df['Gender']
    lan_filter = lan_df['LanguageName'] == lan_selected
    voice_vals = lan_df.loc[lan_filter, 'VoiceDisplay'].str.replace("*", "")
    default_voice_index = 0  # Danielle voice as default
    voice_selected = st.selectbox('IVR language voices', voice_vals, index=default_voice_index)
    
    return voice_selected.split(",")[0]

def create_message_configuration(file_path, output_file, message_fields, button_text, success_message):
    """创建消息配置区域的通用函数"""
    message_data = load_json_file(file_path)
    save_json_file(message_data, output_file)
    
    # 创建输入字段
    updated_values = {}
    for field_key, field_label in message_fields.items():
        updated_values[field_key] = create_message_input_section(field_label, message_data[field_key])
    
    # 保存按钮
    if st.button(button_text):
        save_json_file(updated_values, output_file)
        st.success(success_message)
    
    return updated_values

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
    
def handle_agent_configuration():
    """处理代理配置"""
    with st.expander("Agent Configuration", expanded=True):
        uploaded_file = create_file_uploader_section("Agents", "csv")
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            st.write(df)
            df.to_csv("agents.csv", index=False)

def handle_hours_operation_configuration():
    """处理营业时间配置"""
    with st.expander("Hours of Operation Configuration", expanded=True):
        uploaded_file = create_file_uploader_section("Operation", "json")
        if uploaded_file is not None:
            hop_data = json.load(uploaded_file)
            st.write("Timezone:", hop_data['timeZone'])
            hop_df = pd.DataFrame(hop_data['timeslices'])
            st.write(hop_df)
            save_json_file(hop_data, 'hours_of_operation.json')

# 配置区域
handle_agent_configuration()
handle_hours_operation_configuration()
            
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
        connect_filtered = {k: v for k, v in res['Instance'].items() if k in ['Id', 'Arn']}
        save_json_file(connect_filtered, 'connect.json')
        connect_instance_arn_val = res['Instance']['Arn']
        
        # 获取安全配置文件
        res = connect_client.list_security_profiles(InstanceId=connect_instance_id)
        security_profile_arn_val = None
        
        for item in res['SecurityProfileSummaryList']:
            if item['Name'] == 'Agent':
                security_profile_arn_val = item['Arn']
                item_filtered = {k: v for k, v in item.items() if k in ['Id', 'Arn', 'Name']}
                save_json_file(item_filtered, 'security_profile.json')
                break
        
        # 显示配置信息
        st.text_input('Amazon Connect instance ARN', value=connect_instance_arn_val)
        st.text_input('Security profile ARN (Agent Role)', value=security_profile_arn_val)
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
    st.success("ENV has been set")

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
                        st.error('Deploy failed, please check CloudFormation event for detailed messages.')
                        break
            elif operation_type == 'destroy':
                if stack_name not in stacks:
                    st.success('Destroy complete!')
                    break
                else:
                    res = cfm_client.describe_stacks(StackName=stack_name)
                    status = res['Stacks'][0]['StackStatus']
                    if status == 'DELETE_FAILED':
                        st.error('Destroy failed, please check CloudFormation event for detailed messages.')
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

with st.sidebar:
    # connect instance configuration
    st.subheader('Connect Parameters', divider="rainbow")

    # connect configuration
    default_connect_instance_id = get_default_connect_instance_id()
    connect_instance_id = st.text_input('Connect Instance Id', default_connect_instance_id)

    # load env
    if st.button('Load Configuration'):
        connect_client = boto3.client("connect")
        load_connect_configuration(connect_client, connect_instance_id)

    # tenant configuration
    tenant_name = st.text_input('Tenant Name (Required)')
    tenant_description = st.text_area('Tenant Description (Optional)')
    st.write('*You must click follow button to load and save configuration*')

    # save env
    if st.button('Save Configuration'):
        save_environment_configuration(tenant_name, tenant_description, tts_voice, tab2_button, tab3_button)

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

def cleanup_unused_files():
    """清理未使用的文件"""
    os_data = load_json_file('environment_config.json')
    
    cleanup_rules = [
        (os_data['deploy_survey_flow'] == 'False', ['survey_message_flow.json', 'survey_message.json']),
        (os_data['deploy_screen_flow'] == 'False', ['screenpop_message_flow.json'])
    ]
    
    for condition, files in cleanup_rules:
        if condition:
            for file_path in files:
                if os.path.exists(file_path):
                    os.remove(file_path)

def create_contact_flow(self, file_path, output_file, flow_name, description, connect_instance_arn, formatted_now):
    """创建联系流程的通用函数"""
    if os.path.exists(file_path):
        flow_data = load_json_file(file_path)
        flow_content = json.dumps(flow_data)
        
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
    if os.path.exists('survey_message.json'):
        message_data = load_json_file('survey_message.json')
        os.environ["survey_message"] = message_data['surveyMessage']
        os.environ["survey_message_feedback"] = message_data['surveyMessageFeedback']
        
        flow_data = load_json_file('survey_message_flow.json')
        flow_content = json.dumps(flow_data)
        
        # 替换消息内容
        replacements = {
            "survey_message": os.environ["survey_message"],
            "survey_message_feedback": os.environ["survey_message_feedback"]
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
        flow_content = flow_content.replace(
            "contact_screenpop_flow_name", cfn_contact_flow_screenpop.name
        )
    
    if cfn_contact_flow_survey and os.path.exists('survey_message.json'):
        survey_replacements = {
            "contact_survey_flow_name": cfn_contact_flow_survey.name,
            "contact_survey_flow_id": cfn_contact_flow_survey.attr_contact_flow_arn
        }
        for old_text, new_text in survey_replacements.items():
            flow_content = flow_content.replace(old_text, new_text)
    
    with open('connect_flow_ivr_updated.json', 'w') as f:
        f.write(flow_content)
    
    return flow_content

class ConnectCdkVoiceChannelStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # parameter
        connect_instance_arn = get_config_value('connect.json', 'Arn')
        security_profile_arn = get_config_value('security_profile.json', 'Arn')

        now = datetime.now()
        formatted_now = now.strftime("%Y%m%d%H%M%S")

        cleanup_unused_files()
                
        
        # load hours of operation
        hop_data = load_json_file('hours_of_operation.json')
        hop_name = hop_data['name']
        hop_desc = hop_data['description']
        hop_tz = hop_data['timeZone']
        hop_df = pd.DataFrame(hop_data['timeslices'])

        # define open hours
        hop_props = []
        for index, row in hop_df.iterrows():
            hop_prop = connect.CfnHoursOfOperation.HoursOfOperationConfigProperty(
                day=row['day'],
                end_time=connect.CfnHoursOfOperation.HoursOfOperationTimeSliceProperty(
                    hours=row['endH'],
                    minutes=row['endM']
                ),
                start_time=connect.CfnHoursOfOperation.HoursOfOperationTimeSliceProperty(
                    hours=row['startH'],
                    minutes=row['startM']
                )
            )
            hop_props.append(hop_prop)

        cfn_hop = connect.CfnHoursOfOperation(self, "CfnHoursOfOperation"+formatted_now,
                                              config=hop_props,
                                              instance_arn=connect_instance_arn,
                                              name=os.environ["tenant_name"] +
                                              " "+hop_name,
                                              time_zone=hop_tz,
                                              description=hop_desc)

        # define queue
        cfn_queue = connect.CfnQueue(self, "CfnQueue"+formatted_now,
                                     hours_of_operation_arn=cfn_hop.attr_hours_of_operation_arn,
                                     instance_arn=connect_instance_arn,
                                     description="Queue created using cfn",
                                     name=os.environ["tenant_name"]+" Queue"
                                     )
        
        # load contact flow - ScreenPop
        cfn_contact_flow_screenpop = create_contact_flow(
            self,
            'screenpop_message_flow.json',
            'connect_flow_screenpop_updated.json',
            'ScreenPop Flow',
            'ScreenPop flow created using cfn',
            connect_instance_arn,
            formatted_now
        )

        # load contact flow - Survey
        cfn_contact_flow_survey = create_survey_contact_flow(self, connect_instance_arn, formatted_now)
            
        # define IVR
        message_data = load_json_file('ivr_messages.json')
        os.environ["ivr_welcome_message"] = message_data['welcomeMessage']
        os.environ["ivr_open_hour_message"] = message_data['openHourMessage']
        os.environ["ivr_error_message"] = message_data['errorMessage']
        
        # load contact flow - IVR
        flow_content = create_ivr_contact_flow(cfn_queue, cfn_contact_flow_screenpop, cfn_contact_flow_survey)

        cfn_contact_flow_ivr = connect.CfnContactFlow(self, "CfnContactFlowIVR"+formatted_now,
                                                      content=flow_content,
                                                      instance_arn=connect_instance_arn,
                                                      description="IVR flow created using cfn",
                                                      name=os.environ["tenant_name"] +
                                                      " Inbound Flow",
                                                      type="CONTACT_FLOW"
                                                      )



            
        # define routing profile
        cfn_routing_profile = connect.CfnRoutingProfile(self, "CfnRoutingProfile"+formatted_now,
                                                        default_outbound_queue_arn=cfn_queue.attr_queue_arn,
                                                        description="Routing profile created using cfn",
                                                        instance_arn=connect_instance_arn,
                                                        media_concurrencies=[
                                                            connect.CfnRoutingProfile.MediaConcurrencyProperty(
                                                                channel="VOICE",
                                                                concurrency=1,),
                                                            connect.CfnRoutingProfile.MediaConcurrencyProperty(
                                                                channel="CHAT",
                                                                concurrency=1,)
                                                        ],
                                                        queue_configs=[connect.CfnRoutingProfile.RoutingProfileQueueConfigProperty(
                                                            delay=0,
                                                            priority=1,
                                                            queue_reference=connect.CfnRoutingProfile.RoutingProfileQueueReferenceProperty(
                                                                channel="VOICE",
                                                                queue_arn=cfn_queue.attr_queue_arn
                                                            )
                                                        )],
                                                        name=os.environ["tenant_name"] +
                                                        " Routing Profile"
                                                        )

        # define agents
        # load agents
        agent_df = pd.read_csv("agents.csv")
        for index, row in agent_df.iterrows():
            cfn_user = connect.CfnUser(self, "CfnUser"+formatted_now+str(index),
                                       instance_arn=connect_instance_arn,
                                       phone_config=connect.CfnUser.UserPhoneConfigProperty(
                                           phone_type="SOFT_PHONE",

                                           # the properties below are optional
                                           auto_accept=False),
                                       routing_profile_arn=cfn_routing_profile.attr_routing_profile_arn,
                                       security_profile_arns=[
                                           security_profile_arn],
                                       username=row["Username"],

                                       # the properties below are optional
                                       identity_info=connect.CfnUser.UserIdentityInfoProperty(
                                           first_name=row["FirstName"],
                                           last_name=row["LastName"],
            ),
                password="Aa12345678."
            )
