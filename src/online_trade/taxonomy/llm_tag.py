"""LLM tagging for taxonomy_v1: flat classification with k retrieved reference examples.

Every request is cached (data/taxonomy/llm_cache/llm_cache.jsonl), so a run can be interrupted and rerun
(it resumes from the cache) and reproduced offline (--offline). Spending is capped (--max-cost) and reported.

Input to the model: item wordings, the subcategory list, an abbreviation table and k labelled reference items
retrieved by text-embedding similarity. No sales, co-purchase, customer, cluster or period information.

Reference library:
  eval  excludes gold items and every code sharing a 5-character prefix with a gold item (for R1-R4)
  prod  excludes gold items only (for R5-R6); the item itself is always excluded

Examples:
  python scripts/run_taxonomy.py llm_tag --taxonomy v0 --items gold --sample 5 --run-id trial_v0 --dry-run   # inspect prompt, no API
  python scripts/run_taxonomy.py llm_tag --taxonomy v0 --items gold --sample 5 --run-id trial_v0              # 5-item trial
  python scripts/run_taxonomy.py llm_tag --run R1                                                             # preset (taxonomy_v1)
  python scripts/run_taxonomy.py llm_tag --run R1 --offline                                                   # rebuild from cache only
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from string import Template

import numpy as np
import pandas as pd

from .llm_client import LLM, BudgetExceeded, CacheMiss, load_config, parse_json
from .paths import RESULTS, SCHEMA_CUTOFF
from .rules_v0 import RULES
from .step2_tag import rule_tag
from .taxonomy_io import (LLM_CACHE, PROMPTS, TAX_CFG, V1_WORK, gold_codes, load_catalog, load_embeddings,
                         load_seed_labels, load_taxonomy, pick_examples, prefix)

RUNS = RESULTS / "llm_runs"


def build_v0_compat(cat, E):
    """taxonomy_v0 in the v1 file format (no definitions), only for pipeline trials."""
    ok = cat.variants.map(lambda vs: len({rule_tag(v) for v in vs} - {None}) <= 1)
    seeds = cat[(cat.first_seen < SCHEMA_CUTOFF) & (cat.label_source == "rule") & ok][["stock_code", "l2_id"]].assign(source="v0_rule")
    seeds.to_csv(V1_WORK / "seed_labels_v0.csv", index=False)
    gold = gold_codes()
    excl = set(cat.stock_code[cat.stock_code.map(prefix).isin({prefix(c) for c in gold})])
    tax = {"version": "taxonomy_v0_compat", "status": "v0 categories without definitions; for pipeline trials only",
           "seed_labels": "data/taxonomy/v1_work/seed_labels_v0.csv",
           "l2": [dict(id=l2, l1=l1, name_en=l2.replace("_", " "), definition="", boundary="",
                       examples=pick_examples(cat, E, seeds, l2, excl, 3)) for l2, l1, _ in RULES]}
    path = TAX_CFG / "taxonomy_v0_compat.json"
    path.write_text(json.dumps(tax, indent=1, ensure_ascii=False))
    return path


def system_prompt(tax, template):
    rows = "\n".join(f"{c['id']} | {c['l1']} | {c.get('name_en', '')} | {c.get('definition', '')} | "
                     f"{c.get('boundary', '')} | e.g. " + "; ".join(c.get("examples", [])) for c in tax["l2"])
    abbrev = (PROMPTS / "abbreviations_v1.txt").read_text().strip()
    return Template((PROMPTS / template).read_text()).substitute(taxonomy=rows, abbrev=abbrev)


def user_prompt(code, wordings, examples):
    parts = []
    if examples:
        parts.append("Reference items that are already labelled (most similar first):")
        parts += [f'- "{d}" -> {l2}' for d, l2 in examples]
        parts.append("")
    parts.append(f"Item to classify (stock code {code}). Wording(s):")
    parts += [f"- {w}" for w in wordings]
    return "\n".join(parts)


class Retriever:
    def __init__(self, cat, E, seeds, library, gold):
        self.cat, self.E = cat, E
        excl = set(gold)
        if library == "eval":
            fam = {prefix(c) for c in gold}
            excl |= set(cat.stock_code[cat.stock_code.map(prefix).isin(fam)])
        s = seeds[~seeds.stock_code.isin(excl)]
        pos = pd.Series(cat.index, index=cat.stock_code)
        self.idx = pos[s.stock_code].to_numpy()
        self.l2 = s.l2_id.to_numpy()
        self.code = s.stock_code.to_numpy()
        self.pos = pos

    def __call__(self, code, k):
        if k <= 0:
            return []
        q = self.E[self.pos[code]]
        sims = self.E[self.idx] @ q
        order = [i for i in np.argsort(-sims) if self.code[i] != code]
        top = order[:k]
        if len({self.l2[i] for i in top}) == 1:  # all the same type: add the nearest of another type
            extra = next((i for i in order[k:] if self.l2[i] != self.l2[top[0]]), None)
            if extra is not None:
                top.append(extra)
        return [(self.cat.canonical_description.iat[self.idx[i]], self.l2[i]) for i in top]


def select_items(cat, spec, sample, seed):
    if spec == "gold":
        df = cat[cat.stock_code.isin(gold_codes())]
    elif spec == "all":
        df = cat
    elif spec == "multiwording":
        df = cat[cat.n_variants > 1]
    elif spec.startswith("codes:"):
        df = cat[cat.stock_code.isin(spec[6:].split(","))]
    else:
        df = cat[cat.stock_code.isin(pd.read_csv(spec, dtype=str).stock_code)]
    if sample:
        df = df.sample(n=min(sample, len(df)), random_state=seed)
    return df.sort_values("stock_code")


def tag_one(llm, sysmsg, valid, l1_of, code, wordings, examples, meta):
    msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": user_prompt(code, wordings, examples)}]
    rec = llm.chat(msgs, meta=meta, max_tokens=4000)
    cost, keys, out, note = rec["cost"], [rec["key"]], None, ""
    try:
        out = parse_json(rec["content"])
    except (json.JSONDecodeError, TypeError, IndexError):
        note = "unparseable"
    if out is None or out.get("l2_id") not in valid:  # one corrective retry
        bad = (out or {}).get("l2_id")
        msgs += [{"role": "assistant", "content": rec["content"] or ""},
                 {"role": "user", "content": f'"{bad}" is not a valid id. Answer again with JSON, choosing one id from the list.'}]
        rec2 = llm.chat(msgs, meta={**meta, "retry": 1}, max_tokens=4000)
        cost += rec2["cost"]
        keys.append(rec2["key"])
        try:
            out = parse_json(rec2["content"])
            note = (note + ";retried").strip(";")
        except (json.JSONDecodeError, TypeError, IndexError):
            out = None
    ok = out is not None and out.get("l2_id") in valid
    l2 = out["l2_id"] if ok else "other"
    return dict(stock_code=code, wording=" | ".join(wordings), l2_id=l2, l1_id=l1_of[l2],
                confidence=(out or {}).get("confidence"), reason=(out or {}).get("reason", ""), valid=ok,
                note=note if ok else (note + ";invalid->other").strip(";"), n_examples=len(examples),
                example_l2=";".join(e[1] for e in examples), cost=round(cost, 8), cache_keys=";".join(keys),
                model_returned=rec.get("model_returned"), from_cache=rec["from_cache"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="preset id in configs/taxonomy/llm_runs_v1.json (R1-R6)")
    ap.add_argument("--run-id", help="output folder name (default: the preset id)")
    ap.add_argument("--taxonomy", default="configs/taxonomy/taxonomy_v1.json", help="taxonomy JSON path, or 'v0' for a trial")
    ap.add_argument("--items", help="gold | all | multiwording | codes:A,B | path to a CSV with stock_code")
    ap.add_argument("--sample", type=int, help="random sample of N items (seeded)")
    ap.add_argument("--seed", type=int, default=3111)
    ap.add_argument("--library", choices=["eval", "prod"])
    ap.add_argument("--k", type=int)
    ap.add_argument("--prompt")
    ap.add_argument("--per-variant", action="store_true")
    ap.add_argument("--model")
    ap.add_argument("--max-cost", type=float)
    ap.add_argument("--workers", type=int)
    ap.add_argument("--offline", action="store_true", help="cache only, no API calls")
    ap.add_argument("--dry-run", action="store_true", help="print the first prompt and a size estimate, no API call")
    a = ap.parse_args()

    preset = json.loads((TAX_CFG / "llm_runs_v1.json").read_text()).get(a.run, {}) if a.run else {}
    opt = lambda name, default=None: getattr(a, name) if getattr(a, name) not in (None, False) else preset.get(name, default)
    items, library, k, prompt = opt("items", "gold"), opt("library", "eval"), opt("k", 5), opt("prompt", "tag_v1.txt")
    per_variant = a.per_variant or preset.get("per_variant", False)
    run_id = a.run_id or a.run or "adhoc"

    cat, E = load_catalog(), load_embeddings()
    tax_path = build_v0_compat(cat, E) if a.taxonomy == "v0" else a.taxonomy
    tax = load_taxonomy(tax_path)
    freeze = None
    if a.taxonomy != "v0":
        from .v1_freeze import check_freeze
        freeze = check_freeze(strict=not a.dry_run)
        if freeze is None and a.run:
            raise SystemExit("taxonomy_v1 is not frozen yet: run v1_freeze.py before the R1-R6 runs")
    seeds = load_seed_labels(tax)
    gold = gold_codes()
    if not gold and library == "eval":
        raise SystemExit("gold sample missing: run gold_sample.py first")
    retr = Retriever(cat, E, seeds, library, gold)
    sysmsg = system_prompt(tax, prompt)
    valid, l1_of = set(tax["l2_ids"]), tax["l1_of"]

    df = select_items(cat, items, a.sample, a.seed)
    jobs = []
    for r in df.itertuples():
        ex = retr(r.stock_code, k)
        for w in ([[v] for v in r.variants] if per_variant else [r.variants]):
            jobs.append((r.stock_code, w, ex))

    if a.dry_run:
        u = user_prompt(*jobs[0])
        print(sysmsg + "\n\n===== USER =====\n" + u)
        print(f"\n[dry-run] {len(jobs)} requests; ~{len(sysmsg) // 4} system + ~{len(u) // 4} user tokens each "
              f"(system part is identical across requests, so DeepSeek's prefix cache should bill most of it as cache hits)")
        return

    llm_over = preset.get("llm", {})
    cfg = load_config(a.model or llm_over.get("model"), base_url=llm_over.get("base_url"), api_key_env=llm_over.get("api_key_env"))
    if "SET-ME" in json.dumps(cfg):
        raise SystemExit(f"preset {a.run} needs model/base_url/api_key_env set in llm_runs_v1.json")
    llm = LLM(cfg, LLM_CACHE, max_cost=a.max_cost, offline=a.offline)
    meta0 = {"task": "tag", "run": run_id, "taxonomy": tax["version"], "prompt": prompt, "library": library, "k": k}
    rows, stopped = [], None
    with ThreadPoolExecutor(max_workers=a.workers or cfg["max_workers"]) as pool:
        futs = {pool.submit(tag_one, llm, sysmsg, valid, l1_of, c, w, ex, {**meta0, "stock_code": c}): (c, w) for c, w, ex in jobs}
        for f in as_completed(futs):
            try:
                rows.append(f.result())
            except (BudgetExceeded, CacheMiss) as e:
                stopped = f"{type(e).__name__}: {e}"
            except RuntimeError as e:  # API/network failure after all retries: skip this item, rerun resumes
                stopped = f"API error on {futs[f][0]}: {str(e)[:200]}"
                print("  ", stopped, flush=True)
            if len(rows) % 100 == 0 and rows:
                print(f"  {len(rows)}/{len(jobs)} done, new cost {llm.spent:.4f}", flush=True)

    out = RUNS / run_id
    out.mkdir(parents=True, exist_ok=True)
    res = pd.DataFrame(rows).sort_values(["stock_code", "wording"]) if rows else pd.DataFrame()
    res.to_csv(out / "labels.csv", index=False)
    summary = {"run_id": run_id, "preset": a.run, "taxonomy": tax["version"], "items": items, "sample": a.sample,
               "library": library, "k": k, "prompt": prompt, "per_variant": per_variant,
               "requests_planned": len(jobs), "requests_done": len(rows), "stopped": stopped,
               "invalid": int((~res.valid).sum()) if rows else 0,
               "other_share": round(float((res.l2_id == "other").mean()), 4) if rows else None,
               "taxonomy_frozen_at": (freeze or {}).get("frozen_at"),
               "taxonomy_sha256": (freeze or {}).get("sha256", {}).get("configs/taxonomy/taxonomy_v1.json"),
               "run_cost_incl_cached": round(float(res.cost.sum()), 6) if rows else 0, **llm.summary()}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    if rows:
        show = res.merge(cat[["stock_code", "l2_id"]].rename(columns={"l2_id": "v0_l2"}), on="stock_code")
        print(show[["stock_code", "wording", "l2_id", "v0_l2", "confidence", "reason", "note"]].to_string(index=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    if stopped:
        print(f"\nStopped early ({stopped}). Rerun the same command to resume from the cache.")


if __name__ == "__main__":
    main()
