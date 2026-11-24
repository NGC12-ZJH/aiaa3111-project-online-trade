"""Run four Discovery/Validation diagnostics for the published 1123 experiment."""
import argparse
from collections import Counter
from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import RobustScaler, StandardScaler
from threadpoolctl import threadpool_limits

HERE = Path(__file__).resolve().parent
B = 120


def shuffled(labels, cells, seeds):
    positions = [np.flatnonzero(cells == s) for s in sorted(set(cells))]
    for seed in seeds:
        rng = np.random.default_rng(seed)
        draw = labels.copy()
        for pos in positions:
            draw[pos] = rng.permutation(labels[pos])
            assert Counter(draw[pos]) == Counter(labels[pos])
        yield str(seed), draw


def partitions(original, repo, common, inputs, out):
    from online_trade.clustering.features import feature_matrix
    from online_trade.clustering.methods import order_by_value

    profile, _ = original.profile_features(repo, common, inputs)
    names = original.RFM + original.FORM
    data = profile.loc[:, list(names)].copy()
    for c in ("frequency", "monetary", "qty", "skus", "price"):
        data[c] = np.log1p(data[c])
    old = common.read_json(HERE.parent / "results/profile_audit.json")["label_sequence_sha256"]
    frequency = pd.cut(profile.frequency, [0, 1, 2, 4, 9, np.inf],
                       labels=["1", "2", "3-4", "5-9", "10+"]).astype(str).to_numpy()
    tertiles = pd.qcut(profile.mean_basket_size.rank(method="first"), 3, labels=False).astype(str).to_numpy()
    b2 = np.array([f"{a}|{b}" for a, b in zip(frequency, tertiles)])
    rng = np.random.default_rng(1123)
    draws = [rng.choice(len(profile), int(.8*len(profile)), replace=False) for _ in range(50)]
    maps, rows, strata = {}, [], []
    for variant, cols in original.FEATURES.items():
        x = data.loc[:, list(cols)].to_numpy()
        labels_by_scaler = {}
        for key, scaler in (("zscore", StandardScaler), ("robust", RobustScaler)):
            z = scaler().fit_transform(x)
            fit = KMeans(n_clusters=3, n_init=10, random_state=42).fit(z)
            labels = order_by_value(feature_matrix(profile), fit.labels_).astype(str)
            labels_by_scaler[key] = labels
            for j, sample in enumerate(draws):
                transform = scaler().fit(x[sample])
                sub = KMeans(n_clusters=3, n_init=10, random_state=42).fit(transform.transform(x[sample]))
                predicted = sub.predict(transform.transform(x))
                rows.append(dict(variant=variant, scaler=key, draw=j, ari=adjusted_rand_score(labels, predicted)))
            rows[-1]["silhouette"] = float(silhouette_score(z, labels))
        labels = labels_by_scaler["zscore"]
        assert common.hashlib.sha256("|".join(labels).encode()).hexdigest() == old[variant]
        for key, assigned in (("GL", labels), ("ROBUST", labels_by_scaler["robust"])):
            maps[key, variant, ""] = dict(zip(profile.index, assigned))
        for control, cells in (("S", np.zeros(len(labels))), ("A1", frequency), ("B2", b2)):
            for seed, draw in shuffled(labels, cells, original.SEEDS):
                maps[control, variant, seed] = dict(zip(profile.index, draw))
        for cell in sorted(set(b2)):
            for g in original.GROUPS:
                strata.append(dict(variant=variant, cell=cell, group=g, customers=int(((b2 == cell)&(labels == g)).sum())))
        rows[-1]["ari_vs_zscore"] = adjusted_rand_score(labels, labels_by_scaler["robust"])
    detail = pd.DataFrame(rows)
    stats = detail.groupby(["variant","scaler"]).agg(
        silhouette=("silhouette","max"), mean_ari=("ari","mean"), sd_ari=("ari","std"),
        p10_ari=("ari",lambda x:x.quantile(.1)), ari_vs_zscore=("ari_vs_zscore","max")).reset_index()
    common.csv(detail.drop(columns=["silhouette","ari_vs_zscore"]), out/"stability_draws.csv")
    common.csv(stats, out/"stability_summary.csv")
    common.csv(pd.DataFrame(strata), out/"B2_strata.csv")
    for seed in original.SEEDS:
        assert maps["A1","rfm",str(seed)] == inputs.mappings["A1","R",str(seed)]
    return maps


def bc(a, b):
    return np.abs(a-b).sum()/(a+b).sum()


