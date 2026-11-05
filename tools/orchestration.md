# Support-tool orchestration

**Status:** architectural reference, not a deployment or access grant.
**Reviewed:** November 5, 2026. **Maintaining role:** unassigned.
**Provenance:** proposed support architecture for this library; specific
deployments must document and validate their own configuration separately.

## Distinct roles

| Component | Role in this support pattern |
| --- | --- |
| This repository | Durable, reviewed resources: knowledge, skills, templates, tool guides, and workflows. |
| A task board, such as Paperclip | Requested work, scope, review state, and links to outputs. It is not a second copy of every project repository. |
| An assistant/worker, such as Shelley or Hermes | Performs the requested bounded task using appropriate resources and current sources. Saving a skill here does not configure the worker. |
| Project repositories and the website/playbook | Their own maintained source, issue history, contributor guidance, and approved public content. |
| Restricted operational systems | Credentials, private correspondence, participant records, and other access-controlled information—not public Git content. |

The named tools illustrate roles, not a claim that this repository installs,
connects, or configures any of them.

An optional [private Hermes console](../integrations/hermes/README.md) is for
operator chat and administration, not a replacement for the task board or a
volunteer access point. Direct chat and managed task runs can have different
session/credential lifecycles.

## A small end-to-end loop

1. A human defines a task using the [task brief](../templates/task-brief.md).
2. The task links to relevant resources in [the catalog](../CATALOG.md) and to
   authorized current sources.
3. The worker prepares the bounded output and records evidence, uncertainties,
   and checks. It does not infer additional authority from a library entry.
4. A human reviews consequential decisions and any external action.
5. Reusable public-safe improvements return here; project-specific changes
   belong in the project's maintained repository. Private results stay in
   their restricted system.

## Slack belongs at the coordination layer

Use one organization-owned connection with explicit channel/user boundaries
and task/thread routing, rather than giving every worker its own Slack
credentials or independent listener. The
[proposal-intake pilot](../integrations/slack/README.md) queues private,
unassigned backlog requests and fixed status links; a human reviews before
assignment. It does not provide a conversational worker or email connector.
The separate [email-alert workflow](../workflows/email-reply-alerts.md) remains
a proposal with its own mailbox and review-audience authorization.

## Runtime boundaries

Tool installation, provider/model selection, credential injection, budgets,
sandboxing, scheduling, and service access belong to the actual deployment.
Review those settings separately rather than embedding private runtime state
or old assistant configuration in this library.

Prefer least privilege and bounded work. Verify runtime and API behavior before
relying on it; successful local tests do not establish account access or safe
unattended operation. This reference creates no background jobs or new services.
