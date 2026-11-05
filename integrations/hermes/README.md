# Private Hermes operator console

**Status:** optional operator reference, not an installer, access grant, or
inventory of live services. **Reviewed:** November 5, 2026.
**Maintaining role:** unassigned.

## Purpose and boundaries

Use Hermes' native browser dashboard for an authorized operator's direct chat,
sessions, skills, and administration. Keep the roles distinct:

- **Task board:** requested work, assignments, scope, and results.
- **Hermes console:** private direct interaction and runtime administration.
- **Slack:** a separately approved volunteer-facing interface and review route.
- **This library:** reusable public-safe resources, not credentials or live state.

Browser chat is the native Hermes TUI over PTY/WebSocket. It is not a second
task board: an ordinary chat does not automatically become a managed task or
update its status. Workers and native chat can have different session and
credential lifecycles; validate the task-board adapter separately.

This console is **not a sandbox or a volunteer portal**. It can access files,
run commands, change settings, and handle secrets as its Unix user. Same-user
code, including dashboard-spawned TUI processes, is not isolated from dashboard
credentials. Sharing a profile or choosing a different port is not a substitute
for a restricted worker/account boundary.

## Inputs, outputs, and human gates

Inputs are an owner-approved Hermes installation, deliberately selected
profile/model/provider, restricted ingress, and privately provisioned login
credentials. Outputs are private sessions and administrative changes; only
separately reviewed, public-safe work should return to this library.

An operator must approve setup, access grants, significant configuration
changes, and consequential external actions. Do not copy an old assistant's
identity or overwrite fresh configuration to enable a dashboard. Saving this
guide does not connect Slack or email, schedule work, grant terminal access, or
install library skills. Model usage remains subject to provider billing/limits.

## Deployment pattern

Follow the version-appropriate upstream documentation rather than treating this
reference as a script:

1. Build the production web frontend **and** the embedded TUI using the native
   locked build workflow. Do not run a development server as the operator UI.
2. Bind the backend to loopback, normally port `9119`. Use an authenticated,
   operator-only HTTPS ingress; do not expose the backend port directly.
3. Declare the browser-facing HTTPS origin with `dashboard.public_url` or the
   documented `HERMES_DASHBOARD_PUBLIC_URL` override. A non-loopback public URL
   engages native authentication even when the backend binds to loopback.
4. Configure native authentication. For a genuinely private/authenticated
   ingress, the native password provider can use a generated strong password,
   scrypt hash, and stable random signing key. An unrestricted public Internet
   deployment requires a suitable OAuth/OIDC design instead. Do not use
   `--insecure` as an authentication bypass.
5. Keep auth material in an owner-only secret store or separate private
   environment file, outside Git and task prompts. Native keys are
   `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`,
   `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH`, and
   `HERMES_DASHBOARD_BASIC_AUTH_SECRET`. Generate hashes with the installed
   native helper, without putting a password into shell history or arguments.
   Do not accidentally enable the separate deployment session-token provider.
6. On Linux, supervise the foreground native command with an enabled user
   systemd service. Select the intended home/profile and working directory
   explicitly, apply a private umask, and disable browser auto-opening.
   `--skip-build` is appropriate only after the production assets are built.
   Active `Type=simple` service state is not proof of application readiness.

Keep model/provider settings, existing task-runner credentials, unrelated
services, and assistant instructions unchanged unless separately authorized.
Review effective settings after all service and dotenv overrides, not just the
unit template. Store actual URLs, paths, login instructions, and deployment
automation in the restricted operational record, not this public repository.

With exe.dev, documented alternate ports are accessible only to users with VM
access. Keep VM access restricted; do not grant it merely to let volunteers
interact with a bot. Other hosting environments need their own verified ingress
boundary.

## Acceptance checklist

Perform these in the authorized deployment, using synthetic prompts:

- Verify the expected loopback listener and both private ingress and native
  authentication. Open the actual external URL in the operator's authenticated
  browser; local proxy-header simulation alone is not that final browser hop.
- Check public auth metadata reports `auth_required: true` and only intended
  providers. Health/auth-discovery routes may intentionally be public; protected
  pages should redirect to sign-in and protected APIs reject missing credentials.
- Check wrong passwords/tokens fail, and correct login yields HTTPS
  Secure/HttpOnly/SameSite cookies.
- Check both API and PTY WebSockets reject unauthenticated access, accept valid
  credentials, reject replayed one-use tickets, and reject foreign hostnames.
- Exercise the real chat interface with one harmless prompt. Verify a new
  **assistant** response and expected model, not merely the echoed user input.
  Do not auto-confirm unknown onboarding, approval, or secret dialogs.
- Restart the service, verify readiness and expected session continuity, then
  recheck that task-board operation and protected configuration are unchanged.

Native session cookies are hostname-wide, not port-isolated. Treat services
sharing a hostname as a shared trust context. Basic-auth sessions are stateless:
logout clears browser cookies but does not revoke copied tokens. Rotate the
password/hash **and signing key** after compromise; reducing access-token TTL
alone does not shorten the native refresh-session lifetime.

There are no runnable Hermes acceptance tests or private deployment records in
this library. The Luma offline suite does not validate this console, a live
mailbox, Slack, or an individual operator's ingress.

## Primary references and freshness

Technical behavior was reviewed against Hermes source commit
`74b2ed65e6564bfcafd29236e5fab2447a68fc76`, not assumed to apply to every
past/future release. Recheck after upgrades:

- [Native dashboard documentation](https://github.com/NousResearch/hermes-agent/blob/74b2ed65e6564bfcafd29236e5fab2447a68fc76/website/docs/user-guide/features/web-dashboard.md)
- [Native password provider](https://github.com/NousResearch/hermes-agent/blob/74b2ed65e6564bfcafd29236e5fab2447a68fc76/plugins/dashboard_auth/basic/__init__.py)
- [Native chat/WebSocket boundary](https://github.com/NousResearch/hermes-agent/blob/74b2ed65e6564bfcafd29236e5fab2447a68fc76/hermes_cli/web_server_chat.py)
- [exe.dev proxy and alternate-port documentation](https://exe.dev/docs/proxy.md)
- [Support-tool orchestration](../../tools/orchestration.md)
- [Slack integration plan](../slack/README.md)
- [Publication boundary](../../docs/PUBLICATION.md)
