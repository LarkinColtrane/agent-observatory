# Migration provenance

agent-observatory was developed in a temporary Claude cloud session on branch
`claude/agent-observatory-governance` of the unrelated **public** practice
repository `LarkinColtrane/Og-Repo`, then migrated into this dedicated
private repository (ADR-0004).

## Method

- `git format-patch df5f2a0..cc09ad6` in the source repository, then
  `git am --committer-date-is-author-date` onto an empty `main`.
- `df5f2a0` (the last practice-repository commit) and all of its ancestry are
  **excluded**. No practice-repository files or history were imported.
- **Why SHAs changed:** a commit SHA covers its parent. The originals descend
  from practice-repository history; keeping their SHAs would have required
  importing that unrelated ancestry. A clean, independent history was chosen
  instead.
- **Content preserved:** for every pair below, the migrated commit's tree is
  identical to the original's tree minus the four practice-repository files
  (`README.md`, `test.txt`, `test2.text`, `Result.txt`), which no project
  commit ever modified. Author, author date, committer date, and full message
  are identical (compared by hash of `%an %ae %ad %B`).
- Commit 1 was also pushed to the practice repository before ADR-0004; commits
  2–5 existed only in the temporary session.

## Mapping

| # | Original (temporary session / Og-Repo branch) | Migrated (this repository) | Message | Tree | Metadata |
|---|---|---|---|---|---|
| 1 | `e4d3154cd86ccc13ff153e9a4c01ba1a6d380bcc` | `076649c57d8eeef8ff5006ca31cd9ef57719fc6f` | docs: establish agent-observatory development governance baseline (P0) | identical | identical |
| 2 | `992eca21f97b215ca72058cc414055535d33dc63` | `04ae78dd7ed39041b7168589d1ff5a8d8960cd44` | docs: pre-Phase-1 governance cleanup after independent review | identical | identical |
| 3 | `368429f84fd3350076c0d8f1833fd9efb2ad4a88` | `9c57292b03f8a1ee639b5490426bbf6ece450580` | governance: address reviewer notes from final verification | identical | identical |
| 4 | `4b1b7d0d409ed1b44e58ae30e6b17f86b0c39c53` | `a516d6e739c1909ae5da40d72b8fdfb071cd22c6` | governance: anchor dedicated-repo remote check to the GitHub host | identical | identical |
| 5 | `cc09ad6deaeadda693755871676200c86246f136` | `94a61a2ff775fd6498e43b39eb83139561ef80ec` | docs: record independent review verdicts and validated P0 gate run | identical | identical |

The tag `gov-baseline-v1.0.0` existed only locally in the temporary session,
was never pushed, and was not migrated; it is superseded by `phase-P0-v1.1.0`.
