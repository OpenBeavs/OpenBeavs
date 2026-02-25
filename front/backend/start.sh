#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR" || exit

# =============================================================================
# Check if Cloud SQL Proxy is needed and running
# =============================================================================
if grep -q "USE_SECRET_MANAGER=true" "$SCRIPT_DIR/../.env" 2>/dev/null || \
   grep -q "localhost:5433" "$SCRIPT_DIR/../.env" 2>/dev/null; then
    echo "🔍 Checking Cloud SQL Proxy status..."
    
    if ! pgrep -f cloud_sql_proxy > /dev/null; then
        echo "⚠️  Cloud SQL Proxy is not running!"
        echo "📋 Starting Cloud SQL Proxy..."
        
        PROXY_SCRIPT="$SCRIPT_DIR/../../start_cloud_sql_proxy.sh"
        if [ -f "$PROXY_SCRIPT" ]; then
            bash "$PROXY_SCRIPT" &
            echo "⏳ Waiting for Cloud SQL Proxy to initialize..."
            sleep 3
            
            if pgrep -f cloud_sql_proxy > /dev/null; then
                echo "✅ Cloud SQL Proxy started successfully"
            else
                echo "❌ Failed to start Cloud SQL Proxy"
                echo "   Please start it manually: $PROXY_SCRIPT"
                exit 1
            fi
        else
            echo "❌ Cloud SQL Proxy script not found at: $PROXY_SCRIPT"
            echo "   Please start it manually before running the application"
            exit 1
        fi
    else
        echo "✅ Cloud SQL Proxy is running"
    fi
fi

KEY_FILE=.webui_secret_key

PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"
if test "$WEBUI_SECRET_KEY $WEBUI_JWT_SECRET_KEY" = " "; then
  echo "Loading WEBUI_SECRET_KEY from file, not provided as an environment variable."

  if ! [ -e "$KEY_FILE" ]; then
    echo "Generating WEBUI_SECRET_KEY"
    # Generate a random value to use as a WEBUI_SECRET_KEY in case the user didn't provide one.
    echo $(head -c 12 /dev/random | base64) > "$KEY_FILE"
  fi

  echo "Loading WEBUI_SECRET_KEY from $KEY_FILE"
  WEBUI_SECRET_KEY=$(cat "$KEY_FILE")
fi

if [[ "${USE_OLLAMA_DOCKER,,}" == "true" ]]; then
    echo "USE_OLLAMA is set to true, starting ollama serve."
    ollama serve &
fi

if [[ "${USE_CUDA_DOCKER,,}" == "true" ]]; then
  echo "CUDA is enabled, appending LD_LIBRARY_PATH to include torch/cudnn & cublas libraries."
  export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/usr/local/lib/python3.11/site-packages/torch/lib:/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib"
fi

# Check if SPACE_ID is set, if so, configure for space
if [ -n "$SPACE_ID" ]; then
  echo "Configuring for HuggingFace Space deployment"
  if [ -n "$ADMIN_USER_EMAIL" ] && [ -n "$ADMIN_USER_PASSWORD" ]; then
    echo "Admin user configured, creating"
    WEBUI_SECRET_KEY="$WEBUI_SECRET_KEY" uvicorn open_webui.main:app --host "$HOST" --port "$PORT" --forwarded-allow-ips '*' &
    webui_pid=$!
    echo "Waiting for webui to start..."
    while ! curl -s http://localhost:8080/health > /dev/null; do
      sleep 1
    done
    echo "Creating admin user..."
    curl \
      -X POST "http://localhost:8080/api/v1/auths/signup" \
      -H "accept: application/json" \
      -H "Content-Type: application/json" \
      -d "{ \"email\": \"${ADMIN_USER_EMAIL}\", \"password\": \"${ADMIN_USER_PASSWORD}\", \"name\": \"Admin\" }"
    echo "Shutting down webui..."
    kill $webui_pid
  fi

  export WEBUI_URL=${SPACE_HOST}
fi

WEBUI_SECRET_KEY="$WEBUI_SECRET_KEY" exec uvicorn open_webui.main:app --host "$HOST" --port "$PORT" --forwarded-allow-ips '*' --workers "${UVICORN_WORKERS:-1}"
