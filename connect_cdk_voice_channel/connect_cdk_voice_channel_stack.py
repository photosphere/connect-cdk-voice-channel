from aws_cdk import Stack
from constructs import Construct
from aws_cdk import aws_connect as connect
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_iam as iam
import os
import csv
import json
import shutil

# 工具函数


def str_to_bool(value):
    """将配置文件中的字符串（"True"/"False"）安全地转换为布尔值。

    替代直接使用 eval()，避免执行任意代码并对异常输入更健壮。
    """
    return str(value).strip().lower() in ("true", "1", "yes")


def copy_file(source, destination):
    """复制文件的通用函数"""
    if not os.path.exists(destination):
        shutil.copyfile(source, destination)


def load_json_file(file_path):
    """加载JSON文件的通用函数"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


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
            copy_file(source, dest)
            break

    # 复制附加文件
    for condition, source, dest in additional_files:
        if condition:
            copy_file(source, dest)


def get_config_value(file_path, key, default=''):
    """从配置文件获取值的通用函数"""
    if os.path.exists(file_path):
        json_data = load_json_file(file_path)
        return json_data.get(key, default)
    return default


def load_flows():
    """根据环境配置准备入站流程文件"""
    os_data = load_json_file('environment_config.json')

    create_inbound_flow(
        True, str_to_bool(os_data['deploy_survey_flow']), str_to_bool(os_data['deploy_screen_flow']))


def get_arn_prefix(arn):
    return arn.rsplit(':', 2)[0]


def create_screenpop_contact_flow(self, file_path, output_file, flow_name, description, connect_instance_arn, get_agent_name_lambda_arn=None):
    """创建联系流程的通用函数"""
    if os.path.exists(file_path):
        flow_data = load_json_file(file_path)

        # 注入弹屏翻译到 UpdateContactAttributes (System attributes) action
        if os.path.exists('screenpop_translations.json'):
            translations = load_json_file('screenpop_translations.json')
            for action in flow_data.get('Actions', []):
                if action.get('Identifier') == 'System attributes' and action.get('Type') == 'UpdateContactAttributes':
                    action['Parameters']['Attributes'].update(translations)
                    break

        flow_content = json.dumps(flow_data)

        # 替换消息内容
        replacements = {
            "arn_prefix": get_arn_prefix(connect_instance_arn),
            "contact_queue_name": f"{os.environ['tenant_name']} Queue",
            # 弹屏中显示的语言使用部署时（deploy_cli.py）选择的语言，
            # 而不是未被赋值的 $.LanguageCode 系统属性。
            "screenpop_language": os.environ.get("selected_language", "")
        }

        # 替换 GetAgentNameByAgentId Lambda 的 ARN 占位符与显示名称。
        # 实际部署的 Lambda 名称为 {tenant_name}-GetAgentNameByAgentId，
        # 因此流程中必须引用带租户前缀的真实 ARN 与名称，否则调用会失败。
        if get_agent_name_lambda_arn is not None:
            replacements["get_agent_name_lambda_arn"] = get_agent_name_lambda_arn
            replacements['"displayName": "GetAgentNameByAgentId"'] = \
                f'"displayName": "{os.environ["tenant_name"]}-GetAgentNameByAgentId"'

        for old_text, new_text in replacements.items():
            flow_content = flow_content.replace(old_text, new_text)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(flow_content)

        return connect.CfnContactFlow(
            self,
            f"CfnContactFlow{flow_name}",
            content=flow_content,
            instance_arn=connect_instance_arn,
            description=description,
            name=f"{os.environ['tenant_name']} {flow_name}",
            type="CONTACT_FLOW"
        )
    return None


def create_survey_contact_flow(self, connect_instance_arn):
    """创建调查联系流程"""
    if os.path.exists('survey_message.json') and os.path.exists('survey_message_flow.json'):
        message_data = load_json_file('survey_message.json')
        os.environ["survey_message"] = message_data['surveyMessage']
        os.environ["survey_message_feedback"] = message_data['surveyMessageFeedback']

        flow_data = load_json_file('survey_message_flow.json')
        flow_content = json.dumps(flow_data)

        # 满意度评分的本地化文案（写入 AgentSurveyResult 属性，供主管在 admin 页面搜索）。
        # 若缺失则回退到英文默认值，保证流程占位符一定被替换掉。
        results = message_data.get('results', {})

        # 替换消息内容
        replacements = {
            "Joanna": os.environ["tts_voice"],
            "survey_message": os.environ["survey_message"],
            "survey_feedback": os.environ["survey_message_feedback"],
            "survey_result_1": results.get("1", "VerySatisfied"),
            "survey_result_2": results.get("2", "Satisfied"),
            "survey_result_3": results.get("3", "Unsatisfied"),
            "survey_result_na": results.get("-1", "N/A"),
        }

        for old_text, new_text in replacements.items():
            flow_content = flow_content.replace(old_text, new_text)

        with open('connect_flow_survey_updated.json', 'w', encoding='utf-8') as f:
            f.write(flow_content)

        return connect.CfnContactFlow(
            self,
            "CfnContactFlowSurvey",
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

    with open('inbound_flow_updated.json', 'w', encoding='utf-8') as f:
        f.write(flow_content)

    return flow_content


class ConnectCdkVoiceChannelStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        try:
            # 初始化配置
            config = self._initialize_config()

            # 创建 Lambda 函数（GetAgentNameByAgentId），使用源码目录直接部署
            agent_name_lambda = self._create_get_agent_name_lambda(config)

            # 创建核心资源
            hours_of_operation = self._create_hours_of_operation(config)
            queue = self._create_queue(config, hours_of_operation)

            # 创建联系流程
            contact_flows = self._create_contact_flows(config, agent_name_lambda)
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
            'tenant_name': os.environ.get('tenant_name', 'DefaultTenant')
        }

        if not config['connect_instance_arn']:
            raise ValueError("Connect instance ARN not found in configuration")

        load_flows()
        return config

    def _create_get_agent_name_lambda(self, config):
        """创建 GetAgentNameByAgentId Lambda 函数。

        不再从预打包的 zip 文件导入，而是直接引用 lambda/GetAgentNameByAgentId/
        源码目录，由 CDK 在 synth 阶段自动打包部署（等价于源码直接创建）。
        """
        # Lambda 执行角色，授予调用 Connect describe_user 的权限
        lambda_role = iam.Role(
            self, "GetAgentNameLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["connect:DescribeUser"],
                resources=["*"]
            )
        )

        lambda_source_dir = os.path.join(
            os.path.dirname(__file__), "..", "lambda", "GetAgentNameByAgentId")

        agent_name_fn = _lambda.Function(
            self, "GetAgentNameByAgentId",
            function_name=f"{config['tenant_name']}-GetAgentNameByAgentId",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset(lambda_source_dir),
            role=lambda_role,
            description="Resolve agent full name by agent id for Amazon Connect flows"
        )
        agent_name_fn.grant_invoke(
            iam.ServicePrincipal("connect.amazonaws.com"))

        # 关联到 Amazon Connect 实例，使联系流可以调用该 Lambda
        connect.CfnIntegrationAssociation(
            self, "GetAgentNameLambdaAssociation",
            instance_id=config['connect_instance_arn'],
            integration_type="LAMBDA_FUNCTION",
            integration_arn=agent_name_fn.function_arn
        )

        return agent_name_fn

    def _create_hours_of_operation(self, config):
        """创建营业时间配置"""
        if not os.path.exists('hours_of_operation.json'):
            copy_file('examples/hoursofoperation/hours_of_operation_hk.json',
                      'hours_of_operation.json')

        hop_data = load_json_file('hours_of_operation.json')

        hop_props = [
            connect.CfnHoursOfOperation.HoursOfOperationConfigProperty(
                day=row['day'],
                end_time=connect.CfnHoursOfOperation.HoursOfOperationTimeSliceProperty(
                    hours=row['endH'], minutes=row['endM']
                ),
                start_time=connect.CfnHoursOfOperation.HoursOfOperationTimeSliceProperty(
                    hours=row['startH'], minutes=row['startM']
                )
            ) for row in hop_data['timeslices']
        ]

        return connect.CfnHoursOfOperation(
            self, "CfnHoursOfOperation",
            config=hop_props,
            instance_arn=config['connect_instance_arn'],
            name=f"{config['tenant_name']} {hop_data['name']}",
            time_zone=hop_data['timeZone'],
            description=hop_data['description']
        )

    def _create_queue(self, config, hours_of_operation):
        """创建队列"""
        return connect.CfnQueue(
            self, "CfnQueue",
            hours_of_operation_arn=hours_of_operation.attr_hours_of_operation_arn,
            instance_arn=config['connect_instance_arn'],
            description="Queue created using cfn",
            name=f"{config['tenant_name']} Queue"
        )

    def _create_contact_flows(self, config, agent_name_lambda=None):
        """创建联系流程"""
        flows = {}

        # ScreenPop流程
        flows['screenpop'] = create_screenpop_contact_flow(
            self, 'screenpop_message_flow.json', 'connect_flow_screenpop_updated.json',
            'ScreenPop Flow', 'ScreenPop flow created using cfn',
            config['connect_instance_arn'],
            agent_name_lambda.function_arn if agent_name_lambda is not None else None
        )

        # Survey流程
        flows['survey'] = create_survey_contact_flow(
            self, config['connect_instance_arn']
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
            self, "CfnContactFlowIVR",
            content=flow_content,
            instance_arn=config['connect_instance_arn'],
            description="IVR flow created using cfn",
            name=f"{config['tenant_name']} Inbound Flow",
            type="CONTACT_FLOW"
        )

    def _create_routing_profile(self, config, queue):
        """创建路由配置文件"""
        return connect.CfnRoutingProfile(
            self, "CfnRoutingProfile",
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
            with open("agents.csv", "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for index, row in enumerate(reader):
                    connect.CfnUser(
                        self, f"CfnUser{index}",
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