def distinct(common, original, disc, val, maps, out):
    cats = sorted(disc.items)
    families = {n: [c for c in combinations(cats,n) if disc.mask(c).bit_count() >= 20] for n in (2,3)}
    rows, details, identity = [], [], []
    profiles = {}
    for period, index in (("discovery",disc),("validation",val)):
        masks = {n:[index.mask(c) for c in family] for n, family in families.items()}
        totals = {n:np.array([v.bit_count() for v in bits]) for n,bits in masks.items()}
        for (control, variant, seed), mapping in maps.items():
            if control == "ROBUST":
                continue
            groups = [index.scope(mapping,g) for g in original.GROUPS]
            orders = np.array([g.bit_count() for g in groups])
            assert orders.sum() == index.n and min(orders) > 0
            for n, bits in masks.items():
                count = np.array([[(hit & g).bit_count() for hit in bits] for g in groups])
                support = count/orders[:,None]
                rest = (totals[n]-count)/(index.n-orders[:,None])
                distances = [bc(a,b) for a,b in zip(support,rest)]
                rows.append(dict(period=period, variant=variant, control=control, seed=seed, length=n,
                    rest_bc=np.mean(distances), pair_bc=np.mean([bc(support[i],support[j]) for i,j in combinations(range(3),2)])))
                if control=="GL":
                    details.extend(dict(period=period,variant=variant,length=n,group=j,orders=orders[j],rest_bc=x)
                                   for j,x in enumerate(distances))
            if control=="GL":
                profiles[period,variant] = np.array([[(g & index.items.get(c,0)).bit_count()/o for c in cats]
                                                      for g,o in zip(groups,orders)])
        print(f"Bray–Curtis {period} complete.", flush=True)
    for variant in original.VARIANTS:
        for i,v in enumerate(profiles["validation",variant]):
            d = [bc(v,a) for a in profiles["discovery",variant]]
            identity.extend(dict(variant=variant,validation_group=i,discovery_group=j,distance=x,
                                 closest=j==int(np.argmin(d))) for j,x in enumerate(d))
    frame = pd.DataFrame(rows)
    summary=[]
    for (period, variant, length), group in frame.groupby(["period","variant","length"]):
        for metric in ("rest_bc","pair_bc"):
            real=group.loc[group.control.eq("GL"),metric].iloc[0]
            for ctl in ("S","A1","B2"):
                random=group.loc[group.control.eq(ctl),metric]
                assert len(random)==100
                ge=int(random.ge(real-1e-12).sum())
                summary.append(dict(period=period,variant=variant,length=length,metric=metric,control=ctl,
                    real=real,median=random.median(),min=random.min(),max=random.max(),gap=real-random.median(),
                    random_ge=ge,tail=(1+ge)/101))
    for name,d in (("distinct_systems",frame),("distinct_summary",pd.DataFrame(summary)),
                   ("distinct_groups",pd.DataFrame(details)),("profile_cross_phase",pd.DataFrame(identity))):
        common.csv(d,out/f"{name}.csv")
    return {n:len(f) for n,f in families.items()}


def roster_row(disc,index,definitions,key,position,direction,g,rank):
    a,c=definitions[str(direction)]
    joint=disc.mask(a+c).bit_count()
    conf=joint/disc.mask(a).bit_count()
    return (*key,"P5",position,g,index.ids[direction],rank," + ".join(a),c[0],conf,joint,
            conf/(disc.mask(c).bit_count()/disc.n))


