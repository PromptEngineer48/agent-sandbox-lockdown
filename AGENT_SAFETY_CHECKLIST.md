# Agent Safety Checklist — Prompt Engineer 48

Every item below is implemented in `demo/` and was tested on camera.

## Network
- [ ] **No network by default** — `docker run --network none` for anything that only needs local files.
- [ ] **Internal network** for the agent (`internal: true`) — no route to the internet.
- [ ] **DNS allowlist** (CoreDNS) — allowed names forward, everything else gets `NXDOMAIN` and is never forwarded. This is the fix OpenAI adopted after the Sep 20 2026 DNS escape.
- [ ] **Egress proxy allowlist** (tinyproxy, `FilterDefaultDeny Yes`) — same domain list.

## Container
- [ ] Read-only root filesystem (`read_only: true`, `tmpfs: /tmp`)
- [ ] `cap_drop: [ALL]` and `no-new-privileges:true`
- [ ] Non-root user, memory + PID limits
- [ ] Workspace mounted **read-only**; one separate writable `outbox/`

## Tools
- [ ] Read tools run freely; **write tools need a human "y"**
- [ ] Paths are resolved and checked against the allowed base dir
- [ ] Unknown tool names are refused

## Oversight
- [ ] **Log every tool call** (JSONL: step, tool, args, status, result)
- [ ] **Step cap** (`MAX_STEPS`) — stops retry loops
- [ ] **Kill switch** checked before every step — and *tested*. OpenAI's run was flagged in ~12 min but only killed ~2.5 h later.
- [ ] Attack it yourself with a real prompt injection before trusting it

## Skills & plugins
- [ ] Read a skill before installing it
- [ ] Search it for unreserved placeholder domains (`yoursite.com`, `your-domain.com`) — anyone can register those. In your own docs use `example.com` / `.example` (IANA-reserved).
