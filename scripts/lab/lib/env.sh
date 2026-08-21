#!/usr/bin/env bash
# =============================================================================
# lib/env.sh — secrets loading and redacted reporting for the lab scripts
#
# Sourced, not executed. Every lab script starts with:
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/env.sh"
#   lab_load_env
#   lab_require ONTAP_CLUSTER_MGMT ONTAP_RO_USER
#
# Design constraints this file enforces, because a leak here is unrecoverable once
# pushed:
#
#   * Values are never printed. Reports name the variable, not its contents, so a
#     pasted terminal transcript cannot disclose the topology. `--show-targets`
#     opts into revealing them on the operator's own screen.
#   * No fingerprints or partial masks of hosts. A short hash of an IPv4 address is
#     brute-forceable in seconds -- the whole space is 2^32 -- so "redacted"
#     fingerprints would be a false reassurance. Variable names only.
#   * .env is parsed, not sourced. Sourcing would execute whatever the file
#     contains; a stray backtick in a pasted password would run as a command.
# =============================================================================

# Guard against double-sourcing clobbering the parsed table.
[[ -n "${_LAB_ENV_SH_LOADED:-}" ]] && return 0
_LAB_ENV_SH_LOADED=1

if [[ -t 1 ]]; then
  LAB_RED=$'\033[0;31m'; LAB_GREEN=$'\033[0;32m'; LAB_YELLOW=$'\033[0;33m'
  LAB_BLUE=$'\033[0;34m'; LAB_BOLD=$'\033[1m'; LAB_DIM=$'\033[2m'; LAB_RESET=$'\033[0m'
else
  LAB_RED=''; LAB_GREEN=''; LAB_YELLOW=''
  LAB_BLUE=''; LAB_BOLD=''; LAB_DIM=''; LAB_RESET=''
fi

LAB_PASS=0; LAB_FAIL=0; LAB_WARN=0; LAB_SKIP=0

declare -a _LAB_KNOWN_KEYS=()

# Set by a script's argument parser before calling the reporters.
LAB_SHOW_TARGETS="${LAB_SHOW_TARGETS:-0}"
LAB_APPLY="${LAB_APPLY:-0}"
LAB_CONFIRM="${LAB_CONFIRM:-0}"

lab_pass()  { LAB_PASS=$((LAB_PASS+1)); printf "%s  [PASS]%s %s\n" "$LAB_GREEN"  "$LAB_RESET" "$1"; }
lab_fail()  { LAB_FAIL=$((LAB_FAIL+1)); printf "%s  [FAIL]%s %s\n" "$LAB_RED"    "$LAB_RESET" "$1"; }
lab_warn()  { LAB_WARN=$((LAB_WARN+1)); printf "%s  [WARN]%s %s\n" "$LAB_YELLOW" "$LAB_RESET" "$1"; }
lab_skip()  { LAB_SKIP=$((LAB_SKIP+1)); printf "%s  [SKIP]%s %s\n" "$LAB_BLUE"   "$LAB_RESET" "$1"; }
lab_info()  { printf "%s  [INFO]%s %s\n" "$LAB_BOLD" "$LAB_RESET" "$1"; }
lab_note()  { printf "%s         %s%s\n" "$LAB_DIM" "$1" "$LAB_RESET"; }
lab_header(){ printf "\n%s___ %s%s\n" "$LAB_BOLD" "$1" "$LAB_RESET"; }

# lab_indent — prefix every line of stdin. A per-line prefix is not expressible with
# ${var//search/replace}, which is why this is a function and not a parameter expansion.
lab_indent() { local pad="${1:-      }"; while IFS= read -r l || [[ -n "$l" ]]; do printf '%s%s\n' "$pad" "$l"; done; }

lab_die() { printf "%s  [ABORT]%s %s\n" "$LAB_RED" "$LAB_RESET" "$1" >&2; exit 2; }