def evaluate(original,common,inputs,repo,period,maps,out):
    dense=common.module("dense",repo/"experiments/validation_budget_redesign/run.py")
    disc=inputs.discovery
    index,defs=dense.prepare_index(repo,disc)
    cfg={"P5":inputs.configs["P5"]}
    old=common.read_csv(HERE.parent/"results/frozen_rule_lists.csv")
    additions=[]
    for key,mapping in maps.items():
        if key[0] not in ("B2","ROBUST"):
            continue
        scopes={g:disc.scope(mapping,g) for g in original.GROUPS}
        sizes={g:m.bit_count() for g,m in scopes.items()}
        ranks={g:next(index.ranks(m,sizes[g],cfg))[1] for g,m in scopes.items()}
        pool=common.nested(index,ranks,sizes,B)
        assert len(pool)==B
        additions.extend(roster_row(disc,index,defs,key,p,r,g,t)
                         for p,(r,g,t) in enumerate(pool,1))
    global_order=next(index.ranks(disc.all,disc.n,cfg))[1]
    representatives={}
    for rank,r in enumerate(global_order,1):
        representatives.setdefault(index.joint[r],(r,rank,index.masks[index.joint[r]]))
    todo=list(representatives.values())
    covered=0
    greedy=[]
    for i in range(1,B+1):
        k=max(range(len(todo)),key=lambda j:(todo[j][2]&~covered).bit_count())
        r,rank,mask=todo.pop(k)
        greedy.append((mask&~covered).bit_count())
        covered|=mask
        additions.append(roster_row(disc,index,defs,("GL","G_greedy",""),i,r,"GLOBAL",rank))
    frame=pd.concat([old,pd.DataFrame(additions,columns=old.columns)],ignore_index=True)
    for _,block in frame.groupby(common.KEY):
        combo=[tuple(sorted(a.split(" + ")+[c])) for a,c in zip(block.antecedent,block.consequent)]
        assert len(block)==len(set(combo))==B
    systems, quality, masks=common.coverage_systems(inputs,period,frame,B)
    popular=common.read_csv(HERE.parent/"results/discovery_popularity.csv").l2_id.tolist()
    top,hits,eligible=common.recommend(repo,period,frame,popular)
    merged=systems.merge(top.loc[top["sample"].eq("all"),common.KEY+["hit_at_5","ndcg_at_5"]],on=common.KEY)
    summary=[]
    for variant in original.VARIANTS:
        subset=merged.loc[merged.method.eq(variant)]
        actual=subset.loc[subset.control.eq("GL")].iloc[0]
        for c in ("A1","B2"):
            rand=subset.loc[subset.control.eq(c)]
            assert len(rand)==100
            for m in ("raw_coverage","reliable_coverage","quality_pass_share","hit_at_5"):
                v=rand[m]
                summary.append(dict(variant=variant,control=c,metric=m,real=actual[m],median=v.median(),
                                    min=v.min(),max=v.max(),random_ge=int(v.ge(actual[m]-1e-12).sum())))
    g=masks["G","P5",B][0]
    overlaps=[]
    for method in ("G_greedy",*original.VARIANTS):
        l=masks[method,"P5",B][0]
        past=old.loc[old.control.eq("GL") & old.method.eq("G"),"rule_id"]
        other=frame.loc[frame.control.eq("GL") & frame.method.eq(method),"rule_id"]
        overlaps.append(dict(method=method,both=(g&l).bit_count(),G_only=(g&~l).bit_count(),
                             other_only=(l&~g).bit_count(),same_directions=len(set(past)&set(other))))
    runs=[]; samples={}
    for method in ("G_greedy",*original.VARIANTS):
        for i,m in enumerate(("raw_coverage","reliable_coverage")):
            scope=period.store if i==0 else period.identified
            name=f"{method}_minus_G:{m}"
            runs.append((name,masks["G","P5",B][i],masks[method,"P5",B][i],scope.all));samples[name]=scope
        name=f"{method}_minus_G:hit_at_5"
        runs.append((name,hits["GL","G",""],hits["GL",method,""],eligible));samples[name]=period.store
    for name,d in (("validation_systems",merged),("validation_controls",pd.DataFrame(summary)),
                   ("validation_overlap",pd.DataFrame(overlaps)),("validation_paired",common.intervals(period,runs,samples)),
                   ("validation_rosters",frame.loc[frame.control.ne("A1")]),("validation_GL_quality",quality),
                   ("G_greedy_discovery",pd.DataFrame({"position":range(1,B+1),"new_orders":greedy}))):
        common.csv(d,out/f"{name}.csv")
    print("B2, G greedy and robust-scaling Validation complete.",flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=Path,default=HERE.parent)
    parser.add_argument("--out",type=Path,default=HERE/"results")
    args=parser.parse_args()
    project=args.project.resolve(); repo=project.parent/"repository";out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(repo/"src"))
    from importlib.util import module_from_spec,spec_from_file_location
    spec=spec_from_file_location("main1123",project/"run.py")
    original=module_from_spec(spec);spec.loader.exec_module(original)
    spec=spec_from_file_location("sharedD",repo/"experiments/shared_full_store/run.py")
    common=module_from_spec(spec);spec.loader.exec_module(common)
    inputs=common.Inputs(repo)
    with threadpool_limits(limits=2):
        maps=partitions(original,repo,common,inputs,out)
        val,_,_=__import__("online_trade.evaluation.validation",fromlist=["load_period"]).load_period(
            inputs.local,"validation",inputs.taxonomy,inputs.profile)
        counts=distinct(common,original,inputs.discovery,val,maps,out)
        window=common.read_json(repo/"configs/experiment.json")["validation"]
        data=pd.read_csv(inputs.local/"validation_baskets.csv",dtype=str,keep_default_na=False)
        period=common.Period(data,inputs.taxonomy,inputs.profile,window)
        evaluate(original,common,inputs,repo,period,maps,out)
    common.write_json(out/"audit.json",dict(protocol_sha256=common.sha(HERE/"README.md"),test_loaded=False,
        phase_baskets=[inputs.discovery.n,val.n],comparative_sample=period.audit,
        distinct_combinations=counts,roster_budget=B))


if __name__=="__main__":
    main()
