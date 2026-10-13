# What S3 and EC2 can teach us about building AI agents

This repo has the code for every demo in the AWS Community Day 2026 keynote of the same name. The talk builds one agent in stages, from a first version that reads an AWS account to one running on AgentCore Runtime. On the way it gets a tool of its own, permissions that limit what it can break, tracing and an eval. Each stage is a short Python file you can run.

The code uses Strands Agents for the agent loop, Amazon Bedrock for the models, the AWS MCP Server (part of the Agent Toolkit for AWS) for account access, and Amazon Bedrock AgentCore for the gateway, policy and runtime.

This sample works with Amazon Bedrock, Amazon Bedrock AgentCore, Amazon EC2, Amazon S3 and AWS Lambda.

For the talk's key points, read [TALK-NOTES.md](TALK-NOTES.md).

Everything runs in `us-east-1`. Use a sandbox account. Some demos stop real EC2 instances on purpose.

## Run the first agent

The first agent needs no setup scripts. It reads your account with a read-only AWS profile and answers "What's running in my account?" The model writes a short boto3 script, the AWS MCP Server runs it, and the agent answers from what it finds.

Before you start, you need:

- Python 3.13 and [uv](https://docs.astral.sh/uv/). The agent starts the MCP Proxy for AWS with `uvx`.
- An AWS profile that can only read the account. For example, a role with the `ReadOnlyAccess` managed policy. That policy can also read data, such as the contents of S3 objects, so point the agent at a sandbox account rather than one with data you care about.
- Access in Amazon Bedrock to the model Strands uses by default, `global.anthropic.claude-sonnet-4-6`.

To run it:

1. Create a virtual environment in the repo folder and install the dependencies:

   ```bash
   python3.13 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

   `requirements.txt` includes PyAudio for the phone demo. If it fails to install, install PortAudio first (`brew install portaudio` on macOS) or remove the line. Only the phone needs it.

2. Run the agent, replacing `my-readonly-profile` with the name of your read-only profile:

   ```bash
   cd agent
   TALK_READONLY_PROFILE=my-readonly-profile ../.venv/bin/python 01_first_agent.py
   ```

The terminal prints each tool call as it happens, including the script the model wrote, and then the answer. One run takes about 30 seconds.

The agent itself is the `Agent(tools=[aws])` line in `agent/01_first_agent.py`. Everything in `agent/demo_common.py` is there to connect the AWS MCP Server and print the tool calls.

## Set up the full demo account

The later demos need things in the account to work with: four small instances (three tagged `env=dev`, one tagged `env=prod`), three Lambda functions, four private buckets, a copy of the re:Invent catalog, IAM roles, an AgentCore Gateway and a policy engine. The scripts in `infra/` create all of it. Each one is safe to run again.

You need an AWS profile that can create IAM roles, EC2 instances, S3 buckets, Lambda functions and AgentCore resources. The scripts use the `default` profile unless you set `TALK_ADMIN_PROFILE`.

1. Create the IAM roles:

   ```bash
   cd infra
   ../.venv/bin/python 01_roles.py
   ```

2. Add a `talk-readonly` profile to `~/.aws/config` that assumes the new read-only role. Replace `111122223333` with your account ID, and `default` with your admin profile if it has another name:

   ```ini
   [profile talk-readonly]
   role_arn = arn:aws:iam::111122223333:role/talk-readonly
   source_profile = default
   region = us-east-1
   ```

3. Create the instances, functions and buckets, then the catalog, the gateway, the instance tools and the policies:

   ```bash
   ../.venv/bin/python 04_plant.py
   ../.venv/bin/python 06_catalog_snapshot.py
   ../.venv/bin/python 02_gateway.py
   ../.venv/bin/python 03_instance_tools.py
   ../.venv/bin/python 05_policy.py
   ```

   The scripts save the IDs they create in `infra/state.json`. The agent files read it from there. It contains your account ID, so `.gitignore` keeps it out of git.

4. Check the controls without a model in the loop:

   ```bash
   ../.venv/bin/python test_controls.py
   ```

   Each check prints what it expects, such as "Dogwood should deny", and then the result it got. It doesn't stop any instance unless you add `--stop-dev`.

`04_plant.py` also resets the account. Run it again after any demo that stops instances, so every instance is running and the tags are back.

## Run each demo

Run these from the `agent/` folder. If your read-only profile isn't called `talk-readonly`, set `TALK_READONLY_PROFILE` first. The demos marked "stops instances" ask for approval in the terminal before each stop; type `y` to approve. They stop real dev instances, so reset with `../.venv/bin/python ../infra/04_plant.py` afterwards.

| Demo | Command | What it shows |
|---|---|---|
| The first agent | `01_first_agent.py` | The model writes and runs its own boto3 script through `aws___run_script`. |
| Swap the model | `01_first_agent.py --model` | The same agent on OpenAI GPT-5.6 Luna in Bedrock. Needs access to that model. |
| What the model sees of a tool | `02_catalog.py --spec` | The tool spec Strands builds from a four-word docstring, next to the AWS MCP Server's own description. |
| The vague docstring | `02_catalog.py --lazy` | With the vague docstring, the agent searches the catalog and doesn't look at your functions. |
| The rewritten docstring | `02_catalog.py` | With the rewritten docstring, it reads the account first. |
| A prompt as a guardrail | `03_stop.py --prompt-only` | A system prompt asks it not to stop prod. It usually listens, but a prompt can't make it. |
| Approval, then IAM | `03_stop.py` (stops instances) | You approve the stop, and EC2 refuses because the tool's role can only stop `env=dev`. The error goes back to the model. |
| Look before you stop (Dogwood) | `04_gateway.py --dogwood` (stops instances) | Through the gateway, a stop is refused unless the agent looked that instance up in the last 10 minutes. |
| The trace in CloudWatch | `sh trace.sh 03_stop.py` (stops instances) | The approve-then-refused stop run, with traces sent to CloudWatch. Open CloudWatch, then GenAI Observability, and find the service `talk-demo-agent`. |
| Turn and token limits | `01_first_agent.py --limits` | The same question with a cap on turns and tokens. It prints which limit stopped it, if any. |
| A tag that tells agents what to do | `03_stop.py --note` (stops instances) | A tag on the prod instance tells AI agents to stop it. The agent may believe it, and IAM still refuses. |
| The eval | `05_eval.py` | An eval that runs four questions five times with each docstring, and has a second model check the tools each run used. Takes about 8 minutes. |
| The phone call | `phone_web.py` | A voice agent on Amazon Nova 2.5 Sonic that passes every question to the account agent. Open http://127.0.0.1:8766 in Chrome. |

Model output changes from run to run. The talk shows runs from 12 October 2026. Your run should do the same kind of thing, but the wording and the number of tool calls will differ. On the slide 25c demo, for example, the agent sometimes looks the instance up and retries by itself, and sometimes stops after the refusal and waits for you to tell it to look first.

`phone_web.py` listens on 127.0.0.1 only and has no login. Every call it takes uses your AWS credentials, so don't expose it to a network.

## Deploy the agent to AgentCore Runtime

`deploy/` holds the account agent, the one the phone passes questions to, as an AgentCore CLI project. The agent is one file, `deploy/agent.py`, with the AWS MCP Server and the catalog tool. It uses whatever credentials its environment gives it: your default profile locally, and its execution role on Runtime.

You need the [AgentCore CLI](https://github.com/aws/agentcore-cli) (the demo used version 0.24.2) and Node.js for its CDK step. The catalog from `06_catalog_snapshot.py` must already be in your account.

1. In `deploy/agentcore/aws-targets.json`, replace `111122223333` with your account ID.
2. Deploy and call it:

   ```bash
   cd deploy
   agentcore deploy -y
   agentcore invoke "What's in my account right now?"
   ```

The first deploy in an account and Region also runs a one-time CDK bootstrap, which adds a few minutes. Once the account was bootstrapped, a deploy took about two minutes in testing.

The runtime runs as an execution role whose extra permissions are in `deploy/agentcore/execution-role-policy.json`. That file lets it read EC2, S3 and Lambda configuration and the one catalog object, and nothing else in your account. Callers need a signed AWS request from an identity allowed `bedrock-agentcore:InvokeAgentRuntime`. An unsigned request gets a 403.

Two lines in `deploy/agent.py` exist because of Runtime. Runtime starts the file with no arguments, so with no question the file starts the server. The MCP SDK passes only a few environment variables to the proxy it starts, so `env=dict(os.environ)` passes the rest, including the Runtime credentials.

## Clean up

To see everything the setup scripts created, without changing anything:

```bash
cd infra
../.venv/bin/python teardown.py
```

To delete it, run the same command with `--yes`. This terminates the four instances and deletes the buckets and their contents, the functions, the gateway, the policy engine, the IAM roles and the trace log group.

The teardown script doesn't remove the deployed runtime. To remove it, delete the CloudFormation stack `AgentCore-AccountAgentTalk-default` in `us-east-1`. The `CDKToolkit` stack from the bootstrap can stay for later CDK deploys, or you can delete it too.

## Cost

The four `t4g.nano` instances cost money while they run, and every agent run uses Bedrock tokens. CloudWatch estimated one traced run of `03_stop.py` at $0.034. For anything else, check the [AWS Pricing Calculator](https://calculator.aws/) and the pricing pages for Amazon Bedrock, Amazon EC2 and Amazon Bedrock AgentCore. Run the teardown when you finish.

## What's in the repo

| Folder | Contents |
|---|---|
| `agent/` | One file per stage of the agent, the catalog tool, the eval and the phone demo. |
| `infra/` | The scripts that set up, test and remove the demo account. |
| `lambda/` | The `stop_instance`, `describe_instance` and `terminate_instance` tools that sit behind the gateway. |
| `data/` | 34 sessions from the re:Invent 2026 catalog, copied on 12 October 2026, which `06_catalog_snapshot.py` uploads to S3. |
| `deploy/` | The AgentCore CLI project for the Runtime deploy. |

The dependency versions in `requirements.txt` and `deploy/pyproject.toml` are the ones the demos were tested with.

## License

This project is licensed under the MIT-0 License. See [LICENSE](LICENSE).
