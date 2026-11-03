# Civic Tech DC operations resources

Draft workflows, event templates, and small tools for volunteer-led civic-tech
operations.

**These are working resources, not adopted organizational policy or a promise
of services.** Publishing this repository does not approve a workflow, designate
a spokesperson, authorize external actions, or connect an account.

## Contents

- [Working principles](knowledge/organizational-context.md): user involvement,
  realistic volunteer capacity, continuity, and human decisions.
- [Media-request workflow](knowledge/media-request-workflow.md): an explicitly
  unapproved intake, review, response, and recordkeeping draft.
- [Luma read-only helper](integrations/luma/README.md): dry-run by default,
  explicit live-read safeguards, and network-isolated offline tests.
- [Event template drafts](integrations/luma/event-templates/README.md): five
  incomplete, privacy-conservative starting points for organizer review.
- [Website-work reference](reference/website-workflow.md): a manual checklist
  that defers to the website repository's current source and guidance.

## Start safely

From this checkout:

```bash
# No account or key required; these do not contact Luma.
bash integrations/luma/scripts/luma.sh --help
bash integrations/luma/scripts/luma.sh calendar
bash integrations/luma/tests/run-offline.sh
```

The `calendar` command prints a request plan, not account data. The test runner
requires Linux user/network namespaces and fails rather than running without
network isolation. See the integration README for dependencies and limitations.

No write commands, event publishing, guest exports, invitations, scheduled jobs,
or automatic account connections are included.

## Privacy and approval

Use synthetic examples in public issues and pull requests. Do not commit
credentials, participant records, private correspondence, private schedules or
addresses, internal audit records, or personal profiles.

Actual event dates, venues, accessibility arrangements, project status,
partnerships, public statements, and permissions require current confirmation.
An event template is not a booking or approved API payload. A passing offline
test is not proof of live API compatibility.

See [Contributing](CONTRIBUTING.md) and the
[publication scope](docs/PUBLICATION.md).

## Status

Prepared November 3, 2026. Luma documentation routes were reviewed, but no live
account qualification is claimed. No workflow here should be represented as
official policy without separate human approval.

License selection is pending; no license grant is added by this draft.
