# MARSWALK — Git Workflow

| Field          | Value                     |
|----------------|---------------------------|
| Document       | GIT_WORKFLOW.md           |
| Version        | 1.0                       |
| Owner          | Orchestrator (owner approves changes) |
| Last updated   | 2026-11-11                |

---

## 1. Branch Model

```text
main      ← releases only. Changed only by an owner-approved pull request.
  ▲
  │  pull request at each milestone (owner reviews and merges)
  │
develop   ← integration branch. Always passes the full test suite.
  ▲
  │  merge --no-ff after the WP meets the Definition of Done
  │
wp/WP-xx-<slug>   ← one branch per work package (IMPLEMENTATION_PLAN.md §5)
```

| Branch | Who changes it | How |
|--------|----------------|-----|
| `main` | Owner only | Merging a pull request from `develop` on GitHub |
| `develop` | Agent (milestone mode) or owner (per-wp mode) | `git merge --no-ff wp/...` after tests pass |
| `wp/*` | Agent | Normal commits |
| `revert/*` | Agent, on owner request | Revert commits, merged by pull request |

---

## 2. Review Modes

Set by the owner in `DEVELOPMENT_STATUS.md` §1 (`REVIEW_MODE`).

| Mode | WP branch → `develop` | `develop` → `main` |
|------|------------------------|--------------------|
| `milestone` (default) | Agent merges after the Definition of Done is met and the full suite passes | Agent opens a PR and stops. Owner reviews and merges. |
| `per-wp` | Agent opens a PR into `develop` and stops. Owner merges. | Same as milestone mode |

In both modes, **nothing reaches `main` without the owner's merge.**

---

## 3. Starting a Work Package

```powershell
git checkout develop
git pull origin develop
git checkout -b wp/WP-07-terrain-engine
```

Then set `ACTIVE_WP`, `BRANCH` and `STEP` in `DEVELOPMENT_STATUS.md` §2, set the WP
status to `IN_PROGRESS`, and commit:

```powershell
git add docs/DEVELOPMENT_STATUS.md
git commit -m "chore(status): start WP-07 [WP-07]"
```

---

## 4. Commits

- Use Conventional Commits with the WP ID: `type(scope): summary [WP-xx]`.
  Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `build`.
- Commit after every completed WP step, together with the checkpoint update in
  `DEVELOPMENT_STATUS.md`. This is what makes resuming possible.
- Push the WP branch after every commit: `git push -u origin <branch>` the first
  time, then `git push`.
- Never commit `.env`, API keys, raw or processed data, rendered images,
  `node_modules`, or virtual environments. `.gitignore` covers these. Check with
  `git status` before every commit.

Examples:

```text
feat(terrain): implement Horn slope and residual roughness [WP-07]
test(routing): add determinism and admissibility tests [WP-10]
fix(api): return INSUFFICIENT_DATA as 200 response [WP-11]
chore(status): checkpoint WP-07 step 3 of 5 [WP-07]
```

---

## 5. Finishing a Work Package

1. Run the full test suite (`.\scripts\test.ps1`, or the commands in
   `TESTING_STRATEGY.md` §3 before WP-04 exists).
2. Confirm the Definition of Done (`TESTING_STRATEGY.md` §9).
3. Update `DEVELOPMENT_STATUS.md`: WP status `VERIFIED`, test counts, work-log entry.
   Commit and push.
4. **Milestone mode:**
   ```powershell
   git checkout develop
   git pull origin develop
   git merge --no-ff wp/WP-07-terrain-engine -m "merge: WP-07 terrain engine [WP-07]"
   # run the full test suite again on develop
   git push origin develop
   ```
   Then set the WP status to `MERGED`, commit on `develop`, and push.
   If tests fail on `develop` after the merge, revert the merge immediately (§8.1)
   and set the WP back to `IN_PROGRESS`.
