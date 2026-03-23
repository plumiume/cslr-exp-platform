# レビュー指摘事項への対応

## 実施日: 2026年2月10日

### ✅ 高優先度: YAMLマージキーの重複修正

**問題**: `<<: *ray` と `<<: *gpu` が別行で定義され、後勝ちで設定が欠落する可能性

**修正内容**:
```yaml
# 修正前
ray-gpu:
  <<: *ray
  <<: *gpu

# 修正後
ray-gpu:
  <<: [*ray, *gpu]
```

**影響**: ray-gpuサービスで image, networks, restart などの設定が正しくマージされる

---

### ✅ 中優先度: mlflow depends_on の条件化

**問題**: `mlflow.postgres.enabled=false` の時、存在しない mlflow-postgres への依存が残りエラーになる

**修正内容**:
```yaml
# 修正前
depends_on:
  - mlflow-postgres

# 修正後
{% if services.mlflow.postgres.enabled %}
depends_on:
  - mlflow-postgres
{% endif %}
```

**影響**: 外部DBを使う場合でもエラーなく起動可能

---

### ✅ 中優先度: GPU検出ロジックの改善

**問題**: nvidia-smi の結果が常に config.yaml の設定を上書きする

**修正内容**:
```python
# 修正前: 常に上書き
config.host.has_gpu = has_gpu
config.host.gpu_type = gpu_type

# 修正後: config.yaml が優先
if config.host.gpu_type is None:
    # 自動検出は未設定の場合のみ
    config.host.has_gpu = has_gpu
    config.host.gpu_type = gpu_type
```

**影響**: 
- config.yaml で明示的に設定した場合、その設定が優先される
- Windows環境やAMD GPU環境でも config.yaml の設定が尊重される
- nvidia-smi が無い環境でも正しく動作

---

### ✅ 低優先度: DB資格情報の環境変数化

**問題**: DB資格情報が平文でconfig.yamlとcompose.yamlに埋め込まれている

**修正内容**:

1. `.env.example` を作成（テンプレート）
2. `.env` を `.gitignore` に追加
3. compose.yaml.jinja2 で環境変数をサポート:

```yaml
# PostgreSQL
POSTGRES_USER: ${POSTGRES_USER:-{{ services.mlflow.postgres.user }}}
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-{{ services.mlflow.postgres.password }}}
POSTGRES_DB: ${POSTGRES_DB:-{{ services.mlflow.postgres.database }}}

# Ray Redis
--redis-password=${RAY_REDIS_PASSWORD:-ray}
```

**デフォルト値の仕組み**:
- `${ENV_VAR:-default}`: 環境変数が未設定の場合はdefaultを使用
- .env ファイルがない場合は config.yaml の値がフォールバック
- .env ファイルで上書き可能

**影響**:
- ローカル開発: 変更なし（従来通り動作）
- 共有環境/CI: .env ファイルで資格情報を安全に管理可能
- Git にはテンプレート（.env.example）のみコミット

---

## 使用方法

### 環境変数を使う場合
```bash
# .env.example をコピー
cp .env.example .env

# .env を編集して本番用の資格情報を設定
# POSTGRES_PASSWORD=secure_password_here
# RAY_REDIS_PASSWORD=secure_redis_password

# compose.yamlを生成
uv run python .\ws generate

# 起動
uv run python .\ws up -d
```

### デフォルト値を使う場合
```bash
# そのまま使える（.env ファイル不要）
uv run python .\ws generate
uv run python .\ws up -d
```

---

## 検証結果

- ✅ テンプレート生成成功
- ✅ Docker Compose 構文チェック通過
- ✅ YAMLマージキーが正しく適用されている
- ✅ 環境変数のフォールバックが機能している

---

## 残存する検討事項

### GPU検出の優先度について

**現在の実装**: config.yaml 優先 → 自動検出
- `gpu_type: "nvidia"` が設定されている場合、自動検出をスキップ
- `gpu_type: null` の場合のみ自動検出を実行

**代替案**: 常に自動検出（現在は採用していない）
- メリット: 実機の状態を常に反映
- デメリット: 設定ファイルの意図が無視される

**推奨**: 現在の実装（設定優先）を維持
- 理由: IaCの原則に従い、宣言的な設定を尊重
- 使い分け: 自動検出が必要なら config.yaml で `gpu_type: null` と明示

### 外部DB接続の対応

**現状**: テンプレートに外部DB接続の仕組みがない

**今後の対応案**:
```yaml
mlflow:
  postgres:
    enabled: false  # 内部PostgreSQLを無効化
    external_uri: "postgresql://user:pass@external-host:5432/mlflow"
```

必要に応じて今後実装を検討。
