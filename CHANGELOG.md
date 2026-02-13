# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### 🚨 Breaking Changes

#### nodes.yaml → config.yaml 統合

**変更内容**: 独立した `nodes.yaml` ファイルを廃止し、`config.yaml` のトップレベル `nodes` セクションに統合しました。

**影響範囲**:
- `nodes.yaml` および `nodes.example.yaml` ファイルは削除されました
- `config.yaml` に `nodes` セクションの追加が必要です
- Docker Compose テンプレートは環境変数注入方式に変更されました

**移行方法**:

既存の `nodes.yaml` がある場合、以下の手順で移行してください:

1. **nodes.yaml の内容を確認**
   ```yaml
   # 旧 nodes.yaml
   head_whitelist:
     - ray-cpu
     - ray-gpu
   head_address: null
   health_service:
     url: "http://health:8080"
     timeout: 1
   cluster:
     discovery_timeout: 5
     wait_for_head: 30
   ```

2. **config.yaml のトップレベルに nodes セクションとして追加**
   ```yaml
   # config.yaml
   services:
     ray:
       cpu:
         enabled: true
         # ... other settings
   
   network:
     subnet: "172.28.0.0/16"
   
   nodes:  # ← ここに追加
     head_whitelist:
       - ray-cpu
       - ray-gpu
     head_address: null
     health_service:
       url: "http://health:8080"
       timeout: 1
       max_retries: 3
       retry_interval: 2  # Custom value (default: 0.5)
     cluster:
       discovery_timeout: 5
       wait_for_head: 30
   ```

3. **古いファイルを削除**
   ```bash
   rm nodes.yaml
   ```

4. **設定を再生成**
   ```bash
   uv run ws generate
   ```

**エラー検出**: `nodes.yaml` が存在する場合、`ws` コマンドは以下のエラーメッセージを表示して終了します:

```
❌ nodes.yaml is no longer supported.
Please move nodes settings into config.yaml > nodes section.
```

**移行の理由**:
- 設定ファイルの一元化によるメンテナンス性向上
- Pydantic による統合的なバリデーション
- VS Code YAML スキーマによる自動補完サポート
- 環境変数オーバーライドのサポート（`CSLR_NODES__HEAD_WHITELIST` など）

### Added

- **Pydantic Settings 統合**: `config.yaml` が `pydantic-settings` による環境変数オーバーライドに対応
  - 優先順位: 環境変数 > `.env` ファイル > `config.yaml` > デフォルト値
  - ネストした設定は `__` で区切る（例: `CSLR_NODES__HEAD_WHITELIST`）

- **スキーマ生成コマンド**: `uv run ws schema generate` で VS Code 用 JSON Schema を生成
  - `.vscode/config.schema.json` に出力
  - YAML 編集時の自動補完とバリデーションを提供

- **init コマンド**: `uv run ws init` で初期セットアップを簡略化
  - `config.example.yaml` を `config.yaml` にコピー
  - スキーマファイルを自動生成
  - `--force` オプションで既存ファイルを上書き

- **バリデーション強化**:
  - サブネット CIDR 形式の検証
  - メモリサイズフォーマットの検証（例: `8g`, `16G`）
  - ポート範囲の検証（1024-65535）
  - ポート重複の検出
  - `head_whitelist` 非空チェック

### Changed

- **テンプレートシステム**: ボリュームマウントから環境変数注入方式に変更
  - `nodes.yaml` のボリュームマウントを削除
  - `HEAD_WHITELIST`, `HEALTH_URL` などの環境変数を注入
  - `ray-ep.sh` が環境変数から設定を読み取る

- **ray-ep.sh の簡素化**: YAML パースロジック（grep/sed）を削除し、環境変数読み取りに統一

- **ドキュメント更新**: README.md および関連ドキュメントを統合設定に対応

### Removed

- `nodes.yaml` および `nodes.example.yaml`
- `template/cluster-test.compose.yaml.jinja2.bak`
- `.gitignore` および `.dockerignore` から `nodes.yaml` エントリ
- Docker Compose テンプレートから `nodes.yaml` ボリュームマウント

### Fixed

- Windows 環境での CRLF 問題（YAML パース不要になったため解消）
- マルチホスト環境でのホスト名設定の明確化

## [0.1.0] - 初回リリース予定

プロジェクト初期バージョン（未リリース）

---

## Migration Support

### Legacy Detection

`ws` コマンドは起動時に `nodes.yaml` の存在をチェックし、検出された場合は明示的なエラーメッセージと移行手順を表示します。

### Environment Variable Override

Pydantic Settings により、すべての設定を環境変数でオーバーライド可能:

```bash
# 例: ヘルスチェック URL を環境変数で上書き
export CSLR_NODES__HEALTH_SERVICE__URL="http://custom-health:9090"
uv run ws generate
```

### .env File Support

プロジェクトルートに `.env` ファイルを配置することで、環境変数を永続化できます:

```bash
# .env
CSLR_NODES__HEAD_WHITELIST=ray-cpu,ray-gpu
CSLR_NODES__HEALTH_SERVICE__URL=http://health:8080
```

**注意**: `.env` ファイルは `.gitignore` に含まれており、Git で追跡されません。
