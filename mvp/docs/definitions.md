# Definitions

What counts as a multi-agent incident, how its evidence is classed, and how a failure mode
is assigned. Source: Hammond et al. (2025), *Multi-Agent Risks from Advanced AI*,
arXiv:2502.14143, local copy at `resources/multi-agent-risks.pdf`.

## The multi-agent test: two gates

An event is in scope only if it passes **both** gates, in order.

### Gate 1 — emergence

> Does the risk arise from the interaction between two or more AI agents, such that a single
> sufficiently capable agent could not have produced it?

The paper restricts itself to risks arising among multiple AIs, or multiple instances of one
AI, **which cannot be replicated by a single AI**. A swarm of agents breaking into a
company's servers does not pass: a sufficiently competent single agent could do the same.
That is a multi-agent *setup* in which ordinary AI risk appears — an implementation layer,
not the risk-emergence layer.

One agent acting on another counts as interaction: injection, recruitment, deception. One
agent misbehaving while others happen to be present does not.

This gate is a counterfactual, and counterfactuals are contestable. When it cannot be
settled from the source, the answer is `unclear` and the record goes to review. It is never
guessed.

### Gate 2 — the setting

Having passed Gate 1, the failure mode follows from two facts about the setting:

```
                     was cooperation expected?
                       /                  \
                 no (unexpected)        yes (expected)
                      |                      |
                 FM3 Collusion          objectives?
                                   /         |         \
                            identical      mixed     opposing
                                |            |           |
                   FM1 Miscoordination  FM2 Conflict   out of scope
```

**Identical objectives are not the same as a shared team.** Agents on one team can want the
same outcome and still differ over who achieves it — "I would like to be the one who scores
the goal". Miscoordination needs identical preferences *over outcomes*, not merely a common
goal. In human settings that is rare; it is less rare among instances of one model.

**Opposing objectives are out of scope.** Where the objectives are completely polarised, the
conflict was built by whoever deployed the agents, not produced by their interaction.
Expecting cooperation under complete polarity is not reasonable, so there must be a mixed
element for FM2 to apply.

This tree is applied **in code**, from two extracted facts. It is not a judgement a model is
asked to make in one step, so it is auditable and it always gives the same answer for the
same facts.

### Risk factors without a failure mode

A failure mode is not required. Most security events carry risk factors only — that was the
PoC's finding over its own 27 incidents, where 18 of 27 have no failure mode. An incident
can be in scope, correctly classified, and have `failure_mode: null`.

## Failure modes

| id | name | definition |
|---|---|---|
| FM1 | Miscoordination | Agents share a clear common objective but fail to align behaviour to achieve it. |
| FM2 | Conflict | Mixed-motive interaction ends off the Pareto frontier: commons depletion, warfare, races to the bottom. |
| FM3 | Collusion | Undesired, often covert, cooperation between AI systems at the expense of third parties. |

## Risk factors

RF1 Information Asymmetries · RF2 Network Effects · RF3 Selection Pressures ·
RF4 Destabilising Dynamics · RF5 Commitment and Trust · RF6 Emergent Agency ·
RF7 Multi-Agent Security.

The authors state the categories are "neither exhaustive nor mutually exclusive", and that
for some factors — multi-agent security especially — the agents' objectives "may be largely
irrelevant" (p. 20). Nine of the twenty-one possible FM–RF pairs are never asserted, and a
missing pair carries no information.

## Instances

Evidence reaches a risk **only through an instance**, and each instance belongs to exactly
one risk. Two tags on one incident are a conjunction, never a connection: an FM–RF
association is never inferred from our own tags co-occurring. Associations come only from
Hammond et al., with `basis` recording whether the authors argue the link in prose or one of
their own case studies sits under both ends.

The instance repository is `mvp/taxonomy/instances.csv`: 33 instances from the paper's
Table 1 and 3 authored by this project, each with a written definition. The definitions
exist because a classifier cannot assign an instance from a two-word name like "Credit
Assignment".

## Evidence types

Four classes, in `mvp/taxonomy/evidence_types.csv`. Lab is kept separate from synthetic: a
narrow probe on real models with no environment is a different kind of evidence from a
researcher-built world, and folding them together loses the distinction that matters for
ecological validity.

| label | criterion | not this |
|---|---|---|
| `real_world` | Deployed systems acting on real stakes, outside experimenter control. | Anything an experimenter set up, however realistic. |
| `synthetic` | Agents interacting in a simulated or researcher-built environment: modelled markets, commons, wargames, open-ended agent worlds. | Narrow task probes with no environment. |
| `lab` | Controlled experiment on real models in a narrow task probe, with no environment to act in. | Anything with a persistent environment. |
| `theoretical` | Argument, formal model or non-AI analogue only. No AI system was run. | Any run of an AI system, however small. |

Like the failure mode, the evidence type is derived **in code** from extracted facts —
the setting, the stakes, and who controlled the environment — not asked for directly.

## Label provenance

Three sources of a label, never merged:

- `ours` — a human applied the two gates to the primary source. **Only this puts an incident
  in scope.**
- `external:<source_id>` — someone else's rater said so. Examples: AIID's CSETv1
  `Multiple AI Interaction` attribute; the MIT Navigator's `behaviour` facet; the Agent
  Incident Registry's `multi_agent_system` surface.
- `classifier:<prompt>@<version>` — our own classifier proposed it.

**An external or machine label may mark a candidate. It may never, by itself, put an
incident in scope.** Two reasons, both measured rather than assumed:

1. External raters miss things. The Navigator's rater tagged only 6 of the 9 of our
   incidents that are in AIID — a 33% false-negative rate.
2. External raters mean something else. AIID's CSETv1 `Multiple AI Interaction` is the only
   purpose-built multi-agent label in the corpus, and its five positives include
   "Sexist and Racist Google Adsense Advertisements" and "Amazon's Robotic Fulfillment
   Centers Have Higher Serious Injury Rates". Those involve more than one system, but
   neither obviously passes Gate 1. The label marks a candidate; it is not a verdict.

Every inherited label is kept in `external_labels` with its source, namespace and fetch
date. Where raters disagree — AIID's three annotator namespaces do — every verdict is
kept separately rather than collapsed into one.
