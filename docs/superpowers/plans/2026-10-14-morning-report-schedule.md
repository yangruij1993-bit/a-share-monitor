# Morning Report Schedule Implementation Plan

> **For agentic workers:** Execute inline with test driven development and verification before completion.

**Goal:** Publish the prior trading day's report at 08:00, retry at 09:15 only if incomplete, and stop evening report publication.

**Architecture:** Keep the 18:45 Hong Kong fetch as a cache update without report publication. Add an 08:00 launchd job and make the existing 09:15 job conditional on the 08:00 manifest. Treat missing ETF shares, fund NAV, margin summary, and stock margin detail as incomplete. Retry recent empty stock margin detail cache entries.

**Tech Stack:** Python, pytest, macOS launchd.

---

### Task 1: Accurate completeness and data retry

- [x] Add failing tests for missing per-code ETF shares/NAV, missing exchange margin, and missing current-day stock margin detail.
- [x] Add failing test that a recent empty margin-detail sentinel is queried again and replaced on success.
- [x] Implement the smallest changes in `src/flow_dashboard/pipeline.py` and `src/flow_dashboard/data/loaders.py`.
- [x] Run focused tests.

### Task 2: Conditional 09:15 run

- [x] Add failing CLI tests for a complete 08:00 manifest, partial manifest, and absent manifest.
- [x] Add `--retry-if-partial` to `scripts/flow_dashboard/run_daily_finalize.py`.
- [x] Run focused tests.

### Task 3: Stop evening publication and install schedule

- [x] Add failing test for Hong Kong cache-only execution.
- [x] Add `--fetch-only` to the Hong Kong runner and its 18:45 plist.
- [x] Add an 08:00 plist, pass `--retry-if-partial` at 09:15, and update launchd documentation.
- [x] Validate plists, run focused tests, install plists, stop the 19:30 job, and load the new jobs.
- [x] Verify launchd state and final diff.
