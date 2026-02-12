# Docker Build Matrix - ビルド進捗管理

最終更新: 2026-02-10

## ビルド状況サマリー

| CUDA   | Python | ターゲット         | 状態 | 最終ビルド | 備考 |
|--------|--------|-------------------|------|------------|------|
| 12.8.1 | 3.13   | devel             | ⏳   | -          | -    |
| 12.8.1 | 3.13   | runtime           | ⏳   | -          | -    |
| 12.8.1 | 3.13   | ray-devel         | ⏳   | -          | -    |
| 12.8.1 | 3.13   | ray-runtime       | ⏳   | -          | -    |
| 12.8.1 | 3.13   | marimo-devel      | ⏳   | -          | -    |
| 12.8.1 | 3.13   | marimo-runtime    | ✅   | 2026-02-10 | 既存 |
| 13.1.1 | 3.14   | devel             | ⏳   | -          | -    |
| 13.1.1 | 3.14   | runtime           | ⏳   | -          | -    |
| 13.1.1 | 3.14   | ray-devel         | ⏳   | -          | -    |
| 13.1.1 | 3.14   | ray-runtime       | ⏳   | -          | -    |
| 13.1.1 | 3.14   | marimo-devel      | ⏳   | -          | -    |
| 13.1.1 | 3.14   | marimo-runtime    | ⏳   | -          | -    |
| 12.8.1 | 3.14   | devel             | ⏳   | -          | -    |
| 12.8.1 | 3.14   | runtime           | ⏳   | -          | -    |
| 12.8.1 | 3.14   | ray-devel         | ⏳   | -          | -    |
| 12.8.1 | 3.14   | ray-runtime       | ⏳   | -          | -    |
| 12.8.1 | 3.14   | marimo-devel      | ⏳   | -          | -    |
| 12.8.1 | 3.14   | marimo-runtime    | ⏳   | -          | -    |

**凡例:**
- ⏳ 未実行
- 🔄 ビルド中
- ✅ 成功
- ❌ 失敗
- ⚠️  警告あり

## ビルド優先順位

### Phase 1: 基本構成（最優先）
- [x] CUDA 12.8.1 + Python 3.13 + marimo-runtime (既存)
- [ ] CUDA 12.8.1 + Python 3.13 + runtime
- [ ] CUDA 12.8.1 + Python 3.13 + ray-runtime

### Phase 2: 開発環境
- [ ] CUDA 12.8.1 + Python 3.13 + devel
- [ ] CUDA 12.8.1 + Python 3.13 + ray-devel
- [ ] CUDA 12.8.1 + Python 3.13 + marimo-devel

### Phase 3: 次世代環境（CUDA 13.x）
- [ ] CUDA 13.1.1 + Python 3.14 + marimo-runtime
- [ ] CUDA 13.1.1 + Python 3.14 + runtime
- [ ] CUDA 13.1.1 + Python 3.14 + ray-runtime

### Phase 4: Python 3.14 バリエーション
- [ ] CUDA 12.8.1 + Python 3.14 + marimo-runtime
- [ ] CUDA 12.8.1 + Python 3.14 + runtime
- [ ] CUDA 12.8.1 + Python 3.14 + ray-runtime

### Phase 5: 全開発環境
- [ ] CUDA 13.1.1 + Python 3.14 + devel
- [ ] CUDA 13.1.1 + Python 3.14 + ray-devel
- [ ] CUDA 13.1.1 + Python 3.14 + marimo-devel
- [ ] CUDA 12.8.1 + Python 3.14 + devel
- [ ] CUDA 12.8.1 + Python 3.14 + ray-devel
- [ ] CUDA 12.8.1 + Python 3.14 + marimo-devel

## 各パターンの想定ビルド時間

| ターゲット         | 想定時間 | 備考                           |
|-------------------|----------|--------------------------------|
| devel             | 40-60分  | 完全ビルド（PyG等ソースビルド） |
| runtime           | 5-10分   | devel からコピー              |
| ray-devel         | 50-70分  | devel + Ray ビルド            |
| ray-runtime       | 5-10分   | ray-devel からコピー          |
| marimo-devel      | 55-75分  | ray-devel + marimo            |
| marimo-runtime    | 5-10分   | marimo-devel からコピー       |

**累積時間（1セット）**: 約160-230分（2.7-3.8時間）

## ビルド実行コマンド

### Phase 1 の実行
```powershell
# runtime (基本ランタイム)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target runtime

# ray-runtime (Ray付きランタイム)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target ray-runtime
```

### Phase 2 の実行
```powershell
# devel (開発環境ベース)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target devel

# ray-devel (Ray開発環境)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target ray-devel

# marimo-devel (完全開発環境)
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target marimo-devel
```

### 一括実行（CUDA 12.8.1 + Python 3.13 全パターン）
```powershell
.\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13
```

## CI/CD 定期ビルド計画

### スケジュール案
- **毎週月曜 02:00 JST**: Phase 1（基本構成）
- **毎週水曜 02:00 JST**: Phase 2（開発環境）
- **毎週金曜 02:00 JST**: Phase 3（次世代環境）
- **毎月1日 02:00 JST**: 全パターンビルド

### ビルド環境要件
- Docker with BuildKit
- 最低 100GB 空きストレージ
- 16GB以上のメモリ推奨
- ローカルランナー: Windows PowerShell 7.x

## トラブルシューティングログ

### 2026-02-10
- [✅] CUDA 12.8.1 + Python 3.13 + marimo-runtime: 成功
  - ビルド時間: 約40分
  - イメージサイズ: 確認待ち

## 次回更新予定

- [ ] 各ターゲットのビルド完了後、状態を更新
- [ ] 実際のビルド時間を記録
- [ ] イメージサイズを記録
- [ ] エラーがあれば詳細をトラブルシューティングログに追加
