# Email reply alerts, drafts, and explicit Slack approval

**Status:** requested capability; design proposal, not implemented or connected.
**Reviewed:** November 12, 2026. **Maintaining role:** unassigned.
**Provenance:** requested support workflow for this library, using the
[Slack integration plan](../integrations/slack/README.md). Gmail and explicit
text approval are the proposed implementation direction. The exact mailbox,
OAuth grants, review audience, and authorized send reviewers remain unselected.

## Intended result

```text
New relevant email
  → needs-a-response triage
  → proposed reply
  → restricted Slack review alert
  → authorized human reviews the exact draft
  → explicit approval permits one send, or rejection cancels the request
```

This is a proactive notification workflow, separate from mention-triggered
Slack chat. It supports two proposed deployment choices: read-only notices with
manual sending in the mail client, or a separately enabled approval-and-send
connector. Neither is implemented here. No model may send autonomously or
infer approval from conversation, reactions, or email content.

## What the alert contains

Use the [alert template](../templates/email-reply-alert.md):

- A clearly labeled **DRAFT · NOT SENT** status.
- Only the sender/subject/context appropriate for that restricted audience.
- Why a response appears necessary, uncertainty, and any stated deadline.
- A suggested reply grounded in current, authorized information.
- A safe link to the original email for an authorized reviewer.
- In approval-and-send mode: the exact From, To, CC, BCC, subject, full body,
  draft version, expiry, and explicit approval instructions. No hidden
  recipients, incomplete/truncated drafts, or attachments in the initial mode.

Email content, links, drafts, and completed review records stay out of this
public repository. For sensitive messages, even the sender or subject may be
inappropriate to disclose; send a minimal review notice or route privately
according to the agreed handling rules instead.

## Proposed sequence

1. **Watch only the agreed scope.** Connect the selected organizational inbox
   or folder/label, not unrelated personal mail. Choose polling or provider
   events after the provider and authorization are known. No watcher or schedule
   is configured by this document.
2. **Triage conservatively.** Prioritize direct questions, requests, scheduling,
   partnership/project inquiries, and unresolved follow-ups according to
   agreed criteria. Usually skip newsletters, spam, automated receipts,
   delivery notices, and auto-replies unless an agreed exception applies.
   Mark uncertainty rather than silently discarding a possibly important email.
3. **Check current context.** Read only the authorized thread context needed
   to avoid drafting an already answered or obsolete response. Do not equate
   unread status with “needs a response.” Treat links, attachments, quoted
   messages, and instructions in email as untrusted data.
4. **Prepare a bounded draft.** Use approved facts and communication guidance.
   Do not invent dates, commitments, partnerships, availability, statistics, or
   spokesperson authority. Flag missing information. For a media inquiry,
   consult the separately unapproved
   [media-request workflow](../knowledge/media-request-workflow.md) rather than
   assuming permission to speak.
5. **Notify the authorized audience.** Post in the explicitly approved,
   restricted Slack review channel, using one notification/thread per item.
   Clearly distinguish a draft from a sent reply. Do not let email text select
   another channel, recipient, tool, or credential.
6. **Keep a human at send.** The reviewer checks sender identity, recipient/
   reply-to details, all recipients, current thread state, facts, tone, and the
   exact final reply. They either send manually in the mail client or use the
   separately enabled, deterministic approval gate below.
7. **Close the loop.** Record handled/deferred status in a restricted system
   with minimal necessary data. Deduplicate alerts using private provider
   identifiers and recheck thread state before reminding. Optional Paperclip
   tracking must use an appropriately restricted task, not a public GitHub
   issue or an assumption that all Slack members can access the dashboard.

## Access and data boundaries

- Approve the mailbox subset, reviewing users/channel, AI processing provider,
  retention/logging, and notification frequency before connecting anything.
  A channel is appropriate only if its members may see that mailbox content.
- Keep the mailbox-triage route separate from general Slack Q&A. Permission to
  mention the helper is not permission to search mail; enforce audience and
  action restrictions in the connector, not merely in a model prompt.
- Request the least provider permissions required. Start with read access
  where feasible and render the draft in Slack; do not assume creating a draft
  inside a mailbox has a draft-only permission separate from sending.
