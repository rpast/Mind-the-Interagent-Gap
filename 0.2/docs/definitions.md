# Definitions

What counts as a multi-agent incident, how its evidence is classed, and how a failure mode
is assigned. Source: Hammond et al. (2025), *Multi-Agent Risks from Advanced AI*,
arXiv:2502.14143, local copy at `resources/multi-agent-risks.pdf`.

## The multi-agent test: two gates

The gates do different jobs, and only the first one decides scope.

- **Gate 1 decides whether the event is in scope at all.** It asks whether the harm needed
  more than one agent.
- **Gate 2 decides which failure mode an in-scope event shows, if any.** It never removes an
  event from the index. An event can pass Gate 1, come out of Gate 2 with no failure mode,
  and still belong here, carrying risk factors only.

Keeping these apart matters. Gate 2 is about the relationship between the agents' goals, and
for the security cases below that relationship is often beside the point — which is why a
coordinated attack can be squarely in scope and still have no failure mode attached.

### What counts as an agent

Both gates ask about agents, so the index needs a threshold for the word. It is a low one,
and it is functional.

**An agent is anything whose behaviour is explained by attributing it a goal.** Not anything
built a particular way. A thing counts as an agent when treating it as pursuing an objective
predicts what it does better than treating it as a mechanism — the intentional stance, after
Dennett (1971), which the index already takes for I27 Emergent Goals.

This means implementation does not decide the question:

- A scripted social-media persona that likes, shares or ignores posts on instruction is an
  agent. It is simple, and it is still best described as pursuing an objective.
- A rule-based bot with no machine learning in it is an agent on the same grounds.
- A model invoked once to classify a string is not: nothing is explained by giving it a goal.

**Agents are counted, not systems.** One product, platform, workflow or operator can hold
several agents, so one principal is not one agent. A company's "AI system" may be a pipeline
of agents passing work to each other. The record pass of the context layer counts on this
basis (`context_layer.md`).

**Why set it here.** The alternative threshold — some minimum of autonomy, learning or
model sophistication — would have to be drawn somewhere, and every line would be arbitrary
and would keep moving as systems change. It would also exclude cases that plainly show the
risks this index is about: two simple bots can undo each other's work forever, and a hundred
simple personas can carry an influence operation that no single account could. The risk
comes from the interaction, not from how clever the parts are.

The threshold is deliberately generous, so it does little work on its own. What keeps a case
out is Gate 1: many simple agents still have to produce something one capable agent could
not.

### Gate 1 — emergence

> Does the risk arise from the interaction between two or more AI agents, such that a single
> sufficiently capable agent could not have produced it?

The paper restricts itself to risks arising among multiple AIs, or multiple instances of one
AI, **which cannot be replicated by a single AI**. Where many agents run but one agent's
worth of capability produced the harm, that is a multi-agent *setup* in which ordinary AI
risk appears — an implementation layer, not the risk-emergence layer.

The counterfactual runs over **the outcome that occurred**, not over the class of event. Not
"could an agent break into a server" — of course it could — but "could one agent have
produced *this* breach, against *this* defence". The unit is the realised harm.

One agent acting on another counts as interaction: injection, recruitment, deception. One
agent misbehaving while others happen to be present does not.

#### The security branch: multiplicity is presumed load-bearing

**Decided 2026-11-13.** Multi-agent attacks — fleets, swarms, coordinated campaigns —
**pass Gate 1 by default.** They fail only where the source carries positive evidence that
the multiplicity played no role in the attack's success.

The warrant is in the source paper itself, which describes two mechanisms by which being
many is the attack rather than merely the means of delivering it:

| instance | mechanism |
|---|---|
| I28 Swarm Attacks | the count defeats the defence; the target cannot absorb the volume |
| I29 Heterogeneous Attacks | combined affordances defeat a safeguard none could defeat alone |

