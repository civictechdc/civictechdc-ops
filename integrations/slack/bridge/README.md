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
  private, nonshared pilot channel; an explicitly approved access policy below.
- Subscribe **only** to `app_mention`, not messages, DMs, history, files, search,
  or automatic thread follow-ups. Require an explicit literal bot mention on
  every accepted event. Reject the bot's own events and events marked as
  bot-authored or subtyped.
- Each event's workspace, app ID, and bot authorization must match the private
  configuration. `auth.test` binds the Web API token to the configured workspace,
  bot user, and bot ID. Operators must verify that these IDs describe the same
  installed app, not merely copy IDs from an untrusted request.
- Before every proposal creation or Slack publication, recheck identity,
  channel privacy/archive/membership/sharing flags, and **all** membership pages.
  The requester and bot must be present. In default allowlist mode, all members
  must be allowlisted humans plus this bot. In opt-in channel-members mode,
  current membership defines the approved audience. Missing/invalid data,
  incomplete pagination, rate limits, and API errors refuse the action.
  `groups:read` exists only for these checks.
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

### Access policy: allowlist or current channel members

`access_mode` is optional and defaults to `"allowlist"` for old JSON and code
callers. `allowed_user_ids` remains required in both modes:

| Mode | Required `allowed_user_ids` | Audience and request eligibility |
| --- | --- | --- |
| `"allowlist"` (default) | 1–50 distinct approved human IDs, excluding this bot | Every channel member must be on that list or be this bot; a requester must be listed and currently present. New/unexpected members fail closed. |
| `"channel_members"` (explicit opt-in) | Exactly `[]` | All current channel members form the approved audience. Valid-ID requesters must be present in a fresh complete membership snapshot; new members become eligible automatically and departed members are denied. |

Keep the conservative policy in `config.example.json`, or, **after explicit
approval of membership-as-access including future joins**, replace only these
two fields in the private copy:

```json
{
  "access_mode": "channel_members",
  "allowed_user_ids": []
}
```

This fragment is not a complete config. Unknown modes, missing IDs lists, and
nonempty lists in channel-members mode are rejected rather than silently
ignored. Dynamic access does not copy the live roster into configuration or
broaden access beyond the one approved private/nonshared/nonarchived channel.
People authorized to invite members now also control future bridge access and
the audience for fixed Slack notices; review that authority and explain it to
participants. Neither policy makes private Paperclip links accessible to
everyone automatically.

The callback cannot make network calls: channel-members mode durably queues
syntactically valid target-channel mentions, then rejects nonmembers before
proposal creation/publication. Fresh membership is checked again before every
actual Slack post, including a departure after creation. Status reads/posts
are skipped while the original requester is no longer a member. Snapshots are
not atomic membership locks; the existing race limitations still apply.

Membership can include other Slack apps. Channel-members mode accepts their
valid member IDs as part of the channel audience, **not** as permission to
submit bot-authored requests. Own/bot-marked/subtyped events remain rejected.
No `users.info` classification is performed or claimed; no `users:read`,
history, search, extra endpoint, or dependency is added.

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

   An existing private coordination channel is supported; a new two-person
   channel is only an optional small pilot. Approve the access policy, not just
   the setup operator. Default allowlist mode requires approval of every human
   member's ID and rejects unexpected members/apps. Channel-members mode
   instead requires explicit approval that current **and future** members
   define access. Do not switch policies merely to suppress a validation error.

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
   Supply the required fields; `access_mode` alone is optional and defaults to
   `"allowlist"`. Unknown fields are rejected. Set `integration_approved`
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
   or publish Slack messages. Initial preflight always checks one complete
   channel snapshot, including in channel-members mode with its empty IDs list;
   all allowlisted humans must also be present in allowlist mode. Run only
   after the operator authorizes live access.
   `run` rechecks, takes a single-process lock, recovers durable state, and
   connects Socket Mode. Stop the service to disable it; revoke tokens if
   necessary. Logs contain only fixed diagnostic codes, not exception bodies.

### Safe preflight diagnostics

