# ランダムポート / Traefik リバースプロキシ検討

> このドキュメントは [README.md](./README.md) §4 の補足資料です。  
> `dashboard_port` のホスト側公開方法として「ランダムポート」と「Traefik」を比較し、
> 同時起動不可の原則との整合性を検証します。

---

## 1. ランダムポート + ログ通知

Docker の `"0:<container_port>"` 記法でホスト側ポートをランダム割り当てし、
`docker port` でポート番号を取得してログに通知する方法。

```yaml
# config.yaml / テンプレート提案
  ray:
    ports:
      - "0:{{ services.ray.cpu.head_port }}"        # ランダムホストポート
      - "0:{{ services.ray.cpu.dashboard_port }}"
      - "0:{{ services.ray.cpu.client_port }}"
```

```bash
# 起動後にホスト側ポートを確認
docker port <project>-ray 8265   # → 0.0.0.0:49201
```

`ray.sh` または `health` サービスでのログ通知例:

```bash
# ray.sh への追加案
ACTUAL_DASHBOARD_PORT=$(curl -s --unix-socket /var/run/docker.sock \
  http://localhost/containers/$(hostname)/json | python3 -c \
  "import sys, json; p = json.load(sys.stdin)['NetworkSettings']['Ports']; \
   print(list(p.get('8265/tcp', [{}])[0].get('HostPort', '?')))")
echo "Ray Dashboard available at: http://localhost:${ACTUAL_DASHBOARD_PORT}"
```

### 制約

| ポート | ランダム化可否 | 理由 |
|--------|--------------|------|
| `dashboard_port` | ✅ 可 | HTTP のみ使用、外部からの固定参照なし |
| `head_port` | ❌ 不可 | Worker が `--address=<head>:<port>` で固定参照 |
| `client_port` | ❌ 不可 | Ray Client が `ray://<host>:<port>` で固定参照（gRPC） |

---

## 2. Traefik によるリバースプロキシ

HTTP エンドポイント（Dashboard）を Traefik でルーティングし、
cpu/gpu どちらのプロファイルを起動しても同一 URL でアクセスできる構成。

### 2-1. compose 定義例

```yaml
# compose.yaml (テンプレート提案)
  traefik:
    image: traefik:v3
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.ray-head.address=:6379"    # TCP プロキシ
    ports:
      - "80:80"           # HTTP (dashboard)
      - "8080:8080"       # Traefik UI
      - "6379:6379"       # Ray head port (TCP)
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - ray-network

  ray-cpu:                               # ray-gpu も同様
    labels:
      - "traefik.enable=true"
      # HTTP: Dashboard
      - "traefik.http.routers.ray-dashboard.rule=Host(`ray.localhost`)"
      - "traefik.http.routers.ray-dashboard.entrypoints=web"
      - "traefik.http.services.ray-dashboard.loadbalancer.server.port=8265"
      # TCP: Head port
      - "traefik.tcp.routers.ray-head.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.ray-head.entrypoints=ray-head"
      - "traefik.tcp.services.ray-head.loadbalancer.server.port=6379"
    profiles:
      - ray-cpu    # または ray-gpu
```

### 2-2. 利点

- cpu / gpu どちらを起動しても `http://ray.localhost` でダッシュボードにアクセス可能
- ホスト側の固定ポートを Traefik に集約、コンテナ側は内部ポートのみ管理

### 2-3. 制約

| 対象 | Traefik 対応 | 理由 |
|------|------------|------|
| Dashboard (HTTP) | ✅ 有効 | 通常の HTTP ルーティング |
| Ray Client (gRPC) | ⚠️ TCP プロキシで可 | `HostSNI('*')` で全通過が必要 |
| Worker ↔ Head 間 (GCS / NodeManager / ObjectManager) | ❌ 非現実的 | 多数のランダムポートを使用するため全経路を Traefik 経由にできない |

---

## 3. 同時起動不可原則との整合性チェック

| 構成 | 単一起動保証 | ポート衝突リスク | 実現可能性 |
|------|-------------|----------------|-----------|
| profiles のみ（現行） | ✅ `--profile` で排他 | なし | ✅ 即適用可能 |
| `:8080` ランダムポート | ✅ profiles との併用 | なし（head/client は固定） | ⚠️ head_port / client_port は固定必須 |
| Traefik HTTP | ✅ profiles との併用 | なし（Traefik が単一エンドポイント） | ✅ dashboard のみ有効 |
| Traefik TCP (Ray) | ⚠️ Worker 通信が多ポート | なし | ❌ Ray の多ポート要件と非整合 |

---

## 4. 結論

- `dashboard_port` のみランダムポート (`:0`) または Traefik HTTP ルーティングが有効
- `head_port` / `client_port` は Ray プロトコル上、固定が必須
- Worker 間通信（NodeManager, ObjectManager, worker ポート範囲）は現行の固定ポート設定を維持する
- Traefik 導入は「ダッシュボードの URL 統一」目的に限定すれば有効な選択肢

---

## 参照

| ファイル | 関連箇所 |
|---------|---------|
| [README.md](./README.md) | §4: ポート設定方針の概要 |
| [templates/compose.yaml.jinja2](../templates/compose.yaml.jinja2) | `ports:` 定義 |
| [entrypoints/ray.sh](../entrypoints/ray.sh) | ログ通知追加箇所 |
| [docs/ray-startup-options.md](../docs/ray-startup-options.md) | `--port`, `--dashboard-port`, `--client-server-port` |
