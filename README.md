# Civic Tech DC support library

The central, version-controlled home for reusable **skills, tools, institutional
knowledge, templates, and workflows for supporting Civic Tech DC**.

This is a shared library for volunteers, organizers, and assistants—not just a
recovery snapshot or one assistant's memory. Save useful, public-safe knowledge
here so people can find it, improve it, and carry work forward.

## Find what you need

Start with the **[resource catalog](CATALOG.md)**.

| Section | What belongs here |
| --- | --- |
| [Knowledge](knowledge/README.md) | Organizational context, verified lessons, decision records, and references. |
| [Skills](skills/README.md) | Reusable procedures for doing a bounded support task. |
| [Tools](tools/README.md) | Tool purpose, usage, limitations, and orchestration patterns. |
| [Templates](templates/README.md) | Starting points for project briefs, tasks, decisions, and events. |
| [Workflows](workflows/README.md) | End-to-end processes, handoffs, and human approval points. |
| [Integrations](integrations/README.md) | Service adapters, code, safe setup references, and tests—never credentials. |
| [Reference](reference/website-workflow.md) | Supporting guides and links to maintained sources elsewhere. |

Keep one canonical copy of each resource. The category indexes link to existing
files where appropriate rather than creating competing copies.

## Use and contribute

1. Search the catalog before creating something new.
2. Read the resource's status, sources, limits, and required approvals.
3. Use an existing template or skill for a small, clearly bounded task.
4. Save reusable improvements or verified lessons back here, with context and
   a review date. Update the catalog in the same change.

See [Contributing](CONTRIBUTING.md) and the
[resource guide](docs/RESOURCE-GUIDE.md) for placement and review expectations.

## Try the existing read-only tool

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

The Luma helper includes no write commands, event publishing, guest exports,
invitations, scheduled jobs, or automatic account connections.

The separate [Slack support pilot](integrations/slack/README.md) has an
experimental task-intake bridge and opt-in conversational routing to a
separately qualified restricted worker. Its tests are also offline:

```bash
bash integrations/slack/bridge/tests/run-offline.sh
```

Live use requires separately authorized app installation, private credentials,
and audience/permission checks. Ordinary conversation can return bounded
advice/drafts; explicit task requests create review proposals, not automatic
Engineer runs or email responses. Conversation is disabled by default.

## Shared knowledge is not blanket permission

This repository is public. Do not save credentials, participant records, private
correspondence, private schedules or addresses, internal audit records, or
personal profiles here. Restricted records belong in separately controlled
systems, not a hidden folder or an earlier Git commit in this repository.

Publishing a resource does not adopt a policy, designate a spokesperson, approve
an event, connect an account, or authorize external actions. Drafts and
experimental tools remain labeled. Actual dates, venues, accessibility
arrangements, project states, public claims, and permissions require current
confirmation. A passing offline test does not prove live API compatibility.

The website, playbook, project repositories, and responsible people remain the
sources for their own current facts and decisions; link to them rather than
silently copying or overruling them. See the
[publication boundary](docs/PUBLICATION.md).

## Status

Established November 3, 2026. The initial collection includes draft support
procedures, event templates, website guidance, and an experimental Luma helper.
It can grow as additional material is reviewed; it is not a complete inventory
of connected services or approved organizational policy.

License selection is pending; no license grant is added by this draft.
