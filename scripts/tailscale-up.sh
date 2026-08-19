#!/usr/bin/env bash
# Join this machine to a tailnet. Written for throwaway containers -- Claude Code
# on the web sessions in particular -- where there is no systemd, no package
# manager state worth keeping, and the whole filesystem disappears when the
# session ends.
#
# Two things make this work in that sandbox despite its locked-down egress:
#   - controlplane/login/derp*.tailscale.com are reachable, and tailscaled reads
#     HTTPS_PROXY for the control connection, so registration goes through the
#     egress proxy. WireGuard itself also has direct UDP, so peer traffic can go
#     direct rather than always relaying via DERP.
#   - the sandbox's no_proxy list already contains 100.64.0.0/10 (plus the RFC1918
#     ranges), so once the tunnel is up, traffic to tailnet peers and to subnets
#     behind a subnet router bypasses the egress proxy and rides WireGuard.
#
# Requires TS_AUTHKEY. Everything else has a working default. Safe to re-run: if
# the daemon is already up and logged in, this exits without touching it.
set -euo pipefail

TS_VERSION="${TS_VERSION:-1.90.9}"
TS_HOSTNAME="${TS_HOSTNAME:-}"
TS_STATE_DIR="${TS_STATE_DIR:-/var/lib/tailscale}"
TS_SOCKET="${TS_SOCKET:-/var/run/tailscale/tailscaled.sock}"
TS_LOG="${TS_LOG:-/var/log/tailscaled.log}"
# Inbound connections to an agent sandbox are almost never what you want, so
# shields are up by default. Routes advertised by subnet routers are accepted so
# that "reach the box behind the subnet router" works without extra flags.
TS_SHIELDS_UP="${TS_SHIELDS_UP:-1}"
TS_ACCEPT_ROUTES="${TS_ACCEPT_ROUTES:-1}"
TS_EXTRA_ARGS="${TS_EXTRA_ARGS:-}"
TS_TIMEOUT="${TS_TIMEOUT:-90}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'tailscale-up: %s\n' "$*" >&2; exit 1; }

# `tailscale status` exits non-zero whenever the backend is not Running -- which
# includes the perfectly healthy NeedsLogin state right after startup -- so it
# cannot be used to test whether the daemon is up. `status --json` exits 0 and
# reports the state, so probe with that.
ts_state() {
    tailscale --socket="$TS_SOCKET" status --json 2>/dev/null \
        | grep -o '"BackendState": *"[^"]*"' | cut -d'"' -f4
}

[ "$(id -u)" -eq 0 ] || die "must run as root (needs /dev/net/tun and iptables)"
[ -n "${TS_AUTHKEY:-}" ] || die "TS_AUTHKEY is not set; see docs/TAILSCALE.md"

if [ -z "$TS_HOSTNAME" ]; then
    # Identifies the node in the tailnet admin console. Keep it recognisable as a
    # short-lived agent container rather than a real machine.
    TS_HOSTNAME="claude-$(basename "$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null || echo sandbox)")-$(hostname | tr -cd 'a-zA-Z0-9' | tail -c 8)"
fi

# ---------------------------------------------------------------- install

if ! command -v tailscaled >/dev/null 2>&1; then
    log "Installing tailscale $TS_VERSION"
    arch="$(uname -m)"
    case "$arch" in
        x86_64)  ts_arch=amd64 ;;
        aarch64|arm64) ts_arch=arm64 ;;
        *) die "unsupported architecture: $arch" ;;
    esac
    # The static tarball rather than the apt repo: no systemd here to hand the
    # unit file to, and this is one download instead of a repo refresh.
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    url="https://pkgs.tailscale.com/stable/tailscale_${TS_VERSION}_${ts_arch}.tgz"
    curl -fsSL --retry 3 --retry-delay 2 -o "$tmp/ts.tgz" "$url" \
        || die "download failed: $url"
    tar xzf "$tmp/ts.tgz" -C "$tmp"
    install -m 0755 "$tmp/tailscale_${TS_VERSION}_${ts_arch}/tailscaled" /usr/local/sbin/tailscaled
    install -m 0755 "$tmp/tailscale_${TS_VERSION}_${ts_arch}/tailscale"  /usr/local/bin/tailscale
    rm -rf "$tmp"; trap - EXIT
fi

log "tailscale $(tailscale version | head -1)"

# ---------------------------------------------------------------- daemon

mkdir -p "$TS_STATE_DIR" "$(dirname "$TS_SOCKET")" "$(dirname "$TS_LOG")"

if [ -n "$(ts_state)" ]; then
    log "tailscaled already running"
else
    # Kernel TUN when /dev/net/tun is usable, because then tailnet addresses are
    # reachable from every process without any per-tool proxy configuration.
    # userspace-networking is the fallback; there, reaching the tailnet means
    # going through the SOCKS5/HTTP proxy this starts on 1055/1056.
    mode="kernel"
    if [ ! -c /dev/net/tun ]; then
        mode="userspace"
        log "/dev/net/tun missing; falling back to userspace networking"
    fi

    start_daemon() {
        local tun_args=()
        if [ "$1" = kernel ]; then
            tun_args=(--tun=tailscale0)
        else
            tun_args=(--tun=userspace-networking
                      --socks5-server=localhost:1055
                      --outbound-http-proxy-listen=localhost:1056)
        fi
        setsid /usr/local/sbin/tailscaled \
            --state="$TS_STATE_DIR/tailscaled.state" \
            --socket="$TS_SOCKET" \
            "${tun_args[@]}" >>"$TS_LOG" 2>&1 &
        ts_pid=$!
        # Give the daemon a moment to either come up or die trying.
        for _ in $(seq 20); do
            if [ -n "$(ts_state)" ]; then return 0; fi
            sleep 0.5
        done
        return 1
    }

    log "Starting tailscaled ($mode mode), logging to $TS_LOG"
    if ! start_daemon "$mode"; then
        [ "$mode" = kernel ] || die "tailscaled failed to start; see $TS_LOG"
        log "kernel mode failed; retrying with userspace networking"
        kill "$ts_pid" 2>/dev/null || true
        sleep 1
        mode=userspace
        start_daemon userspace || die "tailscaled failed to start; see $TS_LOG"
    fi
fi

# ---------------------------------------------------------------- login

if [ "$(ts_state)" = Running ]; then
    log "Already logged in"
else
    up_args=(--authkey="$TS_AUTHKEY" --hostname="$TS_HOSTNAME" --timeout="${TS_TIMEOUT}s")
    if [ "$TS_SHIELDS_UP" = 1 ]; then up_args+=(--shields-up); fi
    if [ "$TS_ACCEPT_ROUTES" = 1 ]; then up_args+=(--accept-routes); fi
    if [ -n "$TS_EXTRA_ARGS" ]; then
        # shellcheck disable=SC2206 # intentional word splitting of caller-supplied flags
        up_args+=($TS_EXTRA_ARGS)
    fi

    log "Bringing tailscale up as $TS_HOSTNAME"
    # Never let the key reach the log: tailscale echoes its own args on error.
    if ! tailscale --socket="$TS_SOCKET" up "${up_args[@]}" 2>&1 \
            | sed "s/${TS_AUTHKEY//\//\\/}/<TS_AUTHKEY>/g"; then
        die "tailscale up failed (auth key expired or not authorized?); see $TS_LOG"
    fi
fi

tailscale --socket="$TS_SOCKET" status || true
log "Tailnet IPs: $(tailscale --socket="$TS_SOCKET" ip 2>/dev/null | tr '\n' ' ')"
