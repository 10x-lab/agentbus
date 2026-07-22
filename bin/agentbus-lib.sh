# AgentBus shared shell library. Source this, do not execute it.
#
# Provides container-runtime-agnostic access to the agentbus-redis container.
# Works with docker or podman without any per-script configuration.
#
#   agentbus_runtime     -> prints the container runtime binary (docker|podman)
#   agentbus_redis ARGS  -> runs `redis-cli ARGS` inside the container
#
# Selection order:
#   1. $AGENTBUS_CONTAINER_RUNTIME if set (explicit override)
#   2. the runtime whose running containers include $AGENTBUS_CONTAINER
#      (default agentbus-redis) — handles machines with both installed
#   3. the first of docker / podman that exists on PATH
# The result is cached for the life of the process.

_AGENTBUS_RT=""

agentbus_runtime() {
  if [ -n "$_AGENTBUS_RT" ]; then
    printf '%s' "$_AGENTBUS_RT"
    return 0
  fi

  local container="${AGENTBUS_CONTAINER:-agentbus-redis}" rt

  if [ -n "${AGENTBUS_CONTAINER_RUNTIME:-}" ]; then
    _AGENTBUS_RT="$AGENTBUS_CONTAINER_RUNTIME"
  else
    for rt in docker podman; do
      command -v "$rt" >/dev/null 2>&1 || continue
      if "$rt" ps --format '{{.Names}}' 2>/dev/null | grep -qx "$container"; then
        _AGENTBUS_RT="$rt"
        break
      fi
    done
    if [ -z "$_AGENTBUS_RT" ]; then
      for rt in docker podman; do
        if command -v "$rt" >/dev/null 2>&1; then
          _AGENTBUS_RT="$rt"
          break
        fi
      done
    fi
  fi

  [ -n "$_AGENTBUS_RT" ] || _AGENTBUS_RT=docker
  printf '%s' "$_AGENTBUS_RT"
}

# agentbus_redis [redis-cli args...] — exec redis-cli inside the container.
# Uses -i so callers can pipe stdin (EVAL scripts, payloads).
agentbus_redis() {
  local rt
  rt="$(agentbus_runtime)"
  if ! command -v "$rt" >/dev/null 2>&1; then
    echo "agentbus: no container runtime found (docker or podman); set AGENTBUS_CONTAINER_RUNTIME" >&2
    return 2
  fi
  "$rt" exec -i "${AGENTBUS_CONTAINER:-agentbus-redis}" redis-cli "$@"
}
