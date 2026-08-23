#!/usr/bin/env bash
# start.sh — claudechat launcher and one-time setup
#
# Brings up the always-on speech daemon that speaks Claude's replies aloud.
# Run this once after cloning; afterwards the systemd user service starts it
# with your session and you only ever use `claudechat on|off|toggle|status`.
#
# Processes started:
#   claudechat serve   — resident daemon: Whisper + Kokoro in memory, owns the
#                        Unix socket the Claude Code Stop hook posts to
#
# There are deliberately NO PORTS in this script. claudechat exposes a Unix
# domain socket (0600, peer-UID checked), never a TCP listener — a loopback
# port is reachable by every local process and by browser pages via DNS
# rebinding, and this endpoint spends Claude quota and makes the speakers talk.
# See docs/adr/0009. So there is no --reset-ports flag: there is nothing to
# reset.
#
# Usage:
#   ./start.sh              # set up if needed, then start the daemon
#   ./start.sh --install    # also register the Stop hook + systemd service
#   ./start.sh --stop       # stop the daemon
#   ./start.sh --status     # is speech on, is the daemon up, which voice
#   ./start.sh --rebuild    # force dependency re-sync
#   ./start.sh --uninstall  # remove the hook and the service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
LOG_DIR="${PROJECT_ROOT}/logs"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-${HOME}/.cache/claudechat/run}/claudechat"
SOCKET="${RUNTIME_DIR}/engine.sock"
CONFIG="${HOME}/.config/claudechat/config.toml"
UNIT="${HOME}/.config/systemd/user/claudechat.service"
SETTINGS="${HOME}/.claude/settings.json"

# ── Helpers ──────────────────────────────────────────────────────────────────
info()   { echo "  ${*}"; }
ok()     { echo "  [ok] ${*}"; }
warn()   { echo "  [warn] ${*}"; }
die()    { echo "[fail] ${*}" >&2; exit 1; }
header() { echo; echo "── ${*}"; }

# ── Flags ────────────────────────────────────────────────────────────────────
DO_INSTALL=false
STOP_ONLY=false
STATUS_ONLY=false
FORCE_REBUILD=false
DO_UNINSTALL=false
for arg in "$@"; do
  case "${arg}" in
    --install)    DO_INSTALL=true ;;
    --stop)       STOP_ONLY=true ;;
    --status)     STATUS_ONLY=true ;;
    --rebuild)    FORCE_REBUILD=true ;;
    --uninstall)  DO_UNINSTALL=true ;;
    -h|--help)    sed -n '2,28p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Unknown flag: ${arg}" >&2; exit 1 ;;
  esac
done

daemon_pids() { pgrep -f "claudechat.cli.daemon|claudechat serve" 2>/dev/null || true; }

stop_daemon() {
  if [[ -f "${UNIT}" ]] && systemctl --user is-active --quiet claudechat 2>/dev/null; then
    systemctl --user stop claudechat && ok "Stopped systemd service"
    return
  fi
  local pids; pids="$(daemon_pids)"
  if [[ -n "${pids}" ]]; then
    kill ${pids} 2>/dev/null || true
    local retries=10
    while [[ ${retries} -gt 0 ]] && [[ -n "$(daemon_pids)" ]]; do
      sleep 0.3; retries=$((retries - 1))
    done
    [[ -n "$(daemon_pids)" ]] && { kill -9 $(daemon_pids) 2>/dev/null || true; sleep 0.2; }
    ok "Stopped daemon"
  else
    info "Daemon was not running"
  fi
  rm -f "${SOCKET}"
}

# Readiness is the socket accepting a connection — not merely existing. A stale
# socket file survives a hard kill, so a file-exists check would report a dead
# daemon as ready.
wait_for_socket() {
  local label="${1}" log="${2:-}" timeout=90 elapsed=0
  while ! python3 -c "
import socket,sys
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.settimeout(1)
try: s.connect('${SOCKET}'); s.close()
except OSError: sys.exit(1)
" 2>/dev/null; do
    sleep 0.5; elapsed=$((elapsed + 1))
    if [[ ${elapsed} -ge $((timeout * 2)) ]]; then
      local hint=""; [[ -n "${log}" ]] && hint=" — check ${log}"
      die "${label} did not accept connections after ${timeout}s${hint}"
    fi
  done
}

print_status() {
  if command -v uv &>/dev/null; then
    (cd "${PROJECT_ROOT}" && uv run claudechat status 2>/dev/null | grep -viE "warn") || true
  fi
}

# ── --uninstall ──────────────────────────────────────────────────────────────
if [[ "${DO_UNINSTALL}" == true ]]; then
  header "Removing claudechat from your environment"
  stop_daemon
  if [[ -f "${UNIT}" ]]; then
    systemctl --user disable claudechat &>/dev/null || true
    rm -f "${UNIT}"
    systemctl --user daemon-reload &>/dev/null || true
    ok "Removed systemd service"
  else
    info "No systemd service installed"
  fi
  if [[ -f "${SETTINGS}" ]]; then
    python3 - "${SETTINGS}" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
