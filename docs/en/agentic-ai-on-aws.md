> 🌐 Language: [日本語](../ja/agentic-ai-on-aws.md) | **English**

# Agentic AI on AWS

> Last verified: 2026-08-19

Design questions for putting agentic behaviour on this architecture. Referenced from
[Pattern 01](aws-patterns/01-edge-ai-bedrock.md),
[Pattern 05](aws-patterns/05-agentic-rag.md) and
[Pattern 09](aws-patterns/09-edge-agentic-ai.md), and not duplicated into them.

**There is no agent implementation in this repository.** This is written as design material.

## Availability labels

Every item carries an availability label. Three values.

| Label | Meaning |
|-------|---------|
| **Supported today** | Documented as generally available, with the URL |
| **Public preview** | Explicitly stated as preview by AWS |
| **Conceptual** | An outline with no documented basis. Not written as a generally available feature |

## 1. What counts as an agent

The word is used broadly, so this document distinguishes three things.

| Name | What it does | The hard part |
|---|---|---|
| Single inference | Pass input, get a result | Prompt and input shaping |
| Retrieval-augmented generation | Retrieve, then generate grounded in what was retrieved | Permissions on retrieval scope, chunk design |
| Agent | Decides what to look up, calls tools, runs several steps | Stopping conditions, permissions, handling failure |

**These are not the same thing.** Using an agent where a single inference suffices raises response
time and cost and makes behaviour harder to predict. Conversely, forcing a decision that spans
several sources into a single call ends up stuffing context into the prompt and breaks down.

## 2. Runtime

Amazon Bedrock AgentCore provides the pieces an agent needs as separate components.
**Supported today** (GA, 2025-10;
[source](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available),
[overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html))

| Component | Design problem it addresses | Availability |
|---|---|---|
| Runtime | Where the agent runs, without managing infrastructure | Supported today |
| Memory | Short-term retention within a conversation and long-term retention across sessions, shareable between agents | Supported today |
| Gateway | Treats APIs and functions as tools, and connects to existing MCP servers | Supported today |
| Identity | Authentication when calling tools | Supported today |
| Observability | Tracing what happened | Supported today |

Runtime also offers a form that runs on EC2 in your own account
(**Supported today**, 2026-08;
[source](https://aws.amazon.com/about-aws/whats-new/2026/08/aws-bedrock-agentcore-runtime-instances-generally-available/)).
Because the OS, instance type, networking and storage are specified, it is an option where
reachability to existing resources inside a VPC is required.

**The difference from assembling this in Lambda** is whether memory and tool connections are
hand-built. The current implementation here
([`cloud/ai/image_analyzer/`](../../cloud/ai/image_analyzer/)) is a single inference in Lambda. While
it stays a single inference, there is no reason to replace it.

## 3. Retrieving context

Where the information passed to an agent comes from. Three sources exist in this architecture.

| Source | How to reach it | Suits |
|---|---|---|
| Documents on file storage | Ingested into Knowledge Bases through an S3 access point (**Supported today**, [source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)) | Instructions, drawings, reports |
| Structured analysis results | SQL query results passed as a tool | Aggregates, trends, anomaly history |
| Current time-series values | A query against the time-series database exposed as a tool | Current equipment state |

**The more sources, the harder the permission design.** The permissions an agent holds are not the
same as those of the user who invoked it. That is the largest design trap here (§6).

## 4. Separating long-term storage from memory

Do not blur "memory" and "storage". They have different roles.

| Layer | What it holds | Where it lives |
|---|---|---|
| Agent memory | Conversation context, learning across sessions | AgentCore Memory |
| Vector store | Embeddings for retrieval | The store attached to a knowledge base |
| Source of truth | The original documents, images and telemetry | File storage / data lake |

**The source of truth sits outside the AI.** Keep both memory and vectors in a state that can be
rebuilt from the originals. Decide in the design what happens to memory and vectors when an original
is deleted ([Pattern 05](aws-patterns/05-agentic-rag.md), storage section).

## 5. Multiple agents

Two reasons to split into several agents.

- **Separation of duties**: retrieval, judgement and action as different agents, each with narrower
  permissions
- **Separation of permission boundaries**: agents split by the data they may touch — one of the
  responses in §6

Three things to decide once split.

| Decision | What informs it |
|---|---|
| How far memory is shared | Sharing carries context forward; separating narrows how far information spreads |
| Direction of calls | One-way makes behaviour legible; mutual calls make stopping conditions hard |
| Handling failure | When an intermediate agent fails, stop everything or return partial results |

**Decide the stopping condition first.** In a structure where the agent chooses its own next step, it
does not stop unless a limit — steps, time, cost — is imposed from outside.

## 6. Data governance

**When putting an agent on this architecture, the asymmetry of permissions deserves the most
attention.**

On a file share, different users see different documents. If an agent can search every document
under one identity, that distinction is lost, and information a user cannot access may appear in an
answer.

The directions and their trade-offs are tabulated in
[Pattern 05](aws-patterns/05-agentic-rag.md), security section. Three points are specific to this
architecture.

- **S3 access point authorization has two layers.** An IAM allow is not sufficient: if the file
  system user bound to the access point lacks permission on the file, the request is denied
  ([source](s3ap-compatibility-matrix.md)). Agent permission design passes through both layers
- **Do not maintain catalog and data permissions twice.** Lake Formation table permissions have been
  extended to cover access to the underlying data ([security design](security-design.md))
- **Where data residency requirements apply**, some data cannot be sent to a large cloud model. In
  that case consider placing the decision at the edge
  ([Pattern 09](aws-patterns/09-edge-agentic-ai.md)) or a hybrid configuration. AWS publishes
  [a worked configuration for RAG under data residency requirements](https://aws.amazon.com/blogs/machine-learning/implement-rag-while-meeting-data-residency-requirements-using-aws-hybrid-and-edge-services/)

### Auditability

Because an agent chooses several steps itself, "why it reached that conclusion" cannot be verified
later unless it was recorded. Three things to keep.

| Kept | Why it is needed |
|---|---|
| Sources called and content retrieved | Verifying the grounding |
| Records of tool calls | Tracing side effects, such as writes into business systems |
| Output paired with its input | Because the same input does not guarantee the same output |

## 7. Unverified and unimplemented

| Item | State |
|---|---|
| An agent implementation in this repository | None |
| Verifying tool connections over MCP | Not done |
| Sync design between AgentCore Memory and the source of truth | Not designed |
| Operational load of one knowledge base per permission boundary | Unverified |
| Running an agent at the edge | Not done ([Pattern 09](aws-patterns/09-edge-agentic-ai.md)) |

## References

- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [AgentCore release notes](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- [AWS Prescriptive Guidance: Amazon Bedrock AgentCore](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/amazon-bedrock-agentcore.html)
- [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
- [Edge AI and global inference distribution](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/edge-ai.html)
- Related: [pattern catalog](aws-patterns/README.md) /
  [Flexible AI Data Layer](flexible-ai-data-layer.md)
