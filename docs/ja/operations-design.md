# 運用設計: SLI/SLO・Observability・AI評価・Runbook

> 作成日: 2026-05-29  
> 対象: PoC #1 (3Dプリント品質監視) / PoC #2 (ONTAPテレメトリ)  
> ステータス: Draft  
> レビュー元ペルソナ: Observability/SRE Advocate, Data+AI Architect, Analytics Architect

---

## 1. SLI / SLO 定義

### 1.1 サービスレベル指標 (SLI)

| SLI | 定義 | 測定方法 | 対象 |
|-----|------|---------|------|
| キャプチャ成功率 | 撮影試行のうち成功した割合 | `captures_success / captures_total` | エッジ (Pi) |
| NFS 書き込み成功率 | NFS 書き込み試行のうち成功した割合 | `nfs_writes_success / nfs_writes_total` | エッジ → ONTAP |
| 分析レスポンス時間 | 画像アップロードからアラート発行までの時間 | Lambda Duration + Bedrock latency | クラウド |
| アラート配信成功率 | SNS Publish のうち配信成功した割合 | `sns_delivered / sns_published` | クラウド |
| デバイス稼働率 | ヘルスレポートが期待通り到着した割合 | `heartbeats_received / heartbeats_expected` | エッジ |

### 1.2 サービスレベル目標 (SLO)

| SLO | 目標値 | 測定期間 | エラーバジェット |
|-----|--------|---------|----------------|
| キャプチャ成功率 | ≥ 99.5% | 30日間 | 7.2時間/月 の停止許容 |
| NFS 書き込み成功率 | ≥ 99.0% | 30日間 | 14.4時間/月 (ローカルバッファで吸収) |
| 分析レスポンス (p95) | ≤ 30秒 | 30日間 | 5%のリクエストは30秒超過可 |
| アラート配信成功率 | ≥ 99.9% | 30日間 | 月43秒の配信失敗許容 |
| デバイス稼働率 | ≥ 95.0% | 30日間 | 36時間/月 の停止許容 |

### 1.3 SLO 違反時のアクション

| SLO | 違反時のアクション |
|-----|------------------|
| キャプチャ成功率 < 99.5% | カメラ接続確認、Pi 再起動、カメラ交換検討 |
| NFS 書き込み成功率 < 99.0% | NFS マウント確認、ONTAP ステータス確認、ネットワーク確認 |
| 分析レスポンス > 30秒 (p95) | Bedrock スロットリング確認、画像サイズ最適化 |
| デバイス稼働率 < 95.0% | Pi ハードウェア確認、電源安定性確認、OS 更新確認 |

---

## 2. メトリクス設計

### 2.1 ビジネスメトリクス（CloudWatch カスタムメトリクス）

| メトリクス名 | 単位 | 説明 | アラーム条件 |
|-------------|------|------|-------------|
| `PrintQuality/AnomalyRate` | Percent | 異常検出率 (直近1時間) | > 30% で通知 (プリンター問題の可能性) |
| `PrintQuality/QualityScore` | None (0-100) | 平均品質スコア (直近1時間) | < 50 で通知 |
| `PrintQuality/CaptureGap` | Seconds | 最後のキャプチャからの経過時間 | > 300秒 (5分) でデバイス停止アラート |
| `PrintQuality/CostPerImage` | USD | 1画像あたりの分析コスト | > $0.02 でコスト異常アラート |
| `ONTAP/CapacityUsedPercent` | Percent | ボリューム使用率 | > 80% で容量警告 |
| `ONTAP/LatencyP95` | Microseconds | レイテンシ p95 | > 5000μs で性能警告 |

### 2.2 技術メトリクス（既存 CloudWatch）

| メトリクス | ソース | 用途 |
|-----------|--------|------|
| Lambda Invocations/Errors/Duration | AWS/Lambda | 処理パイプラインの健全性 |
| Kinesis IncomingRecords/Bytes | AWS/Kinesis | データ取り込み量 |
| S3 BucketSizeBytes/NumberOfObjects | AWS/S3 | ストレージ成長率 |
| SNS NumberOfMessagesPublished | AWS/SNS | アラート発行頻度 |

### 2.3 Correlation ID 設計

すべてのログ・メトリクスに `message_id` を含め、横断追跡を可能にする:

```
[Pi: capture] message_id=abc-123 → 
[ONTAP: NFS write] message_id=abc-123 →
[Lambda: analyze] message_id=abc-123 →
[Bedrock: invoke] message_id=abc-123 →
[SNS: alert] message_id=abc-123
```

**CloudWatch Logs Insights クエリ例:**
```
fields @timestamp, @message
| filter message_id = "abc-123"
| sort @timestamp asc
```

---

## 3. AI 精度フィードバックループ

### 3.1 課題

AI分析の精度は時間とともに劣化する可能性がある（プリンター変更、フィラメント変更、照明変化）。継続的な精度評価とフィードバックが必要。

