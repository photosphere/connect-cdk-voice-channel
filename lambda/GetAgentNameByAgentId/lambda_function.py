import boto3

connect = boto3.client('connect')


def get_agent_name(agent_id, instance_id):
    if not agent_id:
        return ""
    response = connect.describe_user(UserId=agent_id, InstanceId=instance_id)
    info = response['User']['IdentityInfo']
    return f"{info['FirstName']} {info['LastName']}"


def get_instance_id(instance_arn):
    return instance_arn.split('/')[1]


def lambda_handler(event, context):
    print(event)
    agent_id = event["Details"]["Parameters"]["LastAgentID"]
    print('agent_id:' + agent_id)
    instance_arn = event["Details"]["ContactData"]["InstanceARN"]
    instance_id = get_instance_id(instance_arn)
    print('instance_id:' + instance_id)
    agent_name = get_agent_name(agent_id, instance_id)
    return {
        'LastAgentName': agent_name
    }
