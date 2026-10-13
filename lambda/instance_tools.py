"""Instance tools, served through AgentCore Gateway as target `InstanceTools`.

Runs as the talk-instance-tools role, which may only stop instances tagged
env=dev. terminate_instance exists so the gateway's Cedar rule has something
to ban (slide 25); the role has no terminate permission either.
"""
import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client("ec2")


def _tool_name(context) -> str:
    full = context.client_context.custom["bedrockAgentCoreToolName"]
    return full.split("___", 1)[1] if "___" in full else full


def describe_instance(instance_id: str) -> dict:
    r = ec2.describe_instances(InstanceIds=[instance_id])
    i = r["Reservations"][0]["Instances"][0]
    return {"instanceId": i["InstanceId"], "state": i["State"]["Name"],
            "tags": {t["Key"]: t["Value"] for t in i.get("Tags", [])}}


def stop_instance(instance_id: str) -> dict:
    r = ec2.stop_instances(InstanceIds=[instance_id])
    s = r["StoppingInstances"][0]
    return {"instanceId": s["InstanceId"], "previousState": s["PreviousState"]["Name"],
            "currentState": s["CurrentState"]["Name"]}


def terminate_instance(instance_id: str) -> dict:
    ec2.terminate_instances(InstanceIds=[instance_id])  # role has no permission
    return {"instanceId": instance_id, "status": "terminating"}


TOOLS = {"describe_instance": describe_instance, "stop_instance": stop_instance,
         "terminate_instance": terminate_instance}


def handler(event, context):
    name = _tool_name(context)
    try:
        return TOOLS[name](event["instanceId"])
    except ClientError as e:
        # Raised so the gateway returns a tool error, which Strands hands back
        # to the model as an error result (slide 24b).
        err = e.response["Error"]
        raise RuntimeError(f"{err['Code']}: {err['Message']}") from None
