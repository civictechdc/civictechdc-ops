# Tools and integrations

Record what a tool is for, how to use it safely, and where its maintained
implementation lives. Documentation in this library is not an installer,
credential store, or live inventory of connected accounts.

## Current material

- [Orchestration pattern](orchestration.md) — how the library, task board,
  assistants/workers, and project repositories fit together.
- [Hermes operator console](../integrations/hermes/README.md) — private direct
  chat/administration, deployment boundaries, and an acceptance checklist;
  not a volunteer interface or installer.
- [Luma helper](../integrations/luma/README.md) — experimental GET-only CLI,
  dry-run by default, with isolated offline tests. Live account access is
  unqualified and requires separate authorization.
- [Slack integration](../integrations/slack/README.md) — experimental private
  proposal bridge with opt-in conversational routing, access boundaries, and
  setup references. Restricted worker deployment and live checks are separate;
  email remains proposed.

Keep service-specific code, safe configuration examples, and tests together
under `integrations/<service>/`. Tool guides should link there rather than
duplicate usage instructions.

New tools need a real purpose, privacy/access boundaries, reproducible checks,
and clear deployment limitations. Do not add a dependency merely to fill an
inventory or copy an old global installation command without review.
