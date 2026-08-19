# Tailscale in Claude Code sessions

Lets an agent session reach hosts that only exist on your tailnet -- a dev
machine, an internal package registry, a staging service, a device on a subnet
behind a subnet router -- instead of only the public internet.

`scripts/tailscale-up.sh` installs `tailscaled`, joins the tailnet, and is safe to
re-run. A `SessionStart` hook can run it automatically for every remote session.

## Why this works in the remote sandbox

Claude Code on the web runs in a container whose outbound HTTPS goes through a
policy-enforcing egress proxy. Tailscale still works there, verified in this repo's
environment:

| Requirement | Status in the sandbox |
| --- | --- |
| `controlplane` / `login` / `derp*.tailscale.com` | reachable (`tailscaled` reads `HTTPS_PROXY` for its control connection) |
| Outbound UDP | works, so WireGuard can hole-punch a direct path instead of relaying via DERP |
| `/dev/net/tun`, root, `CAP_NET_ADMIN`, `iptables` | present, so the kernel-TUN datapath is available |
| Tailnet addresses vs. the egress proxy | the sandbox's `no_proxy` already lists `100.64.0.0/10` and the RFC1918 ranges, so peer traffic bypasses the proxy and rides the tunnel |

Because kernel TUN works, tailnet addresses are reachable from every process --
`curl`, `git`, `ssh`, a test suite -- with no per-tool proxy settings. The script
falls back to `--tun=userspace-networking` if `/dev/net/tun` is ever unavailable;
in that mode reaching the tailnet means going through the SOCKS5 proxy it starts
on `localhost:1055` (or HTTP on `1056`), e.g. `curl --socks5-hostname localhost:1055`.

## Setup

### 1. Mint an auth key

In the [tailnet admin console](https://login.tailscale.com/admin/settings/keys),
generate an auth key with:

- **Ephemeral** -- on. Each session is a throwaway container; ephemeral nodes are
  removed automatically once they go offline, instead of accumulating dead hosts
  in your device list.
- **Reusable** -- on, if more than one session should be able to use the same key.
- **Tags** -- e.g. `tag:ci` or `tag:claude-code`. Tagging is what lets you write an
  ACL that grants these sessions only the access they need. A tagged key also does
  not expire the way a user-owned node does.
- **Expiry** -- as short as your workflow tolerates.

### 2. Scope it with an ACL

An auth key is a credential handed to an automated agent, so grant the narrowest
access that makes the session useful rather than reusing a key that can reach the
whole tailnet. In the admin console's access controls:

```jsonc
{
  "tagOwners": { "tag:claude-code": ["autogroup:admin"] },
  "acls": [
    {
      // Only what the session actually needs -- widen deliberately.
      "action": "accept",
      "src":    ["tag:claude-code"],
      "dst":    ["tag:dev-box:22,8080"]
    }
  ]
}
```

The script passes `--shields-up`, so nothing on the tailnet can open connections
*into* the session; traffic is outbound only. It does not enable Tailscale SSH --
if you want to SSH into a session, set `TS_EXTRA_ARGS="--ssh"` and add a matching
`ssh` rule to the ACL.

### 3. Put the key in the environment

Add `TS_AUTHKEY` as an environment variable on the Claude Code environment
(claude.ai/code → the environment used for this repo → environment variables), so
it is available to sessions without being committed. Never commit a key to the
repo; anything in git history is a leaked credential, and `tskey-auth-...` strings
are exactly what secret scanners look for.

### 4. Enable the automatic hook (optional)

With `.claude/hooks/session-start.sh` in place and registered in
`.claude/settings.json`, every remote session joins the tailnet before the agent
starts working. The hook is a no-op when `TS_AUTHKEY` is unset or when the session
is local, so contributors without a key are unaffected.

Those two files are **not** committed yet -- creating a hook that Claude Code
executes automatically at session start is a change worth making deliberately
rather than having an agent add it in passing. To enable it, create
`.claude/hooks/session-start.sh` (`chmod +x`):

```bash
#!/usr/bin/env bash
# Joins Claude Code on the web sessions to the tailnet so the agent can reach
# private hosts that are not published to the internet. A no-op unless we are in
# a remote sandbox and a TS_AUTHKEY is configured for the environment.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

if [ -z "${TS_AUTHKEY:-}" ]; then
    echo "tailscale: TS_AUTHKEY not set for this environment, skipping"
    exit 0
fi

"$CLAUDE_PROJECT_DIR/scripts/tailscale-up.sh"

echo 'export TS_SOCKET="/var/run/tailscale/tailscaled.sock"' >> "$CLAUDE_ENV_FILE"
```

and register it in `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh"
          }
        ]
      }
    ]
  }
}
```

The hook runs **synchronously**: the session takes ~10-20s longer to start, but the
tunnel is guaranteed to be up before the agent runs anything that depends on it.
Making it asynchronous (`{"async": true}`) trades that guarantee for a faster start.

Hooks only take effect once they are on the branch a session starts from, so this
needs to be merged into the default branch to apply to future sessions.

## Manual use

```bash
TS_AUTHKEY=tskey-auth-... sudo -E ./scripts/tailscale-up.sh
tailscale status
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `TS_AUTHKEY` | *(required)* | Tailnet auth key |
| `TS_VERSION` | `1.90.9` | Pinned tailscale release to install |
| `TS_HOSTNAME` | `claude-<repo>-<host suffix>` | Node name in the admin console |
| `TS_SHIELDS_UP` | `1` | Block all inbound connections to the session |
| `TS_ACCEPT_ROUTES` | `1` | Accept subnet routes advertised by subnet routers |
| `TS_EXTRA_ARGS` | *(empty)* | Extra `tailscale up` flags, e.g. `--ssh`, `--exit-node=...` |
| `TS_SOCKET` | `/var/run/tailscale/tailscaled.sock` | `tailscaled` socket path |
| `TS_TIMEOUT` | `90` | Seconds to wait for the tunnel to come up |

## Troubleshooting

- **`tailscale up` fails with "authorization required"** -- the tailnet requires
  manual device approval, or the key's tag is not permitted by `tagOwners`. Approve
  the node once in the admin console, or fix the tag.
- **Key expired** -- auth keys have a hard expiry; mint a new one and update the
  environment variable.
- **Peers show as `relay` rather than a direct connection** -- traffic is going over
  DERP. It still works, just with more latency. `tailscale netcheck` reports what
  the sandbox's NAT situation allows.
- **A host resolves but does not answer** -- check the ACL first; `--shields-up`
  only affects inbound, so an outbound denial is almost always an ACL rule.
- **Daemon logs** -- `/var/log/tailscaled.log`.