hooks = data.get("hooks", {})
groups = hooks.get("Stop", [])
kept = []
removed = 0
for group in groups:
    entries = [e for e in group.get("hooks", []) if "claudechat_hook.py" not in str(e.get("command", ""))]
    removed += len(group.get("hooks", [])) - len(entries)
    if entries:
        group["hooks"] = entries
        kept.append(group)
if kept:
    hooks["Stop"] = kept
else:
    hooks.pop("Stop", None)
if not hooks:
    data.pop("hooks", None)
json.dump(data, open(path, "w"), indent=2)
print(f"  [ok] Removed {removed} claudechat Stop hook(s) from settings.json")
PY
  fi
  echo; ok "claudechat removed. The repo and your config file are untouched."
  exit 0
fi

# ── --status ─────────────────────────────────────────────────────────────────
if [[ "${STATUS_ONLY}" == true ]]; then
  header "claudechat status"
  print_status
  [[ -f "${UNIT}" ]] && ok "systemd service installed" || info "systemd service not installed (run ./start.sh --install)"
  grep -q "claudechat_hook.py" "${SETTINGS}" 2>/dev/null \
    && ok "Claude Code Stop hook registered" \
    || info "Stop hook not registered (run ./start.sh --install)"
  exit 0
fi

# ── --stop ───────────────────────────────────────────────────────────────────
if [[ "${STOP_ONLY}" == true ]]; then
  header "Stopping claudechat"
  stop_daemon
  echo; ok "Stopped."
  exit 0
fi

# ── 1. Dependency checks ─────────────────────────────────────────────────────
header "1. Checking dependencies"

command -v uv &>/dev/null || die "uv not found — install from https://docs.astral.sh/uv/getting-started/installation/"
ok "uv: $(uv --version)"

command -v python3 &>/dev/null || die "python3 not found"

if ! command -v claude &>/dev/null; then
  die "claude CLI not found — install Claude Code, then run 'claude login'.
       claudechat reaches Claude through the CLI so it uses your existing
       subscription login; there is no API key anywhere in this project."
fi
ok "claude: $(claude --version 2>/dev/null | head -1)"

