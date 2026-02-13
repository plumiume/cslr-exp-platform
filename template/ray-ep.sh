#!/bin/bash
set -e

# Ray Node Entrypoint (CPU/GPU unified)
# This script can start Ray as either head or worker node
# Mode is determined by whitelist and health check

# Detect environment type and set appropriate paths
if [ -d "/opt/conda/envs/py" ] && [ -n "${USE_CONDA_ENV:-}" ]; then
    # Custom runtime image (Python environment in /opt/conda/envs/py)
    export PATH="/opt/conda/envs/py/bin:$PATH"
    echo "Using custom Python environment: /opt/conda/envs/py"
else
    # Official rayproject/ray image (conda in /home/ray/anaconda3)
    export PATH="/home/ray/anaconda3/bin:$PATH"
    echo "Using rayproject/ray default environment"
fi

RAY_EXEC="ray"
PYTHON_EXEC="python"

echo "Starting Ray node..."
HOSTNAME=$(hostname)
echo "Hostname: $HOSTNAME"

# Load head-election settings from environment (generated from config.yaml)
WHITELIST="${HEAD_WHITELIST:-ray-cpu ray-gpu}"
HEALTH_URL="${HEALTH_URL:-http://health:8080}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-1}"
DISCOVERY_TIMEOUT="${DISCOVERY_TIMEOUT:-2}"
WAIT_FOR_HEAD="${WAIT_FOR_HEAD:-60}"
HEAD_ADDRESS_CFG="${HEAD_ADDRESS_CFG:-}"

# Environment variable HEAD_ADDRESS overrides config file
if [ -n "${HEAD_ADDRESS:-}" ]; then
    HEAD_ADDRESS_CFG="$HEAD_ADDRESS"
fi

echo "Head whitelist: $WHITELIST"
echo "Health service: $HEALTH_URL (timeout: ${HEALTH_TIMEOUT}s)"

# Check if current node is in whitelist
IN_WHITELIST=false
for node in $WHITELIST; do
    if [ "$node" = "$HOSTNAME" ]; then
        IN_WHITELIST=true
        break
    fi
done

# Determine mode based on whitelist and health check
MODE="worker"
if [ "$IN_WHITELIST" = "true" ]; then
    echo "✓ Node is in head whitelist"
    
    # Check if health service is available
    echo "Checking health service..."
    if timeout ${HEALTH_TIMEOUT} curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
        echo "✓ Health service is available"
        
        # Check if head node already exists
        HEAD_EXISTS=false
        echo "Checking for existing head nodes in whitelist..."
        for node in $WHITELIST; do
            if [ "$node" != "$HOSTNAME" ]; then
                # Try to connect to potential head node
                HEAD_PORT="${RAY_HEAD_PORT:-6379}"
                echo "  Checking $node:$HEAD_PORT..."
                if timeout "$DISCOVERY_TIMEOUT" bash -c "</dev/tcp/$node/$HEAD_PORT" 2>/dev/null; then
                    echo "✓ Head node already exists on $node (reachable)"
                    HEAD_EXISTS=true
                    RAY_ADDRESS="$node:$HEAD_PORT"
                    break
                else
                    echo "  ✗ $node:$HEAD_PORT not reachable (no head node or network issue)"
                fi
            fi
        done
        
        if [ "$HEAD_EXISTS" = "false" ]; then
            MODE="head"
            echo "✓ No existing head found - starting as HEAD node"
        else
            echo "→ Starting as WORKER node (connecting to $RAY_ADDRESS)"
        fi
    else
        echo "⚠ Health service unavailable - starting as HEAD node"
        MODE="head"
    fi
else
    echo "→ Node not in whitelist - starting as WORKER node"
    # Resolve head address for non-whitelist nodes
    if [ -n "$HEAD_ADDRESS_CFG" ]; then
        RAY_ADDRESS="$HEAD_ADDRESS_CFG"
        echo "  Using explicit head_address: $RAY_ADDRESS"
    else
        # Fall back to first whitelist node + RAY_HEAD_PORT
        FIRST_WHITELIST=$(echo "$WHITELIST" | awk '{print $1}')
        HEAD_PORT="${RAY_HEAD_PORT:-6379}"
        RAY_ADDRESS="${FIRST_WHITELIST}:${HEAD_PORT}"
        echo "  Using first whitelist node: $RAY_ADDRESS"
    fi
fi

echo "Mode: $MODE"

# Build ray start command as array
RAY_CMD=("$RAY_EXEC" "start")

