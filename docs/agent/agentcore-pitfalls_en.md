# AgentCore and Quick Desktop pitfalls

> Read when working with Amazon Bedrock AgentCore Gateway, an AgentCore Lambda target, or Quick Desktop MCP configuration.
>
> 日本語: [agentcore-pitfalls.md](agentcore-pitfalls.md)

Findings from verification, recorded with root cause and fix. All are based on verification as of 2026-07. AgentCore is updated actively, so region availability, event structure, and API shapes should be re-checked against current official documentation before relying on them ([service availability](service-lifecycle_en.md)).

## Region-availability assumption

It is easy to assume AgentCore Gateway is us-east-1 only, but that is because workshop examples default to us-east-1, not a service constraint. **It is available in ap-northeast-1 (Tokyo)** (verified 2026-07; the [official documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html) also lists Tokyo as a supported Region. Region coverage expands, so confirm the current list before relying on it). Place the Gateway and the Lambda in the same Region.

## Lambda target event structure and how to read the tool name

For an AgentCore Lambda target, the assumption that the tool name can be read from `event.toolName` is wrong. `event` arrives as a flat parameter dictionary. Read the tool name from `context.client_context.custom['bedrockAgentCoreToolName']`. The value is in `targetName___toolName` form (three-underscore separator).

## Region mismatch between Gateway and Lambda

The main cause of "Lambda not found" on `create-gateway-target` is a Region mismatch between the Gateway and the Lambda. Same-Region placement is required; cross-Region Lambda invocation is not possible.

## Quick Desktop MCP configuration not persisting

In Quick Desktop, adding an MCP Remote can fail to persist (intermittent behavior). Using the **Import method** (loading from a JSON file) is stable. Direct Local/Remote addition is unreliable.

## Quick Desktop sign-in "account name is invalid"

"account name is invalid" at Quick Desktop sign-in means the IAM user name does not match the QuickSight user name. Check the QuickSight-side user name with `aws quicksight list-users`. Email-based sign-in is the most reliable.
