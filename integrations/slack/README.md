# Slack integration plan

**Status:** proposal; not implemented, installed, or connected by this repository.
**Reviewed:** November 3, 2026. **Maintaining role:** unassigned.
**Provenance:** current official Slack documentation and the Hermes source
snapshot linked below. These are setup references, not a live integration test
or approval from a workspace or project.

## What we want

Use Slack as a convenient support/intake surface, this repository as the shared
support library, and Paperclip as a task/review record. A restricted worker can
prepare requested outputs after the appropriate human review.

Example pilot requests:

- Find the project-brief template or explain a documented workflow.
- Prepare draft event copy from confirmed inputs.
- Propose a small project task for a maintainer to review.
- Receive an explicitly configured email-needs-reply alert, with a draft ready
  for an authorized reviewer.

Do not require volunteers to use a new task system merely to participate.
Deployment-specific Paperclip links may require separate access; do not assume
every Slack participant can open them.

## Recommended pilot

1. Choose one approved channel and a small explicit user allowlist.
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

The controlled Paperclip handoff described here still needs implementation and
testing. A Slack adapter does not automatically supply task authorization.

## Proactive email alerts

The requested [email reply workflow](../../workflows/email-reply-alerts.md)
adds a separate trigger: a relevant email, not a Slack mention. After explicit
setup approval, the bot would post a review notice and proposed reply to the
designated restricted channel.

The first phase is **notify and draft only**. A human reviews and sends in the
mail client. It does not save correspondence to this public library, send email,
or require reading Slack history. An appropriately scoped bot can post to its
approved channel through the message-posting API; mailbox access and detection
need a separate connector and provider-specific permission review.

Neither the mailbox connector nor proactive posting workflow is implemented or
connected by this repository. Use the workflow's decision checklist before
configuring either.

## Connecting the app

Use an approved internal Slack app with **Socket Mode**: events arrive over an
outbound WebSocket, so this does not require exposing a public HTTP request URL
or making a task dashboard public.

For a purpose-built, mention-only front door, the narrow starting contract is:

| Setting | Purpose |
| --- | --- |
| Bot scope `app_mentions:read` | Receive explicit mentions. |
| Bot scope `chat:write` | Reply as the bot. |
| App-level scope `connections:write` | Open Socket Mode connections; this is not a bot scope. |
| Bot event `app_mention` | Deliver mentions, not all channel messages. |

An authorized installer must install the app with required workspace approval
and explicitly add it to the pilot channel. Use channel and user IDs for
runtime allowlists; keep actual IDs outside this public repository.

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

**The two-scope bot above is a custom-app design, not a drop-in minimal
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
- [Public-channel message events](https://docs.slack.dev/reference/events/message.channels/)
- [Private-channel message events](https://docs.slack.dev/reference/events/message.groups/)
- [App distribution and permission changes](https://docs.slack.dev/app-management/distribution/)
- [Slack MCP overview](https://docs.slack.dev/ai/slack-mcp-server/)
- [Slack MCP development requirements](https://docs.slack.dev/ai/slack-mcp-server/developing/)
- [Hermes Slack guide at inspected source commit](https://github.com/NousResearch/hermes-agent/blob/74b2ed65e6564bfcafd29236e5fab2447a68fc76/website/docs/user-guide/messaging/slack.md)
- [Hermes manifest generator at that commit](https://github.com/NousResearch/hermes-agent/blob/74b2ed65e6564bfcafd29236e5fab2447a68fc76/hermes_cli/slack_cli.py)
