<!--Copyright (c) 2026 plumiume-->
<!--SPDX-License-Identifier: MIT-->
<!--License: MIT License (https://opensource.org/licenses/MIT)-->
<!--See LICENSE.txt for details.-->



# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### 🚨 Breaking Changes

#### CPU/GPU イメージ同一使用の制限を撤廃

**変更内容**: CPU サービスと GPU サービスで同じ Docker イメージを使用できるようになりました。

以前はバリデーションエラーが発生していましたが、統合ランタイムイメージ（GPU 対応イメージを CPU ノードでも使用するケース）に対応するため制限を撤廃しました。

#### Ray サービスのプロファイル化

**変更内容**: `ray-cpu` / `ray-gpu` サービスが Docker Compose プロファイルで排他的に起動するようになりました。

- GPU 環境では自動的に `ray-gpu` プロファイルが選択されます
- CPU 環境では `ray-cpu` プロファイルが選択されます
- `uv run ws up` 時にプロファイルが自動決定されるため、手動指定は不要です

#### RAY_NUM_CPUS のデフォルト値廃止

**変更内容**: `RAY_NUM_CPUS` 環境変数のデフォルト値（4）を削除し、`config.yaml` の `services.ray.cpu.cpus` / `services.ray.gpu.cpus` が明示的に設定されている場合のみ出力するようになりました。

未設定の場合、Ray が自動的にシステムの CPU 数を検出します。

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

- **Ray ネットワーク分離/NAT 環境サポート**: Ray ノードに `node_ip_address`, `node_manager_port`, `object_manager_port`, `min_worker_port`, `max_worker_port` を設定可能
  - `config.yaml` の `services.ray.cpu` / `services.ray.gpu` セクションで設定
  - `ray-ep.sh` が環境変数 `NODE_IP_ADDRESS`, `NODE_MANAGER_PORT`, `OBJECT_MANAGER_PORT`, `MIN_WORKER_PORT`, `MAX_WORKER_PORT` を `ray start` に渡す
  - ネットワーク分離されたテストワーカーで固定ポートを使用可能に
  - ワーカーポート範囲の整合性バリデーション（`min_worker_port` ≤ `max_worker_port`）

- **クラスターテスト環境の大幅強化**:
  - `cluster_test` セクションに `test_network_subnet`, `worker_node_manager_port`, `worker_object_manager_port`, `worker_min_worker_port`, `worker_max_worker_port` 等のポート設定を追加
  - GPU テスト時に CPU ヘッド用テストワーカー (`test-ray-worker-cpu`) を自動生成
  - テストワーカーに固定ポートと `NODE_IP_ADDRESS` を設定し、ネットワーク分離環境での接続性を確保
  - テストネットワークサブネットが `config.yaml` から設定可能に（デフォルト: `172.30.0.0/24`）

- **クラスターテストログ収集機能**: `uv run ws test --collect-logs` でテスト環境のログを一括収集
  - `--duration` オプションで収集期間を指定（デフォルト: 10分）
  - Docker Compose ログ、Ray ステータス、`/tmp/ray` セッションログ、コンテナ inspect データをサービスごとに収集
  - `/tmp/ray` をホストボリュームにマウントして永続化
  - シンボリックリンクと Unix ソケットを安全にスキップ

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
  - サブネット CIDR 形式の検証（メインネットワーク・テストネットワーク両方）
  - メモリサイズフォーマットの検証（例: `8g`, `16G`）
  - ポート範囲の検証（1024-65535）
  - ポート重複の検出（クラスターテストワーカーポートを含む）
  - ワーカーポート範囲の重複検出（`check_range_overlap`）
  - `min_worker_port` ≤ `max_worker_port` の整合性チェック
  - `head_whitelist` 非空チェック

### Changed

- **運用ポリシーの明文化**:
  - 通常運用では `ray-cpu` / `ray-gpu` の同時起動を行わず、同時起動は `ws test`（cluster-test）用途に限定
  - 同時起動の抑止はスキーマ制約ではなく実行レベル（`ws up ray-cpu ray-gpu` を拒否）で実施
  - `host.hostname` / `services.ray.*.address` / `volumes.ray_data` を future/reserved 項目として整理

- **クラスターテストテンプレートの大幅リファクタリング**:
  - `x-ray` アンカーからイメージ指定を分離し、各サービスが個別にイメージを指定
  - テストコンテナ (`test-ray-client`, `test-ray-worker`) がターゲットに応じた適切なイメージを使用
  - `test-ray-worker` に固定ポート (`NODE_MANAGER_PORT`, `OBJECT_MANAGER_PORT` 等) とホストマッピングを追加
  - GPU テスト時に `test-ray-worker-cpu` サービスを自動生成（CPU ヘッドへの接続検証用）
  - テストネットワークサブネットをハードコードから `{{ cluster_test.test_network_subnet }}` に変更

- **config.example.yaml の拡充**:
  - `cluster_test` セクションにテストネットワークサブネットとワーカーポート設定を追加
  - Ray CPU/GPU ノードにネットワーク分離用オプション (`node_ip_address`, `node_manager_port` 等) をコメント付きで追加

- **テンプレートシステム**: ボリュームマウントから環境変数注入方式に変更
  - `nodes.yaml` のボリュームマウントを削除
  - `HEAD_WHITELIST`, `HEALTH_URL` などの環境変数を注入
  - `ray-ep.sh` が環境変数から設定を読み取る

- **ray-ep.sh の拡張**:
  - YAML パースロジック（grep/sed）を削除し、環境変数読み取りに統一
  - `NODE_IP_ADDRESS`, `NODE_MANAGER_PORT`, `OBJECT_MANAGER_PORT`, `MIN_WORKER_PORT`, `MAX_WORKER_PORT` 環境変数の読み取りと `ray start` への引数追加

- **ドキュメント更新**:
  - README.md: `--node-ip-address` の説明を「使用しない」から「環境に応じて使用する」に修正
  - トラブルシューティング: ノード IP の自動検出とネットワーク分離環境での明示指定ガイダンスを更新
  - `notes/ray-startup-options.md`: ネットワーク分離/NAT 環境向けの推奨オプション例を追加

- **ログ収集の安定化**:
  - `test-ray-worker-cpu` サービスの `/tmp/ray` ディレクトリを事前作成
  - 非 Ray サービスの成果物収集を N/A としてスキップし、誤検出を防止
  - テストクライアントのヘルスチェックが設定済みポートを使用するよう修正

### Removed

- `nodes.yaml` および `nodes.example.yaml`
- `template/cluster-test.compose.yaml.jinja2.bak`
- `.gitignore` および `.dockerignore` から `nodes.yaml` エントリ
- Docker Compose テンプレートから `nodes.yaml` ボリュームマウント
- `.flake8` 設定ファイル（`pyproject.toml` に統合）
- `.pyrightconfig.json`（不要になったため削除）
- `tests/test_ray_node_memory_validation.py`（バリデーションがモデルに統合されたため）
- `RayConfig` の CPU/GPU 同一イメージバリデーション（統合ランタイム対応のため撤廃）

### Fixed

- Windows 環境での CRLF 問題（YAML パース不要になったため解消）
- マルチホスト環境でのホスト名設定の明確化
- テストクライアントの Ray Python パスを明示指定し、安定性向上
- テストクライアントのヘルスチェックが設定済みの `services.health.port` を使用するよう修正
- 非 Ray サービス（health 等）のログ収集時に Ray 固有の成果物収集をスキップし、偽エラーを防止

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
