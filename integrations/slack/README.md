# Slack integration

**Status:** experimental proposal bridge with opt-in conversational routing.
A separately qualified restricted worker is required for conversation; email
alerts remain proposed. Live installations require their own acceptance checks.
**Reviewed:** November 10, 2026. **Maintaining role:** unassigned.
**Provenance:** official Slack documentation, the published Paperclip
2026.1023.0 API contract, and the Hermes source snapshot linked below.
This public library is not a deployment inventory or workspace approval.

## Available pilot

The [Socket Mode bridge](bridge/README.md) and
[app manifest](bridge/manifest.json) retain proposal-only mode by default:

1. An explicit mention from an allowed person in one approved private channel
   becomes a **private, unassigned backlog proposal** in Paperclip.
2. Slack receives a task link. An organizer reviews the request in Paperclip
   before intentionally assigning it and moving it into work.
3. The bridge can post fixed status notices back to the originating thread.
   It never relays worker comments, drafts, descriptions, or arbitrary output.

Optional `interaction_mode: "conversation"` instead routes normal mentions to
a separately deployed, restricted coordinator over authenticated local Unix
IPC. It replies in the originating thread without making a Paperclip issue.
An explicit human `@bot task: ...` still queues a private, unassigned proposal.
Neither model output nor an ordinary follow-up can assign an agent or silently
modify an assigned task.

The bridge has no in-process model or execution tools. It does not read Slack
history, follow links, fetch files, send DMs, or access email. See the
[coordinator contract](bridge/COORDINATOR.md) for the required no-tools,
stateless worker, bounded protocol, and deployment qualification.
Offline tests use synthetic data and a network-isolated runner; a real app
installation, audience check, and mention/status roundtrip are still required.

### Conversational pilot

Enabling conversation is a separate approval, not a consequence of channel
membership or having installed the app. Disclose the selected model/provider,
processing of explicitly mentioned text, limited retained context, usage
limits, and how to disable the bot before enabling it.

- Every turn requires an explicit mention, including follow-ups in a thread.
- Each request receives at most three recent, successfully sent user/assistant
  pairs from that same thread. Successful pairs are retained locally for a
  24-hour window and removed by the next expiry sweep; this is not a three-pair
  storage cap or a deletion guarantee for Slack, providers or backups. No Slack
  history is read.
- A fresh complete membership check precedes generation and publication.
  Departed contributors invalidate retained context; contributors used for a
  generated reply must still be present at publication.
- Durable limits are 10 model turns per person/hour, 30 total/hour, and 100/day,
  with one controller invocation at a time. These are not a dollar budget or
  a guarantee about an arbitrary worker's internal provider retries.
- The worker receives only text and bounded history—not Slack tokens, routing
  IDs, runtime configuration, or permission to execute tools. Its no-tools,
  no-memory/no-profile behavior must be qualified independently.
- Generated content is escaped before posting as plain text with a draft/advice
  label. It is not an approval, a commitment, or evidence an outside action ran.

The public bridge provides routing and an RPC client, not a Hermes installer
or a complete worker deployment. A separate account/process alone is not proof
of confinement; verify the actual native runtime and OS protections.

### Access policy

The bridge defaults to an explicit user allowlist. An operator can instead
approve `access_mode: "channel_members"` with `allowed_user_ids: []`: all
current and future members of the one selected private channel become eligible
for its explicitly configured interaction mode. Slack membership controls access; people
managing invitations/removals manage this grant. A manual member list is not
maintained or silently expanded.

Both policies require fresh, complete membership checks before model use, task
creation and each publication, reject bot-marked requests, and retain the private,
nonshared-channel boundary. Channel-members access grants no mailbox,
dashboard, assignment, worker-execution or general publishing permissions.
Other apps already in the channel may see notices under their existing Slack
permissions. A separate email-review audience still needs its own approval.

### Ownership and routing

Keep Slack transport and authorization at the shared coordination layer:

| Level | Responsibility |
| --- | --- |
| Organization/coordinator | App ownership, protected credentials, authorization, delivery, and receipts. |
| Channel/project | Approved audience and routing; not workspace-wide access. |
| Task/thread | One tracked request and its review/status links. |
| Restricted coordinator | Automatic advice/drafts in its originating thread; no tools or Slack token. |
| Engineer/other powerful worker | Bounded work after organizer review; no Slack app token in its environment. |

