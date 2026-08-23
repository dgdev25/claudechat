#!/usr/bin/env bash
# start.sh — claudechat launcher and one-time setup
#
# Brings up the speech daemon that speaks Claude's replies aloud.
#
# Two ways to run it, and autostart is NOT the default:
#   per session  ./start.sh          starts the daemon now, gone when you stop it
#   always on    ./start.sh --autostart   adds a systemd user service
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
#   ./start.sh               # set up if needed, then run the daemon for THIS session
#   ./start.sh --install     # register the Claude Code Stop hook (no autostart)
#   ./start.sh --autostart   # hook + systemd service, starts with every login
#   ./start.sh --no-autostart# remove the service, keep the hook
#   ./start.sh --stop        # stop the daemon
#   ./start.sh --status      # speech, daemon, autostart, voice
#   ./start.sh --rebuild     # force dependency re-sync
#   ./start.sh --uninstall   # remove hook and service entirely

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
LOG_DIR="${PROJECT_ROOT}/logs"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-${HOME}/.cache/claudechat/run}/claudechat"
SOCKET="${RUNTIME_DIR}/engine.sock"
CONFIG="${HOME}/.config/claudechat/config.toml"
SETTINGS="${HOME}/.claude/settings.json"

# ── Platform ─────────────────────────────────────────────────────────────────
# Audio and the service manager are the only platform-specific parts; the
# engine itself is identical on both.
OS="$(uname -s)"
if [[ "${OS}" == "Darwin" ]]; then
  IS_MAC=true
  UNIT="${HOME}/Library/LaunchAgents/com.claudechat.daemon.plist"
  AUDIO_TOOLS=(play rec)
  AUDIO_ALT=(ffplay ffmpeg)
  AUDIO_INSTALL="brew install sox        (or: brew install ffmpeg)"
else
  IS_MAC=false
  UNIT="${HOME}/.config/systemd/user/claudechat.service"
  AUDIO_TOOLS=(pw-cat pw-record)
  AUDIO_ALT=()
  AUDIO_INSTALL="sudo apt install pipewire-bin   (Debian/Ubuntu)"
fi

# ── Helpers ──────────────────────────────────────────────────────────────────
info()   { echo "  ${*}"; }
ok()     { echo "  [ok] ${*}"; }
warn()   { echo "  [warn] ${*}"; }
die()    { echo "[fail] ${*}" >&2; exit 1; }
header() { echo; echo "── ${*}"; }

# ── Flags ────────────────────────────────────────────────────────────────────
DO_INSTALL=false
DO_AUTOSTART=false
DO_NO_AUTOSTART=false
STOP_ONLY=false
STATUS_ONLY=false
FORCE_REBUILD=false
DO_UNINSTALL=false
for arg in "$@"; do
  case "${arg}" in
    --install)      DO_INSTALL=true ;;
    --autostart)    DO_AUTOSTART=true ;;
    --no-autostart) DO_NO_AUTOSTART=true ;;
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
  if [[ -f "${UNIT}" ]]; then
    if [[ "${IS_MAC}" == true ]]; then
      launchctl stop com.claudechat.daemon 2>/dev/null && ok "Stopped launchd job" && return
    elif systemctl --user is-active --quiet claudechat 2>/dev/null; then
      systemctl --user stop claudechat && ok "Stopped systemd service"
      return
    fi
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
  rm -f "${HOME}/.local/bin/claudechat" 2>/dev/null && ok "Removed launcher from PATH" || true
  if [[ -f "${UNIT}" ]]; then
    if [[ "${IS_MAC}" == true ]]; then
      launchctl unload "${UNIT}" &>/dev/null || true
    else
      systemctl --user disable claudechat &>/dev/null || true
    fi
    rm -f "${UNIT}"
    [[ "${IS_MAC}" == false ]] && { systemctl --user daemon-reload &>/dev/null || true; }
    ok "Removed autostart"
  else
    info "No autostart installed"
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

# ── --no-autostart ───────────────────────────────────────────────────────────
if [[ "${DO_NO_AUTOSTART}" == true ]]; then
  header "Removing autostart (keeping the Stop hook)"
  (cd "${PROJECT_ROOT}" && uv run claudechat uninstall-service 2>&1 | grep -viE "warn") || true
  ok "Speech now runs only when you start it: ./start.sh"
  exit 0
fi

# ── --status ─────────────────────────────────────────────────────────────────
if [[ "${STATUS_ONLY}" == true ]]; then
  header "claudechat status"
  print_status
  [[ -f "${UNIT}" ]] \
    && ok "autostart installed (remove with ./start.sh --no-autostart)" \
    || info "autostart off — daemon runs per session (add with ./start.sh --autostart)"
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
for tool in "${AUDIO_TOOLS[@]}"; do
  command -v "${tool}" &>/dev/null || MISSING_AUDIO+=("${tool}")
