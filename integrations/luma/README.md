# Luma read-only helper

**Experimental; dry-run by default; not live-account qualified.**
Invoke this CLI explicitly. Do not source it or treat it as an installed
assistant skill.

## Local use without an account

From the repository root:

```bash
bash integrations/luma/scripts/luma.sh --help
bash integrations/luma/scripts/luma.sh calendar
bash integrations/luma/scripts/luma.sh events 2030-01-01T00:00:00Z
bash integrations/luma/scripts/luma.sh event evt-EXAMPLE
bash integrations/luma/scripts/luma.sh slug 'https://lu.ma/example?tracking=x'
```

`calendar`, `events`, and `event` print GET request plans by default, without
contacting Luma or requiring a key. The date and ID are illustrative.
`slug` only normalizes a local string; it never resolves an API event ID.

Supported reads are a calendar summary, one event-list page, and selected
event details/aggregate counts. List pagination is explicit: pass the next
cursor as the second `events` argument. No automatic pagination, retries,
redirects, arbitrary endpoints, raw-response mode, or guest export is provided.

## Live-read safeguards

Real requests require all of:

- Separate human authorization and confirmation of account/key scope.
- The explicit `--live` flag.
- `LUMA_ENABLE_READS=1`.
- `LUMA_API_KEY` supplied through a protected credential service or controlled
  environment injection, outside this repository.

No account connection or live API success is claimed. Documentation routes
were reviewed; actual authentication, entitlement, response shape, and service
behavior still need a separately authorized qualification.

Never paste keys into chat, source, command arguments/history, fixtures, notes,
or logs. Environment injection is not a vault: same-user/root process
inspection remains a risk. Do not trace the caller's credential setup.
GET-only code does not limit the key's actual server-side permissions.

The helper disables its tracing, removes the key from child environments, and
passes authentication through curl stdin rather than argv or a credential
file. It disables curl configuration files, fixes the HTTPS host, bounds
transfer time/size, and suppresses raw error bodies.

Output still requires appropriate private handling. Reading data does not
authorize publishing it, contacting attendees, or sharing private schedules.
No event creation, guest/host changes, invitations, webhooks, or other writes
are implemented.

## Templates and checks

[Template drafts](event-templates/README.md) are human-editing resources, not
approved API payloads. Nothing submits them.

Checks require Bash, jq, GNU date, Python 3, and Linux `unshare` with
unprivileged user/network namespaces:

```bash
bash -n integrations/luma/scripts/luma.sh integrations/luma/tests/run-offline.sh
bash integrations/luma/tests/run-offline.sh
```

The runner strips its environment and requires a fresh network namespace.
Tests use only synthetic credentials and a curl mock that never forwards
requests. Isolation failure is an error, not permission to use the host network.
Passing tests establish local behavior, not live API compatibility.

`docs-contract-snapshot.json` records public official-documentation URLs,
retrieval time, content hashes, and selected schema projections. It contains
no account responses and is not a complete or permanently current schema.
