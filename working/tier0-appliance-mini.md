# Tier-0 Appliance: Ollama on the Mac mini M4

Stood up 2026-06-10 (Slice 3 of the model-tier delegation plan). The always-on
cheap-cognition box for the downgradeability ratchet
(`working/campaign-tick-tock-builder-ratchet.md`, memory `feedback_model_tier_routing`).

## What it is FOR

Drafts, triage, classification, summaries, mechanical local-tier slices — the LOCAL
rung of `docs/reference/task-packet-template.md`'s sizing rubric. Cheap, idle-cheap,
LAN-local cognition that doesn't bill frontier rates.

## What it is NOT for

Supervised builds (those run through the governor runtime + a real coding backend),
theorem-goblin work, or anything needing frontier judgment. Not a replacement for
Fable/Opus — it's the bottom of the ladder.

## Current state (verified)

- **Host:** Mac mini M4 16GB, macOS 15.7.3 arm64, `192.168.69.15`
  (memory `infra_ssh_access_map`). Always on.
- **Install:** Ollama v0.30.7 standalone CLI distribution (`ollama-darwin.tgz`),
  user-local at `/Users/claude/ollama-dist/` — **no root, no homebrew** (the homebrew
  prefix `/opt/homebrew` is not writable by `claude`). Includes MLX Metal accel libs.
- **Serving:** `0.0.0.0:11435`, LAN-reachable. Verified from this host:
  `curl http://192.168.69.15:11435/api/version` → `{"version":"0.30.7"}`.
- **Model:** `qwen2.5:3b` (1.9 GB) — small generalist/coder for the smoke + first
  LOCAL-tier chores. Room for one ~12B Q4 later if a tick demands it; 16 GB unified,
  so don't get drunk on context windows.
- **Port choice:** James already runs his own homebrew ollama as user `jbeck` on
  `127.0.0.1:11434` (localhost-only, not LAN-reachable). The claude-user appliance runs
  on **11435** to avoid colliding with it. Two idle `serve` processes cost ~30 MB each;
  models load on demand. See "Consolidation question" below.

## AG-side wiring (egress verified, NOT yet made default)

The governor egress gate already classifies the RFC-1918 LAN host as **internal** —
no allowlist entry needed, and **no `strict=False` bypass** (which would reopen the
hole the LLM-egress gap closed):

```
http://192.168.69.15:11435/api/chat -> verdict=PASS  destination_class=internal  rule=R4_INTERNAL_ALLOW
```

Smoke round-trip through `create_backend("ollama", host="http://192.168.69.15:11435")`
against `qwen2.5:3b` → reply `PONG`, **1319 ms cold / 256 ms warm**. With a
`GateReceiptSystem` attached, the egress preflight persisted a receipt:

```
receipt_id = 3c6b1d029d0437e52c2e83937f4e6bac145d5676a7671e007d0e12b1f49e6590
gate = egress_policy   verdict = pass   schema_version = 4
store = .tick/tier0-gov/receipts/gate_receipts.jsonl
```

**To point AG at the appliance** (deliberate operator choice — not flipped globally by
this slice): set `OLLAMA_HOST=http://192.168.69.15:11435` for ad-hoc use, or
`backend.ollama.url = http://192.168.69.15:11435` in the governor `daemon.conf`
`[backend]` section. The default ollama gate already passes the host as internal, so no
egress config change is required.

## Known caveats / handoffs

- **Persistence is partial.** `launchctl bootstrap gui/$UID` fails over SSH ("Domain
  does not support specified action" — the gui domain wants an active GUI session), so
  the appliance was started with `nohup … & disown`. The LaunchAgent plist
  (`~/Library/LaunchAgents/com.claude.ollama.plist`, `RunAtLoad`+`KeepAlive`, port
  11435) is in place and **will auto-load on the mini's next GUI login / reboot**. If
  it needs to be loaded *now* under launchd management, James can run from a GUI
  session: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.claude.ollama.plist`.
- **Consolidation question (for James, not a blocker):** the mini now has two ollama
  instances — James's homebrew one (localhost:11434) and the claude appliance
  (LAN:11435). The tidier long-term state is one LAN-exposed instance. Options: (a)
  keep both (cheap, isolated, zero James effort); (b) retire the claude one and flip
  James's homebrew instance to `OLLAMA_HOST=0.0.0.0:11434` (his territory, needs his
  hand). Left as (a) for now since it touches none of James's critical infra.

## Deferred siblings (named, not built)

- **crow** (5060 16GB GPU box, root access): the real local-inference horsepower, but
  usually OFF and its IP is forgotten (`infra_ssh_access_map`). Revisit when a tick
  needs GPU-class local throughput.
- **No DiffusionGemma** here — Google's own guidance says Apple-Silicon unified memory
  is memory-bandwidth-bound and may not see the speedup; wrong fit for 16 GB unified.
- **No ladder wiring.** `routing.py`/`lanes.py` stay library-only until accumulated
  tick suitability evidence licenses it. First downgrade experiment (a tick executed by
  a cheaper model from a template-grade packet) is the next tick candidate.
