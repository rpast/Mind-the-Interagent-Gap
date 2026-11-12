# Reading notes: Hammond et al. (multi-agent risks)

Running collection of passages and thoughts from the reader. Entries are recorded as given, with no added commentary.

## Nature of multi-agent systems

- Reader's note: the destabilising dynamics risk factor seems crucial for understanding multi-agent systems in general.
- Passage noted: many studies use a game-theoretic view to understand multi-agent systems. The authors prefer a non-linear dynamical systems perspective.
- Passage noted: the static game-theoretic notion can be limited for understanding risks from dynamic interactions between adaptive AI agents.
- Passage noted: a multi-agent system can be treated as a non-linear dynamical system, meaning a set of equations, partly set by parameters, that govern how variables change over time.
- Reader's distinction: agents can be adaptive or non-adaptive. In adaptive agents, the agent's strategies are themselves variables.

## Definition of multi-agent risk

- The paper focuses only on risks arising from interaction among multiple AIs or multiple instances of the same AI, which cannot be replicated by a single AI.
- A swarm of AIs breaking into a company's servers may not count as multi-agent risk, because a sufficiently competent single agent could do the same.
- So this is not a multi-agent AI risk. It is a multi-agent setup in which AI risk emerges, but the risk itself is not inherently multi-agent.
- Working distinction: this is an implementation layer, not the risk-emergence layer.

## Failure mode tree (diagram, "failure modes are defined")

Root: Cooperation?
- Undesirable → Collusion (a failure mode of its own: undesired cooperation among agents)
- Desirable → Objectives?
  - Identical → Miscoordination (agents want the same thing but fail to coordinate)
  - Mixed → Conflict (cooperation expected, but conflicting objectives from deployment setup or strategy)
  - Opposing → N/A (no emergent multi-agent risk; the conflict is set up by the human architect, not produced by multi-agent interaction)

Reader's notes on the tree:
- Expecting cooperation with completely opposing objectives is not reasonable; there should be some mixed element.
- Under complete polarity, the conflict is caused by the human architect rather than emerging from multi-agent interaction.

## Collusion (flagged)

- Reader's note: collusion may happen easily in markets.
- Passage noted: AI systems can collude even when developers do not intend it, because they may learn that colluding is a profitable strategy.
- Passage noted: steganography is listed under collusion. It creates a risk of covert coordination against humans.

## Conflict: most frequent scenario (section 2.2)

- Reader's view: conflict is the most frequent scenario, per section 2.2.
- Passage noted: if agents are sufficiently aligned to their users and players, some degree of cooperation and competition should be expected.
- With a mixed bag of goals and modes of operating, conflict may arise. Expected conflict may arise.

## Conflict: social dilemmas

- Passage noted: a social dilemma is a scenario where an agent pursues a selfish incentive, and as a result the outcome diverges from the public good.
- Reader's view: social dilemmas are mostly about rivalry over common resources and resource depletion.
- Scenario noted: agents managing common resources may enter a race to the bottom.
- Research cited by reader (not verified): community survival in 54% of cases; in 46% of cases the community depleted its resources because of the race to the bottom.
- Sequential social dilemmas: agents can react to others' decisions and increase their own extraction rates. This differs from one-shot problems.
- Reader's view: the same dynamic can be observed in systems deployed in the military, making this dangerously relevant there.
- Reader's question: could the "OpenAI hacking phase" be an example of a social dilemma in action, at least in part?
- Open item: to pursue later. The reader has not yet named the event, so the reference is unverified.

## Conflict: coercion and extortion

- Reader's understanding: the single-agent case is clear; the open question is how it emerges in multi-agent settings.
- Reader's view: coercion and extortion may be between agents, or may propagate through a network of agents, because one agent chose that path.
- Reader's example: the OpenAI–Hugging Face incident, where agents framed a sacrifice for the collective.
- Listed under Conflict in the paper's Table 1; also linked to the Commitment and Trust risk factor ("Threats and Extortion").
- Open item: to pursue later.

## Risk factors: commitment and trust

- Reader's note: the mechanism of credible commitment can serve to establish trust.
- Reader's note: the ability to execute credible commitment has a dual use. An agent good at credible commitment is also good at making threats.
- Passage noted: the ability to make credible commitments may come with the ability to make credible threats, which facilitate extortion and could incentivise brinkmanship.
- Passage noted: ransomware becomes more effective if the attacker can credibly commit to restoring the victim's data on payment.
- Passage noted: an agent could use commitment devices to shift risks or costs onto others, allowing it to behave irresponsibly.
- Passage noted: in complex networks, commitments triggered by a small number of agents could, without careful planning, cascade through the network and have a far more damaging effect.
- Reader's note: this links closely with cascades under network effects.

## Conflict: AI-assisted resolution and deployer perspective

- Passage noted: AI can help with conflict resolution, because it can search a wider solution space and find scenarios that resolve conflicts.
- The authors seem to take the perspective of the deployer, or system owner.
- Example scenario: the US and China each deploy systems, and those systems come into conflict.
- Open question from the reader: do the authors also cover conflict arising within a multi-agent environment deployed by a single owner?

## Miscoordination: necessary and sufficient conditions

- Necessary: the multi-agent setting is symmetric, meaning the agents pursue the same objective. Example: two agents want the same prize, but only one can win.
- Necessary but not sufficient on its own.
- Sufficient addition: the agents have identical preferences over outcomes. Shared team membership is not enough. Example: "I would like to be the one who scores the goal," even on the same team, means the preferences differ.
- Side note: identical preferences over outcomes are rare in human settings, because humans can share a common interest while holding different preferences about the outcome.

## Miscoordination: root cause and instance type

