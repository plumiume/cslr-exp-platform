# Ray起動オプション

## Web検索結果まとめ (2026年2月)

### 基本的な起動方法

Rayは3つの方法で起動できます：
1. `ray.init()` - Python内で暗黙的に起動（単一マシン）
2. `ray start` - CLIで明示的に起動
3. `ray up` - クラスタランチャーで起動

### ray start コマンドの主要オプション

#### 基本オプション
- `--head` - ヘッドノードとして起動
- `--address=<address>` - 既存のRayクラスタに接続（例: `ray-cpu:6379`）
- `--port=<port>` - GCSサーバーのポート番号（デフォルト: 6379）

#### ダッシュボード関連
- `--dashboard-host=<host>` - ダッシュボードのホスト（デフォルト: localhost、外部公開には `0.0.0.0`）
- `--dashboard-port=<port>` - ダッシュボードポート（デフォルト: 8265）
- `--ray-debugger-external` - Rayデバッガーを外部公開（ファイアウォール内でのみ安全）

#### リソース管理
- `--num-cpus=<count>` - CPU数を指定（例: `4`, `1.5` など分数も可能）
- `--num-gpus=<count>` - GPU数を指定
- `--resources='{"<name>": <value>}'` - カスタムリソースを指定

#### メモリ管理
- `--object-store-memory=<bytes>` - オブジェクトストアのメモリサイズ（デフォルト: 利用可能メモリの30%）
- `--plasma-directory=<path>` - メモリマップファイル用ディレクトリ
- `--object-spilling-directory=<path>` - オブジェクトスピル用ディレクトリ
- `--system-reserved-memory=<bytes>` - システム予約メモリ（デフォルト: 500MB～10GB）
- `--system-reserved-cpu=<count>` - システム予約CPU（デフォルト: min(3.0, max(1.0, 0.05 * num_cores))）

#### セキュリティ
- `--redis-password=<password>` - Redis認証パスワード

#### その他
- `--temp-dir=<path>` - 一時ディレクトリの指定（--headと併用時のみ）
- `--metrics-export-port=<port>` - Prometheusメトリクスエンドポイントのポート
- `--no-redirect-output` - 非ワーカーの標準出力/エラー出力をファイルにリダイレクトしない
- `--disable-usage-stats` - 使用統計の収集を無効化
- `--block` - プロセスをブロック（デフォルトはバックグラウンド実行）
- `--log-style=<style>` - ログのスタイル
- `--include-log-monitor=<bool>` - ログモニターを起動（デフォルト: true）

#### リソース分離（cgroup v2）
- `--enable-resource-isolation` - cgroup v2によるリソース分離を有効化

### 現在のプロジェクトでの使用例

#### CPU版（config.yaml基準）
```bash
ray start --head \
  --dashboard-host=0.0.0.0 \
  --redis-password=ray \
  --port=6379 \
  --dashboard-port=8265
```

対応するcompose.yamlのcommand:
```yaml
command: ray start --head --dashboard-host=0.0.0.0 --redis-password=ray --port=6379
```

#### GPU版（config.yaml基準）
```bash
ray start --head \
  --dashboard-host=0.0.0.0 \
  --redis-password=ray \
  --num-gpus=1 \
  --port=6380 \
  --dashboard-port=8266
```

対応するcompose.yamlのcommand:
```yaml
command: ray start --head --dashboard-host=0.0.0.0 --redis-password=ray --num-gpus=1 --port=6380
```

### 推奨される追加オプション

プロジェクトに追加を検討できるオプション：

1. **メモリ管理**
   ```yaml
   command: ray start --head \
     --dashboard-host=0.0.0.0 \
     --redis-password=ray \
     --object-store-memory=2000000000 \  # 2GB
     --port=6379
   ```

2. **カスタムリソース**
   ```yaml
   command: ray start --head \
     --dashboard-host=0.0.0.0 \
     --redis-password=ray \
     --resources='{"custom_resource": 1}' \
     --port=6379
   ```

3. **メトリクス収集**
   ```yaml
   command: ray start --head \
     --dashboard-host=0.0.0.0 \
     --redis-password=ray \
     --metrics-export-port=8080 \
     --port=6379
   ports:
     - "8080:8080"  # Prometheusメトリクス
   ```

4. **ネットワーク分離/NAT 環境向け（重要）**
   ```yaml
   command: ray start --address=<head-host>:6379 \
     --node-ip-address=<reachable-host-ip> \
     --node-manager-port=30000 \
     --object-manager-port=30001 \
     --min-worker-port=30010 \
     --max-worker-port=30020
   ports:
     - "30000:30000"
     - "30001:30001"
     - "30010-30020:30010-30020"
   ```

### 接続方法

#### Python内から接続
```python
import ray

# 環境変数で指定
os.environ["RAY_ADDRESS"] = "ray://localhost:10001"
ray.init()

# または直接指定
ray.init(address="ray://localhost:10001")
```

#### ワーカーノードとして接続
```bash
ray start --address=<head-node-ip>:6379 --redis-password=ray
```

### 参考リンク
- [Ray Documentation - Starting Ray](https://docs.ray.io/en/latest/ray-core/starting-ray.html)
- [Ray Documentation - Memory Management](https://docs.ray.io/en/latest/ray-core/scheduling/memory-management.html)
