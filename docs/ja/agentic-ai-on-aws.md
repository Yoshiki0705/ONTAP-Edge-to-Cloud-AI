> 🌐 Language: **日本語** | [English](../en/agentic-ai-on-aws.md)

# Agentic AI on AWS

> 最終確認: 2026-08-19

エージェント型の処理をこのアーキテクチャに載せるときの設計論点。
[Pattern 01](aws-patterns/01-edge-ai-bedrock.md) /
[Pattern 05](aws-patterns/05-agentic-rag.md) /
[Pattern 09](aws-patterns/09-edge-agentic-ai.md) から参照されます。
各パターン側にこの内容を複製しません。

**このリポジトリにエージェントの実装はありません。** 設計論点として書いています。

## 可用性ラベル

各項目には可用性を付けます。3 値です。

| ラベル | 意味 |
|--------|------|
| **Supported today** | 公式ドキュメントに一般提供として記載。URL を併記 |
| **Public preview** | 公式に preview と明示されている |
| **Conceptual** | 公式の裏付けがない構成案。一般提供の機能として書かない |

## 1. 何が「エージェント」か

用語が広く使われるため、このドキュメントでは次を区別します。

| 呼び方 | 何をするか | 設計の難所 |
|---|---|---|
| 単発の推論 | 入力を渡して結果を得る | プロンプトと入力の整形 |
| 検索付き生成 (RAG) | 検索して、取得内容を根拠に生成する | 検索範囲の権限、チャンク設計 |
| エージェント | 何を調べるかを自分で決め、ツールを呼び、複数手順を回す | 停止条件、権限、失敗時の扱い |

**この 3 つは別物です。** 単発で足りる問いにエージェントを使うと、応答時間とコストが増え、
挙動の予測が難しくなります。逆に、複数の情報源をまたぐ判断を単発でやろうとすると、
プロンプトに文脈を詰め込む形になり破綻します。

## 2. 実行基盤

Amazon Bedrock AgentCore は、エージェントの実行に必要な要素を分けて提供します。
**Supported today**（GA、2025-10。[出典](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-available)、
[概要](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)）

| 構成要素 | 対応する設計課題 | 可用性 |
|---|---|---|
| Runtime | エージェントをどこで動かすか。インフラ管理を持たない | Supported today |
| Memory | 会話中の短期保持と、セッションをまたぐ長期保持。エージェント間の共有も可能 | Supported today |
| Gateway | API や関数をツールとして扱う。既存の MCP サーバーにも接続できる | Supported today |
| Identity | ツール呼び出し時の認証 | Supported today |
| Observability | 何が起きたかの追跡 | Supported today |

