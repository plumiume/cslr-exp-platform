# マージ計画: feature/simplify-config → main

## 概要

- **ソースブランチ**: `feature/simplify-config` (コミット: 4b3d33d)
- **ターゲットブランチ**: `origin/main` (コミット: 6f8f970)
- **共通祖先**: f6f5b0d
- **マージ日**: 2026-02-13

## 変更サマリー

### feature/simplify-config の変更内容

1. **Rayサービスのプロファイル管理**
   - Docker Composeプロファイルでray-cpu/ray-gpuを排他的に起動
   - GPU環境の自動検出とプロファイル自動選択
   - `ws up --profile ray-cpu/ray-gpu` オプション追加

2. **クラスターテストの柔軟化**
   - `cluster_test.target` 設定追加（cpu/gpu選択可能）
   - `ws test --target gpu` コマンドオプション追加
   - テンプレートの動的ターゲット切り替え

3. **設定検証の強化**
   - CPU/GPU同一イメージ使用時のエラー検出
   - RAY_NUM_CPUSデフォルト値（4）削除

4. **ドキュメント改善**
   - イメージタグ戦略の明文化
   - Typo修正（plumiume → plumiiume）

### main ブランチの変更内容（issue-4）

1. **設定スキーマ機能**
   - `ws schema generate/validate/show` コマンド追加
   - YAML/JSON形式でのスキーマエクスポート
   - 詳細なエラーレポート

2. **ドキュメント追加**
   - `CHANGELOG.md` 追加
   - `docs/architecture.md` 追加
   - `docs/config-reference.md` 追加
   - `docs/troubleshooting.md` 追加

3. **ファイルクリーンアップ**
   - `nodes.yaml` 削除
   - `build_matrix.todo.md` 削除
   - `template/cluster-test.compose.yaml.jinja2.bak` 削除

4. **コード改善**
   - `.flake8` 設定追加
   - 環境変数オーバーライドサポート
   - レガシー設定の検出と移行ガイダンス

## コンフリクト予想

### 確実にコンフリクトするファイル（3件）

1. **`.gitignore`**
   - **ours**: `.pyre/` 追加
   - **theirs**: `config.schema.yaml`, `config.schema.json` 追加
   - **解決方法**: 両方の変更を受け入れる

2. **`template/cluster-test.compose.yaml.jinja2`**
   - **ours**: 動的ターゲット選択（`cluster_test.target`）、RAY_NUM_CPUS条件付き出力
   - **theirs**: ホスト名設定の改善、nodes.yaml削除
   - **解決方法**: 
     - テンプレート構造はoursを優先（動的ターゲット選択は重要機能）
     - nodes.yaml削除はtheirsを受け入れる
     - ホスト名設定の改善を手動マージ

3. **`ws_src/models.py`**
   - **ours**: 
     - `ClusterTestConfig` クラス追加
     - `model_post_init` に GPU/CPUイメージ同一性検証追加
     - フォーマット調整
   - **theirs**:
     - 環境変数サポート（`EnvVarMixin`）追加
     - `model_post_init` のシグネチャ変更（`__context: Any`）
     - フィールド記述の詳細化
     - バリデーション強化
   - **解決方法**:
     - theirsをベースにoursの機能をマージ
     - `ClusterTestConfig` を追加
     - GPU/CPUイメージ検証ロジックを保持
     - `model_post_init` シグネチャはtheirsを採用

### 自動マージ成功ファイル（4件）

- `config.example.yaml`: 両方の変更を統合可能
- `template/compose.yaml.jinja2`: プロファイル追加とその他の改善が共存可能
- `ws_src/commands.py`: プロファイル機能とスキーマコマンドが独立
- `ws_src/manager.py`: クラスターテスト改善とスキーマ機能が独立

## マージ手順

### フェーズ1: 準備

```bash
# 現在の状態確認
git status

# mainブランチの最新状態を取得
git fetch origin main

# バックアップブランチ作成
git branch feature/simplify-config-backup
```

### フェーズ2: マージ実行

```bash
# マージ開始
git merge origin/main --no-ff

# コンフリクト確認
git status
```

### フェーズ3: コンフリクト解決

#### 3.1 `.gitignore`

```bash
# 両方の変更を受け入れる
# ours: .pyre/
# theirs: config.schema.yaml, config.schema.json

# 手動編集後
git add .gitignore
```

#### 3.2 `template/cluster-test.compose.yaml.jinja2`

**戦略**: oursをベースにtheirsの改善を手動マージ

1. oursの変更を保持:
   - 動的ターゲット選択（`{% set ray_target = cluster_test.target %}`）
   - 条件付きRAY_NUM_CPUS出力
   
2. theirsの改善を取り込む:
   - nodes.yaml参照の削除
   - ホスト名設定の改善