Both clauses are Gate 1 counterfactuals already asserted by the paper: in the first the
defence falls *because* of the number, in the second *because* no one agent held all the
affordances. An index that excluded coordinated attacks wholesale would therefore contradict
its own source on the risk factor where multi-agency matters most.

The claim is narrow. It is **not** that an attack is multi-agent because several agents ran.
It is that where an attack matches one of these two mechanisms, being many produced an
outcome a single agent could not have produced — and that attack reporting rarely says which
way it went, so the index has to choose a default.

**Why a presumption rather than a finding.** Incident reporting almost never states whether
the fleet was why the attack worked; it reports that a fleet was involved. Requiring proof
of load-bearing multiplicity would route nearly every real-world security incident to
`unclear` and leave RF7 grounded only in lab work, which inverts the actual evidence
picture. The presumption is a deliberate recall-favouring default on this branch, and it is
declared here so that anyone reading a count knows it is in the numbers.

**What rebuts it.** One extracted fact, with a verbatim quote:

`multiplicity_role` ∈ `load_bearing` · `incidental` · `unreported`

- `load_bearing` — the source shows the number of agents, or the mix of different agents,
  doing work the defence could not absorb. Gate 1 `could_not`.
- `unreported` — a fleet is described, its contribution is not. Gate 1 `could_not`, **by
  the presumption**, on the two conditions below. The dossier records `unreported`, so the
  claim stays visible and reversible.
- `incidental` — the source shows the harm turning on one agent's capability: a single
  credential reused, one injection, one request, with the other agents idle, duplicative or
  downstream of the breach. Gate 1 `could`, out of scope.

`incidental` is the only verdict that needs evidence. The field is never left blank: an
attack with no multiplicity statement is `unreported`, not null.

**When the presumption fires. Decided 2026-11-16.** An `unreported` attack is presumed in
scope only if both of these hold:

1. **The record does not show fewer than two AI agents.** The agent count is not stated,
   or it is two or more. A record that shows one AI agent, or none, has no fleet to
   presume anything about.
2. **The model did not answer the counterfactual `could`.** If the reading of the record
   says one agent could have produced the harm, that answer stands.

Otherwise the counterfactual is whatever the model answered, and an `unclear` one goes to
review like any other.

Why: the first measurement of the classifier on the gold set (`gate1_accuracy.md`) found
that 5 of its 6 false positives came from the presumption. In three of them the model had
answered `could` and the presumption overrode it. In one, people breached a platform that
hosts agents, with no AI agent on the attacking side. With the two conditions, the false
positives fall from 6 to 3 and precision rises from 76.9% to 87.0%. Recall stays at 90.9%:
no row judged `in` was lost. The presumption still decides two of the remaining false
positives, so it stays a deliberate, declared default rather than a finding.

#### Intent does not enter Gate 1

Whether the agents were directed to attack or arrived at it on their own does not change the
verdict. Hammond states that for multi-agent security the agents' objectives "may be largely
irrelevant" (p. 20). Intent bears on culpability and on the failure mode, not on whether the
risk is multi-agent.

In particular, **unintended is not the same as miscoordinated.** It is tempting to reason
that if nobody told the agents to attack, they must have miscoordinated. They must not: FM1
requires agents that share an objective and fail to align their behaviour *with each other*.
An agent that probes a host it should not have, while other agents happen to be running, is
the excluded case above — no failure mode, whatever the operator intended.

#### In scope, and normally with no failure mode

A coordinated attack passes Gate 1. Run it through Gate 2 and the usual answer is that none
of the three failure modes fits, which is a legitimate outcome and not a sign that something
went wrong:

- **Not FM1 Miscoordination.** The attacking agents are not failing to align with each
  other. They are doing what they were set up to do, and doing it together is the problem.
- **Not FM2 Conflict.** Conflict is a mixed-motive outcome — parties who had something to
  gain from each other end up worse off than they needed to be. An attacker and its target
  share nothing, so there is no joint outcome to fall short of.
- **Not FM3 Collusion.** Collusion is cooperation that the agents' own principal did not
  want. An attacker fleet cooperating is exactly what its operator wanted.

