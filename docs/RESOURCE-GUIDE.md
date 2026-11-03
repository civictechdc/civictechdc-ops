# Saving and maintaining support resources

Reference guide. Reviewed November 3, 2026.

## Pick a home

| Kind | Home | Distinction |
| --- | --- | --- |
| Institutional knowledge | `knowledge/` | What we know, why a decision was made, and where to verify it. |
| Skill | `skills/` | How to perform one repeatable, bounded task. |
| Tool guide | `tools/` | What a tool does, when to use it, and its limits. |
| Template | `templates/` | A reusable structure to fill in; not a completed private record. |
| Workflow | `workflows/` | A sequence across people/tools, including handoffs and approvals. |
| Service integration | `integrations/<service>/` | Adapter code, safe examples, documentation, and tests. |
| Supporting reference | `reference/` | Supplementary material or a pointer to a maintained external source. |

A resource can serve several categories without being copied. For example,
the event-template drafts stay beside the Luma integration, and the template
index links to them. Preserve existing paths when a new index is sufficient.

## Include enough context to reuse it safely

Each substantive resource should identify:

- **Purpose and scope:** what problem it helps with and what it does not do.
- **Status:** draft, reference, experimental, approved, or retired. Use
  “approved” only with a real approval record and its scope.
- **Provenance and freshness:** sources, relevant version/check date, and
  uncertainty. A check date is not an expiry guarantee.
- **Maintaining role:** a role that has agreed to maintain it, or “unassigned.”
  Listing someone does not assign them work or authority.
- **Inputs and outputs:** where they come from and whether they can be public.
- **Human gates:** approvals and privacy checks before consequential actions.
- **Validation:** a completion checklist or, for code, reproducible checks and
  known limitations.

Add it to [the catalog](../CATALOG.md) and the relevant category index.
Existing resources may acquire this structure incrementally; do not invent
sources, maintainers, approvals, or test results to fill a field.

## Keep knowledge useful rather than merely accumulated

- Save verified lessons and decision rationale, not raw chat transcripts or
  everything an assistant guessed.
- Separate facts, proposals, decisions, and open questions.
- Prefer links to an existing authoritative website, playbook, or project
  repository when that is where the material is maintained.
- Review a resource when facts change, it is used for an external action, or
  a relevant tool/service changes. Record the review; do not silently promote
  historical material into current truth.
- Mark superseded material retired and point to its replacement.

## Storage is not installation or authority

Humans and assistants can discover resources through the README and catalog.
Reading or saving a skill does not install it, alter a system prompt, add
permissions, connect a service, or schedule work. Agent-specific packaging,
configuration, and activation require separate review in the target runtime.

Do not commit secrets or completed private records—even encrypted payloads or
“temporary” dumps intended to be removed later. Keep restricted information in
an appropriately controlled system. Public instructions may describe access
requirements without exposing private record links, identifiers, or data.