done
if [[ ${#MISSING_AUDIO[@]} -gt 0 ]] && [[ ${#AUDIO_ALT[@]} -gt 0 ]]; then
  ALT_OK=true
  for tool in "${AUDIO_ALT[@]}"; do
    command -v "${tool}" &>/dev/null || ALT_OK=false
  done
  [[ "${ALT_OK}" == true ]] && MISSING_AUDIO=() && ok "Audio tools: ${AUDIO_ALT[*]} (fallback)"
fi
if [[ ${#MISSING_AUDIO[@]} -gt 0 ]]; then
  die "Missing audio tools: ${MISSING_AUDIO[*]}
       Install with:  ${AUDIO_INSTALL}
       claudechat streams raw PCM, which needs a command-line audio tool."
fi
[[ ${#MISSING_AUDIO[@]} -eq 0 ]] && ok "Audio tools: ${AUDIO_TOOLS[*]}"

if [[ "${IS_MAC}" == false ]] && ! pgrep -x pipewire &>/dev/null; then
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
if [[ "${DO_INSTALL}" == true || "${DO_AUTOSTART}" == true ]]; then
  if [[ "${DO_AUTOSTART}" == true ]]; then
    header "5. Registering the Stop hook and enabling autostart"
    info "This writes to ${SETTINGS} and ${UNIT}."
  else
    header "5. Registering the Stop hook"
    info "This writes to ${SETTINGS} only. No service, no autostart."
  fi
  info "Undo at any time with: ./start.sh --uninstall"
  INSTALL_CMD="install"; [[ "${DO_AUTOSTART}" == true ]] && INSTALL_CMD="autostart"
  (cd "${PROJECT_ROOT}" && uv run claudechat "${INSTALL_CMD}" 2>&1 | grep -viE "warn") \
    || die "Install failed"
  echo

  # Set up echo cancellation for voice barge-in (Linux only, best-effort)
  if [[ "${IS_MAC}" == false ]]; then
    header "5b. Voice barge-in setup (optional)"
    if (cd "${PROJECT_ROOT}" && uv run claudechat setup-echo-cancel 2>&1 | grep -viE "warn") >/dev/null 2>&1; then
      ok "Voice barge-in enabled"
    else
      info "Voice barge-in setup skipped — enable later with: claudechat setup-echo-cancel"
    fi
    echo
  fi
  if [[ "${DO_AUTOSTART}" == true ]]; then
    ok "Installed. The daemon now starts with your session."
  else
    ok "Hook registered. Start speech per session with: ./start.sh"
  fi
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
  printf "│  %-59s │\n" "Autostart later:   ./start.sh --autostart"
  printf "│  %-59s │\n" "Remove everything: ./start.sh --uninstall"
  printf "└──────────────────────────────────────────────────────────────┘\n"
  echo
  exit 0
fi

# ── 6. Start the daemon ──────────────────────────────────────────────────────
header "5. Starting the daemon"

if [[ -f "${UNIT}" ]]; then
  if [[ "${IS_MAC}" == true ]]; then
    launchctl start com.claudechat.daemon || die "launchctl start failed"
    wait_for_socket "claudechat daemon" "${LOG_DIR}/daemon.log"
    ok "Daemon running under launchd"
  else
    systemctl --user start claudechat || die "systemctl --user start claudechat failed"
    wait_for_socket "claudechat daemon" "journalctl --user -u claudechat"
    ok "Daemon running under systemd"
  fi
else
  stop_daemon >/dev/null 2>&1 || true
  info "Starting daemon (models load once, takes about 30s)..."
  # --fork is load-bearing. Plain `setsid` only forks when it is not already a
  # process-group leader; inside a backgrounded subshell it IS one, so it execs
  # instead and the daemon stays a direct child. The script then blocks in
  # wait() at exit and anything piping start.sh hangs long after the summary
  # has printed. --fork reparents the daemon away so the script can exit.
  # `daemon-start` detaches in Python, which behaves the same on Linux and
  # macOS. setsid --fork is util-linux and does not exist on macOS, and doing
  # it with a bare & left the daemon a child of this script, so the script
  # blocked in wait() at exit.
  (cd "${PROJECT_ROOT}" && uv run claudechat daemon-start 2>&1 | grep -viE "warn") \
    || die "Daemon failed to start — check ${LOG_DIR}/daemon.log"
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