MISSING_AUDIO=()
command -v pw-cat &>/dev/null    || MISSING_AUDIO+=("pw-cat")
command -v pw-record &>/dev/null || MISSING_AUDIO+=("pw-record")
if [[ ${#MISSING_AUDIO[@]} -gt 0 ]]; then
  die "Missing PipeWire tools: ${MISSING_AUDIO[*]}
       Install with:  sudo apt install pipewire-audio-client-libraries pipewire-bin
       (Debian/Ubuntu) — claudechat records and plays through PipeWire, not ALSA."
fi
ok "PipeWire tools: pw-cat, pw-record"

if ! pgrep -x pipewire &>/dev/null; then
  warn "pipewire does not appear to be running — audio will fail until it is"
fi

# ── 2. Python environment ────────────────────────────────────────────────────
header "2. Python environment"
mkdir -p "${LOG_DIR}"

deps_need_sync() {
  [[ ! -d "${PROJECT_ROOT}/.venv" ]] && return 0
  [[ "${PROJECT_ROOT}/pyproject.toml" -nt "${PROJECT_ROOT}/.venv" ]] && return 0
  [[ -f "${PROJECT_ROOT}/uv.lock" && "${PROJECT_ROOT}/uv.lock" -nt "${PROJECT_ROOT}/.venv" ]] && return 0
  return 1
}

if [[ "${FORCE_REBUILD}" == true ]] || deps_need_sync; then
  info "Syncing dependencies (Python 3.13, CPU-only — no CUDA)..."
  (cd "${PROJECT_ROOT}" && uv sync --quiet) || die "uv sync failed"
  touch "${PROJECT_ROOT}/.venv"
  ok "Dependencies installed"
else
  ok "Dependencies up to date — skipping (use --rebuild to force)"
fi

# ── 3. Speech models ─────────────────────────────────────────────────────────
header "3. Speech models"
MODELS_DIR="${HOME}/.cache/claudechat/models"
if [[ -f "${MODELS_DIR}/kokoro-v1.0.onnx" && -f "${MODELS_DIR}/voices-v1.0.bin" ]]; then
  ok "Voice model present ($(du -sh "${MODELS_DIR}" 2>/dev/null | cut -f1))"
else
  info "Downloading the voice model (about 340 MB, once only)..."
  info "Each file is checked against a pinned SHA-256 before it is used."
  (cd "${PROJECT_ROOT}" && uv run python -c "
from claudechat.config import load_config
from claudechat.speech.models import KOKORO_MODEL, KOKORO_VOICES, ensure_model
config = load_config()
for spec in (KOKORO_MODEL, KOKORO_VOICES):
    print(f'  fetching {spec.name} ...', flush=True)
    ensure_model(spec, config.models_dir)
" 2>&1 | grep -viE "warn") || die "Model download or digest check failed"
  ok "Voice model downloaded and verified"
fi

info "Transcription model downloads on first use (about 140 MB)"

# ── 4. Configuration ─────────────────────────────────────────────────────────
header "4. Configuration"
if [[ -f "${CONFIG}" ]]; then
  ok "Config: ${CONFIG}"
else
  mkdir -p "$(dirname "${CONFIG}")"
  if [[ -f "${PROJECT_ROOT}/config.example.toml" ]]; then
    cp "${PROJECT_ROOT}/config.example.toml" "${CONFIG}"
    ok "Created ${CONFIG} from config.example.toml"
  else
    printf '[speech]\ntts_voice = "bm_fable"\n\n[hook]\nspoken_summaries = false\n' > "${CONFIG}"
    ok "Created ${CONFIG} with defaults"
  fi
  info "Speech starts OFF. Turn it on later with: claudechat on"
fi

# ── 5. Hook and service (only with --install) ────────────────────────────────
if [[ "${DO_INSTALL}" == true ]]; then
  header "5. Registering the Stop hook and systemd service"
  info "This writes to ${SETTINGS} and ${UNIT}."
  info "Undo at any time with: ./start.sh --uninstall"
  (cd "${PROJECT_ROOT}" && uv run claudechat install 2>&1 | grep -viE "warn") \
    || die "Install failed"
  echo
  ok "Installed. The daemon now starts with your session."
  print_status
  echo
  printf "┌──────────────────────────────────────────────────────────────┐\n"
  printf "│  claudechat is installed                                     │\n"
  printf "├──────────────────────────────────────────────────────────────┤\n"
  printf "│  %-59s │\n" "claudechat on        speak Claude Code replies"
  printf "│  %-59s │\n" "claudechat off       silent"
  printf "│  %-59s │\n" "claudechat toggle    flip it"
  printf "│  %-59s │\n" "claudechat status    speech, daemon, current voice"
  printf "├──────────────────────────────────────────────────────────────┤\n"
  printf "│  %-59s │\n" "Speech is OFF until you run: claudechat on"
  printf "│  %-59s │\n" "Keep /voice enabled — it is input, this is output."
  printf "│  %-59s │\n" "Remove everything: ./start.sh --uninstall"
  printf "└──────────────────────────────────────────────────────────────┘\n"
  echo
  exit 0
fi

# ── 6. Start the daemon ──────────────────────────────────────────────────────
header "5. Starting the daemon"

if [[ -f "${UNIT}" ]]; then
  systemctl --user start claudechat || die "systemctl --user start claudechat failed"
  wait_for_socket "claudechat daemon" "journalctl --user -u claudechat"
  ok "Daemon running under systemd"
else
  stop_daemon >/dev/null 2>&1 || true
  info "Starting daemon (models load once, takes about 30s)..."
  # --fork is load-bearing. Plain `setsid` only forks when it is not already a
  # process-group leader; inside a backgrounded subshell it IS one, so it execs
  # instead and the daemon stays a direct child. The script then blocks in
  # wait() at exit and anything piping start.sh hangs long after the summary
  # has printed. --fork reparents the daemon away so the script can exit.
  (cd "${PROJECT_ROOT}" && setsid --fork uv run claudechat serve \
     </dev/null >"${LOG_DIR}/daemon.log" 2>&1 &)
  wait_for_socket "claudechat daemon" "${LOG_DIR}/daemon.log"
  [[ -n "$(daemon_pids)" ]] || die "Daemon exited immediately — check ${LOG_DIR}/daemon.log"
  ok "Daemon running (not installed as a service — use --install to make it permanent)"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
VOICE="$(grep -oP 'tts_voice\s*=\s*"\K[^"]+' "${CONFIG}" 2>/dev/null || echo unknown)"
SPEECH="$(grep -qP 'spoken_summaries\s*=\s*true' "${CONFIG}" 2>/dev/null && echo on || echo off)"

echo
printf "┌──────────────────────────────────────────────────────────────┐\n"
printf "│  claudechat is running                                       │\n"
printf "├──────────────────────────────────────────────────────────────┤\n"
printf "│  Voice   ──  %-47s │\n" "${VOICE}"
printf "│  Speech  ──  %-47s │\n" "${SPEECH}"
printf "│  Socket  ──  %-47s │\n" "${SOCKET}"
printf "├──────────────────────────────────────────────────────────────┤\n"
printf "│  %-59s │\n" "claudechat on | off | toggle | status"
printf "│  %-59s │\n" "Talk to it directly:  uv run claudechat"
printf "├──────────────────────────────────────────────────────────────┤\n"
printf "│  Logs:  %-52s │\n" "${LOG_DIR}/"
printf "│  Stop:  %-52s │\n" "./start.sh --stop"
printf "│  Setup: %-52s │\n" "./start.sh --install   (hook + autostart)"
printf "└──────────────────────────────────────────────────────────────┘\n"
echo