### 3.2 フィードバックループ設計

```
[画像キャプチャ] → [AI分析] → [結果保存]
                                    ↓
                            [オペレーター確認]
                                    ↓
                            [フィードバック記録]
                            ├── 正解 (True Positive / True Negative)
                            └── 誤り (False Positive / False Negative)
                                    ↓
                            [週次精度レポート]
                                    ↓
                            [プロンプト改善 / 閾値調整]
```

### 3.3 フィードバック記録スキーマ

```json
{
  "feedback_id": "uuid",
  "source_message_id": "分析対象の message_id",
  "timestamp": "2026-05-29T12:00:00Z",
  "ai_prediction": {
    "status": "anomaly_detected",
    "confidence": 0.87,
    "anomaly_type": "stringing"
  },
  "human_judgment": {
    "correct": false,
    "actual_status": "normal",
    "notes": "照明の反射をストリンギングと誤検出"
  },
  "feedback_type": "false_positive"
}
```

### 3.4 精度メトリクス（週次計算）

| メトリクス | 計算式 | 目標 |
|-----------|--------|------|
| Precision | TP / (TP + FP) | ≥ 90% |
| Recall | TP / (TP + FN) | ≥ 80% |
| F1 Score | 2 × (P × R) / (P + R) | ≥ 85% |
| False Positive Rate | FP / (FP + TN) | ≤ 10% |

### 3.5 精度劣化時のアクション

| 状況 | アクション |
|------|-----------|
| FP率 > 10% | プロンプトの「保守的判定」強化、confidence 閾値引き上げ |
| Recall < 80% | プロンプトに見逃しパターンの例を追加 |
| 新しい欠陥タイプ出現 | プロンプトに新タイプを追加、テストケース追加 |
| 環境変化（照明、カメラ位置） | キャリブレーション画像で再テスト |

---

## 4. データリネージ + メダリオンアーキテクチャ

### 4.1 メダリオン対応

| 本プロジェクトの層 | メダリオン | 説明 |
|------------------|-----------|------|
| `raw/` | Bronze | 原本データ。変更不可。到着したままの形式 |
| `processed/` | Silver | クレンジング・構造化済み。Parquet 変換、スキーマ適用 |
| `curated/` | Gold | ビジネス用途に最適化。集計、サマリー、ML特徴量 |

### 4.2 データリネージ追跡

```
[Bronze: raw/image_capture/]
    │ message_id: abc-123
    │ s3_key: raw/image_capture/year=2026/.../image.jpg
    ↓
[Silver: processed/image_analysis/]
    │ source_message_id: abc-123 (← Bronze への参照)
    │ analyzer: bedrock/claude-sonnet-4.5
    │ result: anomaly_detected
    ↓
[Gold: curated/print_quality_summary/]
    │ aggregation: daily summary
    │ source: processed/image_analysis/ (日付パーティション)
    ↓
[Action: SNS Alert / Dashboard / Feedback]
```

### 4.3 リネージメタデータ

各レコードに以下を含める:

| フィールド | 層 | 説明 |
|-----------|-----|------|
| `message_id` | Bronze | 原本の一意ID |
| `source_message_id` | Silver | Bronze レコードへの参照 |
| `processing_timestamp` | Silver/Gold | 加工日時 |
| `processing_job_id` | Silver/Gold | Glue Job Run ID |
| `schema_version` | 全層 | スキーマバージョン |

---

## 5. Runbook

### 5.1 アラート: デバイス停止 (CaptureGap > 5分)

```
症状: 5分以上キャプチャが到着しない
影響: 印刷中の異常を検出できない

手順:
1. SORACOM コンソールでデバイスのオンライン状態を確認
   → オフライン: Step 2 へ
   → オンライン: Step 3 へ

2. [デバイスオフライン]
   a. 電源確認（USB-C 接続、LED 点灯）
   b. ネットワーク確認（Ethernet LED、セルラー LED）
   c. SORACOM Napter で SSH 接続試行
   d. 接続不可 → 現地対応（再起動 or 交換）

3. [デバイスオンライン but キャプチャなし]
   a. SSH 接続: ssh iot-operator@<PI_IP>
   b. サービス状態確認: systemctl status edge-camera
   c. ログ確認: journalctl -u edge-camera --since "5 min ago"
   d. カメラ確認: v4l2-ctl --list-devices
   e. ディスク確認: df -h /var/lib/edge-camera
   f. 問題特定 → 再起動 or 設定修正

復旧確認: CloudWatch で CaptureGap が 60秒以下に戻ること
```

### 5.2 アラート: Lambda エラー多発 (> 3回/5分)

