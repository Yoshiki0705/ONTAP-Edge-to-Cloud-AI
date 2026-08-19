# Design: 3D Print Quality Monitoring

## 設計判断

### なぜ 2段階 AI 分析か

| 選択肢 | コスト/月 | 精度 | 採用 |
|--------|----------|------|------|
| Sonnet のみ（全画像） | ~$259 | 高 | ❌ コスト過大 |
| Haiku のみ | ~$15 | 中 | ❌ 詳細分析不足 |
| **Haiku → Sonnet (異常時のみ)** | **~$40** | **高** | ✅ |

Haiku で高速スクリーニング（正常/異常の二値判定）し、異常疑いのみ Sonnet で詳細分析。
正常画像が大半の環境ではコストが約 85% 下がる。

> **上表の前提**: 60 秒間隔・24 時間連続稼働・異常率 10%・特定リージョンのモデル料金による
> 試算であり、実測値ではない。異常率が下がると Sonnet の呼び出しが減るため削減幅は小さくなる
> （実際の欠陥率 2-5% を仮定した場合の試算は [tests/sample_images/README.md](../../tests/sample_images/README.md)）。
> モデル料金は変動するため、判断前に AWS Pricing Calculator で再計算すること。

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
