# Email reply alerts and drafts in Slack

**Status:** requested capability; design proposal, not implemented or connected.
**Reviewed:** November 3, 2026. **Maintaining role:** unassigned.
**Provenance:** requested support workflow for this library, using the
[Slack integration plan](../integrations/slack/README.md). Mail provider,
mailbox, permissions, and reviewing channel have not been selected here.

## Intended result

```text
New relevant email
  → needs-a-response triage
  → proposed reply
  → restricted Slack review alert
  → human edits and sends from the mail client
```

This is a proactive notification workflow, separate from mention-triggered
Slack chat. **Version one does not send email.** It does not require broad
Slack history access or automatically opening a public issue.

## What the alert contains

Use the [alert template](../templates/email-reply-alert.md):

- A clearly labeled **DRAFT — NOT SENT** status.
- Only the sender/subject/context appropriate for that restricted audience.
- Why a response appears necessary, uncertainty, and any stated deadline.
- A suggested reply grounded in current, authorized information.
- A safe link to the original email for an authorized reviewer.

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
   reply-to details, any CC list, current thread state, facts, tone, and the
   exact final reply. In version one they edit/send in the mail client; the bot
   has no sending workflow.
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
- Do not request email-send capability for this first phase. Review the actual
  provider's permission model before any later mailbox-write feature.
- Keep mailbox and Slack credentials out of the model-facing unrestricted
  worker, public Git, prompts, command history, and logs. Use a reviewed,
  constrained connector/worker boundary.
- No attachment ingestion, cross-mailbox search, raw-message logging, automatic
  long-term memory, or publication of email-derived knowledge by default.

## A possible later approval-and-send phase

Slack “approve and send” is not part of version one. If separately requested,
it needs authenticated reviewer authorization, recipient/thread validation,
approval bound to the exact current draft, invalidation after edits or new mail,
deduplicated send handling, and a private audit trail. An emoji reaction or
instruction inside an email is not sufficient authorization.

## Decisions needed before implementation

- Mail provider and exact organizational inbox/folder/label.
- Who can review which mail, and the restricted Slack destination.
- What counts as needing a reply, urgency rules, and reminder/quiet-hour limits.
- Approved communication references and handling rules for sensitive mail.
- Whether drafts stay in Slack initially or a later mailbox-write feature is
  worth its additional permissions and review.

This document enables no email access, Slack posting, scheduled automation, or
outbound sending.
