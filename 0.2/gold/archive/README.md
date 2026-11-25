# Archive: inputs to the ceiling calculation

`ceiling_input_*.csv` hold, row by row, what the index's earlier hand-curation asserted about
each gold row, paired with the verdict the independent review reached.

They exist for one reason: the accuracy ceiling in `0.2/docs/gold_set.md` is computed from
those assertions, and a number nobody can recompute is not a measurement. They are kept here
rather than in the live gold set so that the earlier labels do not sit next to the verdicts,
where a later reviewer could see them and lose the independence the review depends on.

**These are historical inputs, not labels.** Nothing in the pipeline reads them. No label here
may put an incident in scope, now or ever — `definitions.md` requires a human verdict against
the primary source for that, and the review already supplied one for every row.
