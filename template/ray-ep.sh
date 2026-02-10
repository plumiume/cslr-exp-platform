#!/bin/bash
set -e

# Ray Node Entrypoint (CPU/GPU unified)
# This script can start Ray as either head or worker node
# Mode is determined by whitelist and health check

echo "Starting Ray node..."
HOSTNAME=$(hostname)
echo "Hostname: $HOSTNAME"

# Load nodes configuration
NODES_CONFIG="/config/nodes.yaml"
if [ ! -f "$NODES_CONFIG" ]; then
    echo "ERROR: nodes.yaml not found at $NODES_CONFIG"
    exit 1
fi

# Parse YAML (simple grep-based parsing for head_whitelist)
WHITELIST=$(grep -A 100 "head_whitelist:" "$NODES_CONFIG" | grep "^  -" | sed 's/^  - //' | tr -d '\r' | tr '\n' ' ')
HEALTH_URL=$(grep "url:" "$NODES_CONFIG" | head -1 | sed 's/.*url: *"\(.*\)"/\1/' | tr -d '\r')
HEALTH_TIMEOUT=$(grep "timeout:" "$NODES_CONFIG" | head -1 | sed 's/.*timeout: *\([0-9]*\)/\1/' | tr -d '\r')

# Parse head_address (explicit head address override)
HEAD_ADDRESS_CFG=$(grep "^head_address:" "$NODES_CONFIG" | sed 's/head_address: *//' | sed 's/"//g' | tr -d ' \r')
if [ "$HEAD_ADDRESS_CFG" = "null" ] || [ -z "$HEAD_ADDRESS_CFG" ]; then
    HEAD_ADDRESS_CFG=""
fi
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
        for node in $WHITELIST; do
            if [ "$node" != "$HOSTNAME" ]; then
                # Try to connect to potential head node
                HEAD_PORT="${RAY_HEAD_PORT:-6379}"
                if timeout 1 bash -c "</dev/tcp/$node/$HEAD_PORT" 2>/dev/null; then
                    echo "✓ Head node already exists on $node"
                    HEAD_EXISTS=true
                    RAY_ADDRESS="$node:$HEAD_PORT"
                    break
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

# Build ray start command
RAY_CMD="ray start"

if [ "$MODE" = "head" ]; then
    RAY_CMD="$RAY_CMD --head --dashboard-host=0.0.0.0"
    RAY_CMD="$RAY_CMD --port=${RAY_HEAD_PORT:-6379}"
    RAY_CMD="$RAY_CMD --dashboard-port=${RAY_DASHBOARD_PORT:-8265}"
    RAY_CMD="$RAY_CMD --ray-client-server-port=${RAY_CLIENT_PORT:-10001}"
else
    # Wait for head node to be ready
    echo "Waiting for Ray head node at $RAY_ADDRESS..."
    HEAD_HOST=$(echo "$RAY_ADDRESS" | cut -d: -f1)
    HEAD_PORT=$(echo "$RAY_ADDRESS" | cut -d: -f2)
    
    for i in {1..60}; do
        if timeout 2 bash -c "</dev/tcp/$HEAD_HOST/$HEAD_PORT" 2>/dev/null; then
            echo "✓ Ray head node is reachable!"
            break
        fi
        if [ $i -eq 60 ]; then
            echo "ERROR: Cannot connect to Ray head node after 60 seconds"
            exit 1
        fi
        [ $((i % 10)) -eq 0 ] && echo "  Waiting... ($i/60)"
        sleep 1
    done
    
    RAY_CMD="$RAY_CMD --address=$RAY_ADDRESS"
fi

# Add resource limits
[ -n "$RAY_NUM_CPUS" ] && RAY_CMD="$RAY_CMD --num-cpus=$RAY_NUM_CPUS"
[ -n "$RAY_NUM_GPUS" ] && RAY_CMD="$RAY_CMD --num-gpus=$RAY_NUM_GPUS"

# Start Ray
echo "Executing: $RAY_CMD"
eval $RAY_CMD

# Wait for Ray to be fully ready
echo "Waiting for Ray to be ready..."
for i in {1..60}; do
    if ray status > /dev/null 2>&1; then
        if [ "$MODE" = "head" ]; then
            RAY_NODE_IP=$(ray status 2>&1 | grep -oP '(?<=Local node IP: )[\d.]+' || hostname -I | awk '{print $1}')
            echo "✓ Ray cluster is ready! Node IP: $RAY_NODE_IP"
            echo "✓ Dashboard: http://$RAY_NODE_IP:${RAY_DASHBOARD_PORT:-8265}"
            echo "✓ Connect from other hosts: ray start --address=<HOST_IP>:${RAY_HEAD_PORT:-6379}"
            [ -n "$RAY_NUM_GPUS" ] && echo "✓ GPUs available: $RAY_NUM_GPUS"
        else
            echo "✓ Ray worker successfully joined the cluster!"
            ray status
        fi
        break
    fi
    if [ $i -eq 60 ]; then
        echo "ERROR: Ray failed to start properly after 60 seconds"
        ray status || true
        exit 1
    fi
    [ $((i % 10)) -eq 0 ] && echo "  Waiting... ($i/60)"
    sleep 1
done

# Keep container running
tail -f /dev/null