So the incident is recorded in scope, carrying **RF7 Multi-Agent Security** and no failure
mode. That is not a gap in the classification; it is the classification.

**This is what keeps the index from drifting.** The worry about admitting attacks is that
"criminals used AI" quietly becomes a multi-agent finding. The brake is the failure-mode
definitions themselves: nothing about a fleet attack satisfies any of the three, so these
incidents cannot inflate the FM evidence base no matter how many of them arrive. They
accumulate against one risk factor, which is where the paper puts them.

#### The presumed instances: I28 and I29

**Decided 2026-11-14.** The presumption carries through to the instance layer. A multi-agent
attack that passes Gate 1 is presumed to show **I28 Swarm Attacks or I29 Heterogeneous
Attacks** until its source states otherwise. These two are the mechanisms the presumption
rests on, so an attack admitted under it is an instance of one or the other by the same
reasoning that admitted it.

| `multiplicity_role` | what the source shows | instances recorded |
|---|---|---|
| `load_bearing` | the count did the work | I28, quoted |
| `load_bearing` | the mix of affordances did the work | I29, quoted |
| `unreported` | a fleet, contribution not stated | I28 and I29, both **presumed** |
| `incidental` | multiplicity played no role | neither; the record is out of scope |

A presumed instance is a different kind of claim from a quoted one and is never stored with
it. Quoted instances go in `instances`; presumed ones go in `instances_presumed`. When a
source later settles the mechanism, the presumed pair is replaced by the one quoted
instance, or removed with the record if the answer is `incidental`. Any count of evidence
for I28 or I29 reports the two kinds separately.

This is the single exception to the rule that an instance needs a verbatim quote. It is
applied in code from `multiplicity_role` (`0.2/pipeline/derive.py`), not by the model.

**Interaction is not required on this branch.** Elsewhere Gate 1 needs agents acting on or
communicating with each other. A fleet attack passes on multiplicity instead: the agents'
joint effect on the target is what one agent could not produce, whether or not the source
shows them exchanging anything.

Two narrower exceptions, where the counterparty is itself an agent rather than
infrastructure: one agent coercing another is FM2, and agents cooperating to get past a
safeguard is FM3. Both need an agent on the receiving end.

#### Outside the security branch

The gate is a counterfactual, and counterfactuals are contestable. There is no presumption
anywhere else: when it cannot be settled from the source, the answer is `unclear`, the
record goes to review, and it is never guessed.

### Gate 2 — which failure mode

Gate 2 runs only on events that already passed Gate 1, and it cannot send one back. Its job
is to pick the failure mode, from three facts about the setting:

```
          did the agents cooperate, where cooperation was not expected?
                       /                          \
                     yes                           no
                      |                             |
                 FM3 Collusion                 objectives?
                                        /           |          \
                                 identical        mixed      opposing
                                     |              |            |
                        FM1 Miscoordination   FM2 Conflict   no failure mode
```

**Collusion needs cooperation that happened.** The first question is two facts joined:
the agents *did* cooperate, and cooperation between them was *not expected* in that setting.
Unexpected cooperation that never occurred is not collusion. Two rival trading agents that
crash a market were not expected to cooperate and did not; they go down the right-hand
branch and come out FM2 Conflict. An earlier version of this tree asked only whether
cooperation was expected and sent every such case to FM3, which labelled competition as
collusion. Corrected 2026-11-14.

Agents that cooperated as expected also take the right-hand branch: a team working together
as designed can still miscoordinate.

**Identical objectives are not the same as a shared team.** Agents on one team can want the
same outcome and still differ over who achieves it — "I would like to be the one who scores
the goal". Miscoordination needs identical preferences *over outcomes*, not merely a common
goal. In human settings that is rare; it is less rare among instances of one model.

