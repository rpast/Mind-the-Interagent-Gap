#!/usr/bin/env python3
"""Seed mvp/taxonomy/ from the earlier taxonomy tables plus written instance definitions.

Run once. The CSVs it writes are hand-curated from then on; this script exists
so the seeding is reproducible and reviewable, not so it can be re-run blindly.
It refuses to overwrite a file that already exists.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED_TABLES = ROOT / "poc" / "data"   # frozen reference tables; read once at seed time
OUT = Path(__file__).resolve().parent

PAPER = "Hammond et al. 2025"

# instance_id -> (definition, source_ref, examples)
# Definitions are written from the paper's own paragraph for that instance;
# the page is the page the paragraph starts on.
DEFS = {
    "I01": (
        "Agents that each perform well alone fail together because their strategies do not "
        "mesh: conventions, protocols or equilibrium selections that are individually sound "
        "but mutually incompatible. No agent is deceiving or competing; the policies simply "
        "do not interlock.",
        f"{PAPER} p.11",
        "Two independently trained driving agents each follow a safe but different convention at a junction."),
    "I02": (
        "Agents sharing an objective cannot tell which agent's action produced a good or bad "
        "outcome, so they cannot learn to coordinate. The failure is in attributing outcomes "
        "to actors, not in the actions themselves.",
        f"{PAPER} p.12",
        "A team of learning agents improves slowly because reward cannot be traced to a contributor."),
    "I03": (
        "Agents must coordinate without shared history, prior play or an adequate channel, so "
        "they cannot converge on a joint plan. Zero-shot and few-shot coordination. What is "
        "missing is the history or the channel, not the intent.",
        f"{PAPER} p.12",
        "Agents meeting once, under time pressure, with no way to signal intent."),
    "I04": (
        "Each agent's selfish incentive diverges from the collective good, so individually "
        "rational play leaves every party worse off. Includes commons depletion and races to "
        "the bottom, and the sequential form where agents observe and escalate each other's "
        "extraction.",
        f"{PAPER} p.13",
        "Agents managing a shared fishery each raise their catch until the stock collapses."),
    "I05": (
        "Conflict between agents acting for opposed principals in military or security "
        "settings: autonomous weapons, or AI systems serving as advisors or negotiators in "
        "high-stakes decisions.",
        f"{PAPER} p.14",
        "Two states' AI advisors escalating in a crisis simulation."),
    "I06": (
        "One agent changes another's behaviour by threatening a cost it would not otherwise "
        "impose. Use this instance when the coercion is itself the conflict; use I24 when the "
        "commitment mechanism that makes the threat credible is the point.",
        f"{PAPER} p.14",
        "An agent withholding a needed resource until another concedes."),
    "I07": (
        "Agents trading or setting prices converge on supra-competitive behaviour without any "
        "explicit agreement. The market was supposed to produce efficiency through competition "
        "and does not.",
        f"{PAPER} p.18",
        "Independent pricing algorithms learning to sustain a high price."),
    "I08": (
        "Agents conceal messages inside otherwise innocuous communication, coordinating "
        "outside the channel that is being monitored.",
        f"{PAPER} p.18",
        "Models encoding a side-channel in natural-language text that a monitor reads as benign."),
    "I09": (
        "The information an agent needs cannot be transmitted, because the channel is "
        "constrained, costly or restricted, so the asymmetry persists. I09 is the channel as a "
        "standing condition; I03 is the coordination failure it produces.",
        f"{PAPER} p.21",
        "A bandwidth-limited or format-restricted channel between agents."),
    "I10": (
        "Private valuations make efficient agreement unattainable: agents misrepresent to "
        "capture surplus, and may fail to agree at all even when agreement exists.",
        f"{PAPER} p.21",
        "Two negotiating agents each overstating their reservation value until talks fail."),
    "I11": (
        "An agent takes actions designed to mislead another agent. An information asymmetry is "
        "created or exploited deliberately.",
        f"{PAPER} p.21",
        "An agent misreporting its state to obtain a better allocation."),
    "I12": (
        "A false or corrupted item of information spreads through a network of agents and is "
        "acted on downstream. What propagates is a falsity.",
        f"{PAPER} p.24",
        "One agent's hallucinated fact entering a scaffolded chain and being treated as given."),
    "I13": (
        "The topology of which agents interact with which changes, through preferential "
        "attachment or the centralisation of AI nodes, altering whole-network behaviour.",
        f"{PAPER} p.24",
        "AI intermediaries becoming hubs that most traffic routes through."),
    "I14": (
        "Many agents are built on the same few foundation models, so they share failure modes, "
        "vulnerabilities and biases, and fail at the same time for the same reason.",
        f"{PAPER} p.25",
        "One jailbreak working across an entire fleet of agents."),
    "I15": (
        "Competitive pressure selects for dispositions that are effective but harmful, such as "
        "aggression, deception or risk-taking.",
        f"{PAPER} p.28",
        "Agents iterated in competition becoming more aggressive bargainers."),
    "I16": (
        "Training on human data imports human dispositions into agent-to-agent interaction, "
        "including status-seeking, in-group bias and deceptive norms.",
        f"{PAPER} p.28",
        "Agents reproducing human bargaining tactics they were never instructed to use."),
    "I17": (
        "Agents acquire new capabilities by iteratively exploiting each other's weaknesses: "
        "co-adaptation produces an autocurriculum nobody designed.",
        f"{PAPER} p.28",
        "Hide-and-seek agents discovering tool use through successive counter-strategies."),
    "I18": (
        "The output of the agent system re-enters as its input, creating a cycle that amplifies "
        "or dampens behaviour.",
        f"{PAPER} p.31",
        "Algorithmic traders reinforcing each other's selling in the 2010 flash crash."),
    "I19": (
        "Joint learning dynamics orbit rather than converge, so behaviour never settles.",
        f"{PAPER} p.32",
        "Multi-agent Q-learning cycling instead of reaching equilibrium."),
    "I20": (
        "The joint dynamics become chaotic: small differences in starting conditions produce "
        "divergent collective behaviour, increasingly the norm as agent count grows.",
        f"{PAPER} p.32",
        "Learning dynamics that are unpredictable in principle, not merely unpredicted."),
    "I21": (
        "A small change in a parameter produces a discontinuous change in collective behaviour.",
        f"{PAPER} p.32",
        "A slight change in exploration rate flipping the system to a different equilibrium."),
    "I22": (
        "Co-adapting agents make each other's environment non-stationary, and policies trained "
        "against narrow co-players mis-generalise when the co-players change.",
        f"{PAPER} p.32",
        "A negotiator overconfident against opponents unlike its training partners."),
    "I23": (
        "Low trust between agents, because agents are cheap to create and able to deceive, "
        "produces costly verification, defection and foregone gains from trade.",
        f"{PAPER} p.34",
        "Agents refusing beneficial trades they cannot verify."),
    "I24": (
        "The ability to make credible commitments also confers the ability to make credible "
        "threats, which enables extortion and rewards brinkmanship.",
        f"{PAPER} p.34",
        "Ransomware made more effective by a credible commitment to restore data on payment."),
    "I25": (
        "A commitment is executed even though the belief that triggered it was wrong or "
        "circumstances changed, because the commitment removed the human from the loop.",
        f"{PAPER} p.34",
        "An automated response firing on a false positive in a warning system."),
    "I26": (
        "A composed system of agents can do what no component agent can do alone.",
        f"{PAPER} p.37",
        "Narrow tools chained into a workflow that exceeds each tool's capability."),
    "I27": (
        "Goal-directed behaviour is ascribable to the collective although no single agent holds "
        "the goal. The stance is functional: a goal is attributed when it explains the system's "
        "behaviour.",
        f"{PAPER} p.37",
        "Engagement-optimising bots collectively shifting a population's views."),
    "I28": (
        "Many agents attack jointly, and it is the number of them that defeats the defence.",
        f"{PAPER} p.39",
        "A swarm saturating a target's capacity to respond."),
    "I29": (
        "Agents combine different affordances, access or specialisations to defeat a safeguard "
        "that none of them could defeat alone. The diversity is what matters, not the count.",
        f"{PAPER} p.40",
        "One agent supplying context another needs to bypass its own refusal."),
    "I30": (
        "Many seemingly independent agents coordinate persuasion or phishing, drawing "
        "credibility from their apparent independence and evading detection.",
        f"{PAPER} p.40",
        "A coordinated set of accounts that read as unrelated individuals."),
    "I31": (
        "The agent is itself the attack surface: it is attacked to extract its principal's "
        "information or to make it act against its principal's interests.",
        f"{PAPER} p.41",
        "Prompt injection turning a user's assistant against the user."),
    "I32": (
        "A localised compromise propagates into a macroscopic failure, and is hard to mitigate "
        "because component failure is difficult to detect or localise.",
        f"{PAPER} p.41",
        "A worm spreading agent to agent across a network."),
    "I33": (
        "Attacks constructed so that they evade detection: steganographic channels, illusory "
        "attacks and encrypted backdoors.",
        f"{PAPER} p.41",
        "A backdoor whose trigger cannot be recovered by inspection."),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    written = []

    def write(name, header, rows):
        path = OUT / name
        if path.exists():
            sys.exit(f"refusing to overwrite {path}; delete it first if you mean to reseed")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        written.append(f"{name}: {len(rows)} rows")

    def read(name):
        with open(SEED_TABLES / name, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # risks.csv - carried over unchanged in content
    risks = read("risks.csv")
    write("risks.csv",
          ["risk_id", "risk", "risk_type", "section", "definition"],
          [[r["risk_id"], r["risk"], r["risk_type"], r["section"], r["definition"]]
           for r in risks])

    # associations.csv - Hammond-only, carried over unchanged
    assoc = read("associations.csv")
    write("associations.csv",
          ["fm_id", "rf_id", "basis", "text_reference"],
          [[a["fm_id"], a["rf_id"], a["basis"], a["text_reference"]] for a in assoc])

    # instances.csv - the instance repository, with written definitions
    inst = read("risk_instances.csv")
    rows = []
    for r in inst:
        iid = r["instance_id"]
        if iid in DEFS:
            definition, source_ref, examples = DEFS[iid]
            provenance = "hammond_table_1"
        else:
            # the three instances this project authored; the earlier tables already wrote
            # their definitions into support_summary
            definition = r["support_summary"]
            source_ref = "authored by this project"
            examples = ""
            provenance = "ours"
        notes = r["key_references"] or ""
        if r["support_summary"] and iid in DEFS:
            notes = (notes + " | " if notes else "") + r["support_summary"]
        rows.append([iid, r["instance"], r["risk_id"], definition,
                     provenance, source_ref, examples, notes])
    write("instances.csv",
          ["instance_id", "instance", "risk_id", "definition", "provenance",
           "source_ref", "examples", "notes"],
          rows)

    # evidence_types.csv - the controlled vocabulary, new in the mvp
    write("evidence_types.csv",
          ["evidence_type", "display_name", "criterion", "excludes"],
          [
              ["real_world", "Observed in real world",
               "Deployed systems acting on real stakes, outside experimenter control.",
               "Anything an experimenter set up, however realistic."],
              ["synthetic", "Synthetic evidence",
               "Agents interacting in a simulated or researcher-built environment: modelled "
               "markets, commons and wargames, and open-ended agent worlds.",
               "Narrow task probes with no environment, which are lab."],
              ["lab", "Observed in lab",
               "Controlled experiment on real models in a narrow task probe, with no "
               "environment for the agents to act in.",
               "Anything with a persistent environment, which is synthetic."],
              ["theoretical", "Theoretical",
               "Argument, formal model or non-AI analogue only. No AI system was run.",
               "Any run of an AI system, however small."],
          ])

    print("\n".join(written))


if __name__ == "__main__":
    main()
