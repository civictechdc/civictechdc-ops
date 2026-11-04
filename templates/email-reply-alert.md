# Email reply alert — draft template

**Status:** draft template, not a real email or implemented Slack UI.
**Reviewed:** November 3, 2026. **Maintaining role:** unassigned.
**Provenance:** starter layout for the proposed
[email reply workflow](../workflows/email-reply-alerts.md).

```text
NEEDS REVIEW · DRAFT — NOT SENT

From: REPLACE_ALLOWED_SENDER_SUMMARY
Subject: REPLACE_ALLOWED_SUBJECT
Why it may need a reply: REPLACE_REASON_AND_UNCERTAINTY
Stated deadline, if any: REPLACE_VERIFIED_DEADLINE_AND_TIMEZONE

Suggested reply:
REPLACE_DRAFT_REPLY_WITH_UNCONFIRMED_DETAILS_FLAGGED

Review in email: REPLACE_PRIVATE_MAIL_LINK
Next step: Review recipients, edit as needed, and send manually in the mail client.
Review state: REPLACE_UNCLAIMED_CLAIMED_DEFERRED_OR_HANDLED
```

Use only in a channel whose members may access the underlying message.
If sender, subject, or draft content is sensitive, replace this layout with a
minimal “An email needs authorized review” notice and route through the
approved restricted process.

Do not commit filled-in alerts, real mail links, private identifiers, or
correspondence here. This template does not implement buttons, approvals,
mailbox access, or sending.
