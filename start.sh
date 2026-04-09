#!/usr/bin/env bash

MYSQL_DATA_DIR="$HOME/codebench-mysql"
MYSQL_SOCKET="/tmp/codebench-mysql.sock"
MYSQL_PORT=3307
DB_NAME="codebench"

echo "=== CodeBench Startup ==="

# ── MySQL init ────────────────────────────────────────────────────────────────
if [ ! -d "$MYSQL_DATA_DIR/mysql" ]; then
    echo "[MySQL] Initializing data directory..."
    mysqld --initialize-insecure \
        --datadir="$MYSQL_DATA_DIR" \
        --user="$(whoami)" 2>/dev/null || true
    echo "[MySQL] Initialized."
fi

# ── Start MySQL if not already running ───────────────────────────────────────
if ! mysqladmin --socket="$MYSQL_SOCKET" ping --silent 2>/dev/null; then
    echo "[MySQL] Starting server..."
    mysqld \
        --datadir="$MYSQL_DATA_DIR" \
        --socket="$MYSQL_SOCKET" \
        --port=$MYSQL_PORT \
        --pid-file=/tmp/codebench-mysql.pid \
        --user="$(whoami)" \
        --bind-address=127.0.0.1 \
        --skip-networking=OFF \
        --log-error=/tmp/codebench-mysql-error.log &

    echo "[MySQL] Waiting for server..."
    for i in $(seq 1 40); do
        if mysqladmin --socket="$MYSQL_SOCKET" ping --silent 2>/dev/null; then
            echo "[MySQL] Ready."
            break
        fi
        sleep 1
    done
fi

# ── Create database ───────────────────────────────────────────────────────────
mysql --socket="$MYSQL_SOCKET" -u root \
    -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null || true
echo "[MySQL] Database '$DB_NAME' ready."

# ── Docker daemon (best-effort) ───────────────────────────────────────────────
if command -v dockerd &>/dev/null; then
    if ! docker info &>/dev/null 2>&1; then
        echo "[Docker] Attempting to start daemon..."
        dockerd --host=unix:///var/run/docker.sock &>/tmp/dockerd.log &
        DOCKERD_PID=$!
        # Wait up to 8 seconds for Docker
        for i in $(seq 1 8); do
            if docker info &>/dev/null 2>&1; then
                echo "[Docker] Daemon ready."
                break
            fi
            sleep 1
        done
        if ! docker info &>/dev/null 2>&1; then
            echo "[Docker] Daemon unavailable — submissions will show an error. Check /tmp/dockerd.log for details."
        fi
    else
        echo "[Docker] Daemon already running."
    fi
else
    echo "[Docker] dockerd not found in PATH."
fi

# ── Start FastAPI ─────────────────────────────────────────────────────────────
export DATABASE_URL="mysql+pymysql://root@127.0.0.1:$MYSQL_PORT/$DB_NAME?charset=utf8mb4"

cd "$(dirname "$0")"
echo "[CodeBench] Starting FastAPI on port 5000..."
exec uvicorn main:app --host 0.0.0.0 --port 5000 --reload
