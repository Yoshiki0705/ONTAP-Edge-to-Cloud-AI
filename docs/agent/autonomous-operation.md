# 長時間自律運用の規律

> 多段タスク（パターン追加、検証ラン、IaC 変更）を長時間・自律で進めるときに読む。
> 土台はグローバル steering（`ai-agent-workflow` の Auditor Sub-Agent 節、
> `benchmark-and-evidence-standards`）にあり、ここではこのリポジトリ固有の落とし込みだけを書く。
> 常時ロードではない。
>
> English: [autonomous-operation_en.md](autonomous-operation_en.md)

## 判断記録の置き場所と形式

多段タスク（新しい `usecases/` パターンの追加、実機を伴う検証、`template.yaml` などの
IaC 変更）では、実装の記述とは別に判断記録を残す。判断記録は却下案・未検証前提・根拠 tier を
含む process metadata なので、このリポジトリの非公開作業領域 `.private/tasks/<task>/` に置く
（`.private/` は `.gitignore` 対象。同種の台帳が既に `.private/` にある）。タスクごとに
1ファイル（`impl-note.md` など）を作ってよいが、3節を別々のファイルに切り出さず、そのタスクの
1つの記録に収める。同じことをする入れ物を乱立させない。節は次の3つ。

```markdown
## Decisions
- <決めたこと>: <なぜ。根拠は 測定 / 文献 / 推測 のどれか>

## Rejected alternatives
- <却下した案>: <なぜ却下したか。状況が変われば復活しうるか>

## Assumptions
- <検証せずに前提に置いたこと>: <外れたら何が壊れるか>
```

検証を伴う作業では、`Decisions` の根拠欄に evidence tier を対応づける。使える語は
`verified` / `documented` / `field-observation` / `hypothesis` の4つだけ。これは
`docs/{ja,en}/verification-status.md` の ledger が使う語彙と同じで、
`scripts/check_verification_ledger.py` が5つ目の造語を落とす。判断記録でも同じ4語に
そろえ、ledger に書けない tier を判断記録に書かない。

## 監査役を呼ぶ合図

次のいずれかに気づいたら、作業を続ける前に監査役を呼ぶ。合図の定義と起動方法は
`ai-agent-workflow` の Auditor Sub-Agent 節にあり、ここでは繰り返さない。

- 同一アプローチが2回失敗した
- 同じファイルを3回以上編集し直している
- 多段タスクで同じエラーメッセージが再発している

監査役には判断記録と変更差分を渡し、「補強」ではなく「疑う」方向で指示する。自動 hook は
作らない（read-only を含む呼び出しでの誤爆が自動化の利得を上回る）。公開物をコミットする
直前のレビューは persona review board の担当なので、監査役とは分ける。

## ばらつきを測ってからの効果主張

性能・スループット・レイテンシ・コストの数値を測るときは、変更の効果を主張する前に、
変更していない構成のランごとのばらつきを先に測る。変更の差がそのばらつきの範囲内なら、
効果ではなくノイズである。そう書くか、ばらつきを超えるまで反復数を増やす。1回ずつしか
測っていない「A は B より速い」も同じ扱いにする。要件とメタデータは
`benchmark-and-evidence-standards` にある。

このリポジトリで現時点の唯一の測定証拠は、2段 Bedrock 推論の数値（`verification-status.md`
に記録、特定の推論プロファイルで取得）である。この数値に触れる変更をするときは、ledger の
該当行と推論プロファイルの対応を壊さない。モデル ID や `jp.` などの推論プロファイル接頭辞を
変えると、別の経路・別の課金になり、記録済みの数値がその構成を説明しなくなる
（`check_verification_ledger.py` がこの乖離を検出する）。

## 反復タスク型のチェックリスト

このリポジトリで繰り返し発生するタスク型には、固有の落とし穴がある。2回目の同種の失敗は
「チェックリストに項目が足りない」兆候として扱い、該当タスク型の節に1項目ずつ足す。

### usecases パターンの追加

既存パターン（`usecases/3d-print-quality` ほか）は
README / design.md / demo-guide.md / lambda/ / template.yaml / ontap-setup.sh の定型構成。
新規追加のとき:

- `cfn-params/` に例の `*.example.json` を足し、`cfn-params/README.md` の表に行を足す
  （`check_cfn_params_contract.py` が対応を検査する）
- `template.yaml` の環境変数と handler が読む値、`usecases/handler-map.txt` の
  must-set 宣言を一致させる（`check_lambda_env_contract.py`）
- README / design は JA/EN の `## ` 構造と数を一致させ、同じコミットで両方変える
- `make check` を通す。lint / security / test / drift を含む（テストだけでは静的検査が抜ける）

### 実機を伴う検証ラン

実機でしか動かないスクリプト（SSM、ONTAP REST、AD 操作）は、オフラインのゲートを通っても
実機で動く証拠にならない。検証ランのとき:

- 合否要件に「撤去で消えるアーティファクト」を列挙し、撤去手順の前に退避ステップを置く
- 実機で1回通すまでは、その主張を `hypothesis` として扱う
- 課金前に、各実行主体（インスタンスロール、Lambda ロール）が呼ぶ AWS 操作と権限を突き合わせる
- 計測は変更していない構成のばらつきを先に取る（上節）

### AWS API 呼び出しを前提にする変更

- リージョン提供状況・クォータ・価格・モデル ID は記憶から書かず、呼ぶ前に確認する
- 「未対応」「できない」は主張。出典か実測を添え、添えられないなら「確認していない」と書く
- 破壊的な呼び出しの識別子は手で打たず、保存済みのファイルか一覧の出力から取る