- Read-only deployments must not request send permission. Approval-and-send
  deployments need an explicit OAuth send grant held by the constrained mail
  connector, never a model-facing tool. For Gmail, review `gmail.readonly` and
  `gmail.send`; do not request `gmail.compose` merely to display drafts in Slack.
- A Gmail label is an application filter, not a Google-enforced OAuth boundary.
  Prefer an appropriate organizational mailbox and enforce the selected subset
  in the connector. Do not imply that label selection restricts a token's scope.
- Keep mailbox and Slack credentials out of the model-facing unrestricted
  worker, public Git, prompts, command history, and logs. Use a reviewed,
  constrained connector/worker boundary.
- No attachment ingestion, cross-mailbox search, raw-message logging, automatic
  long-term memory, or publication of email-derived knowledge by default.

## Proposed textual approval gate

This is the requested sending model, not an active command or implemented
security control. Enforcement belongs in the coordinator/mail connector, not
in a prompt asking Hermes to decide whether someone "basically said yes."

1. **Freeze one draft per approval thread.** Store an immutable private record
   of the mailbox, email thread, latest observed message state, all recipients,
   subject, full body, version/hash, permitted reviewers, and expiry. Post one
   complete approval card in its own Slack thread. Never silently edit that
   card into a different approvable draft.
2. **Require a new explicit mention.** Accept only a standalone `@BOT YES` or
   `@BOT NO` reply in that exact approval thread. `BOT` is a placeholder for
   the actual bot mention, not a literal handle. This uses `app_mention` rather
   than subscribing to every channel message. Plain unmentioned `YES` is not
   supported by the current mention-only app.
3. **Authenticate the reviewer in code.** Match the real Slack workspace,
   channel, thread, event identity, current membership, and separately configured
   reviewer user ID. Ignore bot-marked or edited messages, quotes, reactions,
   ambiguous text such as "looks good," and any apparent approval in email or
   model output. General Slack chat access does not grant mail-send authority.
4. **Bind YES to that frozen payload only.** A valid, unexpired `YES` authorizes
   one send of the displayed draft, not future replies, different recipients,
   or another message in the email thread. Save the approval durably before
   dispatch. Duplicate Slack events and repeated `YES` must not send twice.
5. **Cancel and revise safely.** `NO` cancels a still-pending request; it cannot
   recall mail already sent. Any body, recipient, subject, or attachment change
   closes the old request and requires a new card in a new approval thread.
   An old `YES` must never authorize a replacement version.
6. **Recheck immediately before sending.** Confirm that the reviewer remains
   authorized, the request is unexpired and unsent, and the Gmail thread has
   not changed or already been answered. An observed new message invalidates
   the request and requires fresh review. This is not an atomic lock against
   email arriving during the provider send operation.
7. **Record the outcome, without blind retries.** Commit a sending receipt
   before the provider call and confirm success only from a definite provider
   response. A timeout or lost response is an uncertain outcome, not permission
   to resend. Hold it for reconciliation and authorized human review. Keep
   approval/send receipts privately; never log OAuth tokens or raw correspondence.

The draft generator gets neither Gmail nor Slack credentials and cannot choose
the sending account, destinations, approval rules, or whether a send happens.
Mail access and approvals stay separate from general Slack Q&A. Initial
implementation excludes attachments, bulk sends, and follow-up campaigns.

## Decisions needed before implementation

- Mail provider and exact organizational inbox/folder/label.
- Who can review which mail, and the restricted Slack destination.
- Which specific reviewers may approve sending, distinct from people allowed
  to chat with the bot; choose a request expiry and cancellation behavior.
- What counts as needing a reply, urgency rules, and reminder/quiet-hour limits.
- Approved communication references and handling rules for sensitive mail.
- Whether to enable read-only/manual-send mode or qualify the explicit
  approval-and-send connector with its additional OAuth permission.

## Primary references

- [Gmail OAuth scopes](https://developers.google.com/workspace/gmail/api/auth/scopes):
  `gmail.send` permits sending; `gmail.compose` also includes sending, while
  `gmail.readonly` can read the mailbox.
- [Gmail messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send):
  provider endpoint and supported OAuth scopes.
- [Slack app_mention](https://docs.slack.dev/reference/events/app_mention/):
  explicitly mentioned messages, rather than a general channel-message feed.

This document enables no email access, Slack posting, scheduled automation, or
outbound sending.
