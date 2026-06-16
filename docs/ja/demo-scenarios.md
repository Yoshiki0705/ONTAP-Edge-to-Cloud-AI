# デモシナリオ

> 作成日: 2026-06-16
> 対象: 3Dプリント品質監視 PoC
> 目的: 関係者（社内エンジニア、パートナー、データ基盤チーム）に価値を伝える

---

## 0. デモの設計原則

- **30秒で価値が伝わること**: 「印刷中 → 異常発生 → 即座にアラート」を体験させる
- **作り込みすぎない**: ライブデモは失敗しうる。録画版とライブ版を用意
- **役割ごとに見せ方を変える**: 経営層には結果、エンジニアには仕組み

---

## デモ 1: 30秒 品質異常検知（メインデモ）

### 目的
「無人運転中の 3D プリンターで異常が起きたら、AI が自動検知してアラートを出す」を 30 秒で見せる。

### 登場人物
- プレゼンター（操作）
- 観客（社内エンジニア / パートナー / 顧客）

### 事前準備
| 項目 | 状態 |
|------|------|
| Pi + カメラが 3D プリンターを撮影中 | 稼働 |
| `simple_capture.py --loop` 実行中 | 稼働 |
| ClickHouse ダッシュボード（Grafana）表示 | 画面共有 |
| Slack / SNS アラート画面 | 画面共有 |
| 異常を意図的に起こせる準備（フィラメント抜き or 既知の失敗モデル） | 準備 |

### タイムライン（30秒）

| 時間 | アクション | 画面 |
|------|-----------|------|
| 0-5秒 | 「正常に印刷中。カメラが 60 秒ごとに撮影し AI が判定しています」 | ダッシュボードに緑の "normal" が並ぶ |
| 5-10秒 | 異常を発生させる（フィラメントを抜く / 失敗モデルに切替） | プリンターの状態が変化 |
| 10-25秒 | 次のキャプチャ → ONTAP 保存 → Lambda → Bedrock 分析 | ダッシュボードに赤い "anomaly_detected" が出現 |
| 25-30秒 | Slack にアラート通知が届く | 通知ポップアップ + 異常画像 + 推奨アクション |

### 観客に響くポイント
- **データはローカル（ONTAP）に蓄積**されつつ、AI 判定だけクラウド
- **カスタムモデル学習不要**（プロンプトのみ）
- **異常画像と推奨アクションがセット**で届く

### 失敗時のフォールバック
- ライブで異常が検知されない場合 → 録画版を再生
- ネットワーク不調 → 事前キャプチャ済み画像で Lambda を手動 invoke

---

## デモ 2: 切断復旧（レジリエンス）

### 目的
「工場のネットワークが不安定でもデータは失われない」を見せる。

### タイムライン（2分）

| 時間 | アクション | 期待される動作 |
|------|-----------|--------------|
| 0:00 | 正常稼働を確認（Kafka に publish されている） | ダッシュボードにイベント流入 |
| 0:20 | Kafka broker を停止（`docker stop kafka` or VM 停止） | publish 失敗 |
| 0:30 | キャプチャ継続。ログに "buffered" 表示 | ローカルバッファに JSON 蓄積 |
| 0:50 | バッファディレクトリを見せる（`ls /tmp/kafka-buffer/`） | ファイルが増えている |
| 1:00 | Kafka broker を再起動 | broker 復帰 |
| 1:10 | `replay_buffer()` 実行（or 自動リプレイ） | バッファ → Kafka へ時系列順送信 |
| 1:30 | ダッシュボードを確認 | 切断中のデータも欠損なく到着 |
| 2:00 | dead_letter_events が空であることを確認 | データロスゼロ |

### 観客に響くポイント
- **ONTAP への保存は切断の影響を受けない**（NFS はローカル LAN）
- **Kafka 断は自動バッファ → 復旧後リプレイ**
- **冪等性（event_id 重複排除）でリプレイ時の重複なし**

### 検証コマンド
```bash
# 切断前後のイベント数が一致することを確認
clickhouse-client --query "
  SELECT count(), uniqExact(event_id)
  FROM kafka_events_raw
  WHERE timestamp BETWEEN '<demo_start>' AND '<demo_end>'
"
# count() == uniqExact(event_id) なら重複なし
```

---

## デモ 3: ペイロード参照（ONTAP ↔ イベント橋渡し）

### 目的
「ダッシュボードの異常イベントから、元の画像（ONTAP 上）に即座に遡れる」を見せる。

### タイムライン（1分）

| 時間 | アクション | 画面 |
|------|-----------|------|
| 0:00 | ダッシュボードで異常イベントを選択 | anomaly_events の行 |
| 0:15 | payload_manifest を JOIN して payload_uri を取得 | `nfs://svm-iot/vol_images/.../image.jpg` |
| 0:30 | ONTAP 上の実画像を開く | 異常が映った画像 |
| 0:45 | 同じ画像が Bedrock 分析でどう判定されたか確認 | quality_events の verdict + confidence |

### 観客に響くポイント
- **メタデータ（軽量・高速）と原本（大容量）の分離**
- **イベントから原本へのトレーサビリティ**
- **ONTAP がデータの真実の保管場所**

### 検証クエリ
```sql
SELECT a.timestamp, a.anomaly_type, a.severity,
       p.payload_uri, q.confidence
FROM anomaly_events a
JOIN payload_manifest p ON a.trigger_event_id = p.event_id
JOIN quality_events q ON a.trigger_event_id = q.source_event_id
WHERE a.timestamp > now() - INTERVAL 1 HOUR
ORDER BY a.timestamp DESC;
```

---

## デモ 4: AI 精度フィードバックループ

### 目的
「AI の判定が間違っていたら、人が修正でき、それが学習データになる」を見せる。

### タイムライン（1.5分）

| 時間 | アクション | 画面 |
|------|-----------|------|
| 0:00 | 誤検知の例を表示（正常なのに anomaly 判定） | quality_events |
| 0:20 | feedback_recorder にフィードバック送信（correct=false） | API 呼び出し |
| 0:40 | feedback_events に記録される | ClickHouse |
| 1:00 | 週次精度レポートクエリを実行 | accuracy / precision / recall |
| 1:20 | このラベルが training_features に流れることを説明 | Databricks Gold dataset |

### 観客に響くポイント
- **AI 判定は最終決定ではなく参考情報**（人がループに入る）
- **フィードバックが学習データセットに直結**（Databricks へ）
- **精度を継続的に測定・改善できる**

---

## デモ環境チェックリスト

### ライブデモ前（30分前）
- [ ] Pi + カメラが稼働、撮影できている
- [ ] `simple_capture.py --loop` が動いている
- [ ] Kafka broker 稼働、ClickHouse 取り込み確認
- [ ] Grafana ダッシュボードが表示できる
- [ ] Slack / SNS 通知が届く状態
- [ ] 異常発生の手段を準備（フィラメント or 失敗モデル）
- [ ] 録画版を再生できる状態（フォールバック）

### デモ後
- [ ] デモ中に生成したデータに `is_synthetic` or デモ用タグ
- [ ] バッファをクリア（`/tmp/kafka-buffer/`）
- [ ] ダッシュボードをデモ前の状態にリセット

---

## デモ用データ vs 本番データの区別

デモ中のデータは `is_synthetic` フラグ、または専用の `site_id = "demo"` で区別し、本番の品質指標に混入させない。

```bash
# デモ用に site_id を上書きして実行
SITE_ID=demo python3 simple_capture.py --loop
```
