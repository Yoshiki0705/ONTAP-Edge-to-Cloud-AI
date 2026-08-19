# Demo Guide: Visual Inspection (Manufacturing)

手順は [3d-print-quality のデモガイド](../3d-print-quality/demo-guide.md)と**同じ**である。
Pi のセットアップ、NFS マウント、環境変数、連続運転、トラブルシューティングはそちらを見る。
ここには**置き換える箇所だけ**を書く。

## 所要時間

3d-print-quality と同じ。初回は 60〜90 分（AWS デプロイ 15 分 + ONTAP 10 分 + Pi 30 分）。
2 回目以降は 10 分。

## 置き換える箇所

### 1. AWS インフラのデプロイ

スタックとテンプレートが違う。

```bash
aws cloudformation deploy \
  --template-file usecases/visual-inspection/template.yaml \
  --stack-name visual-inspection \
  --parameter-overrides file://cfn-params/visual-inspection.example.json \
  --capabilities CAPABILITY_NAMED_IAM
```

`SharedStackName` が指す共有スタック（S3 バケット、SNS トピック、IAM ロール）は
3d-print-quality と共用する。共有スタックを先に作っていない場合は、そちらのデモガイドの
手順 1 を先に実施する。

### 2. Lambda コードの投入

テンプレートが作る関数は 501 を返すスタブである。実コードは別途投入する。この点は
3d-print-quality と同じで、**投入するコードも同じ**。

```bash
cd cloud/ai/image_analyzer && zip -r /tmp/analyzer.zip handler.py && cd -
aws lambda update-function-code \
  --function-name edge-to-cloud-visual-inspection-visual-inspection \
  --zip-file fileb:///tmp/analyzer.zip
```

プロンプトはテンプレートが環境変数として設定済みなので、コード側の変更は不要。
関数名はスタック名を含むので、`--stack-name` を変えた場合は読み替える。

### 3. ONTAP ボリューム

3d-print-quality の [`ontap-setup.sh`](../3d-print-quality/ontap-setup.sh) を使う。
このユースケース用のスクリプトは置いていない。出力される ONTAP CLI コマンドのうち、
ボリューム名だけを読み替える。

| 3d-print-quality | visual-inspection |
|---|---|
| `vol_images` | `vol_inspection` |
| `vol_results` | `vol_inspection_results` |
| `/vol_images` | `/vol_inspection` |
| `/vol_results` | `/vol_inspection_results` |

サイズ、export policy、security style は変えない。

### 4. 撮影対象

印刷中の 3D プリントではなく完成品を撮る。カメラは固定し、照明を一定にする。
プロンプトは傷・変色・バリ・寸法異常・表面粗さ・異物を探す。

## 確認ポイント

3d-print-quality の確認ポイントに加えて、**プロンプトが差し替わっていること**を確認する。
差し替わっていなければ、金属部品に対して「糸引き」や「スパゲッティ」を探す結果が返る。
デプロイは成功しているので、結果を見るまで気づかない。

```bash
aws lambda get-function-configuration \
  --function-name edge-to-cloud-visual-inspection-visual-inspection \
  --query 'Environment.Variables.DETAIL_PROMPT' --output text | head -1
# -> "You are a manufacturing quality inspector." で始まること
```

## 撤去

3d-print-quality と同じ手順。スタック名だけ読み替える。

```bash
aws cloudformation delete-stack --stack-name visual-inspection
```

共有スタックは 3d-print-quality と共用しているので、両方を使い終わってから消す。

## 検証状態

**この手順は実機で実行していない。** AWS 上でのデプロイ記録はない。段階と根拠は
[検証状態](../../docs/ja/verification-status.md)にある。手順として書いてあることと、
実行して動いたことは別である。
