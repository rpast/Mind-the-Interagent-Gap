#!/usr/bin/env python3
"""The rules that turn call 1's extracted facts into labels. The single authority.

Call 1 (`mvp/prompts/extract_gate.v3.md`) extracts facts and answers the two gate
questions; it does not decide labels. This module decides them, by rule, the same way
every time. `run.py derive` applies it to every extract_gate proposal and writes the
result to mvp/state/verdicts.jsonl; `mvp/gold/score_gate1.py` applies it to a gold run.
The rules are written out in plain words in mvp/docs/classifiers.md and
mvp/docs/definitions.md; where those and this file disagree, this file is what runs.

Pure functions only: no file is read or written here.

    python mvp/pipeline/derive.py --selftest
"""
from __future__ import annotations

import sys

# Bump when a rule changes, so a verdict says which rules made it.
# 2026-11-16: the attack presumption no longer fires on a record that shows fewer than
# two AI agents, or where the model answered the counterfactual `could`.
RULES_VERSION = "2026-11-16"

UNCLEAR = ("unclear", None)
NOT_SECURITY = ("not_applicable", None)
PRESUMED_PAIR = ["I28", "I29"]

STATUSES = ("in_scope", "out_of_scope", "review")


# ------------------------------------------------------------------- helpers

def is_security(row):
    """A security record: an attack, intrusion or abuse campaign. Call 1 marks it by
    giving `multiplicity_role` any value other than not_applicable or null."""
    return row.get("multiplicity_role") not in NOT_SECURITY


def agent_count(row):
    """`n_ai_agents` as an int, or None if the record does not state it."""
    n = row.get("n_ai_agents")
    if isinstance(n, bool):
        return None
    if isinstance(n, int):
        return n
    try:
        return int(str(n).strip())
    except (TypeError, ValueError):
        return None


def presumption_fires(row):
    """The attack presumption, as decided 2026-11-16.

    An attack whose multiplicity is `unreported` is presumed in scope, but only if
    (a) the record does not show fewer than two AI agents (`n_ai_agents` null or >= 2),
    and (b) the model did not itself answer the counterfactual `could`."""
    if row.get("multiplicity_role") != "unreported":
        return False
    n = agent_count(row)
    if n is not None and n < 2:
        return False
    return row.get("single_agent_counterfactual") != "could"


def resolve_counterfactual(row):
    """(counterfactual, by_presumption). On a security record `multiplicity_role`
    governs: load_bearing -> could_not; incidental -> could; unreported -> could_not
    when the presumption fires, else the model's answer stands. Elsewhere the model's
    answer stands. `by_presumption` is true only when the presumption decided it: it
    fired, and the model had not already answered could_not."""
    cf = row.get("single_agent_counterfactual")
    if not is_security(row):
        return cf, False
    role = row.get("multiplicity_role")
    if role == "load_bearing":
        return "could_not", False
    if role == "incidental":
        return "could", False
    if presumption_fires(row):
        return "could_not", cf != "could_not"
    return cf, False


def multi_agent(row, cf=None):
    """Gate 1. Security record: the counterfactual resolves to could_not; interaction
    is not required, multiplicity stands in for it. Any other record: could_not AND
    interaction_present is true."""
    if cf is None:
        cf, _ = resolve_counterfactual(row)
    if is_security(row):
        return cf == "could_not"
    return cf == "could_not" and row.get("interaction_present") is True


def evidence_type(row):
    """From setting, stakes and who controlled the environment, per
    mvp/taxonomy/evidence_types.csv. None when the facts do not settle it."""
    s, st, env = row.get("setting"), row.get("stakes"), row.get("environment_controlled_by")
    if s == "none":
        return "theoretical"
    if s == "narrow_probe":
        return "lab"
    if s == "researcher_built":
        return "synthetic"
    if s == "deployed" and st == "real" and env in ("nobody", "operator"):
        return "real_world"
    return None


