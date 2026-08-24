# VM Deployment (sp00ky.net)

The operator's personal single-user VM deployment on Linode (192.46.223.21),
protected by HTTP Basic authentication, is documented here for operating the
operator's own live box — it is **not** a production-hardening or production-service
claim (see `docs/start-here/what-this-is.md`: alpha software, installed from
source).

## Services

| Service | Unit | Listens | Purpose |
|---------|------|---------|---------|
| Governor daemon | `governor.service` | Unix socket | JSON-RPC 2.0 control plane. Single authority for chat governance. |
| WebUI | `gov-webui.service` | `127.0.0.1:8420` | FastAPI (OpenAI-compat API). Delegates chat to daemon via socket. |
| Bridge | `governor-bridge.service` | `127.0.0.1:7777` | socat TCP→Unix socket. For Maude over SSH tunnel. |

The public HTTPS entrypoint is `https://sp00ky.net` and requires Basic auth.
The credential is deployment-secret material and must not be stored in this
repository. Existing exposed credentials require rotation/revocation through
the deployment owner.

## Socket path

The daemon listens on a Unix socket derived from the governor directory:

```
sha256("/opt/governor/data/.governor")[:12] = 80f5c2338ca6
socket = /run/user/0/governor-80f5c2338ca6.sock
```

The bridge (socat) and Maude (SSH tunnel) connect to this socket via TCP:7777.

## Dependencies

```
governor.service  ←  gov-webui.service (Requires + After)
                  ←  governor-bridge.service (Requires + After)
```

Restarting `governor` cascades to both dependents. All three recover cleanly.

## Environment variables

### governor.service

| Var | Value | Source |
|-----|-------|--------|
| `GOVERNOR_DIR` | `/opt/governor/data/.governor` | Inline |
| `XDG_RUNTIME_DIR` | `/run/user/0` | Inline (systemd doesn't inherit this) |
| `BACKEND_TYPE` | `anthropic` | Inline |
| `ANTHROPIC_API_KEY` | (secret) | `/etc/governor/secrets.env` |

### gov-webui.service

| Var | Value | Source |
|-----|-------|--------|
| `GOVERNOR_DIR` | `/opt/governor/data/.governor` | Inline |
| `GOVERNOR_MODE` | `code` | Inline |
| `BACKEND_TYPE` | `anthropic` | Inline |
| `GOVERNOR_SOCKET` | `/run/user/0/governor-80f5c2338ca6.sock` | Inline (required; XDG_RUNTIME_DIR not inherited) |
| `ANTHROPIC_API_KEY` | (secret) | `/etc/governor/secrets.env` |

## Secrets

API key lives in `/etc/governor/secrets.env` (mode 600, root:root). Both services load it via `EnvironmentFile=`.

```bash
# Rotate key
echo "ANTHROPIC_API_KEY=sk-ant-..." > /etc/governor/secrets.env
chmod 600 /etc/governor/secrets.env
systemctl restart governor
```

The WebUI Basic-auth credential belongs in equivalent deployment-owned secret
custody. Examples below refer to `GOV_WEBUI_BASIC_AUTH`, whose value has the
usual `username:password` form; never commit its value.

## Log rotation

`/etc/logrotate.d/governor` rotates `gate_receipts.jsonl` weekly (12 weeks retained, compressed).

## Deploying updates

```bash
# From dev machine:
rsync -az --delete --exclude='__pycache__' --exclude='.git' --exclude='*.pyc' \
  ~/git/agent_gov/ root@192.46.223.21:/opt/governor/agent_gov/
rsync -az --delete --exclude='__pycache__' --exclude='.git' --exclude='*.pyc' \
  ~/git/gov-webui/ root@192.46.223.21:/opt/governor/gov-webui/

# On VM:
ssh root@192.46.223.21 "
  /opt/governor/venv/bin/pip install -e /opt/governor/agent_gov -e /opt/governor/gov-webui
  systemctl restart governor
"
```

## Smoke test

```bash
VM=root@192.46.223.21

# 1. Health
ssh $VM "curl -s http://127.0.0.1:8420/health | python3 -m json.tool"

# 2. Chat through daemon (proves split-brain fix)
ssh $VM 'curl -s -X POST http://127.0.0.1:8420/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"claude-sonnet-4-5-20250929\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"stream\":false}" \
  | python3 -m json.tool'

# 3. Receipt emitted (proves daemon governance ran)
ssh $VM "tail -1 /opt/governor/data/.governor/receipts/gate_receipts.jsonl | python3 -m json.tool"

# 4. TCP bridge (Maude tunnel)
ssh $VM '/opt/governor/venv/bin/python3 -c "
import asyncio, json
async def t():
    r, w = await asyncio.open_connection(\"127.0.0.1\", 7777)
    m = {\"jsonrpc\":\"2.0\",\"method\":\"governor.hello\",\"id\":1,\"params\":{}}
    d = json.dumps(m).encode()
    w.write(f\"Content-Length: {len(d)}\r\n\r\n\".encode() + d)
    await w.drain()
    h = {}
    while True:
        l = await r.readline()
        if l.decode().strip() == \"\": break
        if \":\" in l.decode(): k,_,v = l.decode().partition(\":\"); h[k.strip()] = v.strip()
    b = await r.readexactly(int(h[\"Content-Length\"]))
    print(json.dumps(json.loads(b), indent=2))
    w.close()
asyncio.run(t())
"'

# 5. HTTPS via Caddy (set the credential outside the repository)
curl --silent --user "$GOV_WEBUI_BASIC_AUTH" https://sp00ky.net/health | python3 -m json.tool
```

## Known gotchas

- **XDG_RUNTIME_DIR**: systemd services don't inherit it. The daemon needs it inline for socket placement; the webui needs `GOVERNOR_SOCKET` pinned explicitly.
- **API key placement**: Must be on `governor.service` (not just webui) because chat now flows through the daemon.
- **Cascade restart**: Restarting the daemon restarts both webui and bridge (`Requires=`). This is correct behavior — the socket is invalidated on daemon restart.
