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
from datetime import datetime


st.set_page_config(
    page_title="Amazon Connect Voice Channel Deployment Tool!", layout="wide")

# app title
header = f"Amazon Connect Voice Channel Deployment Tool!"
st.write(f"<h3 class='main-header'>{header}</h3>", unsafe_allow_html=True)

# add connect agents
with st.expander("Agent Configuration", expanded=True):
    uploaded_file = st.file_uploader(
        "Choose a CSV file of Agents", accept_multiple_files=False, type="csv")
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.write(df)
        df.to_csv("agents.csv", index=False)


# add hours of Operation
with st.expander("Hours of Operation Configuration", expanded=True):
    uploaded_file = st.file_uploader(
        "Choose a Json file of Operation", accept_multiple_files=False, type="json")
    if uploaded_file is not None:
        hop_data = json.load(uploaded_file)
        st.write("Timezone:", hop_data['timeZone'])
        hop_df = pd.DataFrame(hop_data['timeslices'])
        st.write(hop_df)
        with open('hours_of_operation.json', 'w') as f:
            json.dump(hop_data, f)

tab1_button = st.checkbox('Deploy IVR Flow', value=True, disabled=True)
tab2_button = st.checkbox('Deploy Survey Flow')
tab3_button = st.checkbox('Deploy Screen Flow')

tab1, tab2, tab3 = st.tabs(
    ["IVR Flow", "Survey Flow", "Screen Flow"])

if tab1_button:
    with tab1:
        # ivr configuration
        with st.expander("IVR Configuration", expanded=True):

            # language of polly
            lan_df = pd.read_csv('examples/languages/languages_neural.csv')
            lan_vals = lan_df.iloc[:, 0].unique()
            lan_selected = st.selectbox('IVR languages', (lan_vals))

            lan_df['VoiceDisplay'] = lan_df['Voice'] + ','+lan_df['Gender']
            lan_filter = lan_df['LanguageName'] == lan_selected
            voice_vals = lan_df.loc[lan_filter,
                                    'VoiceDisplay'].str.replace("*", "")
            voice_selected = st.selectbox('IVR language voices', (voice_vals))
            tts_voice = voice_selected.split(",")[0]

            uploaded_file = st.file_uploader(
                "Choose a Json file of IVR Messages", accept_multiple_files=False, type="json")
            if uploaded_file is not None:
                message_data = json.load(uploaded_file)
                # welcome message of IVR
                ivr_welcome_message = st.text_area(
                    'IVR welcome message', value=message_data['welcomeMessage'])

                # open hour message of IVR
                ivr_open_hour_message = st.text_area(
                    'IVR open hour message', value=message_data['openHourMessage'])

                # error message of IVR
                ivr_error_message = st.text_area(
                    'IVR error message', value=message_data['errorMessage'])

                with open('ivr_messages.json', 'w') as f:
                    json.dump(message_data, f)

                # update
                save_button = st.button('Update IVR Messages')
                if save_button:
                    updated_message_data = {
                        "welcomeMessage": ivr_welcome_message,
                        "openHourMessage": ivr_open_hour_message,
                        "errorMessage": ivr_error_message
                    }

                    with open('ivr_messages.json', 'w') as f:
                        json.dump(updated_message_data, f)

                    st.success("IVR messages have been updated")


if tab2_button:
    with tab2:
        with st.expander("Survey Configuration", expanded=True):
            uploaded_survey_file = st.file_uploader(
                "Choose a Json file of Survey Options", accept_multiple_files=False, type="json")
            if uploaded_survey_file is not None:
                survey_data = json.load(uploaded_survey_file)

                with open('survey_message.json', 'w') as f:
                    json.dump(survey_data, f)

                survey_message = st.text_area(
                    'Survey Message', value=survey_data['surveyMessage'])
                survey_message_feedback = st.text_area(
                    'Survey Message Feedback', value=survey_data['surveyMessageFeedback'])

                save_button = st.button('Update Survey Message')
                if save_button:
                    updated_survey_data = {
                        "surveyMessage": survey_message,
                        "surveyMessageFeedback": survey_message_feedback
                    }

                    with open('survey_message.json', 'w') as f:
                        json.dump(updated_survey_data, f)

                    st.success("Survey message have been updated")