Runtime には自アカウントの EC2 上で動かす形態もあります
（**Supported today**、2026-08。[出典](https://aws.amazon.com/about-aws/whats-new/2026/08/aws-bedrock-agentcore-runtime-instances-generally-available/)）。
OS・インスタンスタイプ・ネットワーク・ストレージを指定できるため、
既存の VPC 内リソースへの到達性が必要な場合の選択肢になります。

**Lambda で組む場合との違い**は、記憶とツール接続を自前で持つかどうかです。
このリポジトリの現行実装（[`cloud/ai/image_analyzer/`](../../cloud/ai/image_analyzer/)）は
単発の推論を Lambda で組んでいます。単発のままなら置き換える理由はありません。

## 3. コンテキストの取得

エージェントに渡す情報をどこから取るか。このアーキテクチャでは 3 系統あります。

| 情報源 | 取り方 | 向く内容 |
|---|---|---|
| ファイルストレージ上の文書 | S3 Access Point 経由で Knowledge Bases に取り込む（**Supported today**、[出典](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)） | 手順書、図面、報告書 |
| 構造化された分析結果 | SQL クエリの結果をツールとして渡す | 集計値、トレンド、異常の履歴 |
| 時系列の現在値 | 時系列データベースへの問い合わせをツール化する | 設備の現在状態 |

**取得元を増やすほど、権限の設計が難しくなります。** エージェントが持つ権限は、
呼び出した利用者の権限と一致しません。ここが最大の設計上の落とし穴です（§6）。

## 4. 長期保存と記憶の区別

「記憶」と「保存」を混ぜないでください。役割が違います。

| 層 | 何を持つか | 実体 |
|---|---|---|
| エージェントの記憶 | 会話の文脈、セッションをまたぐ学習 | AgentCore Memory |
| ベクトルストア | 検索用の埋め込み表現 | Knowledge Base に紐づくストア |
| 真実の源 | 文書、画像、テレメトリの原本 | ファイルストレージ / データレイク |

**真実の源は AI の外にあります。** 記憶もベクトルも、原本から再構築できる状態を保ちます。
原本を削除したときに記憶とベクトルがどうなるかを設計で決めてください
（[Pattern 05](aws-patterns/05-agentic-rag.md) §ストレージ）。

## 5. 複数エージェントの構成

複数のエージェントに分ける動機は 2 つあります。

- **責務の分離**: 検索担当、判断担当、実行担当を分ける。各エージェントの権限を絞れる
- **権限境界の分離**: 扱えるデータの範囲でエージェントを分ける。§6 の対処の 1 つ

分けたときに決めることが 3 つあります。

| 決めること | 判断の材料 |
|---|---|
| 記憶の共有範囲 | 共有すると文脈が繋がる。分けると情報の流出範囲が狭まる |
| 呼び出しの方向 | 一方向にすると挙動が読める。相互呼び出しは停止条件が難しくなる |
| 失敗の扱い | 途中のエージェントが失敗したとき、全体を止めるか部分結果を返すか |

**停止条件を先に決めてください。** エージェントが自分で次の手を決める構造では、
上限（手数、時間、コスト）を外から与えないと止まりません。

## 6. データガバナンス

**このアーキテクチャでエージェントを載せるとき、最も注意が必要なのは権限の非対称です。**

ファイル共有では利用者ごとに見える文書が違います。エージェントが単一の資格情報で
全文書を検索できると、その区別は失われます。利用者が本来アクセスできない情報が
回答に現れる可能性があります。

対処の方向と trade-off は [Pattern 05](aws-patterns/05-agentic-rag.md) §セキュリティ に
表で整理しています。加えて、このアーキテクチャ固有の点が 3 つあります。

- **S3 Access Point の認可は 2 層です。** IAM で許可しても、access point に紐づいた
  ファイルシステムユーザーがファイルへの権限を持たなければ拒否されます
  （[出典](s3ap-compatibility-matrix.md)）。エージェントの権限設計はこの 2 層を通ります
- **カタログ権限とデータ権限を二重管理にしない。** Lake Formation のテーブル権限は
  背後のデータへのアクセスにも及ぶ拡張が入っています（[セキュリティ設計](security-design.md)）
- **データ所在の要件がある場合**、クラウドの大型モデルに送れないデータが出ます。
  その場合は判断をエッジに置く構成（[Pattern 09](aws-patterns/09-edge-agentic-ai.md)）か、
  ハイブリッド構成を検討します。AWS が
  [データ所在要件下での RAG の構成例](https://aws.amazon.com/blogs/machine-learning/implement-rag-while-meeting-data-residency-requirements-using-aws-hybrid-and-edge-services/)
  を公開しています

### 監査可能性

エージェントは複数の手順を自分で決めるため、「なぜその結論になったか」が
記録されていないと後から検証できません。残すものは 3 つです。

| 残すもの | なぜ必要か |
|---|---|
| 呼び出した情報源と取得した内容 | 根拠の検証 |
| ツール呼び出しの記録 | 副作用（業務システムへの書き込み等）の追跡 |
| 生成物と入力の対応 | 同じ入力で同じ出力が返るとは限らないため |

## 7. 未確認・未実装の項目

| 項目 | 状態 |
|---|---|
| このリポジトリでのエージェント実装 | なし |
| MCP サーバー経由のツール接続の検証 | 未実施 |
| AgentCore Memory と真実の源の同期設計 | 未設計 |
| 権限境界ごとに Knowledge Base を分ける場合の運用負荷 | 未検証 |
| エッジ側でのエージェント実行 | 未実施（[Pattern 09](aws-patterns/09-edge-agentic-ai.md)） |

## 参考

- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [AgentCore リリースノート](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
- [AWS Prescriptive Guidance: Amazon Bedrock AgentCore](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/amazon-bedrock-agentcore.html)
- [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)
- [Edge AI and global inference distribution](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/edge-ai.html)
- 関連: [パターンカタログ](aws-patterns/README.md) /
  [Flexible AI Data Layer](flexible-ai-data-layer.md)
