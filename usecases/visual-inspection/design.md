# Design: Visual Inspection (Manufacturing)

このユースケースは [3d-print-quality](../3d-print-quality/design.md) と**同じ設計**である。
2 段階 AI 分析の理由、Pi が直接 Lambda を invoke する理由、S3 に直接 PUT する理由、
NFS v4.1 を選んだ理由、代替案、セキュリティ上の判断は、すべてそちらが正典。ここには
複製しない。

このドキュメントは**差分だけ**を書く。

## 何を変えて何を変えないか

| 層 | 3d-print-quality との関係 |
|---|---|
| Lambda コード | 同一。[`cloud/ai/image_analyzer/handler.py`](../../cloud/ai/image_analyzer/handler.py) |
| インフラの形 | 同一（Lambda + CloudWatch Alarm + Athena NamedQuery） |
| プロンプト | **異なる**。[`template.yaml`](./template.yaml) の `SCREENING_PROMPT` / `DETAIL_PROMPT` |
| 欠陥の語彙 | **異なる**。糸引き・層間剥離 → 傷・変色・バリ・寸法異常・表面粗さ・異物 |
| 検査対象 | **異なる**。印刷中の 3D プリント → 完成品（金属/ 樹脂部品） |

## なぜコードを分けないか

検査対象が変わっても、経路は変わらない。画像を取得し、安価なモデルで振り分け、疑いのある
ものだけ高精度モデルに送り、結果を保存して閾値を超えたら通知する。この構造は検査対象に
依存しない。依存するのは**モデルに何を探させるか**だけで、それはプロンプトである。

同じ理由で、ハンドラを fork するとプロンプト以外の修正が 2 か所に必要になる。片方だけ
直る状態を作らないために、プロンプトを設定として外に出している。

## プロンプトを環境変数で渡す設計上の帰結

3 点ある。いずれもこの構成を選んだ代償である。

**プロンプトの長さに上限がある。** AWS Lambda の環境変数は合計 4 KB。既定のプロンプト 2 本で
約 1.4 KB を使う。これより大幅に長いプロンプトが必要なら、環境変数ではなく Amazon S3 か
Lambda レイヤーに置く設計に変える。

**プロンプトが応答形式の契約を握る。** ハンドラは `status`（`anomaly_detected` のときだけ
通知）、`confidence`、`anomalies` を読む。プロンプトがこの語彙を要求しなければ、値は
「欠落」として解釈される。欠陥を見つけても通知されない状態になり、例外は出ない。
この対応は [`scripts/check_lambda_env_contract.py`](../../scripts/check_lambda_env_contract.py)
が検査する。

**既定値が別のユースケースのものである。** 環境変数を設定しなければ、ハンドラは 3D プリント用
プロンプトで動く。デプロイは成功し、金属部品に対して「糸引き」を探す。
[`usecases/handler-map.txt`](../handler-map.txt) がこのユースケースの
`must-set=SCREENING_PROMPT,DETAIL_PROMPT` を宣言しているのは、この状態を出荷しないため。

## 検証状態

実機で確認していない。段階と根拠は
[検証状態](../../docs/ja/verification-status.md)にある。プロンプトの差し替えが機能することは
[`tests/test_image_analyzer_prompts.py`](../../tests/test_image_analyzer_prompts.py) が
単体で確認しているが、実際の完成品画像に対する判定精度は未検証である。
3d-print-quality 側で測った精度（公開ドキュメントの実写 4 枚で 4/4）は**このユースケースの
根拠にはならない**。対象物も欠陥の種類も違う。
