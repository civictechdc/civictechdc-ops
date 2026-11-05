# Publication and privacy boundary

The support library was established for public sharing on November 3, 2026.
It is an ongoing collection, not a frozen migration export.

Its initial collection used a selected, independently initialized snapshot,
not a mirror of a private recovery workspace or its Git history.

## Included

- Generalized volunteer-support principles and an unapproved media workflow.
- A dry-run-by-default, GET-only Luma helper and synthetic offline tests.
- Incomplete event-template drafts with placeholders and privacy-first defaults.
- Public-documentation contract metadata and a manual website-work checklist.
- Additional public-safe skills, tools, knowledge, templates, and workflows as
  they are reviewed and added through the contribution process.

## Excluded

- Recovery archives, historical assistant identity, personal profiles and memory.
- Authentication, configuration files or fingerprints, runtime identifiers,
  local environment/service inventories, and private audit reports.
- Historical rosters, contact lists, venue directories, attendance metrics,
  unverified accomplishments, private correspondence, and old account details.
- The private workspace's commit history and any deployment automation.

The public library has its own history. Do not merge private recovery history
into this repository later. A private recovery archive is not a second active
library and is not automatically synchronized with this one. Review additions
for privacy even when they contain no recognizable credential patterns.

Institutional knowledge can include verified public facts and actual public
decisions, not just drafts. Verification and policy approval are different:
record sources and review dates, and never infer approval from publication.

Local tests use synthetic credentials and isolated network namespaces. Luma's
HTTP tests use a non-forwarding curl replacement; Slack's tests use in-process
fakes and socket/DNS blockers. They establish local behavior only. Live API
access and organizational adoption remain separate approval steps.
