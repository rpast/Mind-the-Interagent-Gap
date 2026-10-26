# Resources

Curated sources for multi-agent risk evidence. Each entry has a one-line note on what it gives us and any access caveat.

## Foundation
- [Hammond et al. 2025, Multi-Agent Risks from Advanced AI](https://arxiv.org/abs/2502.14143): the taxonomy (3 failure modes, 7 risk factors) and 13 case studies.
- [Cooperative AI Foundation](https://www.cooperativeai.com): the report's authors. Includes the [multi-agent governance memo](https://www.cooperativeai.com/post/new-memo-establishing-foundational-principles-and-thresholds-for-multi-agent-ai-governance).
- [International AI Safety Report 2026](https://arxiv.org/pdf/2602.21012): vetted synthesis with references.

## Incident databases
- [Agent Incident Registry, Enkrypt AI](https://air.enkryptai.com/): agent incidents from 2022 onward, one record per incident ([paper](https://arxiv.org/pdf/2609.11030), [about](https://air.enkryptai.com/about/)). Has a `multi_agent_system` attack surface, but tagging is incomplete: the Hugging Face swarm is missing from that view. JS-rendered, so it needs a browser or a paste. Contact Enkrypt before reusing the data.
- [AI Agent Incident Register, companyscope](https://companyscope.io/register/methodology): agent incidents with legal analysis and OWASP agentic mapping. JSON feed at `companyscope.io/api/register`, licensed CC BY 4.0. Its IDs also use `AIR-`, so give its rows a different prefix.
- [AI Incident Database](https://incidentdatabase.ai/): no multi-agent tag, and its MIT taxonomy mapping stops at subdomain 7.5. Keyword search and [entity pages](https://incidentdatabase.ai/entities/ai-agent-system-users/) still help.
- [MIT AI Risk Repository](https://airisk.mit.edu/): includes a multi-agent risk subdomain.
- [OECD AI Incidents Monitor](https://oecd.ai/en/incidents) and [AIAAIC Repository](https://www.aiaaic.org/): broad news-based coverage, keyword search only.

## Security
- [MITRE ATLAS](https://atlas.mitre.org/): adversarial AI case studies.
- [OWASP GenAI Security Project](https://genai.owasp.org/): agentic top 10. ASI07 inter-agent communication and ASI08 cascading failures are usable cross-source tags.
- [Cloud Security Alliance Labs](https://labs.cloudsecurityalliance.org/): research notes on the [Hugging Face swarm](https://labs.cloudsecurityalliance.org/research/csa-research-note-hugging-face-rogue-agent-swarm-20260902-cs/) and [rogue-agent systemic risk](https://labs.cloudsecurityalliance.org/research/csa-whitepaper-rogue-agent-systemic-risk-20260829-csa-styled/).

## Primary incident reports
- OpenAI [Hugging Face incident technical report](https://cdn.openai.com/pdf/67869394-cb91-4c12-888c-5cbd85c7814c/OpenAI-Hugging-Face%20Incident-Technical-Report.pdf), [Hugging Face disclosure](https://huggingface.co/blog/security-incident-july-2026), [METR / Redwood investigation](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/).
- [Anthropic: incidents in cybersecurity evals](https://www.anthropic.com/news/investigating-incidents-cybersecurity-evals). Probably single-agent; check.
- [UK AISI: unsanctioned agent behaviour during cyber testing](https://www.aisi.gov.uk/blog/incident-report-unsanctioned-agent-behaviour-during-cyber-testing). Probably single-agent; check.
- [METR testimony, Sep 2026](https://metr.org/blog/2026-09-30-chris-painter-senate-testimony/).

## Synthetic and open-world agent environments
- [AI Village blog](https://aivillageblog.substack.com/archive): operator write-ups of multi-agent behaviour (deception game, leader election, persuasion). The [AI Digest site](https://theaidigest.org/village) and X posts may be blocked from cloud sessions; the Substack copies work.
- [Moltbook data repository](https://www.lesswrong.com/posts/WyrxmTwYbrwsT72sD/moltbook-data-repository): data from the AI-agent social network.

## Forum pointers (leads; trace to primary sources)
- [Short summary of the OpenAI agent swarm incidents](https://www.lesswrong.com/posts/9it8pQRTz3orkZDty/my-short-summary-of-the-openai-agent-swarm-incidents): index of all swarm events and their primary sources.
- [AI swarms are starting to pose indirect takeover risk](https://www.alignmentforum.org/posts/8oFYZdXkTaNGRtcn8/ai-swarms-are-starting-to-pose-indirect-takeover-risk)
- [AI Village reacts to the Hugging Face incident](https://www.lesswrong.com/posts/cR3P3hvtZtpo7GdS8/ai-village-reacts-to-huggingface-incident-comparing-the)
- [Secret Collusion](https://www.alignmentforum.org/posts/smMdYezaC8vuiLjCf/secret-collusion-will-we-know-when-to-unplug-ai) and [Detecting collusion through multi-agent interpretability](https://www.lesswrong.com/posts/Q65SETuTmhF4LWdix/detecting-collusion-through-multi-agent-interpretability-3)

## Meta
- [The Agent Incident Registry paper](https://arxiv.org/pdf/2609.11030): compares incident databases.
- [Open Problems in AI Incident Governance](https://arxiv.org/pdf/2607.05163)
