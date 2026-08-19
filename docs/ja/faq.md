# FAQ

## セットアップ

**Q: ONTAP がなくても試せますか？**

A: クラウド側（Lambda + Bedrock）は ONTAP なしで動作します。エッジ側も Pi + カメラ + S3 直接アップロードで検証可能です。ONTAP 連携（FPolicy、SnapMirror、S3 AP）は Phase 2 以降のオプションです。

**Q: Raspberry Pi 以外のデバイスでも動きますか？**

A: カメラキャプチャスクリプトは OpenCV ベースなので、Linux + USB カメラがあれば動作します。NVIDIA Jetson、x86 Linux PC、WSL2 でも動作するはずです（未検証）。

**Q: AWS のどのリージョンで動きますか？**

A: Bedrock の Claude モデルが利用可能なリージョンが必要です。本プロジェクトは `ap-northeast-1`（東京）で検証しています。CloudFormation テンプレートのリージョンパラメータを変更すれば他リージョンでも動作します。

## 技術的な質問

**Q: AI の精度はどのくらいですか？**

A: 公開ドキュメント中の実写 4 枚で 4/4、テキストで書いた症状の記述 5 件で 5/5 です。測っているものが違うので合算しません（[検証状態](verification-status.md)）。実環境（照明、カメラ角度、フィラメント色）での精度は未検証です。プロンプトは保守的に設計しており、明確な欠陥のみ検出します。

**Q: 2段階分析の仕組みは？**

A: Stage 1 で Claude Haiku（安価・高速）が「欠陥あり/なし」を判定。「欠陥あり」の場合のみ
Stage 2 で Claude Sonnet（高精度）が詳細分析します。正常画像が大半を占める環境では、
異常率 10% の前提でコストが約 85% 下がる**試算**になります（実測ではありません）。
異常率が高い環境では削減幅は小さくなります。

**Q: 3Dプリント以外の検査にも使えますか？**

A: はい。Lambda のプロンプトを変更するだけで、任意の画像判定に適用できます。外観検査（傷、変色）、在庫確認、安全装備チェックなど。プロンプト変更のみでモデル再学習は不要です。

**Q: FPolicy の性能影響は？**

A: FPolicy は対象ファイル操作にレイテンシを追加します（同期モードで数ms〜数十ms）。高頻度書き込み環境では非同期モードの使用、またはフィルタリングで通知対象を絞ることを推奨します。

**Q: FSx for ONTAP S3 Access Points の制約は？**

A: 主なものは、条件付き書き込み非対応（Iceberg / Delta Lake の直接書き込みができない）、
S3 イベント通知非対応（オブジェクト作成での Lambda トリガーができない）、ListObjectsV2 が
ネイティブ S3 より遅い、ONTAP 9.17.1 以降が必要。制約の一覧と各項目の根拠は
[S3 AP 互換性と制約](./s3ap-compatibility-matrix.md) に集約している。

## コスト

**Q: AWS の月額費用はどのくらいですか？**

A: PoC 規模（1デバイス、60秒間隔撮影）で約 $40/月。内訳: Bedrock API ~$30、S3 ~$3、Kinesis ~$0（ON_DEMAND、データなし時）、Lambda ~$1、その他 ~$5。Kinesis は ON_DEMAND モードのためアイドル時は課金なし。

**Q: コストを下げるには？**

A: (1) 撮影間隔を 120秒に延長（コスト半減）、(2) プリンターアイドル時はスキップ、(3) Haiku のみで運用し Sonnet を使わない（精度は下がる）。

## トラブルシューティング

**Q: Lambda が AccessDenied エラーを返す**

A: S3 バケットポリシーが KMS 暗号化を強制しています。`ServerSideEncryption: aws:kms` ヘッダーなしの PutObject は拒否されます。また、存在しないオブジェクトへの GetObject は ListBucket 権限も要求されます。

**Q: Bedrock が ValidationException を返す**

A: モデル ID にインファレンスプロファイルが必要です。`anthropic.claude-sonnet-4-5-20250929-v1:0` ではなく `jp.anthropic.claude-sonnet-4-5-20250929-v1:0`（JP プロファイル）を使用してください。

**Q: テストが失敗する**

A: `pip install pytest requests opencv-python-headless numpy` を確認。Python 3.12+ が必要です。テストは外部サービスに依存しません（すべてモック）。
