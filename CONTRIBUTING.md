# Contributing

Small, reviewable improvements are welcome. Keep volunteer time, accessibility,
privacy, and maintenance burden in mind.

1. Search [the catalog](CATALOG.md), describe the problem, and choose the
   smallest useful change. Reuse or link an existing resource before duplicating
   it. Use the [resource guide](docs/RESOURCE-GUIDE.md) for placement.
2. Use public sources or synthetic data; do not post private participant or
   organizational records in issues, tests, logs, or pull requests.
3. Include purpose, status, sources/provenance, last review date, limitations,
   and any approval requirements. Name a maintaining role if one has agreed;
   otherwise say it is unassigned. Keep proposed policy and event copy clearly
   marked **draft** until an authorized human approves them. Update the catalog
   and relevant category index in the same change.
4. Preserve the Luma helper's dry-run default and narrow read-only scope.
   Credential handling, new endpoints, writes, guest-data access, notifications,
   and external services require separate review.
5. Run relevant offline checks from the repository root:

   ```bash
   bash -n integrations/luma/scripts/luma.sh integrations/luma/tests/run-offline.sh
   bash integrations/luma/tests/run-offline.sh
   bash integrations/slack/bridge/tests/run-offline.sh
   ```

   Tests need Bash, jq, GNU date, Python 3, and Linux `unshare` with unprivileged
   user/network namespaces. Slack's synthetic suite does not require the live
   SDK or tokens. Tests must not fall back to the host network.
6. Review your complete diff and report checks not run. Do not use real
   credentials or contact external services merely to test a contribution.

This repository does not install assistant-wide instructions or grant
permission to speak for Civic Tech DC. Publishing changes here is not approval
to publish events, contact people, deploy the website, or adopt a policy.
