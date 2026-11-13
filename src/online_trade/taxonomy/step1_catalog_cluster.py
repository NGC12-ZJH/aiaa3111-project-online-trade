"""Step 1: build the item catalog, embed cleaned descriptions, and cluster schema items.

Only codes first seen before 2010-12-01 shape the clusters; later codes are assigned to the
nearest existing centroid. No sales, co-purchase, customer or cluster information is used for
labels; Discovery line counts are kept only to order the human review sheet.
"""
import json
import re

import numpy as np
import pandas as pd
import torch
from sklearn.cluster import KMeans
from transformers import AutoModel, AutoTokenizer

from .paths import CACHE, EMBED_MODEL, EMBED_REVISION, INPUT, N_CLUSTERS, RESULTS, SCHEMA_CUTOFF, SEED, TAXONOMY

COLOUR_SIZE_WORDS = set("""red pink blue green white black ivory cream yellow purple orange silver gold brown grey gray
natural antique vintage spotty spots spot retrospot polkadot dots dot stripe stripes stripey paisley baroque pastel
bright dark clear colour coloured assorted finish floral lilac turquoise magenta small large mini medium jumbo set of
pack the and with in design piece s/2 s/3 s/4 s/6 s/12 sml lge med""".split())


def clean_text(desc):
    words = [w for w in re.findall(r"[a-z][a-z'\-/]*", desc.lower()) if w not in COLOUR_SIZE_WORDS]
    return " ".join(words) if words else desc.lower()


def build_catalog():
    t = pd.read_csv(INPUT / "clean_transactions.csv.gz", dtype=str,
                    usecols=["stock_code", "description", "split", "is_valid_basket_item", "invoice_datetime"])
    t = t[t.is_valid_basket_item == "1"].dropna(subset=["description"])
    t["description"] = t.description.str.strip().str.replace(r"\s+", " ", regex=True)
    first = t.sort_values(["invoice_datetime", "description"]).groupby("stock_code").head(1).set_index("stock_code")
    rows = []
    for code, g in t.groupby("stock_code"):
        split = first.loc[code, "split"]
        counts = g[g.split == split].description.value_counts()
        canonical = sorted(counts[counts == counts.max()].index)[0]  # most common wording in first-seen split
        rows.append(dict(stock_code=code, canonical_description=canonical, first_seen_split=split,
                         first_seen=first.loc[code, "invoice_datetime"], n_variants=g.description.nunique(),
                         variants=json.dumps(sorted(g.description.unique()))))
    cat = pd.DataFrame(rows)
    cat["schema_item"] = cat.first_seen < SCHEMA_CUTOFF
    disc = t[t.split == "discovery"].stock_code.value_counts()
    cat["discovery_lines"] = cat.stock_code.map(disc).fillna(0).astype(int)
    cat["clean_text"] = cat.canonical_description.map(clean_text)
    return cat


def embed(texts):
    tok = AutoTokenizer.from_pretrained(EMBED_MODEL, revision=EMBED_REVISION)
    model = AutoModel.from_pretrained(EMBED_MODEL, revision=EMBED_REVISION).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 256):
            batch = tok(texts[i:i + 256], padding=True, truncation=True, return_tensors="pt")
            hidden = model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).float()
            vec = (hidden * mask).sum(1) / mask.sum(1)
            out.append(torch.nn.functional.normalize(vec, dim=1).numpy())
    return np.vstack(out)


if __name__ == "__main__":
    torch.manual_seed(SEED)
    cat = build_catalog()
    E = embed(list(cat.clean_text))
    schema = cat.schema_item.values
    km = KMeans(n_clusters=N_CLUSTERS, n_init=10, random_state=SEED).fit(E[schema])
    C = km.cluster_centers_ / np.linalg.norm(km.cluster_centers_, axis=1, keepdims=True)
    sim = E @ C.T
    cat["cluster"] = sim.argmax(1)
    cat["cluster_sim"] = sim.max(1).round(3)
    np.save(CACHE / "embeddings.npy", E)
    cat.drop(columns=["variants"]).to_csv(CACHE / "catalog_clusters.csv", index=False)
    cat[["stock_code", "variants"]].to_csv(TAXONOMY / "item_description_variants.csv", index=False)
    with open(RESULTS / "cluster_review_v0.txt", "w") as f:
        f.write("# Text clusters of schema items (first seen before 2010-12-01); top descriptions by Discovery lines\n")
        for k, g in cat[cat.schema_item].groupby("cluster"):
            g = g.sort_values(["discovery_lines", "stock_code"], ascending=[False, True])
            f.write(f"#{k} n={len(g)} | " + " ; ".join(g.canonical_description.head(7)) + "\n")
    print("codes", len(cat), "| first-seen split", cat.first_seen_split.value_counts().to_dict(),
          "| schema items", int(schema.sum()), "| clusters", N_CLUSTERS)
