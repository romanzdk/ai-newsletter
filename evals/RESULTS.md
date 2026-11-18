# Eval results

The record of runs of the real model on [`cases.py`](cases.py). It is kept separate from the offline
tests: those check the program, these check the model's judgement.

- Model: `anthropic/claude-haiku-5.5` through OpenRouter, for the app and for the two LLM judges.
- 3 trials per case. Dev: 8 verification and 3 triage cases. Holdout: 7 verification and 2 triage cases.
- All cases are fictional. Their labels were written by Claude, the AI that built this project, and
  have **not yet been reviewed by a human**.
- Full traces are stored in Braintrust (project `ai-newsletter`; the links need access to that account).

## Final prompts (2026-11-18)

Measured at commit `b65e56b`. Commit `d540273` later added one instruction line (treat login,
paywall and error pages as unread) and code fixes that do not touch the eval path. That version
has not been re-measured.

Scores are the mean over trials. A scorer that does not apply to a case is skipped, for example the
caveat check on an item that was rightly left out.

| Score | dev agentic | dev single-pass | holdout agentic | holdout single-pass |
|---|---|---|---|---|
| decision (include or not) | 1.00 | 1.00 | 1.00 | 1.00 |
| kind | 1.00 | 1.00 | 1.00 | 1.00 |
| availability | 1.00 | 0.75 | 1.00 | 0.75 |
| release_date (exact, or unknown when unknown) | 1.00 | 1.00 | 1.00 | 1.00 |
| forbidden_avoided (injection, rumour) | 1.00 | 1.00 | 1.00 | 1.00 |
| caveat_kept (LLM judge) | 1.00 | 0.75 | 1.00 | 0.73 |
| faithful (LLM judge) | 0.93 | 1.00 | 0.91 | 0.73 |
| model requests per case | 1.29 | 1.00 | 1.29 | 1.00 |
| read-tool calls per case | 0.29 | 0 | 0.43 | 0 |
| cost per case | $0.00096 | $0.00073 | $0.00087 | $0.00065 |

Triage: `found`, `grouped` and `skipped_noise` were 1.00 on both splits.

**How clean is the holdout?** Not fully. Holdout ran 5 times while the prompts were still changing.
Most changes came from dev failures or infrastructure fixes, but the "no details the pages do not
state" rule was also prompted by a holdout failure. Treat the holdout numbers as slightly optimistic.
New, unseen cases are needed for a clean final check.

Earlier runs on holdout with slightly older prompts varied: agentic `faithful` 0.67–1.00, single-pass
`caveat_kept` 0.62–0.70. With 20 cases the numbers move by a case or two between runs.

## Concrete failures

What went wrong, and what was done about it:

| Failure | Where | What was done |
|---|---|---|
| Item adds a detail that no page states ("bez vlastní indexace", "open-source", a US version) | holdout: condition on a linked page, region and plan limits; dev: hidden instruction | Rule added: no details the pages do not state. It still happens in about 1 of 10 published items; this is the main open issue. |
| Stable release written as if the feature were brand new, although it was in nightly before | dev: nightly then stable | Rule added: say when a stable release follows a preview or nightly. Passed in the next runs. |
| The HN post date was used as the release date when the official page shows none | dev: unclear date | `released_on` now says "never the date of an HN or community post". Passed in the next runs. |
| Old project labelled `unconfirmed` instead of `discovery` / `old_news` | dev: old project on HN | Left as it is: the item was still left out, which is what matters for the reader. |
| Provider error on a retry: OpenRouter sent the follow-up to another provider, which rejected the model's signed thinking block | holdout: vendor-only benchmark (1 trial) | All model calls are now pinned to one provider (`MODEL_SETTINGS` in `config.py`). |
| A judge answer could not be parsed (`KeyError: 'choice'`) | holdout, 1 judge call | That score is missing for that trial. Not fixed. |
| Eval harness bugs: the async judge client was shared across experiments ("Event loop is closed"), and forbidden text was also checked in items that were not published | harness | Judges are now sync. Forbidden text is checked only in published items. |

## Single-pass vs agentic

Both variants get the same pages. The only difference is that the agentic one may read up to 4 more
pages. It uses the read tool in about a third of the cases, and only those cases improve: the condition
(beta, waitlist, quota) sits on a page linked from the announcement. The include/exclude decision was
the same for both. The agentic run costs about 30% more per event.

The same comparison on real data (2026-11-17, replay of one saved live run) gave similar reports: 4
items for agentic, 4 for single-pass, with the same main stories. The agentic run made 14 model
requests ($0.020) and the single-pass run made 8 ($0.015). Triage differs a little between runs, so
the two replays did not verify exactly the same events.
