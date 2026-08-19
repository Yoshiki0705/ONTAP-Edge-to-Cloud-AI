# Design: 3D Print Quality Monitoring

## 設計判断

### なぜ 2段階 AI 分析か

| 選択肢 | 呼び出しの構成 | 精度 | 採用 |
|--------|--------------|------|------|
| Sonnet のみ（全画像） | 全画像 × 高精度モデル | 高 | ❌ 呼び出し単価が支配的になる |
| Haiku のみ | 全画像 × 安価モデル | 中 | ❌ 詳細分析が得られない |
| **Haiku → Sonnet (異常時のみ)** | **全画像 × 安価 + 異常率 × 高精度** | **高** | ✅ |

Haiku で高速スクリーニング（正常/異常の二値判定）し、異常疑いのみ Sonnet で詳細分析。
削減幅は異常率で決まる。異常率が上がるほど 2 段目が増えて縮み、異常率 100% では
スクリーニングが純粋な追加になるため 2 段構成のほうが高くなる。

> **金額を書かない理由**: 以前この表には月額（$259 / $15 / $40）があったが、出典の異なる
> 単価から来ていて、同じ前提に対してリポジトリ内で 3 通りの答えが出ていたため撤回した。
> 式・価格基準日・現行単価は [コストモデル](../../docs/ja/cost-model.md) にある。
> トークン数は `InputTokens` / `OutputTokens` メトリクスで実測できる。

### なぜ Pi が直接 Lambda を invoke するか（PoC Phase 1）

| 選択肢 | 仕組み | 複雑さ | 採用 |
|--------|--------|--------|------|
| **Pi → Lambda 直接** | Pi が NFS 書き込み後に invoke | 低 | ✅ Phase 1 |
| Pi を FPolicy サーバーに | ONTAP → Pi → Lambda | 中 | Phase 2 |
| 専用 FPolicy サーバー (EC2) | ONTAP → EC2 → Lambda | 高 | 本番 |

PoC では Pi が自分の書き込みを知っているため直接 invoke が最もシンプル。
FPolicy は Phase 2 で「他デバイスからの書き込み検知」に使用。

### なぜ S3 に直接 PUT するか（PoC shortcut）

本来の構成: ONTAP → SnapMirror → FSx for ONTAP → S3 AP → Lambda がアクセス

PoC Phase 1 では SnapMirror/FSx for ONTAP が未構成のため、Pi が S3 に直接 PUT して Lambda に渡す。
Phase 3 で SnapMirror 構成後に S3 AP 経由に移行。

### なぜ NFS v4.1 か

| プロトコル | 暗号化 | 認証 | 採用 |
|-----------|--------|------|------|
| NFS v3 | なし | IP ベース | ❌ セキュリティ不足 |
| **NFS v4.1** | Kerberos 対応 | ユーザーベース | ✅ |
| SMB 3.0 | AES 暗号化 | AD 認証 | Windows 機のみ |

Pi は Linux なので NFS。v4.1 は Kerberos 対応で本番セキュリティ要件を満たす。
PoC では専用 VLAN で代替。

## 代替案として検討したもの

| 代替案 | 不採用理由 |
|--------|-----------|
| AWS IoT Core + MQTT | ONTAP に集約する設計と合わない。デバイスが直接クラウドに送る構成 |
| S3 Event Notification → Lambda | FSx for ONTAP S3 AP はイベント通知非対応 |
| Kinesis Video Streams | 動画ストリーミングは過剰。静止画で十分 |
| Rekognition Custom Labels のみ | カスタムモデル学習が必要。プロンプトベースの方が柔軟 |
| エッジ推論のみ (TFLite) | Pi の計算能力では精度不足。クラウド AI が必要 |

## セキュリティ上の判断

- Pi に AWS Access Key を置かない → `aws configure` で IAM ユーザーの一時認証を使用
- 画像データは機密の可能性 → S3 SSE-KMS + ONTAP NVE で暗号化
- FPolicy サーバー (Phase 2) は専用 VLAN に隔離
- Lambda の IAM ロールは最小権限（GetObject, InvokeModel, PutObject, Publish のみ）
