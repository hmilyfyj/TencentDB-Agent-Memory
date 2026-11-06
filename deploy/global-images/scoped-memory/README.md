# Scoped memory overlay — opt-in experiment

This is a small local experiment for one owner's private Multica agent. It adds
combined retrieval while preserving existing Memory Core/Hub accounts and stored
project memories. Explicit tools work on their own; an optional dedicated Codex
proxy adds automatic text capture and recall. It is **not** the Hub's L0/L1
extraction pipeline and is not enabled by installing this directory.

## Data and access

| Scope | Default readers | Runtime writers |
| --- | --- | --- |
| `public` | This owner's enabled private agent, across configured projects | None; local human approval only |
| `daily` | The same agent in no-project issues/chats | Current no-project issue/chat |
| `project:<UUID>` | The same agent in that project | Current project issue |

“Public” means shared across this owner's projects, not workspace-public. Runtime
identity comes from task-scoped Multica credentials, the daemon marker, live issue
metadata, the configured private agent owner and project resources. Unknown
projects fail closed. Each source is pinned to its first scope; moving an issue
requires a new issue/session. Parallel tasks do not modify any shared selection.

Every result includes its scope, source, timestamp, state, revision and previous
record ID. Raw archives and explicit summaries are separate records. Only the
latest confirmed revision is returned. Superseded/revoked records remain in the
audit history and are not physically erased. Records from memory are data, not
instructions or authority to execute an action.

Automatic recall gives confirmed summaries priority over raw archives within its
bounded context, so repetitive task dispatch text cannot crowd out reviewed
preferences and project facts. Relevance orders records within each group.

## Install for an experiment

Copy `scoped_memory.py`, `scoped_auth.py` and `manager.py` into a dedicated private
directory outside the checkout, beside the existing `project-routing` directory.
Use mode 0700 for the directory. Create `scope-config.json` with mode 0600:

```json
{
  "workspace_id": "<real Multica workspace UUID>",
  "agent_id": "<private test agent UUID>",
  "owner_id": "<the authorized human owner UUID>",
  "projects": ["<explicitly authorized project UUID>"]
}
```

No keys or service credentials belong in this file. The tool creates
`overlay.sqlite` alongside it using umask 077. Do not install it into a directory
readable by other OS users. Do not share the configured agent or change its owner;
the next call will reject that change. This prototype uses an explicit project
allowlist; the owner must remove a project if authorization is withdrawn.

## Runtime use

In an authorized Multica task, replace `<tool>` below with the installed script:

```sh
python3 <tool> query --query "relevant phrase"
python3 <tool> query --kind skill
python3 <tool> archive --name "unique-source-note" --text-file raw.txt
python3 <tool> remember --name "decision-key" --kind fact --text-file summary.txt
python3 <tool> propose --name "reply-style" --kind preference --text-file preference-summary.txt
```

`archive` stores raw text in the current scope. `remember` stores an explicitly
chosen fact, preference, task status or method in the current scope. A model
choosing “confirmed” is not evidence of human verification; the source must be
checked before treating a remembered business fact as authoritative.

`propose` saves a private candidate, excluded from default retrieval. It does not
publish to `public`. Summarize only the stable preference or validated method,
not its original private conversation. Ambiguous statements remain in the raw
archive. Automatic classification is not a security boundary.

Use `revise --id <latest-id> --text-file corrected.txt` to correct a current-scope
record or update a task from in-progress to completed. Use `revoke --id <latest-id>`
to remove it from future retrieval. Changing an old revision is rejected. Previous
versions remain available to the local owner for audit. Do not put a task status
inside a reusable skill; record it as `kind=task` and update it explicitly.

The tool does not resolve natural-language project names. Ask the user when a
project is unclear. In a no-project session, an explicit read-only comparison is:

```sh
python3 <tool> compare --project <UUID-A> --project <UUID-B> --kind fact
```

This queries only the listed allowed projects and returns source labels. It does
not change the session's write scope. Start a new project task to work/write in a
selected project. Cross-project comparisons from an existing project task are
rejected. No unrestricted `--scope`, `--database` or account override is exposed.

When a project rule conflicts with a public default, explain both sources and
apply the project rule within that project. Current user instructions and checked
code take priority over remembered suggestions. No remembered rule overrides ACLs.

## Local owner management

Open a normal terminal on the machine as the configured owner, outside a Multica
agent run. Do not paste or export a Multica task token into it:

```sh
python3 <tool> inspect --limit 100
python3 <tool> publish --id <candidate-id>
python3 <tool> correct-public --id <latest-public-id> --text-file corrected.txt
python3 <tool> revoke-public --id <latest-public-id>
```

Mutations show the record and require typing the exact action and ID. Publishing
consumes the reviewed candidate and adds a public record referencing it in one
SQLite transaction. Reusing a consumed/stale candidate is rejected. There is no
public-publishing operation available inside a task run. The local OS user is
trusted: a process with that user's file access can bypass these CLI guardrails.
This is not a hostile-process sandbox or server-enforced human approval system.

For a local web review page, run `python3 <installed-directory>/manager.py` from
that same owner terminal. Open `http://127.0.0.1:8126/` and enter the random password
printed in the terminal; it changes after every restart. The page lists authorized
scopes and states, shows record provenance/history, and supports editing a
candidate before public publication, correction and revocation. Writes require
an authenticated cookie, same-origin request, CSRF token and exact action/ID
confirmation. Models cannot start the management entry point from a task. Both
management entry points reject records in removed project scopes. This remains a
trusted local OS user boundary, not protection from that user's hostile processes.