```
症状: 画像分析 Lambda が連続エラー
影響: 異常検出が停止、アラートが出ない

手順:
1. CloudWatch Logs で Lambda エラーログを確認
   → Bedrock throttling: Step 2 へ
   → S3 access denied: Step 3 へ
   → Timeout: Step 4 へ

2. [Bedrock throttling]
   a. Bedrock コンソールでモデルのスロットリング状態確認
   b. 一時的 → 自動復旧を待つ (5-10分)
   c. 継続的 → Provisioned Throughput 検討 or 撮影間隔延長

3. [S3 access denied]
   a. IAM ロールのポリシー確認
   b. S3 バケットポリシー確認
   c. KMS キーポリシー確認

4. [Timeout]
   a. 画像サイズ確認 (大きすぎないか)
   b. Lambda メモリ/タイムアウト設定確認
   c. Bedrock レスポンス時間確認

復旧確認: Lambda Errors メトリクスが 0 に戻ること
```

### 5.3 アラート: 異常検出率が高い (> 30%/1時間)

```
症状: 1時間の異常検出率が30%を超えている
影響: プリンターに実際の問題がある可能性

手順:
1. 直近の分析結果を確認 (S3 processed/image_analysis/)
   → 同じ anomaly_type が連続: Step 2 へ
   → 多様な anomaly_type: Step 3 へ

2. [同一タイプの連続異常]
   a. プリンターの状態を目視確認
   b. 異常が実在 → プリンター停止、原因対処
   c. 誤検知 → フィードバック記録、プロンプト調整検討

3. [多様な異常タイプ]
   a. カメラ位置/照明の変化がないか確認
   b. フィラメント変更がないか確認
   c. 環境変化 → キャリブレーション実施

復旧確認: 異常検出率が 10% 以下に戻ること
```

### 5.4 アラート: ONTAP 容量警告 (> 80%)

```
症状: ONTAP ボリュームの使用率が 80% を超えた
影響: 新規画像の保存に支障が出る可能性

手順:
1. ONTAP REST API で容量詳細を確認
   curl -k -u svc-iot-telemetry https://<ONTAP>/api/storage/volumes?fields=space

2. 古いデータの確認
   a. 90日以上前の raw 画像 → S3 に移行済みか確認
   b. 移行済み → ONTAP 上の古いファイルを削除
   c. 未移行 → SnapMirror 同期を実行してから削除

3. 容量追加が必要な場合
   a. ボリュームの自動拡張設定を確認
   b. アグリゲートの空き容量を確認
   c. 必要に応じてディスク追加 or ボリューム拡張

復旧確認: 使用率が 70% 以下に戻ること
```

### 5.5 エスカレーションフロー

```
[アラート発生]
    │
    ▼ (0-5分)
[L1: 自動対応]
    担当: システム (自動復旧スクリプト)
    対象: 一時的なエラー、自動リトライで解決するもの
    │
    │ 自動復旧失敗
    ▼ (5-15分)
[L2: オペレーター対応]
    担当: 当番オペレーター (Slack通知で認知)
    対象: Runbook に従って手動対応
    手段: SSH、SORACOM Napter、AWS コンソール
    │
    │ Runbook で解決不可
    ▼ (15-60分)
[L3: エンジニア対応]
    担当: 開発エンジニア (電話/PagerDuty)
    対象: コード修正、設定変更、インフラ変更が必要
    │
    │ 重大インシデント (データ損失、セキュリティ)
    ▼ (即時)
[L4: マネージャー判断]
    担当: プロジェクトマネージャー
    対象: サービス停止判断、顧客通知、根本対策の優先度決定
```

| レベル | 対応時間目標 | 通知手段 | 判断権限 |
|--------|------------|---------|---------|
| L1 | 即時 (自動) | — | 自動スクリプト |
| L2 | 15分以内 | Slack | サービス再起動、デバイス再起動 |
| L3 | 1時間以内 | 電話/PagerDuty | コード修正、設定変更 |
| L4 | 即時 (重大時) | 電話 | サービス停止、顧客通知 |

> **PoC フェーズ**: L1-L2 のみ運用。L3-L4 は本番移行時に正式化。

---

## 6. 将来の Iceberg 移行判断基準

現在は Parquet + Hive-style partition で運用。以下の条件が発生した場合に Apache Iceberg への移行を検討する:

| トリガー条件 | 理由 |
|-------------|------|
| レコード単位の Update/Delete が必要になった | GDPR 対応、誤データ修正 |
| 同時書き込みが発生する | 複数デバイスが同一テーブルに書き込み |
| スキーマ変更が頻繁になった | フィールド追加/型変更が月1回以上 |
| タイムトラベル（過去データ参照）が必要 | 監査、再現性検証 |
| データ量が 1TB を超えた | メタデータ管理の効率化 |
| 複数クエリエンジンからのアクセス | Athena + Redshift + EMR |

**現時点で Iceberg が不要な理由:**
- Append-only ワークロード（画像メタデータ、センサーデータ）
- 単一書き込み元（Kinesis Firehose / Glue ETL）
- データ量が小さい（PoC: 数GB/月）
- クエリエンジンは Athena のみ
