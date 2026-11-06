# Personal fork maintenance

This repository is maintained in `hmilyfyj/TencentDB-Agent-Memory`.
The maintained integration branch is `fengit-maintained-memory`.

- Push changes and open pull requests only in this personal fork. Do not open or
  reopen pull requests against `TencentCloud/TencentDB-Agent-Memory` unless the
  user explicitly changes this instruction.
- For subsequent work, branch from the current `fengit-maintained-memory` head
  and target that branch in fork-local pull requests. The initial consolidation
  pull request targets the fork's existing `feat/server_team` baseline.
- Preserve the original project isolation patches and scoped-memory experiment.
  Keep upstream synchronization separate and review conflicts before accepting it.
- Do not commit local credentials, runtime identity configuration, databases or
  private deployment files. Do not enable the experiment on formal agents as part
  of repository maintenance.
- Validate affected behavior. The scoped overlay tests run with
  `python3 -m unittest discover -s deploy/global-images/scoped-memory -v`.
  Changes to Knowledge or Proxy authorization also require their relevant tests.
