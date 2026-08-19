> 🌐 Language: **日本語** | [English](../en/verification-status.md)

# 検証状態

> **最終更新**: 2026-08-19

このリポジトリのどのコードがどこまで実際に動かされたか、どの数値をどの根拠で引けるかを
記録します。「テストが通る」ことは「本番で動く」ことと同じではありません。実行していない
段を実行済みと書くと、PoC の現場で最初に壊れる箇所が読者から見えなくなります。

## 結論

**AWS の実機で測定したのは Amazon Bedrock の 2 段階分析だけです。** エッジデバイスと
FSx for ONTAP を含む経路は実行していません。SAM テンプレートは cfn-lint と単体テストを
通っていますが、スタックを作成した記録はありません。

## 2 つの軸を分ける理由

「コードがどこまで動いたか」と「数値をどの根拠で引けるか」は別の問いです。1 つの段階表に
混ぜると、単体テストが通ったことを本番で動く根拠として引用でき、公開価格からの手計算を
実測値として引用できてしまいます。ここでは軸を分け、それぞれ既に公開されている語彙を
そのまま使います。新しい語彙は作りません。

## コードの実行状況

### 段階の定義

[FSx for ONTAP S3 Access Points Serverless Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
の実機検証の段階に合わせています。同リポジトリの `DemoMode のみ` はポータル固有なので
`ローカルのみ` に置き換え、`実機 読み取り` は読み書きの区別ではなく段の範囲を表すため
`実機 単体` としています。

| 段階 | 意味 | 読者が期待してよいこと |
|---|---|---|
| 実機 E2E | 経路の全段を実 AWS・実機で通した | その構成でなら動く |
| 実機 単体 | その段だけを実 AWS で実行した。前後の段は接続していない | その段の挙動。経路として動く根拠にはならない |
| 自動テストのみ | 単体テストが通る。AWS では実行していない | コードの形が壊れていないこと |
| ローカルのみ | 手元の Docker などで動かした。AWS では実行していない | 経路の考え方。マネージドサービスとの差は未確認 |
| 未実行 | 実行していない | 何も |

### 経路ごとの状況

| 経路の段 | 段階 | 根拠 |
|---|---|---|
| カメラ → ローカルストレージ (NFS) | 未実行 | エッジデバイスが未到着 |
| ローカルストレージ → FSx for ONTAP 同期 | 未実行 | 実 ONTAP 環境がない |
| FSx for ONTAP → S3 Access Point | 未実行 | 同上 |
| S3 Access Point → AWS Lambda（スクリーニング） | 自動テストのみ | [`tests/`](../../tests/) |
| Amazon Bedrock 2 段階分析 | **実機 単体** | [`tests/sample_images/README.md`](../../tests/sample_images/README.md) |
| 判定結果の保存と通知（Amazon S3 / Amazon SNS） | 自動テストのみ | [`tests/`](../../tests/) |
| 人手フィードバックの記録 | 自動テストのみ | [`tests/`](../../tests/) |
| センサー → AWS IoT Core → AWS Lambda | 自動テストのみ | [`tests/`](../../tests/) |
| AWS Glue / Amazon Athena | 未実行 | テンプレートのみ |
| Kafka / ClickHouse | ローカルのみ | [`local-demo/`](../../local-demo/) |
| ONTAP テレメトリ収集（REST API ポーリング） | 未実行 | 実 ONTAP 環境がない |
| SAM テンプレートのデプロイ | 未実行 | cfn-lint は通る。スタック作成の記録はない |
| スタック撤去（[`scripts/teardown.sh`](../../scripts/teardown.sh)） | 未実行 | 削除順はテンプレートの `Fn::ImportValue` から導出し、引数処理は `aws` を差し替えて確認した。`delete-stack` と `wait` の実行記録はない |

「実機 E2E」の段はまだありません。

## 数値と主張の根拠

### 段階の定義

[FSx for ONTAP Adoption Playbook の evidence-policy](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/evidence-policy.md)
の 4 区分をそのまま使います。定義と昇格・降格の規則は同ドキュメントが正典で、ここには
複製しません。要点だけ再掲すると、`documented` は「一次情報に記載がある」であって
「測った」ではありません。測ったと主張できるのは `verified` だけです。

### 主張ごとの根拠

| 主張 | 区分 | 根拠と併記すべき条件 |
|---|---|---|
| テキスト記述シナリオ 5/5 正解 | `verified` | 2026-05-29 / ap-northeast-1 / `jp.anthropic.claude-sonnet-4-5-20250929-v1:0`。**画像ではなくテキストで書いた症状の記述に対する判定**。視覚判定の精度ではない |
| 実画像 4/4 正解 | `verified` | 同上 + スクリーニング `jp.anthropic.claude-haiku-4-5-20251001-v1:0`。Bambu Lab Wiki と Prusa Help が公開している 4 枚 |
| 合成画像を非実写と識別 | `verified` | 同上。OpenCV で生成した画像に対する別ラウンドの結果 |
| Haiku 平均 1,417 ms / Sonnet 平均 7,186 ms | `verified` | n=4、逐次実行、クライアント側での計測。VPC 内の AWS Lambda からではない |
| 画像あたり $0.005〜0.011 | `documented` | 公開されているモデル料金からの手計算。`cloud/ai/image_analyzer/handler.py` は token usage を取得しないため、請求実績でも API 応答由来でもない |
| 2 段階構成で月 $259 → $40 | `hypothesis` | 60 秒間隔・24 時間連続・異常率 10%・特定リージョンの料金という仮定。異常率が下がれば削減幅は縮む |
| 異常を 60 秒以内に検知 | `hypothesis` | 設計目標。未計測 |
| S3 Access Point は ONTAP 9.17.1 以降が必要 | `documented` | AWS 公式ドキュメント。[S3 AP 互換性と制約](s3ap-compatibility-matrix.md) |
| S3 Access Point はイベント通知に対応しない | `documented` | 同上。FPolicy / 明示的な呼び出し / ポーリングで補う |
| FlexCache write-back は 9.15.1 以降。ただし本番非推奨 | `documented` | NetApp のガイドラインと FAQ。[Greengrass + FlexCache 連携](iot-greengrass-flexcache-integration.md) |
| 実環境での判定精度 | — | 主張していません。照明・カメラ角度・フィラメント色の影響は未確認 |

## 数値を公開するときに併記するもの

必須項目は
[evidence-policy の「数値を書くときの必須条件」](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/ja/evidence-policy.md)
が正典です。このリポジトリで測る対象に当てはめると、計測日、リージョン、モデル ID または
推論プロファイル、AWS Lambda のメモリ設定と VPC の内外、画像サイズ、試行回数、並列度、
そして**どこで時間を測ったか**（クライアント側かサービス側か）になります。

これらを欠いた数値は再現できないので、比較にも見積りにも使えません。上の表で
`jp.` 接頭辞まで書いているのはそのためです。接頭辞が違えば別の推論プロファイルで、
経路も課金も変わります。

## 測っていない項目

埋めていません。測っていないことを空欄にすると、忘れたのか測って出なかったのかが
読者から区別できません。

| 項目 | 理由 |
|---|---|
| S3 Access Point 経由のスループットとレイテンシ | 実 ONTAP 環境がない。測る場合は下記の姉妹リポジトリの harness を流用する |
| 請求実績 | スタックをデプロイした記録がない。公開価格からの試算しかない |
| エッジからクラウドまでの end-to-end 遅延 | エッジデバイスが未到着 |
| 複数デバイスの同時運用とスケールアウト | 同上 |
| 実環境での判定精度 | 同上。公開画像での結果は撮影条件が違う |
| visual-inspection の判定精度 | 未検証。3d-print-quality で測った精度は対象物も欠陥の種類も違うので根拠にならない |
| VPC 内の AWS Lambda から見た Bedrock のレイテンシ | 記録した測定はクライアント側から。経路が違う |
| ONTAP のバージョン | 実環境がないため取得できていない。上の `documented` 行は公式ドキュメントの記載であって、この環境で確認した値ではない |

## 姉妹リポジトリの数値を引くときの条件

環境が併記されていない数値は引き写しません。引くときは出典リポジトリと環境をそのまま
併記します。

- **S3 Access Point の操作レイテンシ** は
  [s3-burst-on-ontap-files](https://github.com/Yoshiki0705/s3-burst-on-ontap-files)
  に測定があります。ただし 64 B・並列度 1・SINGLE_AZ_1 / 128 MBps・**AWS 外から
  インターネット経由**という条件です。このリポジトリが想定する VPC 内の AWS Lambda から
  S3 Access Point を読む経路とは条件が重なりません。そのまま設計根拠にはできません。
- **ONTAP REST API の落とし穴**（HTTP 202 とジョブのポーリング、エラーコード、
  EMS ペイロードのキー形式）は
  [fsxn-observability-integrations](https://github.com/Yoshiki0705/fsxn-observability-integrations)
  に実機で確認した記録があります。ONTAP テレメトリ収集を実装するときはこちらを参照し、
  同じ調査をやり直しません。
- 同リポジトリには ONTAP の性能カウンタを収集する実装は**ありません**。メトリクス収集は
  NetApp Harvest に委ねられています。このリポジトリの REST API ポーリングと重複しません。

## 記録の訂正

証跡と突き合わせて見つかった食い違いです。

- **「9/9 正解」は 2 つの異なるテストの合算でした。** テキスト記述シナリオ 5 件と実画像
  4 枚を足した数です。前者は画像を見ていないので、合算した値を視覚判定の精度として
  引くことはできません。上の表では分けています。
- **「AI 精度は合成テストのみ」は誤りでした。** 4 枚はベンダーが公開しているドキュメント
  中の実写です。合成画像（OpenCV 生成）は別ラウンドで、結果も「非実写と正しく識別した」
  という別の内容です。
- **記録した実行を再現するスクリプトがありません。** `edge/raspberry-pi/camera/test_prompt.py`
  は単段で、モデル ID に `jp.` 接頭辞が付いていません。記録は 2 段構成で `jp.` 付きです。
  再現には 2 段構成を呼ぶ経路が必要です。
- **コストは測定値ではありません。** レイテンシと同じ表に並んでいましたが、由来が違います。
  上の表では区分を分けました。

## 段階の昇格と降格

降格はいつでも構いません。根拠を失ったことを正直に示すほうが、古い `verified` を
残すより読者にとって安全です。昇格するときだけ根拠を要求します。

| 遷移 | 添えるもの |
|---|---|
| 未実行 → 自動テストのみ | テストの追加 |
| 自動テストのみ → 実機 単体 | 実行した環境（リージョン、日付、対象リソース）と、再現する手順 |
| 実機 単体 → 実機 E2E | 経路の全段を通した記録 |
| `hypothesis` / `documented` → `verified` | 上記の必須メタデータを添えた測定 |

## 関連ドキュメント

- [S3 AP 互換性と制約](s3ap-compatibility-matrix.md) — 制約ごとの根拠区分
- [FAQ](faq.md) — 未検証の項目に触れている箇所
- [デプロイガイド](deployment-guide.md) — 実行手順（実行結果ではない）
- [`tests/sample_images/README.md`](../../tests/sample_images/README.md) — Bedrock の測定の生記録
