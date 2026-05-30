# Design: ONTAP Telemetry Analytics

## 設計判断

### なぜ REST API ポーリングか

| 選択肢 | 仕組み | リアルタイム性 | 採用 |
|--------|--------|-------------|------|
| **REST API ポーリング** | Pi が 1分間隔で GET | 1分遅延 | ✅ シンプル、十分 |
| SNMP トラップ | ONTAP → Pi に push | 即時 | ❌ 設定複雑、Pi で SNMP サーバー必要 |
| Active IQ / Cloud Insights | SaaS 経由 | 数分遅延 | ❌ 外部依存、カスタマイズ困難 |
| EMS イベント | ONTAP → syslog → Pi | 即時 | △ イベントのみ、定期メトリクスに不向き |

PoC では 1分間隔のポーリングで十分。REST API は ONTAP 9.x 標準搭載で追加設定不要。

### なぜ NFS に JSON で保存するか

| 選択肢 | 保存先 | 分析方法 | 採用 |
|--------|--------|---------|------|
| **NFS → JSON ファイル** | ONTAP ボリューム | SnapMirror → S3 AP → Athena | ✅ |
| 直接 S3 PUT | S3 バケット | Athena 直接 | △ ONTAP 集約の設計に合わない |
| InfluxDB / Prometheus | 時系列 DB | Grafana | △ 追加インフラ必要 |
| CloudWatch PutMetricData | CloudWatch | ダッシュボード | △ 詳細分析に不向き |

ONTAP に集約する設計方針に従い、NFS に JSON で保存。
SnapMirror で FSx for ONTAP に同期後、S3 AP 経由で Athena 分析。

### なぜ Parquet 変換するか (Glue ETL)

- JSON のまま Athena クエリ: スキャン量大、コスト高
- Parquet: カラムナ形式、圧縮効率高、Athena スキャン量 90% 削減
- Glue ETL で日次変換: raw (JSON) → processed (Parquet)

### 容量予測の手法

| 手法 | 複雑さ | 精度 | 採用フェーズ |
|------|--------|------|------------|
| 線形回帰 (Athena SQL) | 低 | 中 | Phase 2 |
| SageMaker Random Cut Forest | 中 | 高 | Phase 3 |
| SageMaker DeepAR | 高 | 高 | 本番 |

Phase 2 では Athena SQL の線形回帰で「あと何日で満杯か」を概算。
Phase 3 で SageMaker の時系列モデルに移行。

## 代替案として検討したもの

| 代替案 | 不採用理由 |
|--------|-----------|
| NetApp Cloud Insights | SaaS 依存。カスタム分析・AI 連携が困難 |
| Prometheus + Grafana (オンプレ) | 追加インフラの運用負荷。クラウド分析基盤がない課題を解決しない |
| ONTAP → Kinesis 直接 | ONTAP から Kinesis に直接送る手段がない |
| Pi → CloudWatch Metrics のみ | 詳細な時系列分析に不向き。保持期間制限あり |

## セキュリティ上の判断

- REST API サービスアカウントは readonly ロール（書き込み権限なし）
- Pi からの HTTPS 接続のみ許可（firewall-policy で IP 制限）
- パスワードは systemd EnvironmentFile で管理（コードに含めない）
- テレメトリデータは「社内」分類（インフラ構成情報を含む）
