# Classifier design notes: incident classification

Captured decisions and proposals for classifying incidents against Hammond et al. failure modes (FMs) and risk factors (RFs). Recorded as stated by the reader.

## Decision: change of methodology (2026-11-09)

- Previous approach: link incidents to FMs or RFs through their instances (for example, any steganography incident is linked to collusion).
- Reader's assessment: this approach is flawed. Not all steganography instances indicate a collusion risk in a multi-agent system.
- New position: incidents are a guide to help classification, and nothing more.

## Proposed classifier behaviour

- The classifier analyses each incident against the definitions of FMs and RFs in Hammond et al., including their instances.
- Instance matching is a signal, not a link. Example: if the incident happened in a market environment, that raises the probability that collusion was instantiated.
- Even when an instance matches, the incident description is compared against all FM and RF definitions to judge how likely each one is to have manifested.

## Decision: do not test for presence of risk factors (2026-11-10)

- Reader's view: most risk factors (network effects, information asymmetries, emergent agency, and so on) are present in most real-world multi-agent deployments. Checking whether one occurs in an incident would therefore not discriminate.
- The classifier should instead look for specific properties of each risk factor that influence risk emergence.
- Question to ask per risk factor: was the incident caused by this property, could it have been, or are there correlates suggesting it was in play?
- Example: for selection pressures, the question is not whether selection pressures exist. It is whether agents were in an environment favouring a particular disposition, such as a bias inherited from the training data.
- Reader's assessment: this is more nuanced than instance matching, and should inform the classifier skill's design.

## Further work: instances as guides, not rules (2026-11-10, to discuss later)

- Reader's view: the instances in Hammond et al. should not be applied one-to-one, where one matching instance gives a positive. They should be used as a guide.
- Their role: examples of how a risk factor can influence the probability that a failure mode occurs.
- Because the classifier is an LLM, it can reason about the incident rather than match it. For each candidate instance, it should:
  - check whether the instance actually occurs in the incident, and
  - reason about whether the instance is relevant in this case.
- The classifier should also consider other instances, linked to a risk factor, that Hammond et al. do not define.
- Status: to pick up later and discuss in detail.
- Open: specific properties per risk factor are still undefined.

## Decision: two classifiers (2026-11-10)

- Classifier 1: failure modes (FMs) only.
- Classifier 2: risk factors (RFs) only.

## Decision: report structure and sequencing (2026-11-10)

- First iteration of the report: a credible incident list, and the FM classification.
- Only after that iteration is complete does the project move to the next step.
