# AgentCore と Quick Desktop の落とし穴

> Amazon Bedrock AgentCore Gateway、AgentCore の Lambda ターゲット、Quick Desktop の MCP 設定に触れるときに読む。
>
> English: [agentcore-pitfalls_en.md](agentcore-pitfalls_en.md)

検証で判明した知見を、根本原因と対処とともに残す。いずれも 2026-07 時点の検証に基づく。AgentCore は活発に更新されるため、リージョン提供状況・イベント構造・API の形は、依拠する前に現行の公式ドキュメントで再確認すること（[サービスの提供状況](service-lifecycle.md)）。

## リージョン提供状況の思い込み

AgentCore Gateway は us-east-1 のみという前提を置きがちだが、これはワークショップの例が us-east-1 を既定にしているためで、サービスの制約ではない。**ap-northeast-1(東京)で利用可能**（2026-07 検証。[公式ドキュメント](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html)でも東京が対応リージョンとして記載されている。提供リージョンは拡大するため、依拠前に現行を確認する)。Gateway と Lambda は同一リージョンに配置する。

## Lambda ターゲットのイベント構造とツール名の取得

AgentCore の Lambda ターゲットで、ツール名を `event.toolName` から取得できるという前提は誤り。`event` はフラットなパラメータ辞書として渡される。ツール名は `context.client_context.custom['bedrockAgentCoreToolName']` から取得する。値は `targetName___toolName` 形式(アンダースコア3つ区切り)。

## Gateway と Lambda のリージョン不一致

`create-gateway-target` で「Lambda not found」になる主因は、Gateway と Lambda のリージョン不一致。同一リージョンへの配置が必須で、クロスリージョンの Lambda 呼び出しはできない。

## Quick Desktop の MCP 設定の非永続化

Quick Desktop で MCP の Remote 追加が永続化されない場合がある(間欠的な挙動)。**Import 方式**(JSON ファイルからの読み込み)を使うと安定する。Local/Remote の直接追加は不安定。

## Quick Desktop のサインインで「account name is invalid」

Quick Desktop のサインインで「account name is invalid」が出るのは、IAM ユーザー名と QuickSight ユーザー名が一致していないため。`aws quicksight list-users` で QuickSight 側のユーザー名を確認する。Email ベースのサインインが最も確実。
