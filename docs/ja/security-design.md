# セキュリティ設計

> 作成日: 2026-05-29  
> 対象: PoC #1 (3Dプリント品質監視) / PoC #2 (ONTAPテレメトリ)  
> ステータス: Draft

---

## 1. 設計方針

| 方針 | 理由 |
|------|------|
| 最小権限の原則 (Least Privilege) | 各コンポーネントは必要最小限の権限のみ保持 |
| デバイス認証は NFS/Kerberos + 証明書 | PoC 段階: NFSv3 (sys 認証) で迅速に開始。Phase 6 で NFS v4.1 + Kerberos に段階的移行 |
| 転送中・保存時の暗号化を必須とする | LAN/セルラー回線経由のデータ保護、S3/ONTAP 上のデータ保護 |
| シークレットはコードに含めない | 環境変数 / AWS Secrets Manager で管理 |
| ネットワークセグメンテーション | ONTAP管理プレーンとIoTデータプレーンを分離 |

(remaining content unchanged - updating only section 1 row 2)