The existing Memory Hub panel continues to manage its own data; it does not display
this independent overlay. No admin key is needed or handed to the model. Web
review tests use a temporary database and do not represent actual human approval.

## Optional automatic Codex capture

Use a **separate test proxy**, port and state volume. Never stop a proxy your own
agent depends on to deploy its replacement. Keep the existing provider available
until the replacement is ready; change only the enabled private test agent.

Initialize the overlay schema with `Store(<database-path>)` before starting the
proxy. Add this to the dedicated proxy's configuration, using verified account
IDs from its existing authentication service, not caller-provided scope headers:

```yaml
scopedMemory:
  database: /data/overlay/overlay.sqlite
  accounts:
    <owner-no-project-account-id>: daily
    <owner-project-account-id>: project:<allowed-project-UUID>
extraction:
  enabled: true
  extractors: [tdai-memory]
skillRuntime:
  allowLlmWrite: false
```

Map only this owner's authorized accounts. Do not enable this on a proxy serving
other owners or shared agents. These IDs are scope mappings, not API keys. Keep
the full deployment configuration private. The database and state volume must be
writable by the proxy user; a missing store or invalid scope fails the request.
New Docker volumes can be root-owned. Set the dedicated state volume's owner to
the image's application UID before starting it, and require `/health` to report
`storage.effective=sqlite`. Checking HTTP 200 or `degraded=false` alone is
insufficient. Validate a restart separately from successful in-memory requests.

For newly started test runs, point the Codex provider at the dedicated port and
use `scoped_auth.py` as its auth command. It validates live Multica identity and
scope before delegating to the existing protected project credential resolver;
it pins the issue/chat source so moving a project requires a new task/session.
The resolver is not bundled here and must already exist in `project-routing`.
Do not read or paste credential files into prompts or command arguments.

For the fixed ISSUE-1073 deployment, the overlay directory is named
`scoped-memory-1073-stage2` and its proxy listens on 8097. Back up the existing
`project-routing/project_bridge.py`, then install this directory's
`project_bridge.py` there, beside `project_auth.py`. Its existing command syntax
is unchanged. It routes only sessions pinned in the trial SQLite to 8097;
earlier sessions keep using 8096. The current task's protected credential resolver
and the bridge's ownership checks still decide access. A rejection never causes
a credential change or endpoint retry. This fixed-port caller is a local trial
integration, not a general multi-proxy router.

The Codex Responses main path archives the latest user text before forwarding.
Completed final answers are archived separately; tool-only, incomplete and
truncated responses are excluded. Retries reuse names and cannot resurrect an
owner's corrected/revoked record. Large user text is split into 12k-character
records. Recall injects latest confirmed public + current-scope records with
provenance, capped at 200 candidates, eight selected records and a 6k-character
budget. It is bounded lexical recall, not guaranteed semantic retrieval. A model
receives archived text as untrusted data, with no authority to change permissions.

This path requires full Responses input arrays and stable session IDs. Auxiliary,
legacy passthrough, intercepted commands/forms, other protocols, images, tool
outputs and compaction history are outside its capture guarantee. Streaming
archive errors are logged after the response has started; successful model text
alone is not evidence of durable archival. Verify the stored rows separately.

The extraction whitelist disables automatic Hub Skill creation on this proxy;
the write gate also blocks manual `skill/extract` and all Skill mutation routes.
It does not quarantine old active Skills, cancel old Hub jobs, or constrain
clients using another proxy. Candidates remain explicit `propose` records;
automatic raw capture does not imply automatic preference extraction or approval.
Existing active Skills require separate provenance review before trusted use.

## Skills, validation and rollback

Public methods exist as one public `kind=skill` record, not copies in every
project. Project methods are scoped records. These are method documents, not
automatically installed executable skills. Keep actual Multica workspace skills
as their existing single source; do not duplicate them into Memory Hub. Do not
publish automatically extracted executable skills without review and validation.

Run the isolated tests (no live service or credentials needed):

```sh
cd deploy/global-images/scoped-memory
python3 -m unittest -v
```

Tests cover identity failure, chat/no-project routing, private data boundaries,
scope changes, public approval, stale revisions, correction/revocation, task
updates, project methods, explicit comparisons and concurrent writes. Synthetic
chat-marker tests are not evidence that a real Multica Chat was created and
recalled. Record live acceptance results separately.

Opt in by including the tool commands in a test task. No global agent instruction
change, model proxy modification or container restart is necessary. Stop all
trial calls before cleanup; archive this dedicated directory to retain test data,
or remove it after deciding the audit records are no longer needed. For an
automatic-capture trial, first restore the test agent's saved provider arguments
to the still-running original proxy, then stop the dedicated test container.
Restore the saved bridge caller as well, before retiring its trial session store.
Keep its database and volume for audit; do not remove shared volumes. Existing Hub
volumes, project routing and formal agents are unchanged. For a database backup,
use Python's `sqlite3.Connection.backup()`;
do not copy an active database file while writers run.

Known limits: automatic capture only on the enabled Codex main path; lexical
search rather than semantic ranking; no automatic expiry or synchronization with
Multica task status; human approval rather than guaranteed automatic extraction;
latest-record inspection capped at 100; static owner-managed project allowlist;
no multi-machine deployment or strong isolation from the same OS user's processes.
