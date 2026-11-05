# Approval-first Slack → Paperclip intake

**Status:** experimental reusable coordination-layer code, not organizational
approval or a deployment. **Maintaining role:** unassigned.
**Reviewed:** November 5, 2026. **Inputs:** restricted Slack mentions.
**Outputs:** private unassigned backlog proposals and fixed threaded notices.
Only synthetic offline checks accompany this code; they prove no live Slack
installation, membership, transport, or Paperclip permission behavior.

This is **not** a Hermes gateway, autonomous assistant, or worker. There is no
LLM, shell, subprocess, email, link-fetching, issue-comment, assignment, or
agent-execution interface. A human reviews, moves, and assigns a proposal in
Paperclip separately. Publishing this code grants none of those permissions.

## Fixed pilot boundary

- One expected workspace, Slack app, authenticated bot user/bot ID, and one
  private, nonshared pilot channel; explicit human ID allowlist.
- Subscribe **only** to `app_mention`, not messages, DMs, history, files, search,
  or automatic thread follow-ups. Require an explicit literal bot mention on
  every accepted event. Reject the bot's own, bot-authored, and subtyped events.
- Each event's workspace, app ID, and bot authorization must match the private
  configuration. `auth.test` binds the Web API token to the configured workspace,
  bot user, and bot ID. Operators must verify that these IDs describe the same
  installed app, not merely copy IDs from an untrusted request.
- Before every proposal creation or Slack publication, recheck identity,
  channel privacy/archive/membership/sharing flags, and **all** membership pages.
  Members must be a subset of allowlisted humans plus this bot; the requester
  and bot must be present. Missing fields, unknown members, rate limits, and
  API errors refuse the action. `groups:read` exists only for these checks.
- An incoming mention is untrusted data, bounded to 4,096 Unicode characters /
  16,384 UTF-8 bytes. It is placed inside a labeled untrusted description, never
  executed or fetched. Request links and attachments are not retrieved.
- At most one proposal per thread. Subsequent explicit mentions may receive
  only a fixed reference to the existing proposal; their text is discarded.
  They never append comments or new instructions to an assigned task.
- Slack receives only a fixed acknowledgement/link or one fixed notification
  per status (`in_review`, `done`, `blocked`, `cancelled`). Never post worker
  comments, drafts, descriptions, or other enriched issue content. Disable
  Markdown interpretation and link/media unfurls on every send.
- Poll at most ten active proposals per interval with durable fair rotation.
  Each batch gets one fresh complete membership snapshot and checks each
  requester's presence; every actual publication still gets its own fresh full
  gate. Spent receipts trigger no extra send gate. A `done`/`cancelled` delivery
  attempt, including an uncertain or rate-limited attempt, durably stops polling
  that proposal; its thread ledger remains available for fixed references.

### Paperclip field and automation boundary

`paperclip.py` is the sole explicit API/field adapter. It creates through
`POST /companies/{company_id}/issues`, with a fixed title, bounded description,
`status:"backlog"`, `visibility:"private"`, and explicit null
`assigneeAgentId`, `assigneeUserId`, `projectId`, `parentId`, `executionPolicy`,
and `watchdog`. `allowDuplicate:true` prevents unrelated equal titles from
being merged; a stable company/channel/thread-derived body `idempotencyKey`
supplements the bridge's permanent ledger. The installed API's native
idempotency retention is only seven days; it does **not** authorize replay of
an uncertain request.

The adapter requires the creation response to confirm private backlog and
both assignees null. Private issues may automatically acquire the responsible
local user's personal private project, even though the submitted project is
null. The bridge intentionally omits `responsibleUserId`, allowing the
local-trust board's current-owner default; verify that owner during deployment.
Private issue links may not be accessible to every Slack participant.

