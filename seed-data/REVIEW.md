# Human review log (PRD Section 5.3, step 5)

The Bug Injector Agent is **not trusted unsupervised** on the demo path. Every
injected bug is reviewed by hand before it enters the seed set, even when the
automated check in `author_challenges.py` has already confirmed that it makes a
hidden test fail.

## What a reviewer checks

1. **Realism** — is this a mistake an engineer could actually make? A bug that
   reads as deliberate sabotage teaches nothing.
2. **Solvability** — can the bug be found from the function alone, in the time
   limit, without knowing the upstream repo?
3. **Single unambiguous fix** — is there exactly one right answer, so the
   Evaluator Agent's "minimal and targeted" judgement is meaningful?
4. **Not trivially obvious** — a bug that a linter or a glance would catch is
   discarded even if it fails a test.
5. **Formatting untouched** — the diff should be the bug and nothing else.

## Current seed set

| Challenge | Repo | Function | Category | Origin | Reviewed |
|---|---|---|---|---|---|
| challenge-01 | python/cpython | `bisect_left` | incorrect-boundary | hand-authored | yes |
| challenge-02 | python-humanize/humanize | `ordinal` | wrong-condition | hand-authored | yes |
| challenge-03 | python-humanize/humanize | `naturalsize` | off-by-one | hand-authored | yes |
| challenge-04 | django/django | `slugify` | wrong-operator | hand-authored | yes |
| challenge-05 | pallets/werkzeug | `secure_filename` | swapped-variable | hand-authored | yes |

**Origin = hand-authored** means the bug was written by the team to the same
specification the Bug Injector Agent's prompt gives, because the agent needs
Bedrock credentials that were not available when the seed set was first built.
To regenerate every bug through the agent and re-review:

```bash
python seed-data/author_challenges.py --use-agent   # rewrites buggy.py + ground_truth.json
git diff seed-data/challenges                       # review every change by hand
python scripts/validate_golden_set.py               # re-run the golden set
```

Update the Origin column to `bug-injector-agent` once that has been done and
re-reviewed. Any bug that fails a check above is discarded and regenerated with
a different `bug_category` in `meta.json`.

## Source attribution

Each `meta.json` records the upstream repository, its licence and the file the
function comes from. The functions are faithful reimplementations of those
public APIs, trimmed of repo-internal dependencies so they can run standalone in
the sandbox — they are not verbatim copies of the upstream files.
