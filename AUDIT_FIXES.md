# Portable native paths and repository hygiene

Repair branch: `fix/internship-audit-20261010`. Changes are scoped to audit findings; no deployment or live provider action is included.

## Changed

Removed tracked frontend/node_modules while retaining the lockfile; dependencies are recreated with npm ci. Native executable discovery uses configured paths/PATH or a sibling build instead of developer-machine drive paths. PowerShell startup is relocatable. README describes the actually wired router and optimizer paths.

## Verification

`MKDB_SERVER=/absolute/path/mkdb_server pytest -q`

Commands are entry points, not a claim that every live integration was executed. See the repair bundle for actual results.

## Setup and remaining evidence

This is the cluster layer around the sibling MiniDB engine, not an independent second database product. Reads are leader-local; do not claim linearizable reads without a read-index/lease implementation and tests. Static membership, snapshots/log compaction, replicated write barriers during rebalancing and crash/concurrent-write workload proof remain open. Historical benchmarks must be rerun with configuration, seed and raw logs. The optional LLM optimizer test is skipped without a provider.