Before creation, conservatively require `GET /plugins` and
`GET /companies/{company_id}/routines` to return empty arrays, and every agent
from `GET /companies/{company_id}/agents` to have a well-formed explicit
disabled heartbeat (`enabled:false` or finite `intervalSec<=0`). Missing or
malformed runtime configuration blocks creation. This is a **current-state
drift guard, not an atomic or universal no-execution guarantee**: issue creation
emits activity/plugin events; independent automation can race the checks.
Stop the bridge before enabling/changing routines, plugins, scheduled agents,
or other consumers of issue events. Review new integrations separately.

The adapter was aligned with the installed Paperclip 2026.1023 API contract
reviewed November 5, 2026. It uses unauthenticated **loopback local-trust
board-admin** access only, with no proxy use or redirects; it is not an
agent-token-compatible or remote-authentication implementation. Status reads
use `GET /issues/{id}` and extract only status after verifying issue/company.
These GETs may trigger Paperclip recovery/audit behavior; “check” means no
deliberate issue creation or Slack publication, not that server-side GETs are
guaranteed pure.

## Private operator setup

1. Obtain workspace, channel, integration, retention, and responsible-operator
   approval. Tell pilot participants what is retained, who can review it, and
   how to disable the bridge. Confirm the receiving private Paperclip owner,
   visibility, and absence of independent execution triggers.
2. Review `manifest.json`. Bot scopes are exactly `app_mentions:read`,
   `chat:write`, `groups:read`; bot event exactly `app_mention`. Separately
   create an **app-level** token with `connections:write` (not a bot scope).
   Install/reinstall with authorized approval and add the app to the private
   pilot channel. Do not add `chat:write.public`, history, DM, file, or search
   scopes/subscriptions.
3. Use a separately restricted service account and operator-reviewed isolation.
   Keep code read-only to that account and give it neither worker tools nor
   unrelated credentials. Merely running another process under an unrestricted
   worker account is not an isolation boundary. Deployment/service automation
   is intentionally outside this public component.
4. Install the official SDK in an isolated operator-managed Python environment:

   ```sh
   python3 -m pip install --require-hashes --only-binary=:all: -r requirements.txt
   ```

   Only `slack-sdk==3.46.0` is required; no Bolt or optional SDK extras. This
   implementation uses the SDK's built-in `SocketModeClient` and `WebClient`;
   all application HTTP calls disable SDK retries. Python 3.10+ and Linux are
   required by this implementation (the SDK's minimum is not the bridge's).
5. Make a **private copy** of `config.example.json` outside the repository.
   Every example ID/UUID, hostname, and uppercase path placeholder is synthetic.
   Supply all fields; unknown fields are rejected. Set `integration_approved`
   to literal `true` only after approval. The example deliberately refuses run.
   The config must be a regular single-link file: service-euid-owned `0600`,
   or root-owned `0640` with the nonroot service's effective group as its group.
   DB/lock files must be service-euid-owned regular single-link files, `0600`.
   Symlinks are refused. The DB parent must be service-owned mode `0700`.
6. Supply **only** `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` through a protected
   runtime environment. Never put tokens in JSON, command arguments, examples,
   public logs, or Git. There is no Paperclip token in this local-trust adapter.
   `paperclip_api_url` must be an HTTP literal loopback origin ending `/api`.
   `paperclip_public_url` is an approved HTTPS origin (or literal loopback HTTP),
   without a path; issue links are `/{company_prefix}/issues/{identifier}`.
   `state_path` is an absolute path in the private state directory.
   `poll_interval_seconds` must be an integer from 30 to 3,600.
7. Using the trusted environment's Python, run:

   ```sh
   python -I /TRUSTED-SOURCE/bridge/slack_bridge.py check --config /PRIVATE-CONFIG.json
   python -I /TRUSTED-SOURCE/bridge/slack_bridge.py run --config /PRIVATE-CONFIG.json
   ```

   The entry point works with `-I` and does not depend on the current directory.
   `check` validates config and makes live preflight API reads; it does **not**
   open/create a SQLite DB or lock, connect Socket Mode, create a proposal,
   or publish Slack messages. All allowlisted humans must be current members
   for initial preflight. Run only after the operator authorizes live access.
   `run` rechecks, takes a single-process lock, recovers durable state, and
   connects Socket Mode. Stop the service to disable it; revoke tokens if
   necessary. Logs contain only fixed diagnostic codes, not exception bodies.

