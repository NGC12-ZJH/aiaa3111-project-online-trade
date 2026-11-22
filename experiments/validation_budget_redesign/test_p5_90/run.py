"""Freeze and evaluate the P5/90 shared-budget follow-up."""
import argparse
from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

KEYS = ["control", "method", "seed"]
BUDGET = 90
QUALITY = dict(min_antecedent_orders=20, min_joint_orders=10, min_antecedent_customers=10,
               min_joint_customers=5, max_customer_joint_share=.5, min_confidence_uplift=.10,
               min_lift=1.2, min_triple_increment_pp=5, adjustment="BY", alpha=.05)


def write_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def rosters(path):
    f = pd.read_csv(path, keep_default_na=False, dtype={"rule_id": str, "seed": str, "owner": str})
    f["ant"] = f.antecedent.map(lambda x: tuple(x.split(" + ")))
    f["con"] = f.consequent.map(lambda x: (x,))
    f["itemset"] = [tuple(sorted(a+b)) for a,b in zip(f.ant,f.con)]
    B = f.groupby(KEYS)
    assert len(B) == 102
    assert set(f.config) == {"P5"} and set(f.unit) == {"combination"}
    assert B.size().eq(BUDGET).all()
    assert B.rule_id.nunique().eq(BUDGET).all() and B.itemset.nunique().eq(BUDGET).all()
    assert set(f.loc[f.control.eq("A1"),"seed"]) == {str(i) for i in range(1000,1100)}
    assert f.loc[f.control.eq("GL"),"method"].value_counts().to_dict() == {"G":90,"L":90}
    for _, z in B:
        assert sorted(z.position) == list(range(1,BUDGET+1))
    return f


def freeze(repo, dest, sha):
    if (dest / "freeze.json").exists() or (dest / "results").exists():
        raise SystemExit("Freeze or Test results already exist.")
    original = read_json(repo / "configs/test_frozen.json")
    source = repo / "experiments/validation_budget_redesign/results/global_local_A1_rule_paths.csv.gz"
    validation = repo / "experiments/validation_budget_redesign/results/verification.json"
    assert read_json(validation)["test_accessed"] is False
    f = pd.read_csv(source, keep_default_na=False, dtype={"rule_id":str,"seed":str,"owner":str})
    sel = f.loc[f.config.eq("P5") & f.unit.eq("combination") & f.position.le(BUDGET)]
    sel = sel.sort_values(KEYS + ["position"])
    dest.mkdir(parents=True, exist_ok=True)
    order = dest / "frozen_rule_lists.csv"
    sel.to_csv(order, index=False, lineterminator="\n")
    rosters(order)
    local = repo / "data/processed/local/D_validation"
    paths = [
        source, validation, repo/"src/online_trade/evaluation/quality.py",
        repo/"src/online_trade/evaluation/validation.py", repo/"scripts/run_frozen_test.py",
        local/"discovery_baskets.csv", local/"core/configurations.csv",
        local/"core/inputs/customer_clusters.csv", local/"core/inputs/item_taxonomy_v1.csv",
        repo/"data/taxonomy/item_taxonomy_v1.csv",
    ]
    spec = {
        "status":"frozen", "recorded_at":datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "status_relative_to_previous_test":"Exploratory follow-up on a historical Test period already reported under the original P5/100 restricted protocol.",
        "selection_source":"Dense Validation only; at Added Value >=10pp, 90 is the smallest budget within 1pp of both G/L maxima.",
        "config":"P5", "budget":BUDGET, "identity":"unique undirected category combination",
        "flow":"shared for all rules, with the chosen direction retained for rule quality",
        "primary_metrics":["shared complete co-occurrence order coverage",
                           "shared reliable order coverage with Added Value >=10pp"],
        "secondary_metrics":["rule quality pass share", "customer macro coverage",
                             "base quality_v1 with Added Value >=5pp", "global fallback on non-Profile orders"],
        "primary_contrasts":["paired L-G", "L compared with 100 A1 seeds"],
        "correction_family":"BY within each system, 90 selected directions only, shared evaluation scope; same family for strict and base quality.",
        "strict_quality":QUALITY, "base_quality":{**QUALITY,"min_confidence_uplift":.05},
        "test_window":original["test_window"], "source_baskets_sha256":original["source_baskets_sha256"],
        "a_snapshot_commit":original["a_snapshot_commit"],
        "bootstrap":dict(repeats=2000, seed=3111, unit="eligible customer"),
        "input_hashes":{p.relative_to(repo).as_posix():sha(p) for p in paths},
        "frozen_rule_lists_sha256":sha(order), "runner_sha256":sha(Path(__file__)),
        "refit_or_refill_in_test":False,
    }
    write_json(dest / "freeze.json", spec)
    print("Frozen 102 shared rule lists of 90 distinct undirected combinations each.", flush=True)