if tab3_button:
    with tab3:
        with st.expander("Screen Configuration", expanded=True):
            uploaded_screen_file = st.file_uploader(
                "Choose a Json file of Screen Fields", accept_multiple_files=False, type="json")

with st.sidebar:
    # connect instance configuration
    st.subheader('Connect Parameters', divider="rainbow")

    # connect configuration
    connect_instance_id = st.text_input('Connect Instance Id')

    # load env
    if st.button('Load Configuration'):
        connect_client = boto3.client("connect")

        try:
            res = connect_client.describe_instance(
                InstanceId=connect_instance_id)
            connect_filtered = {k: v for k, v in res['Instance'].items() if k in [
                'Id', 'Arn']}
            with open('connect.json', 'w') as f:
                json.dump(connect_filtered, f)

            connect_instance_arn_val = res['Instance']['Arn']

            res = connect_client.list_security_profiles(
                InstanceId=connect_instance_id)
            for item in res['SecurityProfileSummaryList']:
                if (item['Name'] == 'Agent'):
                    security_profile_arn_val = item['Arn']
                    item_filtered = {k: v for k, v in item.items() if k in [
                        'Id', 'Arn', 'Name']}
                    with open('security_profile.json', 'w') as f:
                        json.dump(item_filtered, f)
                    break

            connect_instance_arn = st.text_input(
                'Amazon Connect instance ARN', value=connect_instance_arn_val)

            # security profile configuration
            security_profile_arn = st.text_input(
                'Security profile ARN (Agent Role)', value=security_profile_arn_val)

            st.success("Connect instance has been loaded")

        except Exception as e:
            st.error('Load Connect instance failed')
            st.error(e)

    # tenat configuration
    tenant_name = st.text_input('Tenant Name (Required)')

    # tenat description
    tenant_description = st.text_area('Tenant Description (Optional)')

    st.write('*You must click follow button to load and save configuration*')

    # save env
    if st.button('Save Configuration'):
        os.environ["tenant_name"] = tenant_name
        os.environ["tenant_description"] = tenant_description
        os.environ["tts_voice"] = tts_voice
        st.success("ENV has been set")

    # deploy cdk
    st.subheader('CDK Deployment', divider="rainbow")
    if st.button('Deploy CDK Stack'):
        subprocess.Popen(['cdk', 'deploy'])
        st.write('CDK stack initialized...........')
        time.sleep(5)
        with st.spinner('Deploying......'):
            cfm_client = boto3.client("cloudformation")
            try:
                while True:
                    time.sleep(5)
                    res = cfm_client.describe_stacks()
                    stacks = [i['StackName'] for i in res['Stacks']]
                    if os.environ["tenant_name"] in stacks:
                        res = cfm_client.describe_stacks(
                            StackName=os.environ["tenant_name"])
                        status = res['Stacks'][0]['StackStatus']
                        if status == 'CREATE_COMPLETE':
                            st.success('Deploy complete!')
                            break
                        elif status in ['CREATE_FAILED', 'ROLLBACK_COMPLETE']:
                            st.error(
                                'Deploy failed, please check CloudFormation event for detailed messages.')
                            break
                        else:
                            continue
            except Exception as e:
                st.error('Failed')

    # destroy cdk
    st.subheader('Clean Resources', divider="rainbow")
    if st.button('Destroy CDK Stack'):
        subprocess.Popen(['cdk', 'destroy', '--force'])
        st.write('Destroying CDK stack...........')
        time.sleep(5)
        with st.spinner('Destroying......'):
            cfm_client = boto3.client("cloudformation")
            try:
                while True:
                    time.sleep(5)
                    res = cfm_client.describe_stacks()
                    stacks = [i['StackName'] for i in res['Stacks']]
                    if os.environ["tenant_name"] not in stacks:
                        st.success('Destroy complete!')
                        break
                    else:
                        res = cfm_client.describe_stacks(
                            StackName=os.environ["tenant_name"])
                        status = res['Stacks'][0]['StackStatus']
                        if status == 'DELETE_FAILED':
                            st.error(
                                'Destroy failed, please check CloudFormation event for detailed messages.')
                            break
                        else:
                            continue
            except Exception as e:
                st.error('Failed')


class ConnectCdkVoiceChannelStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # parameter
        connect_instance_arn = ''
        if os.path.exists('connect.json'):
            with open('connect.json') as f:
                json_data = json.load(f)
                connect_instance_arn = json_data['Arn']

        security_profile_arn = ''
        if os.path.exists('security_profile.json'):
            with open('security_profile.json') as f:
                json_data = json.load(f)
                security_profile_arn = json_data['Arn']

        now = datetime.now()
        formatted_now = now.strftime("%Y%m%d%H%M%S")

        # load hours of operation
        with open('hours_of_operation.json') as f:
            hop_data = json.load(f)
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

        # define IVR
        with open('ivr_messages.json') as f:
            message_data = json.load(f)
            os.environ["ivr_welcome_message"] = message_data['welcomeMessage']
            os.environ["ivr_open_hour_message"] = message_data['openHourMessage']
            os.environ["ivr_error_message"] = message_data['errorMessage']

        # load contact flow - IVR
        with open('examples/flows/welcome_message_flow/welcome_message_flow.json') as f:
            flow_data = json.load(f)
            flow_content = json.dumps(flow_data)
            flow_content = flow_content.replace(
                "contact_queue_name", os.environ["tenant_name"]+" Queue")
            flow_content = flow_content.replace(
                "contact_name", os.environ["tenant_name"])
            flow_content = flow_content.replace(
                "Joanna", os.environ["tts_voice"])
            flow_content = flow_content.replace(
                "welcome-message", os.environ["ivr_welcome_message"])
            flow_content = flow_content.replace(
                "open-hour-message", os.environ["ivr_open_hour_message"])
            flow_content = flow_content.replace(
                "error-message", os.environ["ivr_error_message"])
            flow_content = flow_content.replace(
                "queue-arn", cfn_queue.attr_queue_arn)
            with open('connect_flow_ivr_updated.json', 'w') as f:
                f.write(flow_content)

        cfn_contact_flow_ivr = connect.CfnContactFlow(self, "CfnContactFlow"+formatted_now,
                                                      content=flow_content,
                                                      instance_arn=connect_instance_arn,
                                                      description="IVR flow created using cfn",
                                                      name=os.environ["tenant_name"] +
                                                      " Inbound Flow",
                                                      type="CONTACT_FLOW"
                                                      )

        # load contact flow - Survey
        if os.path.exists('survey_message.json'):
            with open('survey_message.json') as f:
                message_data = json.load(f)
                os.environ["survey_message"] = message_data['surveyMessage']
                os.environ["survey_message_feedback"] = message_data['surveyMessageFeedback']

            with open('examples/flows/survey_message_flow/survey_message_flow.json') as f:
                flow_data = json.load(f)
                flow_content = json.dumps(flow_data)
                flow_content = flow_content.replace(
                    "survey_message", os.environ["survey_message"])
                flow_content = flow_content.replace(
                    "survey_message_feedback", os.environ["survey_message_feedback"])
                with open('connect_flow_survey_updated.json', 'w') as f:
                    f.write(flow_content)

            cfn_contact_flow_survey = connect.CfnContactFlow(self, "CfnContactFlow"+formatted_now,
                                                             content=flow_content,
                                                             instance_arn=connect_instance_arn,
                                                             description="Survey flow created using cfn",
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