On a failed `check`, stderr is exactly one line:
`preflight_failed:CODE` (plus its terminating newline), with a nonzero exit.
No IDs, provider error text, response bodies, payloads, tokens, or exception
representations are printed. Only the fixed codes below are supported; unknown
or malformed errors use a fixed stage fallback. `run` retains only its generic
`bridge_failed_closed` failure message, not these setup diagnostics.

These are evidence about the failed check, **not a diagnosis of an unobserved
workspace**. The check still makes only the previously authorized preflight
reads, without saving credentials, writing bridge state, activating Socket Mode,
creating an issue, or posting. It does not qualify the app-level connection
token or a live mention roundtrip.

| Code | Authorized operator's next check |
| --- | --- |
| `config_invalid` | Review the exact private schema, explicit approval, file ownership/modes, and existing private state-directory requirements. |
| `credentials_missing` | Supply the required bot/app tokens through the protected environment; verify their expected token-type prefixes without printing them. |
| `dependency_unavailable` | Verify the pinned SDK is installed in the Python environment used by this command. |
| `slack_auth_failed` | The authentication step failed; check authorized API connectivity and that the bot token is valid, unrevoked, and approved for the intended installation. |
| `slack_identity_mismatch` | Reconcile the approved workspace and bot user/bot IDs through trusted operator records; do not adopt IDs from untrusted input. |
| `slack_channel_unavailable` | Verify the approved private channel ID and the app's access to it. |
| `slack_missing_scope` | Verify the intended **private** pilot and the exact three bot scopes in the manifest; reinstall/reauthorize after approved scope changes. See the public-channel caveat below. |
| `slack_channel_not_private` | Select the approved private pilot; public channels are not supported. |
| `slack_channel_not_member` | Have an authorized human add the correct installed bot to the approved channel. |
| `slack_channel_not_safe` | The channel is archived or shared; use an approved nonarchived, nonshared private pilot. |
| `slack_channel_metadata_invalid` | Required privacy/safety metadata was missing or malformed; review API compatibility without bypassing the gate. |
| `slack_member_not_allowed` | In allowlist mode, review the complete audience against approved humans plus bot; do not automatically approve an unexpected member. Access-policy changes require separate approval. |
| `slack_requester_not_member` | Verify the requester is currently in the pilot channel; allowlist preflight checks every configured requester. |
| `slack_membership_unavailable` | Membership lookup failed or could not complete; review authorized API availability/access before trying again. |
| `slack_membership_invalid` | Membership or pagination data was incomplete/malformed; never accept a partial list. |
| `slack_rate_limited` | Stop repeated checks and retry later under operator control; do not weaken checks or blindly retry writes. |
| `paperclip_preflight_failed` | Review the existing local Paperclip connectivity and automation-safety requirements. This code reveals no task data. |
| `validation_failed` | An unexpected validation failure occurred; review this implementation/environment without enabling raw SDK logging. |

With only `groups:read`, asking Slack about a **public** channel can produce a
missing-scope error for `channels:read` before privacy metadata is available.
That is not a request to add `channels:read`, history scopes, or broader
subscriptions: choose the intended private pilot instead, then verify the
existing manifest scopes and reinstall after any approved changes. The bridge
neither reports the provider's requested scope string nor broadens permissions.

## Durable state, failures, and retention

The Socket Mode callback commits the syntactically accepted event before
acknowledging its envelope. An asynchronous main-loop worker performs all
external checks and requests. SQLite deduplicates envelope IDs, event IDs,
threads, and status-notification receipts. The private ledger is bound to the
workspace/app/bot/channel/company/URLs/access policy; reusing it with a changed
binding fails closed. Default/explicit allowlist preserves the legacy binding
digest. Channel-members mode adds an explicit policy marker, not a live roster;
ordinary joins/leaves do not change that binding. Changing policies requires
stopping and reviewing existing state offline, never silently rebinding or
discarding the ledger to bypass that protection.

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
binding, both access policies and joins/departures, backward-compatible default
binding, and preflight without state writes even with an empty dynamic IDs list.

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