## Durable state, failures, and retention

The Socket Mode callback commits the syntactically accepted event before
acknowledging its envelope. An asynchronous main-loop worker performs all
external checks and requests. SQLite deduplicates envelope IDs, event IDs,
threads, and status-notification receipts. The private ledger is bound to the
workspace/app/bot/channel/company/URLs/allowlist; reusing it with a changed
binding fails closed. Do not discard the ledger to bypass that protection.

Creation states: `pending → creating → created | uncertain | rate_limited`;
gate/expiry failures become `rejected`. Delivery states:
`sending → sent | uncertain | rate_limited`.
Before each POST, durably save `creating` or `sending`. A crash while in that
state becomes `uncertain` on restart, with **no automatic re-creation/resend**.
Timeouts and malformed or unconfirmed responses are likewise uncertain.
Only a definite HTTP 429 records a bounded retry-after delay; it is terminal
too, not automatically retried. This sacrifices delivery rather than claiming
exactly-once network behavior. Native idempotency does not change that rule.

Pending text becomes eligible for expiry after one hour. Cheap sweeps erase
eligible text before worker steps and status batches, and between batch items;
expiry does not wait for each event to reach the head of the queue. This is
running-process cleanup, **not a hard wall-clock deletion SLA** while the process
is blocked or stopped. Text is also erased on rejection or just before creation
transport; uncertain records retain no request text. SQLite uses
secure-delete, DELETE journals, and full synchronous commits, but cannot erase
filesystem snapshots, backups, API-side retention, Slack, or memory. Pending
events are capped at 100; receipts/IDs/status metadata persist for deduplication
and need operator-reviewed private retention/storage management. A disabled
service cannot run the pending-text expiry job: keep the service down only
with an operator-reviewed retention cleanup plan.

There is deliberately no reconciliation/reset command. If uncertain or
rate-limited, stop and inspect private state and the receiving systems as an
authorized operator; establish the real outcome manually. Do **not** reset a
receipt to pending, delete the DB, or replay an old POST blindly. Preserve the
ledger and plan any migration offline. Backups must remain private and account
for pending text and consistent DB/lock handling.

## Offline validation

From the repository root:

```sh
bash -n integrations/slack/bridge/tests/run-offline.sh
bash integrations/slack/bridge/tests/run-offline.sh
```

Requires Linux `unshare` with unprivileged user/network namespaces and Python
3.10+. The runner refuses fallback to the host network, starts with an empty
environment, uses a temporary home, and blocks socket/DNS connections as a
second layer. All Slack/Paperclip data and transports are mocks; no SDK install,
real home writes, credentials, private fixtures, or live service tests.
Coverage includes identity/privacy gates, complete two-page membership,
durable-before-ack, replay/thread dedupe, text erasure, crash/ambiguous POST
holds, rate limits, exact proposal fields, automation drift, fixed-only status
posts, bounded polling/terminal retirement, FIFO-independent expiry, private DB
binding, and preflight without state writes.

These checks do not establish OS/service isolation, filesystem crash durability
under power loss, Slack reconnect behavior, live installed scopes/API contracts,
or private frontend permissions. Review these independently before deployment.

## Public primary setup references

- [Official Python Socket Mode SDK](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/)
- [Socket Mode envelope acknowledgements](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [Mention event](https://docs.slack.dev/reference/events/app_mention/)
- [Channel information](https://docs.slack.dev/reference/methods/conversations.info/)
- [Paginated membership](https://docs.slack.dev/reference/methods/conversations.members/)
- [Token identity](https://docs.slack.dev/reference/methods/auth.test/)
- [Threaded publication](https://docs.slack.dev/reference/methods/chat.postMessage/)
- [Official SDK package](https://pypi.org/project/slack-sdk/3.46.0/)

Slack documentation was reviewed November 5, 2026; references are setup
contracts, not a claim of workspace installation or authorized adoption.
