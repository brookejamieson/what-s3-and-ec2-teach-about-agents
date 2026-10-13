"""Step 5: policy engine (Cedar + Dogwood) attached to the gateway.

Policies (default deny once ENFORCE is on):
  permit_reads            AwsMcp run_script + search_documentation, InstanceTools describe_instance
  forbid_terminate        slide 25: nobody calls terminate_instance
  permit_stop_after_look  slide 25c: stop only if the account was read in the last 10 minutes

Usage:  ../.venv/bin/python 05_policy.py [LOG_ONLY|ENFORCE]   (default ENFORCE)
"""
import sys

from botocore.exceptions import ClientError

from common import (GATEWAY_NAME, POLICY_ENGINE_NAME, TAG, load_state, save_state,
                    session, wait_for)

MODE = sys.argv[1] if len(sys.argv) > 1 else "ENFORCE"
ctl = session().client("bedrock-agentcore-control")
st = load_state()
GW = st["gateway_arn"]

POLICIES = {
    "permit_reads": ("cedar", f'''permit (
  principal,
  action in [
    AgentCore::Action::"AwsMcp___aws___run_script",
    AgentCore::Action::"AwsMcp___aws___search_documentation",
    AgentCore::Action::"InstanceTools___describe_instance"
  ],
  resource == AgentCore::Gateway::"{GW}"
);'''),
    "forbid_terminate": ("cedar", f'''forbid (
  principal,
  action == AgentCore::Action::"InstanceTools___terminate_instance",
  resource == AgentCore::Gateway::"{GW}"
);'''),
    "permit_stop_after_look": ("policy", f'''permit (
  principal,
  action == AgentCore::Action::"InstanceTools___stop_instance",
  resource == AgentCore::Gateway::"{GW}"
)
when temporal {{
  formerly within 10m
    AgentCore::Action::"InstanceTools___describe_instance"::response{{
      eventResource: resource,
      output.instanceId: context.input.instanceId
    }}
}};'''),
}

# --- engine ---
eng = next((e for e in ctl.list_policy_engines()["policyEngines"] if e["name"] == POLICY_ENGINE_NAME), None)
if not eng:
    eng = ctl.create_policy_engine(name=POLICY_ENGINE_NAME, tags=TAG,
                                   description="Talk demo: Cedar ban + Dogwood look-before-stop")
    print("created policy engine", eng["policyEngineId"])
eid = eng["policyEngineId"]
eng = wait_for(lambda: ctl.get_policy_engine(policyEngineId=eid),
               lambda r: r["status"] not in ("CREATING", "UPDATING"), "engine active")
print("engine", eng["status"])

# --- policies ---
have = {p["name"]: p for p in ctl.list_policies(policyEngineId=eid)["policies"]}
for name, (kind, stmt) in POLICIES.items():
    definition = {"cedar": {"statement": stmt}} if kind == "cedar" else {"policy": {"statement": stmt}}
    # The validator flags a forbid that blocks every caller as "Overly Restrictive".
    # For the terminate ban that is the intent, so findings are ignored for it only.
    vmode = "IGNORE_ALL_FINDINGS" if name == "forbid_terminate" else "FAIL_ON_ANY_FINDINGS"
    try:
        if name in have:
            ctl.update_policy(policyEngineId=eid, policyId=have[name]["policyId"],
                              definition=definition, validationMode=vmode)
            pid = have[name]["policyId"]
            print("updated", name)
        else:
            pid = ctl.create_policy(policyEngineId=eid, name=name, definition=definition,
                                    validationMode=vmode)["policyId"]
            print("created", name)
    except ClientError as e:
        print(f"POLICY {name} REJECTED:", e.response["Error"]["Message"])
        sys.exit(1)
    p = wait_for(lambda: ctl.get_policy(policyEngineId=eid, policyId=pid),
                 lambda r: r["status"] not in ("CREATING", "UPDATING"), f"policy {name}")
    print(f"  {name}: {p['status']} {p.get('statusReasons') or ''}")

# --- let the gateway role call the engine (CDK grantEvaluateForGateway pattern) ---
import json  # noqa: E402
session().client("iam").put_role_policy(
    RoleName="talk-gateway", PolicyName="talk-gateway-policy-engine",
    PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow",
         "Action": ["bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions"],
         "Resource": [eng["policyEngineArn"], GW]},
        {"Effect": "Allow", "Action": "bedrock-agentcore:GetPolicyEngine",
         "Resource": eng["policyEngineArn"]},
        # Needed once a policy engine is attached: the gateway gets a workload
        # access token before calling the AWS MCP Server target.
        {"Effect": "Allow",
         "Action": ["bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId"],
         "Resource": [f"arn:aws:bedrock-agentcore:us-east-1:{st['account']}:workload-identity-directory/default",
                      f"arn:aws:bedrock-agentcore:us-east-1:{st['account']}:workload-identity-directory/default/workload-identity/*"]},
    ]}),
)
import time  # noqa: E402
time.sleep(10)  # IAM propagation

# --- attach ---
gw = ctl.get_gateway(gatewayIdentifier=st["gateway_id"])
ctl.update_gateway(
    gatewayIdentifier=gw["gatewayId"], name=GATEWAY_NAME, roleArn=gw["roleArn"],
    protocolType=gw["protocolType"], authorizerType=gw["authorizerType"],
    description=gw.get("description", ""), exceptionLevel="DEBUG",
    policyEngineConfiguration={"arn": eng["policyEngineArn"], "mode": MODE},
)
gw = wait_for(lambda: ctl.get_gateway(gatewayIdentifier=st["gateway_id"]),
              lambda r: r["status"] in ("READY", "FAILED"), "gateway READY after attach")
print("gateway", gw["status"], "policy mode", MODE, gw.get("statusReasons") or "")
save_state(policy_engine_id=eid, policy_engine_arn=eng["policyEngineArn"], policy_mode=MODE)
