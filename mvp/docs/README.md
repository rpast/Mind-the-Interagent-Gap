# Docs: reading order

Start at the top. The first two are enough to work with; the rest are reference.

| # | file | read it for | time |
|---|---|---|---|
| 1 | [how_it_works.md](how_it_works.md) | the whole pipeline, one record from fetch to index, the gates, how to run it | 15 min |
| 2 | [glossary.md](glossary.md) | every project term in a sentence or two | look up as needed |
| 3 | [definitions.md](definitions.md) | what counts as an agent and as a multi-agent incident; the two gates, the attack presumption, failure modes, evidence types, label provenance | 20 min |
| 4 | [context_layer.md](context_layer.md) | read before you judge: read depths, `not_stated` against `unread`, readiness, the flag rule | 10 min |
| 5 | [classifiers.md](classifiers.md) | why one extraction call plus rules plus an instance call; the proposal and verdict files | 15 min |
| 6 | [input_layer.md](input_layer.md) | the record store, the record key, the update routine, prefilter, manual incidents, dossier format, `check` | 15 min |
| 7 | [aiid_background.md](aiid_background.md) | what AIID is, its namespaces, why the prefilter queues every recent record | 10 min |
| 8 | [gold_set.md](gold_set.md) | how the evaluation set was built and how the ceiling is computed | 10 min |
| 9 | [gate1_accuracy.md](gate1_accuracy.md) | the measured figures for the classifier and the older predictors | 5 min |

Outside this folder:

- `mvp/pipeline/derive.py`: the labelling rules. Where any doc disagrees with it, it wins.
- `mvp/prompts/`: the prompts the model follows (`enrich_context.v2`, `extract_gate.v3`,
  `assign_instances.v2`).
- `mvp/skills/classify-incidents/SKILL.md`: what `/classify-incidents` does, step by step.
- `mvp/review/README.md`: the two review sheets a person fills in, and their logs.
- `mvp/testenv/README.md`: the test run and its made-up cases.
- `OPEN.md` at the repo root: open questions and recorded decisions, by number.
- `docs/project_outline.md`: the project's goal and its three layers.
