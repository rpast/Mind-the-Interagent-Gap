## MIT AI Risk Navigator (`mit_navigator`)

- URL: https://airisk.mit.edu/navigator
- Access: browser — a script cannot reach this.
- Last fetched: 2026-11-09
- Reuse: cc_by_4_0
- Multi-agent label: yes at behaviour facet (UI only, not in the API export)
- Caveat: Self-declared research prototype, 'preliminary and not yet validated'; asks that its visualizations not be redistributed. Measured 33% false-negative rate against our own incidents. JS app in a cross-origin iframe that frame-busts, so it needs a real browser.

**To do:** open the URL, find incidents involving two or more AI agents that are not already in `mvp/records/`, and save what you find to `mvp/raw/mit_navigator/` as JSON lines with at least `source_record_id`, `title`, `text`, `date` and `url`. Then run `python mvp/pipeline/run.py normalise mit_navigator`.

## Agent Incident Registry (Enkrypt AI) (`air_enkrypt`)

- URL: https://air.enkryptai.com/
- Access: browser — a script cannot reach this.
- Last fetched: 2026-10-25
- Reuse: permission_needed
- Multi-agent label: yes at multi_agent_system attack surface
- Caveat: Contact Enkrypt before reusing the data. Tagging is incomplete: the Hugging Face swarm is missing from the multi_agent_system view. JS-rendered.

**To do:** open the URL, find incidents involving two or more AI agents that are not already in `mvp/records/`, and save what you find to `mvp/raw/air_enkrypt/` as JSON lines with at least `source_record_id`, `title`, `text`, `date` and `url`. Then run `python mvp/pipeline/run.py normalise air_enkrypt`.

## AI Village operator write-ups (`aivillage`)

- URL: https://aivillageblog.substack.com/archive
- Access: manual — a script cannot reach this.
- Last fetched: 2026-10-26
- Reuse: unknown
- Multi-agent label: no
- Caveat: The Substack copies are reachable where theaidigest.org and X are not. All 7 of our AI Village incidents are absent from AIID entirely.

**To do:** open the URL, find incidents involving two or more AI agents that are not already in `mvp/records/`, and save what you find to `mvp/raw/aivillage/` as JSON lines with at least `source_record_id`, `title`, `text`, `date` and `url`. Then run `python mvp/pipeline/run.py normalise aivillage`.

## Antimemetics Multi-Agent Databank (`antimemetics`)

- URL: https://databank.antimemetics.institute
- Access: browser — a script cannot reach this.
- Last fetched: never
- Reuse: unknown
- Multi-agent label: no
- Caveat: Screened in but not yet recorded: GovSim replication, algorithmic collusion in an LLM duopoly, Prompt Infection.

**To do:** open the URL, find incidents involving two or more AI agents that are not already in `mvp/records/`, and save what you find to `mvp/raw/antimemetics/` as JSON lines with at least `source_record_id`, `title`, `text`, `date` and `url`. Then run `python mvp/pipeline/run.py normalise antimemetics`.

## OECD AI Incidents Monitor (`oecd_aim`)

- URL: https://oecd.ai/en/incidents
- Access: browser — a script cannot reach this.
- Last fetched: never
- Reuse: unknown
- Multi-agent label: no
- Caveat: Broad news-based coverage, keyword search only.

**To do:** open the URL, find incidents involving two or more AI agents that are not already in `mvp/records/`, and save what you find to `mvp/raw/oecd_aim/` as JSON lines with at least `source_record_id`, `title`, `text`, `date` and `url`. Then run `python mvp/pipeline/run.py normalise oecd_aim`.

## AIAAIC Repository (`aiaaic`)

- URL: https://www.aiaaic.org/
- Access: browser — a script cannot reach this.
- Last fetched: never
- Reuse: unknown
- Multi-agent label: no
- Caveat: Broad news-based coverage, keyword search only.

**To do:** open the URL, find incidents involving two or more AI agents that are not already in `mvp/records/`, and save what you find to `mvp/raw/aiaaic/` as JSON lines with at least `source_record_id`, `title`, `text`, `date` and `url`. Then run `python mvp/pipeline/run.py normalise aiaaic`.

## Moltbook data repository (`moltbook`)

- URL: https://www.lesswrong.com/posts/WyrxmTwYbrwsT72sD/moltbook-data-repository
- Access: manual — a script cannot reach this.
- Last fetched: never
- Reuse: unknown
- Multi-agent label: no
- Caveat: Data from the AI-agent social network.

**To do:** open the URL, find incidents involving two or more AI agents that are not already in `mvp/records/`, and save what you find to `mvp/raw/moltbook/` as JSON lines with at least `source_record_id`, `title`, `text`, `date` and `url`. Then run `python mvp/pipeline/run.py normalise moltbook`.