if [ "$MODE" = "head" ]; then
    RAY_CMD+=("--head" "--dashboard-host=0.0.0.0")
    RAY_CMD+=("--port=${RAY_HEAD_PORT:-6379}")
    RAY_CMD+=("--dashboard-port=${RAY_DASHBOARD_PORT:-8265}")
    RAY_CMD+=("--ray-client-server-port=${RAY_CLIENT_PORT:-10001}")
else
    # Wait for head node to be ready
    echo "Waiting for Ray head node at $RAY_ADDRESS..."
    HEAD_HOST=$(echo "$RAY_ADDRESS" | cut -d: -f1)
    HEAD_PORT=$(echo "$RAY_ADDRESS" | cut -d: -f2)
    
    echo "  Target: $HEAD_HOST:$HEAD_PORT"
    echo "  Note: Ensure $HEAD_HOST is reachable from this host (check DNS/hosts file)"

    i=1
    while [ "$i" -le "$WAIT_FOR_HEAD" ]; do
        if timeout 2 bash -c "</dev/tcp/$HEAD_HOST/$HEAD_PORT" 2>/dev/null; then
            echo "✓ Ray head node is reachable!"
            break
        fi
        if [ "$i" -eq "$WAIT_FOR_HEAD" ]; then
            echo "ERROR: Cannot connect to Ray head node after ${WAIT_FOR_HEAD} seconds"
            echo "  Troubleshooting:"
            echo "    1. Check if head node is running: docker ps"
            echo "    2. Verify network connectivity: ping $HEAD_HOST"
            echo "    3. Check DNS/hosts resolution: getent hosts $HEAD_HOST"
            echo "    4. Verify firewall allows port $HEAD_PORT"
            exit 1
        fi
        [ $((i % 10)) -eq 0 ] && echo "  Waiting... ($i/${WAIT_FOR_HEAD})"
        sleep 1
        i=$((i + 1))
    done
    
    RAY_CMD+=("--address=$RAY_ADDRESS")
fi

# Add explicit node address and fixed internal ports when configured
[ -n "$NODE_IP_ADDRESS" ] && RAY_CMD+=("--node-ip-address=$NODE_IP_ADDRESS")
[ -n "$NODE_MANAGER_PORT" ] && RAY_CMD+=("--node-manager-port=$NODE_MANAGER_PORT")
[ -n "$OBJECT_MANAGER_PORT" ] && RAY_CMD+=("--object-manager-port=$OBJECT_MANAGER_PORT")
[ -n "$MIN_WORKER_PORT" ] && RAY_CMD+=("--min-worker-port=$MIN_WORKER_PORT")
[ -n "$MAX_WORKER_PORT" ] && RAY_CMD+=("--max-worker-port=$MAX_WORKER_PORT")

# Add resource limits
[ -n "$RAY_NUM_CPUS" ] && RAY_CMD+=("--num-cpus=$RAY_NUM_CPUS")
[ -n "$RAY_NUM_GPUS" ] && RAY_CMD+=("--num-gpus=$RAY_NUM_GPUS")

# Start Ray
echo "Executing: ${RAY_CMD[*]}"
"${RAY_CMD[@]}"

# Wait for Ray to be ready
for i in {1..60}; do
    if "$RAY_EXEC" status > /dev/null 2>&1; then
        if [ "$MODE" = "head" ]; then
            RAY_NODE_IP=$("$RAY_EXEC" status 2>&1 | grep -oP '(?<=Local node IP: )[\d.]+' || hostname -I | awk '{print $1}')
            echo "✓ Ray cluster is ready! Node IP: $RAY_NODE_IP"
            echo "✓ Dashboard: http://$RAY_NODE_IP:${RAY_DASHBOARD_PORT:-8265}"
            echo "✓ Connect from other hosts: ray start --address=<HOST_IP>:${RAY_HEAD_PORT:-6379}"
            [ -n "$RAY_NUM_GPUS" ] && echo "✓ GPUs available: $RAY_NUM_GPUS"
        else
            echo "✓ Ray worker successfully joined the cluster!"
            "$RAY_EXEC" status
        fi
        break
    fi
    if [ $i -eq 60 ]; then
        echo "ERROR: Ray failed to start properly after 60 seconds"
        "$RAY_EXEC" status || true
        exit 1
    fi
    [ $((i % 10)) -eq 0 ] && echo "  Waiting... ($i/60)"
    sleep 1
done

# Keep container running
tail -f /dev/null
