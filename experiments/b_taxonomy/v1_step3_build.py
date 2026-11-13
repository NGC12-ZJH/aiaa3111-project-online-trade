"""taxonomy_v1 step 3: build the draft taxonomy from the human decisions + accepted proposals.

Inputs : configs/taxonomy/taxonomy_v1_decisions.json (edited by a human), data/taxonomy/v1_work/proposals/*.json
Outputs: configs/taxonomy/taxonomy_v1.json        subcategories with definition, boundary and 3 examples (DRAFT)
         data/taxonomy/v1_work/seed_labels_v1.csv  labelled schema items = reference-example pool for llm_tag.py
         data/taxonomy/item_attributes_v1.csv      season / design_line for every code (keyword match, no LLM)

Subcategories kept from v0 get a definition drafted by one LLM call (cached). Examples avoid gold items and
their prefix families. Everything stays "draft" until a human has reviewed taxonomy_v1.json.
"""
import argparse
import json
import re
from datetime import date

import pandas as pd

from llm_client import LLM, load_config, parse_json
from paths import SCHEMA_CUTOFF, TAXONOMY
from step2_tag import rule_tag
from taxonomy_io import LLM_CACHE, TAX_CFG, V1_WORK, gold_codes, load_catalog, load_embeddings, pick_examples, prefix

PROP = V1_WORK / "proposals"

DEFINE_PROMPT = """You are writing a labelling guide for a product-type taxonomy of a UK online giftware wholesaler
(Online Retail II). For each subcategory below (id | parent group | sample items), write name_en, name_zh (Simplified
Chinese), a one-sentence definition of the product type, and boundary rules naming confusable items that go in or out.
Define by what the product is / how it is used, not by colour, theme or season.
Return only a JSON object: {"<id>": {"name_en": "...", "name_zh": "...", "definition": "...", "boundary": "..."}, ...}

Subcategories:
"""


def load_prop(name):
    f = PROP / f"{name.replace(':', '__')}.json"
    return json.loads(f.read_text())["proposal"] if f.exists() else None


