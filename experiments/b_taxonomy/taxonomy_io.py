"""Shared loaders for taxonomy_v1: catalog, embeddings, gold set, prefix families, taxonomy files and seed labels."""
import json

import numpy as np
import pandas as pd

from paths import CACHE, ROOT, TAXONOMY

V1_WORK = TAXONOMY / "v1_work"
GOLD_DIR = TAXONOMY / "gold"
LLM_CACHE = TAXONOMY / "llm_cache" / "llm_cache.jsonl"
TAX_CFG = ROOT / "configs" / "taxonomy"
PROMPTS = ROOT / "configs" / "prompts"
for p in (V1_WORK, GOLD_DIR, LLM_CACHE.parent):
    p.mkdir(parents=True, exist_ok=True)


def prefix(code):
    return str(code)[:5]


def load_catalog():
    """One row per stock code, in the same order as embeddings.npy (sorted stock_code)."""
    cat = pd.read_csv(TAXONOMY / "item_taxonomy_v0.csv", dtype={"stock_code": str})
    var = pd.read_csv(TAXONOMY / "item_description_variants.csv", dtype=str).set_index("stock_code").variants
    cat["variants"] = cat.stock_code.map(var).map(json.loads)
    cc = pd.read_csv(CACHE / "catalog_clusters.csv", dtype={"stock_code": str}, usecols=["stock_code", "first_seen"])
    cat = cat.merge(cc, on="stock_code", how="left")
    assert list(cc.stock_code) == list(cat.stock_code), "catalog order must match embeddings.npy"
    return cat.reset_index(drop=True)


def load_embeddings():
    return np.load(CACHE / "embeddings.npy")


def gold_codes():
    f = GOLD_DIR / "gold_items_v1.csv"
    return set(pd.read_csv(f, dtype=str).stock_code) if f.exists() else set()


def load_taxonomy(path):
    tax = json.loads((ROOT / path).read_text() if not str(path).startswith("/") else open(path).read())
    tax["l2_ids"] = [c["id"] for c in tax["l2"]] + ["other"]
    tax["l1_of"] = {c["id"]: c["l1"] for c in tax["l2"]} | {"other": "other"}
    return tax


def load_seed_labels(tax):
    return pd.read_csv(ROOT / tax["seed_labels"], dtype=str)


def pick_examples(cat, E, seeds, l2, exclude, n=3, diverse=False):
    """n seed items of an L2 closest to its centroid (text embedding), skipping excluded codes.
    diverse=True: each example from a different 5-character prefix family and not a near-duplicate wording
    (cosine < 0.85 to examples already chosen, different first two words), falling back to the plain order if too few remain."""
    pool = seeds[(seeds.l2_id == l2) & ~seeds.stock_code.isin(exclude)]
    if pool.empty:
        return []
    idx = cat.index[cat.stock_code.isin(pool.stock_code)]
    c = E[idx].mean(0)
    order = idx[np.argsort(-(E[idx] @ c))]
    if not diverse:
        return list(cat.loc[order[:n], "canonical_description"])
    chosen, fams, heads = [], set(), set()
    for i in order:
        f = prefix(cat.stock_code[i])
        h = " ".join(cat.canonical_description[i].split()[:2])
        if f in fams or h in heads or any(float(E[i] @ E[j]) >= 0.85 for j in chosen):
            continue
        chosen.append(i)
        fams.add(f)
        heads.add(h)
        if len(chosen) == n:
            break
    for i in order:  # fallback for small subcategories
        if len(chosen) == n:
            break
        if i not in chosen:
            chosen.append(i)
    return list(cat.loc[chosen, "canonical_description"])