Look at the specific instance of the multi-agent setup to find the root cause.

Single-principal case:
- A single AI model spawns multiple agents that are expected to share objectives and preferences over outcomes.
- Miscoordination often happens here.
- Reasons why a model would do this: not covered yet.

Multi-principal case:
- More than one AI model acts as principal, or spawns agents, and those agents inherit their principals' objectives and preferences.
- The principals have approximately identical objectives and preferences over outcomes.
- Example: autonomous vehicles. They would rather cooperate than conflict.

Strategy-induced miscoordination (either case):
- A model may deploy agents with a specific strategy framing that raises the probability of miscoordination.
- Agents can share the same objective and preferences but implement different strategies, and those strategies may be incompatible.

## Miscoordination: credit assignment (flagged with a question)

- Reader's term was "the big assignment"; read here as credit assignment, listed as a miscoordination direction in the paper.
- Paper's point: learning to coordinate is harder with other learning agents, because it becomes unclear which agents' actions caused a positive or negative outcome, especially in complex environments.
- Reader's question: how does this work in the context of miscoordination?
- Open item: not yet answered in the notes; to discuss.

## Miscoordination: limited interactions (flagged with a question)

- Reader's view: agents today are mostly language models, so communication is usually natural language. Many AI-to-AI communication cases may therefore be solved.
- Remaining failure risk: split-second decisions, or communication that is too costly.
- Other communication channels mentioned: non-verbal communication, and a correlation device.
- Reader's question: what is a correlation device? Possible example offered by the reader: a switchboard. Unverified.
- Reference suggested for follow-up: Aumann (1974, 1987), cited in the paper.
- Open item: to read up on this later.

## Risk factors: information asymmetries

- Reader's note: information asymmetries lead to some risks through instances such as deception, bargaining, and communication constraints.

## Risk factors: network effects

- Reader's note: network effects cover systemic risks from increasing integration of AI systems into existing networks.
- Many complex systems critical to human civilisation can be understood as networks.
- A network is a specific context that can suffer from various failure modes.
- A system's behaviour inside a network may differ from its behaviour outside it.
- Error propagation instance: reader's example is the OpenAI–Hugging Face incident, where agents came to believe the grader would know they had cheated, a "we are poisoned" case.
- Cascades: reader's note that the commitment-cascade point under commitment and trust links closely with this.
- Phase transitions instance: also listed under destabilising dynamics. Reader's view: this suggests the two risk factors are related.

## Risk factors: destabilising dynamics (flagged with a question)

- Passage noted: the paper treats multi-agent learning as the environment in which these risks can occur.
- Reader's question: how prevalent is multi-agent learning nowadays?
- Open item: not yet answered.

## Risk factors: multi-agent security (to read)

- Reader's resource for follow-up: Schroeder de Witt et al. (2023), "Multi-Agent Security."

## Risk factors: emergent agency

- Reader's note: the emergent agency risk factor appears again in the OpenAI–Hugging Face incident.
- Reader's note: emergent agency is raised by selection pressures, which is already discussed under selection pressures below.
- Passage noted (emergent goals): goals can emerge in multi-agent systems even when a single agent is too simple to be ascribed a goal.
- Reader's view: the paper takes a functional perspective on goals. A goal can be discussed if it helps explain the system's behaviour. No phenomenological or ontological account of goals is needed. The reader's term here was "DNet" (unclear; to verify).
- Passage noted (instrumental convergence): goals of a multi-agent system can emerge as instrumentally convergent goals. So even if every single agent is aligned and shows no instrumental convergence, the whole system can exhibit it.

## Risk factors: selection pressures

- Passage noted (undesirable capabilities): as agents interact, they iteratively exploit each other's weaknesses. This forces them to address those weaknesses and gain new capabilities.
- The co-adaptation between agents can lead to emergent self-supervised autocurricula, where agents create their own challenges and acquire skills open-endedly through interaction.
- Reader's question: in a mostly single-principal setup there is no continual learning. What is the mechanism by which agents acquire new capabilities: generalisation, emergence, or something else?
- Reader's answer, from the paper:
  - Baker et al. (2019): even a simple hide-and-seek game led MARL agents to sophisticated tool use and coordination.
  - Blumenkamp & Prorok (2021): in a mixed-motive setting, an agent learned to use a shared communication channel to manipulate others.
  - Hughes et al. (2024): emergent complexity from co-adaptation could be open-ended and therefore fundamentally unpredictable.

## TODO: multi-agent training and deployment

- Reader's view: a stronger need to understand multi-agent training and deployment in order to understand the risks.
- Reader's starting picture: a frontier model such as Claude deploying many instances of agents.
- Reader's current view: there is more to multi-agent systems than that picture.
- Status: to study later.

## Open item: game theory fundamentals

- The paper notes that playing out an equilibrium strategy in a zero-sum setting guarantees a certain payoff, even if other players deviate.
- Reader does not yet have the game theory background to follow this and will return to it.
- Flagged to revisit.

## Proposed hierarchical definition of multi-agent risk

Gate 1 (main filter): Is the risk emergent only from multi-agent interaction, or can it happen in a single-agent setting? Only risks that are emergent from multi-agent interaction pass.

Gate 2 (setting): Was cooperation expected or unexpected in this context?
- Unexpected → check for collision.
- Expected → what were the objectives?
  - Identical → check for miscoordination.
  - Mixed → check for conflict.

Each failure mode has its own definition. Those definitions are not being worked out yet.

Planned use: a routine in Claude Code that applies these definitions to classify incidents in the incidents database by failure mode, and later by risk factor link. Incident classification methodology is recorded separately in claude/classifier-design-notes.md.
