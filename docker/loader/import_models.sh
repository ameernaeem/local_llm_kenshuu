#!/bin/sh
set -eu

LOG_DIR="/logs"
LOG_FILE="$LOG_DIR/model-loader.log"
CFG="/config/llm.yaml"

mkdir -p "$LOG_DIR"

echo "[loader] starting" | tee -a "$LOG_FILE"
echo "[loader] OLLAMA_HOST=${OLLAMA_HOST:-}" | tee -a "$LOG_FILE"

# Wait for Ollama to be ready
echo "[loader] waiting for ollama..." | tee -a "$LOG_FILE"
until ollama list >/dev/null 2>&1; do
  sleep 1
done
echo "[loader] ollama ready" | tee -a "$LOG_FILE"

# Extract system_prompt block from llm.yaml (expects: system_prompt: |)
SYS="$(awk '
  BEGIN{inblock=0}
  /^system_prompt:[[:space:]]*\|/ {inblock=1; next}
  inblock==1 {
    if ($0 ~ /^[^[:space:]]/) { exit }   # stop when indentation ends
    sub(/^[[:space:]]+/, "", $0)         # strip indentation
    print
  }
' "$CFG" | sed 's/"/\\"/g' | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g' | sed 's/[[:space:]]*$//')"

echo "[loader] system_prompt length=${#SYS}" | tee -a "$LOG_FILE"

# Import models
found=0
for f in /models/*.gguf; do
  [ -e "$f" ] || continue
  found=1

  name="$(basename "$f" .gguf | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9._-]/-/g')"

  if ollama list | awk 'NR>1{print $1}' | grep -qx "$name"; then
    echo "[loader] $name exists, skip" | tee -a "$LOG_FILE"
    continue
  fi

  echo "[loader] importing $f as $name" | tee -a "$LOG_FILE"

  printf "FROM %s\nSYSTEM \"%s\"\n" "$f" "$SYS" > "/tmp/Modelfile.$name"
  ollama create "$name" -f "/tmp/Modelfile.$name" 2>&1 | tee -a "$LOG_FILE"
done

if [ "$found" -eq 0 ]; then
  echo "[loader] no .gguf found in /models" | tee -a "$LOG_FILE"
fi

echo "[loader] done" | tee -a "$LOG_FILE"