Paperclip remains the task record. The bridge's private database holds transport
receipts, pending intake, and limited short-lived conversation context—not a
second task-management system or an institutional-memory archive.
Reusable source and instructions belong here; live credentials, IDs, message
content, and deployment automation do not.

Paperclip also has native Slack chat connectors. Its published 2026.1023.0
release labels chat connectors experimental, and the documented setup uses
webhook delivery and account linking. Qualify those permissions, identities,
and hosting requirements before choosing that path. Do not make a trusted-local
dashboard public just to receive Slack callbacks, or enable an independent
Hermes gateway alongside the same bot.

Private backlog is not a universal platform-wide execution lock. The bridge
conservatively checks for routines, plugins, and scheduled agent heartbeats;
independent automation could otherwise consume new-task activity. Stop and
requalify it before changing those assumptions. A separate process/account
also does not protect secrets from a VM owner or a privileged worker.

## What we want

Use Slack as a convenient support/intake surface, this repository as the shared
support library, and Paperclip as a task/review record. A restricted worker can
prepare requested outputs after the appropriate human review.

Examples for restricted conversational support:

- Find the project-brief template or explain a documented workflow.
- Prepare draft event copy from confirmed inputs.
- Propose a small project task for a maintainer to review.
- Separately proposed: an explicitly configured email-needs-reply alert, with
  a draft ready for an authorized reviewer.

Do not require volunteers to use a new task system merely to participate.
Deployment-specific Paperclip links may require separate access; do not assume
every Slack participant can open them.

## Support workflow and remaining boundaries

1. Choose one approved channel and an explicitly approved access policy.
2. For interactive chat, reply only to explicit mentions in the initiating
   thread. Require a new mention for a follow-up; do not silently monitor
   ordinary conversation.
3. Initially retrieve only the public support library and other explicitly
   approved public sources for chat. A separately authorized mailbox workflow
   may access only its agreed email scope. Do not import historical Slack
   messages.
4. Return answers, drafts, and task proposals—not terminal execution, automatic
   assignments, announcements, DMs, event creation, merges, or deployments.
5. Proactive email alerts require their own explicit mailbox and restricted
   review-channel approval. They do not grant general unsolicited posting or
   workspace monitoring.
6. Agree on a short data-handling notice, limited retention, rate/usage limits,
   a responsible operator, and a way to disable the bot.

The Slack-facing process must not inherit unrestricted worker tools,
credentials, files, or administrative access. Treat message text, links, and
attachments as untrusted input. Use a reviewed isolation boundary; a separate
process or profile on the same account alone is not a security boundary.

Proposal intake and optional bounded conversational routing are implemented.
The generator is a separately qualified deployment dependency. Public-project
channels, tool-enabled execution from Slack, general arbitrary publication,
and mailbox integration remain outside this pilot.

## Proactive email alerts

The requested [email reply workflow](../../workflows/email-reply-alerts.md)
adds a separate trigger: a relevant email, not a Slack mention. After explicit
setup approval, the bot would post a review notice and proposed reply to the
designated restricted channel.

The proposed workflow supports **notify/draft with manual sending**, or a
separately enabled **explicit approval-and-send** connector. The latter accepts
only an authorized reviewer's standalone `@BOT YES` or `@BOT NO` in the exact
frozen draft's approval thread. Changes require a new draft/thread and fresh
approval; email or model text cannot authorize sending. Bot chat access is not
mail-send authority. See the workflow for recipient binding, expiry, thread
rechecks, and uncertain-send handling.

Neither mode saves correspondence to this public library or needs broad Slack
history access. An appropriately scoped bot can post to its approved channel
through the message-posting API; mailbox access, detection, sending, and reviewer
authorization need a separate connector and provider-specific permission review.

Neither the mailbox connector nor proactive posting workflow is implemented or
connected by this repository. Use the workflow's decision checklist before
configuring either.

## Connecting the app

Use an approved internal Slack app with **Socket Mode**: events arrive over an
outbound WebSocket, so this does not require exposing a public HTTP request URL
or making a task dashboard public.

For either implemented private-channel mode, the app contract is:

| Setting | Purpose |
| --- | --- |
| Bot scope `app_mentions:read` | Receive explicit mentions. |
| Bot scope `chat:write` | Reply as the bot. |
| Bot scope `groups:read` | Verify the private channel and its complete current membership, not message history. |
| App-level scope `connections:write` | Open Socket Mode connections; this is not a bot scope. |
| Bot event `app_mention` | Deliver mentions, not all channel messages. |

