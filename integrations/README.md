# Service integrations

Service-specific implementation, safe setup references, and tests. Listing a
service here does not mean it is installed, connected, or authorized.

| Integration | Status |
| --- | --- |
| [Luma](luma/README.md) | Experimental read-only CLI; dry-run by default; live account unqualified. |
| [Slack](slack/README.md) | Experimental approval-first proposal bridge; live Slack access unqualified; email/chat assistance still proposed. |
| [Hermes operator console](hermes/README.md) | Optional private-admin reference; no installer, live inventory, or access grant. |

Store no credentials, real workspace/member/channel IDs, participant records,
or private service exports here. Follow the
[resource guide](../docs/RESOURCE-GUIDE.md) and update
[the catalog](../CATALOG.md) when adding or changing an integration.