def failure_mode(row):
    """The Gate 2 tree. Cooperation that occurred where it was not expected -> FM3.
    Otherwise by objectives: identical -> FM1, mixed -> FM2, opposing or unclear ->
    none. Meaningful only for an in-scope record."""
    if row.get("cooperation_occurred") == "yes" \
            and row.get("cooperation_expected") == "unexpected":
        return "FM3"
    return {"identical": "FM1", "mixed": "FM2"}.get(row.get("objective_relation"))


def gate1_unclear(row):
    """Gate 1 fields the model left unclear. Any of them routes to review, with two
    exceptions on a security record: `interaction_present` is not a review reason
    there (multiplicity stands in for it), and an unclear counterfactual is not one
    where the attack presumption fired and resolved it. A load_bearing or incidental
    role does not excuse an unclear counterfactual: only the presumption does."""
    out = []
    if not is_security(row) and row.get("interaction_present") in UNCLEAR:
        out.append("interaction_present")
    if row.get("single_agent_counterfactual") in UNCLEAR and not presumption_fires(row):
        out.append("single_agent_counterfactual")
    return out


def gate2_unclear(row):
    """Gate 2 fields left unclear where they decide the branch: cooperation_occurred
    always; cooperation_expected only when cooperation occurred; objective_relation
    only off the FM3 branch."""
    out = []
    occurred = row.get("cooperation_occurred")
    expected = row.get("cooperation_expected")
    if occurred in UNCLEAR:
        out.append("cooperation_occurred")
    if occurred == "yes" and expected in UNCLEAR:
        out.append("cooperation_expected")
    on_fm3 = occurred == "yes" and expected == "unexpected"
    if not on_fm3 and row.get("objective_relation") in UNCLEAR:
        out.append("objective_relation")
    return out


# --------------------------------------------------------------------- derive

def derive(row, manual=None):
    """Labels for one extract_gate row, by rule.

    Returns:
      status         in_scope | out_of_scope | review
      gate1          in | out | review | curator   (scope alone, before Gate 2)
      review_why     why it is a review item; empty otherwise
      by_presumption scope came from the attack presumption
      labels                (settled)   or
      labels_if_confirmed   (review: what the rules give if a person confirms the facts)
        multi_agent, counterfactual_resolved, evidence_type, failure_mode,
        instances_presumed

    A manual record (`manual`, default: source_id == "manual") is in scope on the
    curator's word: no Gate 1 verdict is derived and `multi_agent` stays null.
    """
    if manual is None:
        manual = row.get("source_id") == "manual" \
            or str(row.get("record_key", "")).startswith("manual:")
    why = []
    if row.get("confidence") != "high":
        why.append(f"confidence {row.get('confidence')}")

    if manual:
        cf, presumed, ma, gate1 = row.get("single_agent_counterfactual"), False, None, "curator"
        in_scope = True
    else:
        cf, presumed = resolve_counterfactual(row)
        ma = multi_agent(row, cf)
        g1 = gate1_unclear(row)
        why += g1
        gate1 = "review" if g1 else ("in" if ma else "out")
        in_scope = ma

    et = evidence_type(row)
    fm = None
    if in_scope:
        fm = failure_mode(row)
        why += gate2_unclear(row)
        if et is None:
            why.append("evidence type not derivable")
    instances = list(PRESUMED_PAIR) if (not manual and ma and is_security(row)
                                        and row.get("multiplicity_role") == "unreported") \
        else []

    labels = {"multi_agent": ma, "counterfactual_resolved": cf,
              "evidence_type": et, "failure_mode": fm,
              "instances_presumed": instances}
    status = "review" if why else ("in_scope" if in_scope else "out_of_scope")
    out = {"status": status, "gate1": gate1, "review_why": why,
           "by_presumption": bool(presumed and ma), "rules_version": RULES_VERSION}
    out["labels_if_confirmed" if status == "review" else "labels"] = labels
    return out


