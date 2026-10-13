"""Remove everything the setup scripts created.

    python teardown.py          # list what would be deleted, change nothing
    python teardown.py --yes    # delete it

It finds resources by the names in common.py and by the project=aws-ai-agents-talk
tag, in us-east-1, with the TALK_ADMIN_PROFILE profile. It does not touch the agent
you deployed to AgentCore Runtime from deploy/; see the README for that.
"""
import sys
import time

from botocore.exceptions import ClientError

from common import (GATEWAY_NAME, GATEWAY_ROLE, INSTANCE_TOOLS_FN, POLICY_ENGINE_NAME,
                    READONLY_ROLE, STOP_TOOL_ROLE, TAG, account_id, session)

DELETE = "--yes" in sys.argv
s = session()
ec2, s3, lam, iam, logs = (s.client(n) for n in ("ec2", "s3", "lambda", "iam", "logs"))
ctl = s.client("bedrock-agentcore-control")
ACCT = account_id()

ROLES = [READONLY_ROLE, STOP_TOOL_ROLE, GATEWAY_ROLE, "talk-planted-fn"]
FUNCTIONS = [INSTANCE_TOOLS_FN, "thumbnail-resizer", "orders-api", "nightly-report"]
BUCKETS = [f"talk-{r}-{ACCT}" for r in ("catalog", "assets", "logs", "site")]
LOG_GROUP = "/aws/bedrock-agentcore/talk-demo-agent"


def step(what, fn):
    """Print one resource, and delete it when --yes is set. Missing resources are skipped."""
    print(("deleting " if DELETE else "would delete ") + what)
    if DELETE:
        try:
            fn()
        except ClientError as e:
            print(f"  skipped: {e.response['Error']['Code']}")


def wait_gone(get, what, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        try:
            get()
        except ClientError:
            return
        time.sleep(5)
    print(f"  still there after {timeout}s: {what}")


# --- AgentCore Gateway, its targets, then the policy engine ---
for g in ctl.list_gateways()["items"]:
    if g["name"] != GATEWAY_NAME:
        continue
    gid = g["gatewayId"]
    for t in ctl.list_gateway_targets(gatewayIdentifier=gid)["items"]:
        step(f"gateway target {t['name']}",
             lambda t=t: ctl.delete_gateway_target(gatewayIdentifier=gid, targetId=t["targetId"]))
    if DELETE:
        for _ in range(60):  # targets must be gone before the gateway can be deleted
            if not ctl.list_gateway_targets(gatewayIdentifier=gid)["items"]:
                break
            time.sleep(5)
    step(f"gateway {GATEWAY_NAME} ({gid})", lambda: ctl.delete_gateway(gatewayIdentifier=gid))
    if DELETE:
        wait_gone(lambda: ctl.get_gateway(gatewayIdentifier=gid), "gateway")

for e in ctl.list_policy_engines()["policyEngines"]:
    if e["name"] != POLICY_ENGINE_NAME:
        continue
    eid = e["policyEngineId"]
    for p in ctl.list_policies(policyEngineId=eid)["policies"]:
        step(f"policy {p['name']}", lambda p=p: ctl.delete_policy(policyEngineId=eid, policyId=p["policyId"]))
    if DELETE:
        time.sleep(10)
    step(f"policy engine {POLICY_ENGINE_NAME} ({eid})", lambda: ctl.delete_policy_engine(policyEngineId=eid))

# --- Lambda functions ---
for name in FUNCTIONS:
    try:
        lam.get_function(FunctionName=name)
    except ClientError:
        continue
    step(f"Lambda function {name}", lambda name=name: lam.delete_function(FunctionName=name))

# --- EC2 instances and the security group ---
ids = [i["InstanceId"]
       for r in ec2.describe_instances(Filters=[
           {"Name": "tag:project", "Values": [TAG["project"]]},
           {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])["Reservations"]
       for i in r["Instances"]]
if ids:
    step(f"EC2 instances {', '.join(ids)}", lambda: (ec2.terminate_instances(InstanceIds=ids),
                                                    ec2.get_waiter("instance_terminated").wait(InstanceIds=ids)))
for sg in ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["talk-no-ingress"]}])["SecurityGroups"]:
    step(f"security group talk-no-ingress ({sg['GroupId']})",
         lambda sg=sg: ec2.delete_security_group(GroupId=sg["GroupId"]))

# --- S3 buckets (emptied first) ---
for b in BUCKETS:
    try:
        s3.head_bucket(Bucket=b)
    except ClientError:
        continue

    def empty_and_delete(b=b):
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=b):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                s3.delete_objects(Bucket=b, Delete={"Objects": keys})
        s3.delete_bucket(Bucket=b)
    step(f"S3 bucket {b} and its objects", empty_and_delete)

# --- IAM roles ---
for name in ROLES:
    try:
        iam.get_role(RoleName=name)
    except ClientError:
        continue

    def delete_role(name=name):
        for p in iam.list_attached_role_policies(RoleName=name)["AttachedPolicies"]:
            iam.detach_role_policy(RoleName=name, PolicyArn=p["PolicyArn"])
        for p in iam.list_role_policies(RoleName=name)["PolicyNames"]:
            iam.delete_role_policy(RoleName=name, PolicyName=p)
        iam.delete_role(RoleName=name)
    step(f"IAM role {name}", delete_role)

# --- trace log group from agent/trace.sh ---
if logs.describe_log_groups(logGroupNamePrefix=LOG_GROUP)["logGroups"]:
    step(f"log group {LOG_GROUP}", lambda: logs.delete_log_group(logGroupName=LOG_GROUP))

print("done." if DELETE else "\nNothing was changed. Run again with --yes to delete these.")