def run(repo, dest, sha, load_inputs, load_period, quality_type, adjust, classify, bootstrap):
    spec = read_json(dest / "freeze.json")
    assert spec["status"]=="frozen" and spec["budget"]==BUDGET and spec["strict_quality"]==QUALITY
    assert sha(Path(__file__))==spec["runner_sha256"]
    for path, digest in spec["input_hashes"].items():
        assert sha(repo/path)==digest, path
    candidates = dest / "frozen_rule_lists.csv"
    assert sha(candidates)==spec["frozen_rule_lists_sha256"]
    r = rosters(candidates)
    out = dest / "results"
    if out.exists():
        raise SystemExit("Test output already exists.")
    local = repo / "data/processed/local/D_validation"
    _, taxonomy, clusters, _, _, _ = load_inputs(local, repo, {"configs": ("P1","P2","P3","P4","P5")})
    discovery, _, _ = load_period(local, "discovery", taxonomy, clusters)

    runner = import_and_return("original_frozen_test_reader", repo / "scripts/run_frozen_test.py")
    index, fallback, audit = runner.test_index(spec, taxonomy, clusters)
    # The cohort is fixed by the Profile population and source snapshot, independent of the rules.
    assert (index.n,len(index.by_customer),fallback.n)==(5730,1510,5160)
    definitions = {z.rule_id:(z.ant,z.con) for z in r.itertuples()}
    engine = quality_type(index, discovery, {}, definitions)
    lookup = {k:index.mask(a+b) for k,(a,b) in definitions.items()}
    triggers = {k:index.mask(a) for k,(a,_b) in definitions.items()}
    results, details = [], []
    gl_masks = {}
    g = r.loc[r.method.eq("G")]
    fallback_union = 0
    for z in g.itertuples():
        fallback_union |= fallback.mask(z.itemset)
    eligible_totals = index.customer_counts(index.all)

    for key, table in r.groupby(KEYS, sort=False):
        control, method, seed = key
        ordered = table.sort_values("position")
        ids = ordered.rule_id.tolist()
        evidence = [engine.get("GLOBAL", rid) for rid in ids]
        q = adjust([e["p_combined"] for e in evidence], "BY")
        raw = strict = base = triggered = 0
        strict_pass = base_pass = 0
        for position,(rid,e,a) in enumerate(zip(ids,evidence,q),start=1):
            fact = {**e,"q_BY":float(a)}
            sb = classify(fact,spec["base_quality"])
            ss = classify(fact,spec["strict_quality"])
            raw |= lookup[rid]
            triggered |= triggers[rid]
            if sb=="accepted":
                base |= lookup[rid]
                base_pass += 1
            if ss=="accepted":
                strict |= lookup[rid]
                strict_pass += 1
            if control=="GL":
                details.append({"method":method,"position":position,**fact,
                                "strict_status":ss,"base_status":sb})
        assert not (strict & ~base) and not (base & ~raw) and not (raw & ~triggered)
        row = dict(zip(KEYS,key)) | {"orders":index.n,"unique_combinations":BUDGET,
                "triggered_orders":triggered.bit_count(),"triggered_coverage":triggered.bit_count()/index.n,
                "strict_passed":strict_pass,"strict_pass_share":strict_pass/BUDGET,
                "base_passed":base_pass,"base_pass_share":base_pass/BUDGET}
        for name, mask in (("raw",raw),("strict",strict),("base",base)):
            row[name+"_orders"] = mask.bit_count()
            row[name+"_coverage"] = mask.bit_count()/index.n
            row[name+"_customer_macro"] = (index.customer_counts(mask)/eligible_totals).mean()
            if control=="GL":
                gl_masks[method,name] = mask
        results.append(row)

    systems=pd.DataFrame(results)
    main=systems.loc[systems.control.eq("GL")].set_index("method")
    random=systems.loc[systems.control.eq("A1")]
    assert len(random)==100
    comparisons=[]
    for metric in ("raw_coverage","strict_coverage","base_coverage","raw_customer_macro",
                   "strict_customer_macro","base_customer_macro","strict_pass_share","base_pass_share"):
        values=random[metric]
        a,b=main.loc["G",metric],main.loc["L",metric]
        upper=int(values.ge(b).sum())
        comparisons.append(dict(metric=metric,G=a,L=b,L_minus_G=b-a,A1_min=values.min(),A1_median=values.median(),
                                A1_max=values.max(),A1_ge_L=upper,tail=(1+upper)/(1+len(values))))
    weights=np.random.default_rng(spec["bootstrap"]["seed"]).multinomial(
        len(eligible_totals), np.full(len(eligible_totals),1/len(eligible_totals)),
        size=spec["bootstrap"]["repeats"]).astype(float)
    bands=[]
    for m in ("raw","strict","base"):
        fitted=bootstrap(index,gl_masks["G",m],gl_masks["L",m],weights)
        for (contrast,metric),(estimate,lo,hi) in fitted.items():
            bands.append(dict(quality=m,metric=metric,contrast=contrast,estimate=estimate,low95=lo,high95=hi))
    overlaps=[]
    for name in ("raw","strict","base"):
        g,l=gl_masks["G",name],gl_masks["L",name]
        overlaps.append(dict(quality=name,both=(g&l).bit_count(),G_only=(g&~l).bit_count(),
                             L_only=(l&~g).bit_count(),union=(g|l).bit_count()))
    fallback_row={"orders":fallback.n,"G_hits":fallback_union.bit_count(),
                  "G_coverage":fallback_union.bit_count()/fallback.n}
    out.mkdir()
    systems.to_csv(out/"system_metrics.csv",index=False)
    pd.DataFrame(comparisons).to_csv(out/"a1_comparisons.csv",index=False)
    pd.DataFrame(bands).to_csv(out/"paired_intervals.csv",index=False)
    pd.DataFrame(overlaps).to_csv(out/"coverage_overlap.csv",index=False)
    pd.DataFrame(details).to_csv(out/"GL_rule_quality.csv",index=False)
    write_json(out/"verification.json",{"sample":audit,"fallback":fallback_row,
              "systems":len(systems),"rules_per_system":BUDGET,"test_refit":False,
              "freeze_sha256":sha(dest/"freeze.json")})
    print(main[["raw_coverage","strict_coverage","base_coverage","strict_pass_share"]].to_string(),flush=True)


def import_and_return(name,path):
    spec=spec_from_file_location(name,path)
    module=module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("freeze","run"))
    parser.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument("--dest",type=Path,default=Path(__file__).resolve().parent)
    args=parser.parse_args()
    repo=args.repo.resolve()
    sys.path.insert(0,str(repo/"src"))
    from online_trade.evaluation.validation import sha, load_inputs, load_period, bootstrap_pairs
    from online_trade.evaluation.quality import QualityEvidence, adjust_fdr, classify
    if args.action=="freeze":
        freeze(repo,args.dest,sha)
    else:
        run(repo,args.dest,sha,load_inputs,load_period,QualityEvidence,adjust_fdr,classify,bootstrap_pairs)


if __name__=="__main__":
    main()