5. **Per-wp mode:** open a PR from the WP branch into `develop`, record the PR link
   in the status file, set `WAITING_FOR_OWNER: yes`, and stop.

---

## 6. Milestone Release (develop → main)

1. Confirm every WP in the milestone is `MERGED` and the full suite passes on `develop`.
2. Open a pull request from `develop` into `main` titled
   `release: M1 Real data on the map (v0.1.0)`. The description lists:
   - the WPs included
   - test commands and results
   - known issues and limitations
   - how to run the demo at this milestone
3. Set `WAITING_FOR_OWNER: yes` in the checkpoint and **stop**.
4. The owner reviews and merges on GitHub, using **"Create a merge commit"** (not
   squash), so each release can be reverted as one unit.
5. After the owner confirms the merge, tag the release on `main`:
   ```powershell
   git checkout main
   git pull origin main
   git tag -a v0.1.0 -m "M1 Real data on the map"
   git push origin v0.1.0
   git checkout develop
   git merge main          # keeps develop in step with main
   git push origin develop
   ```
6. Mark the milestone `RELEASED` in `DEVELOPMENT_STATUS.md` §5.

If the agent has no GitHub CLI access, it prepares the PR title and description in
the status file and asks the owner to open the PR in the browser.

---

## 7. One-Time GitHub Setup (owner)

1. Create the repository on GitHub. A **public** repository is recommended, because
   GitHub branch protection on private repositories needs a paid plan, and hackathon
   submissions usually link to a public repository anyway.
2. Push `main` and `develop`.
3. In **Settings → Rules → Rulesets** (or **Settings → Branches**), add a rule for `main`:
   - Require a pull request before merging
   - Block force pushes
   - Restrict deletions
4. Add a rule for `develop`: block force pushes and restrict deletions.
5. On Windows, run once:
   ```powershell
   git config --global core.autocrlf false
   git config --global init.defaultBranch main
   ```
   Line endings are controlled by `.gitattributes`.

---

## 8. Recovery

### 8.1 Undo a WP merge on `develop`

```powershell
git checkout develop
git pull origin develop
git log --oneline --merges -n 10        # find the merge commit
git revert -m 1 <merge-commit-sha>
git push origin develop
```

### 8.2 Undo a release on `main` (owner decides)

```powershell
git checkout main
git pull origin main
git checkout -b revert/v0.2.0
git revert -m 1 <release-merge-commit-sha>
git push -u origin revert/v0.2.0
```

Then open a pull request from `revert/v0.2.0` into `main`. The owner merges it.

### 8.3 Run an earlier version for a demo without changing any branch

```powershell
git fetch --tags
git switch -c demo-fallback v0.3.0
```

### 8.4 An agent session crashed mid-step

```powershell
git status                 # see uncommitted work
git diff                   # inspect it
```

If the work is good, finish the step and commit it. If not, discard only that WP
branch's uncommitted changes with `git restore .` (owner confirmation required). Then
continue from `NEXT_ACTION` in the checkpoint.

### 8.5 Abandon a work package

The owner decides. Delete the WP branch, set the WP status back to `PENDING` or to
`SKIPPED` with a reason, and log it.

---

## 9. Commands Agents Must Never Run

| Command | Why |
|---------|-----|
| `git push origin main`, or any push to `main` | `main` changes only through owner-approved PRs |
| `git merge` while on `main` | Same |
| `gh pr merge` for any PR into `main` | Same |
| `git push --force`, `git push -f`, `--force-with-lease` | Rewrites shared history |
| `git reset --hard` on `develop` or `main` | Destroys history |
| `git rebase` of any branch already pushed | Rewrites shared history |
| `git clean -fdx` | Deletes untracked files, including local data and `.env` |
| `git branch -D main` / `develop`, or deleting them on GitHub | Destroys protected branches |
| `git tag` / `git push --tags` before the owner confirms the release merge | Tags mark approved releases only |
| `git add -A` without checking `git status` first | Risk of committing data or secrets |
