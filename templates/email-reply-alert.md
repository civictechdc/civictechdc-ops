# Email reply alert and approval card

**Status:** draft template, not a real email or implemented Slack UI.
**Reviewed:** November 12, 2026. **Maintaining role:** unassigned.
**Provenance:** starter layout for the proposed
[email reply workflow](../workflows/email-reply-alerts.md).

```text
NEEDS REVIEW · DRAFT · NOT SENT

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

## Optional approval-and-send card

Use only after a real sending connector, reviewer authorization, and Gmail
OAuth grant have been implemented and separately approved. These commands do
not work merely because this template exists.

```text
EMAIL DRAFT · NOT SENT

Version: REPLACE_FROZEN_VERSION
Expires: REPLACE_EXPIRY_AND_TIMEZONE
From: REPLACE_APPROVED_FROM_ADDRESS
To: REPLACE_ALL_TO_ADDRESSES
CC: REPLACE_ALL_CC_ADDRESSES_OR_NONE
BCC: REPLACE_ALL_BCC_ADDRESSES_OR_NONE
Subject: REPLACE_EXACT_SUBJECT
Attachments: None

REPLACE_COMPLETE_EXACT_REPLY_BODY

Review original: REPLACE_PRIVATE_MAIL_LINK
Authorized reviewers: REPLACE_APPROVED_REVIEWERS

Reply in THIS thread with only:
@BOT YES
to send this exact email once, or:
@BOT NO
to cancel this pending request.

BOT means the actual bot mention. Any edit needs a fresh draft and approval
in a new thread. NO cannot recall an email already sent.
```

Never reuse an approval thread for a revised draft or hide/truncate fields
needed for informed approval. For manual-send mode, keep the first layout and
do not display approval commands.

Use only in a channel whose members may access the underlying message.
If sender, subject, or draft content is sensitive, replace this layout with a
minimal “An email needs authorized review” notice and route through the
approved restricted process.

Do not commit filled-in alerts, real mail links, private identifiers, or
correspondence here. This template does not implement command parsing, approvals,
mailbox access, or sending.
