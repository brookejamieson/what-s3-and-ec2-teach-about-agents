#!/bin/sh
# Slide 27: run any demo stage with tracing to CloudWatch (AgentCore Observability).
# Follows the AgentCore docs for agents hosted outside AgentCore Runtime.
#
#   sh trace.sh 03_stop.py          # the slide 22-24 run: approve, IAM refuses
#
# Then: CloudWatch console > GenAI Observability > Agents (or Traces), service
# "talk-demo-agent". New traces can take a few minutes to appear.
cd "$(dirname "$0")" || exit 1
LOG_GROUP=/aws/bedrock-agentcore/talk-demo-agent
aws logs create-log-group --region us-east-1 --log-group-name "$LOG_GROUP" 2>/dev/null
aws logs create-log-stream --region us-east-1 --log-group-name "$LOG_GROUP" --log-stream-name runtime-logs 2>/dev/null

AWS_REGION=us-east-1 \
AWS_DEFAULT_REGION=us-east-1 \
AGENT_OBSERVABILITY_ENABLED=true \
OTEL_PYTHON_DISTRO=aws_distro \
OTEL_PYTHON_CONFIGURATOR=aws_configurator \
OTEL_RESOURCE_ATTRIBUTES="service.name=talk-demo-agent,aws.log.group.names=$LOG_GROUP" \
OTEL_EXPORTER_OTLP_LOGS_HEADERS="x-aws-log-group=$LOG_GROUP,x-aws-log-stream=runtime-logs,x-aws-metric-namespace=bedrock-agentcore" \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_TRACES_EXPORTER=otlp \
  ../.venv/bin/opentelemetry-instrument ../.venv/bin/python "$@"