def compile_patterns(pats):
    return re.compile(r"\b(?:" + "|".join(re.escape(p.upper()) for p in pats) + r")\b") if pats else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--max-cost", type=float)
    ap.add_argument("--unfreeze", action="store_true", help="allow overwriting a frozen taxonomy (then refreeze)")
    a = ap.parse_args()
    if (V1_WORK / "FREEZE_taxonomy_v1.json").exists() and not a.unfreeze:
        raise SystemExit("taxonomy_v1 is frozen (data/taxonomy/v1_work/FREEZE_taxonomy_v1.json). "
                         "Changing it invalidates R1-R6; pass --unfreeze only on purpose, then rerun v1_freeze.py.")
    dec = json.loads((TAX_CFG / "taxonomy_v1_decisions.json").read_text())
    cat, E = load_catalog(), load_embeddings()
    schema = cat.first_seen < SCHEMA_CUTOFF
    gold = gold_codes()
    excl = set(cat.stock_code[cat.stock_code.map(prefix).isin({prefix(c) for c in gold})])

    l2 = {}  # id -> dict(l1, name_en, name_zh, definition, boundary, origin)
    l1_of_v0 = cat.drop_duplicates("l2_id").set_index("l2_id").l1_id.to_dict()
    seed = {}  # stock_code -> (l2_id, source)
    variant_ok = cat.variants.map(lambda vs: len({rule_tag(v) for v in vs} - {None}) <= 1)
    for r in cat[schema & (cat.label_source == "rule") & variant_ok].itertuples():
        seed[r.stock_code] = (r.l2_id, "v0_rule")

    pending = {}
    for v0 in sorted(set(cat.l2_id) - {"other"}):
        s = dec["splits"].get(v0)
        p = load_prop(f"split:{v0}") if s and s["accept"] else None
        if p is None:
            l2[v0] = dict(l1=l1_of_v0[v0], origin="v0")
            continue
        for sub in p["subcategories"]:
            l2[sub["id"]] = dict(l1=l1_of_v0[v0], origin=f"split_of:{v0}", **{k: sub.get(k, "") for k in
                                 ("name_en", "name_zh", "definition", "boundary")}) | s.get("edits", {}).get(sub["id"], {})
        pending.update({code: sid for code, sid in p["assignments"].items() if code in seed})
    for code, sid in pending.items():  # applied after all subcategories exist (items may move to other existing ids)
        seed[code] = (sid, "llm_split")

    po = load_prop("other")
    if po:
        if dec["other"]["accept_new_subcategories"]:
            for sub in po.get("new_subcategories", []):
                l2[sub["id"]] = dict(origin="from_other", **{k: sub.get(k, "") for k in
                                     ("l1", "name_en", "name_zh", "definition", "boundary")})
        if dec["other"]["accept_assignments"]:
            for code, sid in po["assignments"].items():
                if sid in l2:
                    seed[code] = (sid, "llm_other")

    for src, dst in dec.get("merge", {}).items():  # after all proposals, so new ids can be merged too
        if src.startswith("_"):
            continue
        if dst not in l2:
            raise SystemExit(f"merge target {dst} does not exist")
        l2.pop(src, None)
        l2[dst]["definition"] = ""  # redraft the definition of the merged subcategory
        l2[dst]["merged_from"] = l2[dst].get("merged_from", []) + [src]
        seed = {c: ((dst, v[1] + "+merged") if v[0] == src else v) for c, v in seed.items()}
    # human seed corrections: {"match": regex on description, "from": l2 or "*", "to": l2}
    desc = dict(zip(cat.stock_code, cat.canonical_description))
    n_fix = 0
    for o in dec.get("seed_overrides", []):
        if "match" not in o:
            continue
        rx = re.compile(o["match"])
        if o["to"] not in l2:
            raise SystemExit(f"seed override target {o['to']} does not exist")
        for c, v in list(seed.items()):
            if (o["from"] in ("*", v[0])) and rx.search(desc[c]):
                seed[c] = (o["to"], "human_override")
                n_fix += 1
    print("seed overrides applied:", n_fix)

    seeds = pd.DataFrame([(c, v[0], v[1]) for c, v in seed.items() if v[0] in l2], columns=["stock_code", "l2_id", "source"])
    seeds = seeds.sort_values("stock_code")
    seeds.to_csv(V1_WORK / "seed_labels_v1.csv", index=False)

    # definitions for subcategories without one (kept from v0, or merge targets). The LLM draft is stored in
    # definitions_draft_v1.json, so later human edits or seed fixes do not trigger a new API call.
    draft_f = V1_WORK / "definitions_draft_v1.json"
    draft = json.loads(draft_f.read_text()) if draft_f.exists() else {}
    todo = [k for k, v in l2.items() if not v.get("definition") and k not in draft]
    if todo:
        block = "\n".join(f"{k} | {l2[k]['l1']} | " + "; ".join(pick_examples(cat, E, seeds, k, excl, 8)) for k in todo)
        llm = LLM(load_config(a.model), LLM_CACHE, max_cost=a.max_cost)
        rec = llm.chat([{"role": "user", "content": DEFINE_PROMPT + block}], meta={"task": "v1_define"}, max_tokens=64000)
        if rec["finish_reason"] != "stop":
            raise SystemExit(f"definition request ended with finish_reason={rec['finish_reason']}; raise max_tokens")
        draft.update(parse_json(rec["content"]))
        draft_f.write_text(json.dumps(draft, indent=1, ensure_ascii=False))
        print("definitions:", json.dumps(llm.summary()))
    for k, v in l2.items():
        if not v.get("definition"):
            d = draft.get(k, {})
            v.update({f: d.get(f, "") for f in ("definition", "boundary")})
            v.update({f: d.get(f, "") for f in ("name_en", "name_zh") if not v.get(f)})
    for k, e in dec.get("edits", {}).items():  # human edits win over every LLM draft
        if not k.startswith("_"):
            l2[k].update({f: x for f, x in e.items() if not f.startswith("_")})
            l2[k]["edited_by_human"] = True
    missing = [k for k, v in l2.items() if not v.get("definition")]
    if missing:
        raise SystemExit(f"subcategories without definition: {missing}")

    tax = {"version": "taxonomy_v1_draft", "status": "DRAFT: LLM-assisted, needs human review before freezing",
           "built": date.today().isoformat(), "seed_labels": "data/taxonomy/v1_work/seed_labels_v1.csv",
           "l2": [dict(id=k, **v, examples=pick_examples(cat, E, seeds, k, excl, 3, diverse=True)) for k, v in sorted(l2.items(), key=lambda kv: (kv[1]["l1"], kv[0]))]}
    (TAX_CFG / "taxonomy_v1.json").write_text(json.dumps(tax, indent=1, ensure_ascii=False))

    # season / design_line attributes (deterministic keyword match)
    pd_ = load_prop("design") if dec.get("design", {}).get("accept") else None
    if pd_:
        extra = {k: v for k, v in dec["design"].get("season_extra", {}).items() if not k.startswith("_")}
        seasons = [(s, compile_patterns(p + extra.get(s, []))) for s, p in pd_.get("seasons", {}).items()]
        keep = dec["design"].get("keep_only")
        lines = [(d["id"], compile_patterns(d["patterns"])) for d in pd_.get("design_lines", []) if not keep or d["id"] in keep]
        first = lambda txt, rules: next((k for k, rx in rules if rx and rx.search(txt)), "none")
        txt = cat.variants.map(lambda vs: " | ".join(vs).upper())
        pd.DataFrame({"stock_code": cat.stock_code, "season": txt.map(lambda t: first(t, seasons)),
                      "design_line": txt.map(lambda t: first(t, lines))}).to_csv(TAXONOMY / "item_attributes_v1.csv", index=False)

    print(f"l2={len(l2)} | l1={len({v['l1'] for v in l2.values()})} | seeds={len(seeds)} {seeds.source.value_counts().to_dict()}")