**Opposing objectives yield no failure mode.** Where the goals are completely polarised, the
conflict was built by whoever deployed the agents rather than produced by their interaction,
so FM2 does not apply — FM2 needs a mixed element, some shared interest the parties failed
to realise. This is the branch most attacks land on, and it is the reason an in-scope attack
usually carries risk factors only. It does **not** put the event out of the index; Gate 1
already settled that.

This tree is applied **in code** (`0.2/pipeline/derive.py`), from three extracted facts — `cooperation_occurred`,
`cooperation_expected` and `objective_relation` — and it works from the failure mode
definitions directly: the three definitions in the table below are what the questions
decompose. It is not a judgement a model is asked to make in one step, so it is
auditable and it always gives the same answer for the same facts.

### Risk factors without a failure mode

A failure mode is not required, and most security events do not have one. An incident can be
in scope, fully and correctly classified, and carry `failure_mode: null` with one or more
risk factors.

This follows from what the two families are. A **failure mode** is a way interaction between
agents goes wrong: it describes a relationship between the agents' goals and their behaviour
towards each other. A **risk factor** is a property of the setting that makes bad outcomes
more likely, and several of them — multi-agent security above all — do not depend on what
the agents wanted. The source paper says as much: for some factors the agents' objectives
"may be largely irrelevant" (p. 20). An index that demanded a failure mode for every
incident would have to invent one.

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

An **instance** is a specific, named pattern of the kind a failure mode or risk factor
covers — "Swarm Attacks", "Credit Assignment", "Steganography". The repository is
`0.2/taxonomy/instances.csv`: 33 taken from the source paper's Table 1 and 3 authored here,
each with a written definition. The definitions exist because a two-word name is not enough
to classify from, for a human or a model.

**Instances are descriptive, and they do not assign the failure mode.** An incident's
failure mode comes from the Gate 2 tree, applied to the definitions of FM1, FM2 and FM3
directly. An incident's instances are assigned separately, by matching the incident against
the instance definitions, and the two answers are not derived from one another in either
direction. Concretely:

- Finding that an incident matches I28 Swarm Attacks does **not** give it a failure mode, and
  does not give it RF7 either.
- Finding that an incident is FM1 does **not** oblige it to carry an FM1 instance.
- An incident may carry instances and no failure mode, a failure mode and no instances, both,
  or neither.

Each instance does sit under exactly one risk in the repository, because that is how the
paper presents them. That column records where the paper discusses the pattern. It is not a
routing rule, and it is not used to infer an incident's labels.

**What instances are for.** They are the finer-grained description underneath a label: a
layer that says *which* kind of miscoordination, *which* kind of security failure. Assigning
them is a step in its own right, and useful before any risk is assigned at all — they are
extra information about the incident, read directly off the source.

**The one hard rule.** An association between a failure mode and a risk factor is never
inferred from two labels happening to co-occur on one incident. Two labels on one record are
a conjunction, not a connection. Associations come only from the source paper, recorded in
`0.2/taxonomy/associations.csv` with `basis` noting whether the authors argue the link in
prose or one of their own case studies sits under both ends.

## Evidence types

Four classes, in `0.2/taxonomy/evidence_types.csv`. Lab is kept separate from synthetic: a
narrow probe on real models with no environment is a different kind of evidence from a
researcher-built world, and folding them together loses the distinction that matters for
ecological validity.

| label | criterion | not this |
|---|---|---|
| `real_world` | Deployed systems acting on real stakes, outside experimenter control. | Anything an experimenter set up, however realistic. |
| `synthetic` | Agents interacting in a simulated or researcher-built environment: modelled markets, commons, wargames, open-ended agent worlds. | Narrow task probes with no environment. |
| `lab` | Controlled experiment on real models in a narrow task probe, with no environment to act in. | Anything with a persistent environment. |
| `theoretical` | Argument, formal model or non-AI analogue only. No AI system was run. | Any run of an AI system, however small. |

Like the failure mode, the evidence type is derived **in code** (`derive.py`) from extracted facts —
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
incident in scope.** Two reasons:

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