def labels_of(verdict):
    """The labels of a verdict, settled or not."""
    return verdict.get("labels") or verdict.get("labels_if_confirmed") or {}


# ------------------------------------------------------------------ selftest

def _row(**kw):
    base = {"source_id": "aiid", "source_record_id": "1", "n_ai_agents": 2,
            "interaction_present": True, "setting": "deployed", "stakes": "real",
            "environment_controlled_by": "nobody", "single_agent_counterfactual": "could_not",
            "multiplicity_role": "not_applicable", "cooperation_occurred": "no",
            "cooperation_expected": "expected", "objective_relation": "identical",
            "confidence": "high"}
    base.update(kw)
    return base


def selftest():
    cases = []

    def case(name, row, manual=None, **want):
        got = derive(row, manual=manual)
        lab = labels_of(got)
        flat = {**got, **lab}
        bad = {k: (v, flat.get(k)) for k, v in want.items() if flat.get(k) != v}
        cases.append((name, bad))

    # Gate 1, non-security
    case("non-security in scope, FM1", _row(), status="in_scope", multi_agent=True,
         failure_mode="FM1", evidence_type="real_world", gate1="in", review_why=[])
    case("non-security could -> out", _row(single_agent_counterfactual="could"),
         status="out_of_scope", multi_agent=False, gate1="out")
    case("non-security no interaction -> out", _row(interaction_present=False),
         status="out_of_scope", multi_agent=False)
    case("non-security unclear cf -> review", _row(single_agent_counterfactual="unclear"),
         status="review", review_why=["single_agent_counterfactual"], gate1="review")
    case("non-security null interaction -> review", _row(interaction_present=None),
         status="review", review_why=["interaction_present"])
    case("confidence medium -> review", _row(confidence="medium"), status="review",
         review_why=["confidence medium"], multi_agent=True)
    case("review puts labels under labels_if_confirmed",
         _row(confidence="low"), status="review", labels=None)
    case("settled puts labels under labels", _row(), labels_if_confirmed=None)

    # Gate 1, security: the attack presumption
    case("load_bearing -> could_not", _row(multiplicity_role="load_bearing",
                                           single_agent_counterfactual="could",
                                           interaction_present=None,
                                           objective_relation="opposing"),
         status="in_scope", multi_agent=True, counterfactual_resolved="could_not",
         by_presumption=False, failure_mode=None, instances_presumed=[])
    case("load_bearing with an unclear counterfactual still routes to review",
         _row(multiplicity_role="load_bearing", single_agent_counterfactual="unclear",
              objective_relation="opposing"),
         status="review", multi_agent=True, gate1="review",
         review_why=["single_agent_counterfactual"])
    case("incidental -> could", _row(multiplicity_role="incidental",
                                     single_agent_counterfactual="could_not"),
         status="out_of_scope", multi_agent=False, counterfactual_resolved="could")
    case("incidental with an unclear counterfactual still routes to review",
         _row(multiplicity_role="incidental", single_agent_counterfactual="unclear"),
         status="review", multi_agent=False, review_why=["single_agent_counterfactual"])
    case("unreported, n null, cf unclear -> in by presumption",
         _row(multiplicity_role="unreported", n_ai_agents=None,
              single_agent_counterfactual="unclear", interaction_present=None,
              objective_relation="opposing"),
         status="in_scope", multi_agent=True, by_presumption=True,
         instances_presumed=["I28", "I29"], review_why=[], failure_mode=None)
    case("unreported, n 3, cf could_not -> in, not by presumption",
         _row(multiplicity_role="unreported", n_ai_agents=3,
              objective_relation="opposing"),
         status="in_scope", by_presumption=False, instances_presumed=["I28", "I29"])
    case("NEW: unreported, n 1 -> presumption does not fire",
         _row(multiplicity_role="unreported", n_ai_agents=1,
              single_agent_counterfactual="unclear"),
         status="review", multi_agent=False, by_presumption=False,
         review_why=["single_agent_counterfactual"], instances_presumed=[])
    case("NEW: unreported, n 0, cf could -> out",
         _row(multiplicity_role="unreported", n_ai_agents=0,
              single_agent_counterfactual="could"),
         status="out_of_scope", multi_agent=False, by_presumption=False)
    case("NEW: unreported, model answered could -> out",
         _row(multiplicity_role="unreported", n_ai_agents=None,
              single_agent_counterfactual="could"),
         status="out_of_scope", multi_agent=False, counterfactual_resolved="could",
         by_presumption=False)
    case("NEW: unreported, n '5' as a string -> fires",
         _row(multiplicity_role="unreported", n_ai_agents="5",
              single_agent_counterfactual="unclear", objective_relation="opposing"),
         status="in_scope", by_presumption=True)
    case("security: interaction_present is not a review reason",
         _row(multiplicity_role="load_bearing", interaction_present=None,
              objective_relation="opposing"),
         status="in_scope", review_why=[])

    # Gate 2
    case("FM3: cooperated, unexpected",
         _row(cooperation_occurred="yes", cooperation_expected="unexpected",
              objective_relation="unclear"),
         status="in_scope", failure_mode="FM3", review_why=[])
    case("FM2: mixed", _row(objective_relation="mixed"), failure_mode="FM2")
    case("opposing -> no FM, still in scope", _row(objective_relation="opposing"),
         status="in_scope", failure_mode=None)
    case("competition is not collusion",
         _row(cooperation_occurred="no", cooperation_expected="unexpected",
              objective_relation="mixed"), failure_mode="FM2")
    case("gate2: cooperation_occurred unclear -> review",
         _row(cooperation_occurred="unclear"), status="review",
         review_why=["cooperation_occurred"])
    case("gate2: expected unclear matters only when cooperation occurred",
         _row(cooperation_occurred="no", cooperation_expected="unclear"),
         status="in_scope", review_why=[])
    case("gate2: expected unclear when cooperation occurred -> review",
         _row(cooperation_occurred="yes", cooperation_expected="unclear"),
         status="review", review_why=["cooperation_expected"])
    case("gate2: objectives unclear off the FM3 branch -> review",
         _row(objective_relation="unclear"), status="review",
         review_why=["objective_relation"])
    case("gate2 unclears ignored when out of scope",
         _row(single_agent_counterfactual="could", cooperation_occurred=None,
              objective_relation=None, setting=None),
         status="out_of_scope", review_why=[], failure_mode=None)

    # evidence type
    for setting, stakes, env, et in (("none", None, None, "theoretical"),
                                     ("narrow_probe", "simulated", "experimenter", "lab"),
                                     ("researcher_built", "simulated", "experimenter",
                                      "synthetic"),
                                     ("deployed", "real", "operator", "real_world"),
                                     ("deployed", "real", "nobody", "real_world")):
        case(f"evidence type {setting}/{stakes}/{env}",
             _row(setting=setting, stakes=stakes, environment_controlled_by=env),
             evidence_type=et)
    case("evidence type not derivable -> review when in scope",
         _row(setting="deployed", stakes="real", environment_controlled_by="experimenter"),
         status="review", evidence_type=None,
         review_why=["evidence type not derivable"])

    # manual records
    case("manual: no Gate 1, in scope on the curator's word",
         _row(source_id="manual", single_agent_counterfactual="unclear",
              interaction_present=None),
         status="in_scope", gate1="curator", multi_agent=None, review_why=[])
    case("manual: Gate 2 still routes",
         _row(source_id="manual", objective_relation="unclear", confidence="medium"),
         status="review", review_why=["confidence medium", "objective_relation"])

    failed = [(n, b) for n, b in cases if b]
    for name, bad in cases:
        print(f"  {'FAIL' if bad else 'ok  '}  {name}" + (f"  {bad}" if bad else ""))
    print(f"{len(cases) - len(failed)} of {len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(__doc__)