# ---------------------------------------------------------------------------
# lab_load_env [path]
#
# Parses KEY=VALUE from the env file into the environment. Refuses to continue when
# the file is missing or world/group readable: a lab .env holds cluster admin
# credentials, and 0644 means every local account can read them.
# ---------------------------------------------------------------------------
lab_load_env() {
  local env_file="${1:-${LAB_ENV_FILE:-}}"
  if [[ -z "$env_file" ]]; then
    env_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
  fi

  if [[ ! -f "$env_file" ]]; then
    lab_die "env file not found: ${env_file}
         Copy the template and fill it in:
           cp scripts/lab/.env.example scripts/lab/.env
           chmod 600 scripts/lab/.env"
  fi

  # stat differs between BSD (macOS) and GNU (Linux); this lab spans both.
  local mode
  if stat -f '%Lp' "$env_file" >/dev/null 2>&1; then
    mode="$(stat -f '%Lp' "$env_file")"
  else
    mode="$(stat -c '%a' "$env_file")"
  fi
  if [[ "$mode" != "600" && "$mode" != "400" ]]; then
    lab_die "env file mode is ${mode}, refusing to read credentials from it.
         Other local accounts can read 0${mode}. Fix with:
           chmod 600 ${env_file}"
  fi

  local line_no=0 key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line_no=$((line_no+1))
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "${line#"${line%%[![:space:]]*}"}" == \#* ]] && continue

    if [[ ! "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=(.*)$ ]]; then
      # Naming the line number but not the content: the malformed line may be a
      # half-pasted secret.
      lab_die "${env_file}:${line_no} is not KEY=VALUE. Not showing the line (it may contain a secret)."
    fi
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"

    # Strip one layer of matching quotes and trailing whitespace on bare values.
    if [[ "$value" =~ ^\"(.*)\"[[:space:]]*$ ]] || [[ "$value" =~ ^\'(.*)\'[[:space:]]*$ ]]; then
      value="${BASH_REMATCH[1]}"
    else
      value="${value%"${value##*[![:space:]]}"}"
    fi

    export "${key}=${value}"
    _LAB_KNOWN_KEYS+=("$key")
  done < "$env_file"

  LAB_ENV_FILE="$env_file"
  lab_info "Loaded $(( ${#_LAB_KNOWN_KEYS[@]} )) variables from ${env_file##*/} (values not shown)"
}

# ---------------------------------------------------------------------------
# lab_require VAR...
#
# Aborts listing the names of variables that are unset or empty. Names are safe to
# print; that is the entire reason this reports names rather than a diff of values.
# ---------------------------------------------------------------------------
lab_require() {
  local missing=() v
  for v in "$@"; do
    [[ -z "${!v:-}" ]] && missing+=("$v")
  done
  if (( ${#missing[@]} > 0 )); then
    lab_die "missing or empty in ${LAB_ENV_FILE:-.env}: ${missing[*]}"
  fi
}

# ---------------------------------------------------------------------------
# lab_target VAR — prints the variable NAME for reports, or the value when the
# operator passed --show-targets.
# ---------------------------------------------------------------------------
lab_target() {
  local v="$1"
  if [[ "$LAB_SHOW_TARGETS" == "1" ]]; then
    printf '%s' "${!v:-<unset>}"
  else
    # The literal text ${NAME} is the intended output: reports name the variable
    # instead of resolving it. Expansion here would defeat the whole redaction.
    # shellcheck disable=SC2016
    printf '${%s}' "$v"
  fi
}

# ---------------------------------------------------------------------------
# lab_ssh VAR_HOST VAR_USER -- command...
#
# BatchMode so a missing key fails instead of hanging on a password prompt, which
# would look like a network timeout. StrictHostKeyChecking stays at the default:
# turning it off here would make a man-in-the-middle silently succeed against the
# cluster management LIF.
# ---------------------------------------------------------------------------
lab_ssh() {
  local host_var="$1" user_var="$2"; shift 2
  [[ "${1:-}" == "--" ]] && shift
  local host="${!host_var:-}" user="${!user_var:-}"
  [[ -z "$host" || -z "$user" ]] && { lab_die "lab_ssh: \${${host_var}} or \${${user_var}} is empty"; }

  local -a key_opt=()
  [[ -n "${ONTAP_SSH_KEY:-}" && -f "${ONTAP_SSH_KEY}" ]] && key_opt=(-i "${ONTAP_SSH_KEY}")

  ssh -n -o BatchMode=yes \
      -o ConnectTimeout="${LAB_SSH_TIMEOUT:-8}" \
      -o NumberOfPasswordPrompts=0 \
      "${key_opt[@]+"${key_opt[@]}"}" \
      "${user}@${host}" "$@"
}

# ---------------------------------------------------------------------------
# Verdicts over command output.
#
# A pattern search over empty output finds nothing, and a naive check then reports the
# healthy verdict. Against an unreachable cluster that produced eight PASS lines from
# commands that never ran. "No bad rows" and "no rows at all" are different facts, so
# every verdict here refuses to conclude anything from empty input.
# ---------------------------------------------------------------------------
lab_have_output() {
  local label="$1" out="$2"
  if [[ -z "${out//[[:space:]]/}" ]]; then
    lab_fail "${label} — nothing to evaluate; the read command returned no output"
    return 1
  fi
  return 0
}

# lab_absent LABEL PATTERN OUTPUT FOUND_MSG — PASS when the pattern is absent.
lab_absent() {
  local label="$1" pattern="$2" out="$3" found_msg="$4"
  lab_have_output "$label" "$out" || return 0
  if grep -qiE "$pattern" <<< "$out"; then lab_fail "$found_msg"; else lab_pass "$label"; fi
}

# lab_absent_warn LABEL PATTERN OUTPUT WARN_MSG — as above but advisory.
lab_absent_warn() {
  local label="$1" pattern="$2" out="$3" warn_msg="$4"
  lab_have_output "$label" "$out" || return 1
  if grep -qiE "$pattern" <<< "$out"; then lab_warn "$warn_msg"; return 1; fi
  lab_pass "$label"; return 0
}

# lab_present_warn LABEL PATTERN OUTPUT MISSING_MSG — PASS when the pattern IS there.
lab_present_warn() {
  local label="$1" pattern="$2" out="$3" missing_msg="$4"
  lab_have_output "$label" "$out" || return 1
  if grep -qiE "$pattern" <<< "$out"; then lab_pass "$label"; return 0; fi
  lab_warn "$missing_msg"; return 1
}

# ---------------------------------------------------------------------------
# lab_probe_tcp VAR_HOST PORT — bounded TCP connect test, no external binaries.
#
# Measured on macOS
#   nc -z -w 1 <black-holed addr> 22   ->  returned after 75 seconds
# because BSD nc treats -w as an idle/read timeout, not a connect timeout. GNU
# `timeout` is not present on macOS either, so the obvious fallback silently reports
# every host unreachable with status 127. Both failure modes look like a hung probe or
# a dead network rather than a broken tool, so the watchdog is implemented here: the
# connect runs in a background subshell and is killed once the budget expires.
# ---------------------------------------------------------------------------
lab_probe_tcp() {
  local host="${!1:-}" port="$2"
  local limit="${LAB_TCP_TIMEOUT:-5}"
  [[ -z "$host" || -z "$port" ]] && return 2

  ( exec 3<>"/dev/tcp/${host}/${port}" ) 2>/dev/null &
  local pid=$! ticks=0 budget=$(( limit * 10 ))

  while kill -0 "$pid" 2>/dev/null; do
    if (( ticks >= budget )); then
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 1
    fi
    sleep 0.1
    ticks=$(( ticks + 1 ))
  done

  # Exit status of the connect itself, so a refused port is distinguishable from a
  # timeout by the caller's own timing if it cares.
  wait "$pid" 2>/dev/null
}

# ---------------------------------------------------------------------------
# lab_summary — final counters. Exit status is the caller's business; a probe
# script should not decide the exit code for a checklist it does not own.
# ---------------------------------------------------------------------------
lab_summary() {
  lab_header "Summary"
  printf "  %sPASS: %d%s  %sFAIL: %d%s  %sWARN: %d%s  %sSKIP: %d%s\n" \
    "$LAB_GREEN" "$LAB_PASS" "$LAB_RESET" \
    "$LAB_RED" "$LAB_FAIL" "$LAB_RESET" \
    "$LAB_YELLOW" "$LAB_WARN" "$LAB_RESET" \
    "$LAB_BLUE" "$LAB_SKIP" "$LAB_RESET"
  if [[ "$LAB_SHOW_TARGETS" != "1" ]]; then
    lab_note "Targets shown as variable names. Add --show-targets to resolve them locally."
  else
    printf "  %s[!] Resolved values are on screen. Do not paste this transcript anywhere.%s\n" \
      "$LAB_YELLOW" "$LAB_RESET"
  fi
  (( LAB_FAIL == 0 ))
}

# ---------------------------------------------------------------------------
# lab_evidence_path NAME  — TRACKED. Redacted content only: variable names, counters,
#                           pass/fail. Safe to commit.
# lab_raw_log_path NAME    — GITIGNORED. Raw device output, which carries addresses,
#                           serial numbers and host names. Never committed.
#
# These are separate functions rather than one with a flag because the flag would
# eventually be passed wrong, and the failure mode is a serial number in git history
# that survives rebase.
# ---------------------------------------------------------------------------
lab_evidence_path() {
  local name="$1"
  local root="${LAB_EVIDENCE_DIR:-docs/verification-evidence}"
  mkdir -p "$root"
  printf '%s/%s-%s.md' "$root" "${LAB_RUN_ID:-unstamped}" "$name"
}

lab_raw_log_path() {
  local name="$1"
  local root="${LAB_RAW_DIR:-${SCRIPT_DIR:-scripts/lab}/.evidence}"
  mkdir -p "$root"
  chmod 700 "$root" 2>/dev/null || true
  printf '%s/%s-%s.log' "$root" "${LAB_RUN_ID:-unstamped}" "$name"
}