```bash
# 手動編集後
git add template/cluster-test.compose.yaml.jinja2
```

#### 3.3 `ws_src/models.py`

**戦略**: theirsをベースにoursの新機能を追加

1. theirsの変更を受け入れる:
   - `EnvVarMixin` とその実装
   - `model_post_init` の新しいシグネチャ
   - 詳細なフィールド記述
   - バリデーション強化

2. oursの変更をマージ:
   - `ClusterTestConfig` クラスを追加
   - `RayConfig.model_post_init` にGPU/CPUイメージ検証を追加
   - `Config` に `cluster_test` フィールドを追加

```python
# マージ後の構造イメージ:
# - EnvVarMixin (from theirs)
# - 既存のConfig classes (enhanced by theirs)
# - ClusterTestConfig (from ours) 
# - RayConfig.model_post_init (combined: theirs base + ours validation)
# - Config.cluster_test field (from ours)
```

```bash
# 手動編集後
git add ws_src/models.py
```

### フェーズ4: 検証

```bash
# フォーマット確認
uv run black ws_src/

# 設定の検証
uv run python -c "from ws_src.manager import WorkspaceManager; from pathlib import Path; wm = WorkspaceManager(Path('.')); config = wm.load_config(); print('✅ Config validation passed')"

# テンプレート生成
uv run python tools/ws.py generate

# クラスターテスト生成
uv run python tools/ws.py test --target gpu
```

### フェーズ5: コミット

```bash
# マージコミット作成
git commit

# コミットメッセージ例:
# Merge branch 'origin/main' into feature/simplify-config
# 
# Resolved conflicts:
# - .gitignore: Combined both changes
# - template/cluster-test.compose.yaml.jinja2: Kept dynamic target selection, 
#   integrated hostname improvements
# - ws_src/models.py: Integrated EnvVarMixin from main, added ClusterTestConfig 
#   and image validation from feature branch
# 
# This merge combines:
# - Profile management and cluster test improvements (feature/simplify-config)
# - Config schema and documentation enhancements (issue-4 from main)
```

## リスク評価

### 高リスク

- **`ws_src/models.py`**: 大規模な変更の統合
  - 両方のブランチで `model_post_init` を変更
  - 新しいクラスとミックスインの追加
  - **対策**: 慎重なマージと十分なテスト

### 中リスク

- **`template/cluster-test.compose.yaml.jinja2`**: テンプレートロジックの変更
  - 動的ターゲット選択機能の保持が重要
  - **対策**: テンプレート生成のテスト実施

### 低リスク

- **`.gitignore`**: シンプルな行追加のみ
- **自動マージ成功ファイル**: Gitが適切に統合

## ロールバック計画

### 問題発生時の対応

```bash
# マージ前の状態に戻す
git merge --abort

# または、マージコミット後に問題が発覚した場合
git reset --hard feature/simplify-config-backup

# バックアップブランチから再開
git checkout -b feature/simplify-config-retry feature/simplify-config-backup
```

## テスト計画

### 必須テスト項目

1. **設定ロード**
   - [ ] config.yamlの正常ロード
   - [ ] ClusterTestConfigの検証
   - [ ] GPU/CPUイメージ同一性検証

2. **テンプレート生成**
   - [ ] compose.yaml生成（CPU環境）
   - [ ] compose.yaml生成（GPU環境）
   - [ ] cluster-test.compose.yaml生成（--target cpu）
   - [ ] cluster-test.compose.yaml生成（--target gpu）

3. **プロファイル機能**
   - [ ] GPU環境で自動プロファイル選択（ray-gpu）
   - [ ] CPU環境で自動プロファイル選択（ray-cpu）
   - [ ] 手動プロファイル指定（--profile）

4. **新機能（main由来）**
   - [ ] ws schema generate
   - [ ] ws schema validate
   - [ ] ws schema show
   - [ ] 環境変数オーバーライド

5. **統合テスト**
   - [ ] クラスターテストの実行
   - [ ] Ray headノードの起動
   - [ ] workerノードの参加

## 完了条件

- [ ] すべてのコンフリクトが解決されている
- [ ] 上記のテスト計画がすべて成功
- [ ] コードフォーマットがblackで統一されている
- [ ] ドキュメントが最新状態を反映している
- [ ] マージコミットがpushされている

## 想定作業時間

- コンフリクト解決: 30-60分
- テスト実施: 30分
- ドキュメント更新: 15分
- **合計**: 約1.5-2時間

## 次のステップ

1. このマージプランをレビュー
2. フェーズ1（準備）を実行
3. フェーズ2-3（マージとコンフリクト解決）を実行
4. フェーズ4（検証）を実行
5. フェーズ5（コミット）を実行
6. プルリクエスト作成またはmainへのマージ実施
