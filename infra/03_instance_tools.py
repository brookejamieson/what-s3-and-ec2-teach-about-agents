"""Step 3: the instance-tools Lambda and its gateway target `InstanceTools`."""
import io
import json
import pathlib
import zipfile

from botocore.exceptions import ClientError

from common import INSTANCE_TOOLS_FN, TAG, load_state, save_state, session, wait_for

s = session()
lam = s.client("lambda")
ctl = s.client("bedrock-agentcore-control")
st = load_state()

src = pathlib.Path(__file__).parent.parent / "lambda" / "instance_tools.py"
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.write(src, "instance_tools.py")
code = buf.getvalue()

try:
    fn = lam.create_function(
        FunctionName=INSTANCE_TOOLS_FN, Runtime="python3.13", Role=st["stop_role_arn"],
        Handler="instance_tools.handler", Code={"ZipFile": code}, Timeout=30,
        Architectures=["arm64"], Tags=TAG,
        Description="Talk demo: describe/stop/terminate instance tools behind AgentCore Gateway",
    )
    print("created function")
except ClientError as e:
    if e.response["Error"]["Code"] != "ResourceConflictException":
        raise
    fn = lam.update_function_code(FunctionName=INSTANCE_TOOLS_FN, ZipFile=code)
    print("updated function code")
wait_for(lambda: lam.get_function(FunctionName=INSTANCE_TOOLS_FN)["Configuration"],
         lambda c: c["State"] == "Active" and c.get("LastUpdateStatus") in (None, "Successful"),
         "lambda active")
fn_arn = lam.get_function(FunctionName=INSTANCE_TOOLS_FN)["Configuration"]["FunctionArn"]

ID_IN = {"type": "object", "required": ["instanceId"],
         "properties": {"instanceId": {"type": "string", "description": "EC2 instance ID, for example i-0123456789abcdef0"}}}
TOOLS = [
    {"name": "describe_instance",
     "description": "Look up one EC2 instance by ID. Returns its state and tags.",
     "inputSchema": ID_IN,
     "outputSchema": {"type": "object", "properties": {
         "instanceId": {"type": "string"}, "state": {"type": "string"}, "tags": {"type": "object"}}}},
    {"name": "stop_instance",
     "description": "Stop one running EC2 instance by ID. Stopping can be undone by starting it again.",
     "inputSchema": ID_IN,
     "outputSchema": {"type": "object", "properties": {
         "instanceId": {"type": "string"}, "previousState": {"type": "string"}, "currentState": {"type": "string"}}}},
    {"name": "terminate_instance",
     "description": "Permanently delete one EC2 instance by ID. This cannot be undone.",
     "inputSchema": ID_IN},
]

gw_id = st["gateway_id"]
existing = {t["name"]: t["targetId"] for t in ctl.list_gateway_targets(gatewayIdentifier=gw_id)["items"]}
cfg = {"mcp": {"lambda": {"lambdaArn": fn_arn, "toolSchema": {"inlinePayload": TOOLS}}}}
creds = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
if "InstanceTools" in existing:
    tid = existing["InstanceTools"]
    ctl.update_gateway_target(gatewayIdentifier=gw_id, targetId=tid, name="InstanceTools",
                              targetConfiguration=cfg, credentialProviderConfigurations=creds)
    print("updated target")
else:
    tid = ctl.create_gateway_target(gatewayIdentifier=gw_id, name="InstanceTools",
                                    description="describe/stop/terminate EC2 instances",
                                    targetConfiguration=cfg,
                                    credentialProviderConfigurations=creds)["targetId"]
    print("created target")
t = wait_for(lambda: ctl.get_gateway_target(gatewayIdentifier=gw_id, targetId=tid),
             lambda r: r["status"] not in ("CREATING", "UPDATING", "SYNCHRONIZING"), "target ready")
print("InstanceTools", t["status"], t.get("statusReasons"))
save_state(instance_tools_fn_arn=fn_arn, instance_tools_target_id=tid)
print(json.dumps({"function": fn_arn, "target": tid}))