An authorized installer must install the app with required workspace approval
and explicitly add it to the pilot channel. Configure its exact channel ID and
choose the reviewed access policy: explicit user IDs or channel membership.
Keep actual IDs outside this public repository.

The bot token and app-level token must be supplied through a protected
credential channel. Do not paste them into chat, public examples, command
history, Git, or logs. Never give those tokens to an unrestricted worker.

This minimal contract does **not** fetch the full thread, read ordinary channel
history, read DMs, or access files. It can reply in a thread using `thread_ts`
without reading all preceding messages. Do not add `chat:write.public`.
Broader history access requires separately reviewed scopes and subscriptions,
such as `channels:history`/`message.channels` or
`groups:history`/`message.groups`.

Adding scopes requires reauthorization/reinstallation for an existing token.
Removing a scope from a manifest does not remove it from tokens already issued;
revoke/reinstall as appropriate when reducing access.

## Reusing Hermes versus building a front door

Hermes has a native Slack Socket Mode adapter and a `hermes slack manifest`
helper. Its generated full manifest requests substantially more than the narrow
pilot above, including history, DMs, files, and slash-command capabilities.

**The narrow bot above is a purpose-built bridge, not a drop-in minimal
configuration for the full Hermes gateway.** Do not assume it can support all
Hermes features. If using that gateway, review the installed version's scopes,
subscriptions, user authorization, toolsets, and platform settings first.

In the inspected source, channel allowlists do not by themselves disable 1:1
DMs, and ordinary mention gating can allow later thread auto-engagement.
Explicitly review strict-mention and DM controls, session separation, memory,
logs, and tool access. Never enable unrestricted workspace-wide access just
to get an initial connection working.

## Optional: an assistant searches Slack

This is different from a bot that people mention. Slack also documents a hosted
MCP server for user-authorized Slack tools. It needs app registration, supported
OAuth setup, appropriate user scopes, and consent; adding an endpoint alone
does not complete that setup. Check client compatibility, including Slack's
lack of Dynamic Client Registration, before choosing this route.

Search/history access and posting permissions should be reviewed separately.
No MCP server is registered or authenticated by this repository.

## Public library versus workspace conversation

A workspace-visible channel is not automatically internet-public. Do not
automatically commit Slack messages, summaries, member details, or private
permalinks to this public library. Propose a sanitized, reusable knowledge
update and obtain the appropriate review before publishing it.

## Sources checked

Official Slack pages below were retrieved directly over HTTPS and inspected.
[Documentation review metadata](docs-review.json) records retrieval time and
public-page hashes. It contains no workspace data and is not a live integration
or client-compatibility test.

- [Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [Mention scope](https://docs.slack.dev/reference/scopes/app_mentions.read/)
- [Socket connection scope](https://docs.slack.dev/reference/scopes/connections.write/)
- [Mention event and its limits](https://docs.slack.dev/reference/events/app_mention/)
- [Message posting, membership, and threads](https://docs.slack.dev/reference/methods/chat.postMessage/)
- [Private-channel metadata scope](https://docs.slack.dev/reference/scopes/groups.read/)
- [Conversation information](https://docs.slack.dev/reference/methods/conversations.info/)
- [Paginated membership](https://docs.slack.dev/reference/methods/conversations.members/)
- [Python Slack SDK Socket Mode](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/)
- [Paperclip Slack task-tool design](https://github.com/paperclipai/paperclip/blob/f7ad1dc7cacedf7153a45e854ddfdd544aa87abd/doc/connections/SLACK-TASK-TOOLS.md)
- [Public-channel message events](https://docs.slack.dev/reference/events/message.channels/)
- [Private-channel message events](https://docs.slack.dev/reference/events/message.groups/)
- [App distribution and permission changes](https://docs.slack.dev/app-management/distribution/)
- [Slack MCP overview](https://docs.slack.dev/ai/slack-mcp-server/)
- [Slack MCP development requirements](https://docs.slack.dev/ai/slack-mcp-server/developing/)
- [Hermes Slack guide at inspected source commit](https://github.com/NousResearch/hermes-agent/blob/74b2ed65e6564bfcafd29236e5fab2447a68fc76/website/docs/user-guide/messaging/slack.md)
- [Hermes manifest generator at that commit](https://github.com/NousResearch/hermes-agent/blob/74b2ed65e6564bfcafd29236e5fab2447a68fc76/hermes_cli/slack_cli.py)
