# Restricted conversational coordinator boundary

**Status:** experimental optional transport; not organizational approval or a
live deployment claim. **Reviewed:** November 5, 2026.
**Maintaining role:** unassigned. **Provenance:** operator-approved bounded
Unix-RPC design and synthetic offline tests, not Slack conversation history.

Default `interaction_mode:"proposal"` does not call this service. Explicit
`"conversation"` opt-in permits automatic draft/advice replies to authorized
mentions. It does **not** grant terminal, email, agent assignment, task execution,
or automatic publication of Paperclip workers' outputs.

## Restricted external worker, not an independent gateway

The bridge uses only `coordinator.py`, Python's standard-library Unix socket
client. No LLM dependency, direct model HTTP call, credential-file access,
subprocess, fallback provider, or arbitrary executable exists in this adapter.
The actual coordinator/model profile is fixed and managed separately by the
authorized deployment operator, never selected by Slack text or runtime config.
Deployment must qualify that worker's no-tools/no-mail/no-credentials isolation
and approved model identity independently; this code cannot prove it.
The worker must be stateless per connection apart from supplied text/history:
no unrelated Hermes sessions, persistent memories, task context, or other
threads may be loaded into a reply.

Runtime source allowlist: `__init__.py`, `config.py`, `store.py`, `core.py`,
`paperclip.py`, `slack_bridge.py`, and **`coordinator.py`**. The only Python
dependency remains the pinned official Slack SDK. Existing Slack scopes,
subscriptions, Web API endpoints, and disabled SDK retries are unchanged.

The optional `coordinator_socket` is empty in proposal mode. Conversation mode
requires an absolute canonical ASCII filesystem socket path (no empty, `.` or
`..` components, control characters, trailing slash, or more than 107 bytes).
The socket must be root-owned, mode `0660`, with group equal to the service's
effective group. Every parent, including `/`, must be a real root-owned
directory with no group/other write permission; symlinks are refused.
An operator-managed root socket-activation service can expose this boundary
while its actual worker runs as a separate restricted identity and verifies
the bridge's peer identity. A socket path alone is not worker isolation.

`check` calls **stat only**: no socket connection, activation, or model query.
Every query rechecks the socket path. There is one Unix connection and no retry;
the total socket exchange deadline is 120 seconds.

## Exact NDJSON protocol, version 1

Each connection carries exactly one UTF-8 JSON request line:

```json
{"version":1,"text":"A question","history":[{"role":"user","content":"Earlier question"},{"role":"assistant","content":"Earlier advice"}]}
```

Only `version`, `text`, and `history` are sent. No channel, workspace, requester,
bot identity, model, commands, or controller contributor IDs are added. All
literal mentions of this configured bot are removed from query and both
history roles before RPC. Other identifiers deliberately present in human
content remain untrusted user data, not generated identity metadata.

- `version`: integer `1`, not a JSON boolean.
- `text`: 1–4,096 characters and at most 16,384 UTF-8 bytes.
- `history`: at most six alternating `user`/`assistant` messages, complete pairs
  starting with `user`; each object has exactly `role` and `content`.
  Total history is at most 6,000 characters / 24,000 UTF-8 bytes.
- No NUL, invalid UTF-8/surrogates, or partial/truncated decoding is accepted.
- Each wire line is at most **65,536 bytes including its terminating newline**.

The worker returns exactly one of:

```json
{"version":1,"ok":true,"text":"Draft advice"}
```

```json
{"version":1,"ok":false,"error":"generation_failed"}
```

`ok` is a strict boolean. Success has exactly `version`, `ok`, `text`; text is
1–3,000 characters / at most 12,000 UTF-8 bytes. Failure has exactly `version`,
`ok`, `error`; permitted errors are `invalid_request`, `rate_limited`, `timeout`,
`unavailable`, `generation_failed`. Duplicate keys, extra routing fields,
unknown codes, malformed or oversized responses fail closed. No provider
exception or raw error text is relayed to Slack or logs.

Model replies are escaped for `&`, `<`, `>` before posting, with Markdown/name
expansion/parsing/unfurls disabled and a fixed suffix:
“Draft/advice only; no work executed.” Channel, thread, and requester come only
from the validated durable event, never from model text. A model-produced
`task:` string has no effect.

## Durable attempts, history, and privacy

New `chat_turns` rows are stamped `conversation`; legacy `events`/`proposals`
retain their semantics. Envelopes and event IDs deduplicate across both queues,
and accepted chat is committed before Socket Mode acknowledgement.

The single main worker rechecks a complete fresh Slack identity/private-channel
membership gate before generation. It commits `generating` plus an attempt
timestamp **before** RPC and blanks the persisted pending prompt. A crash in
`generating` becomes `uncertain` on restart, never an automatic model replay.
The shared `sending`/`sent`/`uncertain` Slack receipt similarly prevents blind
resends. One chat event permits at most one RPC attempt and one outgoing POST.
Unknown delivery sacrifices the reply rather than claiming exactly-once delivery.

Only a model pair with a confirmed **SENT** receipt is persisted for temporary
history. RPC failures, rejected or ambiguous posts, and held outcomes retain no
raw prompt/reply. Generic rate/error notices are not model history. History
comes only from up to three recent whole SENT pairs in the same bound thread;
oversized pairs are skipped, never partially truncated. There are no Slack
history requests.

If **any** unexpired SENT contributor has departed, all thread history is
withheld to avoid indirectly replaying later replies that quoted them. **All**
unexpired SENT contributors form a controller-only publication fence, including
contributors whose older/oversized pairs are not in the bounded RPC history.
Immediately before a generated POST, a new complete membership gate must still
include the current requester and that entire fence. Otherwise discard the
generated reply and retain no history. Membership checks are snapshots, not
atomic channel locks.

This fence covers the unexpired 24-hour SENT set, not transitive quote ancestry
beyond that window. Retained minimal metadata is not an ancestry index. The
bridge does not detect indirect quotes from expired context, erase prior Slack
posts, or guarantee full retrospective erasure.

Pending chat becomes eligible for erasure after ten minutes. SENT raw pairs
become eligible for secure-delete after 24 hours. Sweeps run at worker/poll
opportunities; no hard deletion deadline applies while blocked or stopped, and
filesystem snapshots/backups/Slack/model-provider retention are separate.
Minimal event/thread/requester IDs, attempt times, states, and delivery receipts
persist for deduplication and rate limits. An operator must approve private
retention and cleanup; do not delete the ledger to bypass holds or limits.

Persistent rolling attempt caps are **10 per requester/hour, 30 globally/hour,
100 globally/24 hours**, with at most 20 pending chat turns and one main worker.
Failed or uncertain dispatched attempts count too. These are call ceilings,
**not a dollar budget** or token-price guarantee. On a cap, timeout, or worker
failure the bridge may send only one fixed generic notice, after a fresh
publication gate; if authorization cannot be established, it stays silent.
No automatic retry, assignment, agent wake, or tools follow an error.
