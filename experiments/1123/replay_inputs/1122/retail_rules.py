"""Mining, de-duplication, scoring, calibration and paired recommendation helpers."""
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pandas as pd

P5 = dict(support=.02, confidence=.4, lift=1.3, min_joint_count=20,
          min_antecedent_count=20, triple_increment_pp=10)
QUALITY = dict(min_antecedent_orders=20, min_joint_orders=10, min_antecedent_customers=10,
               min_joint_customers=5, max_customer_joint_share=.5, min_confidence_uplift=.05,
               min_lift=1.2, min_triple_increment_pp=5, adjustment="BY", alpha=.05)
GROUPS = ("0", "1", "2")


def runtime(repo):
    sys.path.insert(0, str(repo / "src"))
    from online_trade.evaluation.validation import BasketIndex
    from online_trade.evaluation.quality import QualityEvidence, adjust_fdr, classify

    source = repo / "experiments/discovery_residual_refill/run.py"
    spec = spec_from_file_location("frozen_direction_index", source)
    shared = module_from_spec(spec)
    spec.loader.exec_module(shared)
    return BasketIndex, QualityEvidence, adjust_fdr, classify, shared.DirectionIndex


def union(masks):
    mask = 0
    for value in masks:
        mask |= value
    return mask


def portion(i, n):
    return i / n if n else np.nan


@dataclass(frozen=True, slots=True)
class Rule:
    identifier: str
    antecedent: tuple
    consequent: str

    @property
    def combination(self):
        return tuple(sorted((*self.antecedent, self.consequent)))


@dataclass(frozen=True, slots=True)
class Ranked:
    key: int
    joint: int
    total: int
    confidence: float
    lift: float
    added: float
    gap: float


@dataclass(frozen=True, slots=True)
class Pick:
    group: str
    stats: Ranked
    score: float


class Book:
    def __init__(self, training, repo_runtime):
        BasketIndex, _, _, _, DirectionIndex = repo_runtime
        self.training = training
        self.orders = BasketIndex(training.customer_id, training.basket)
        self.direction = DirectionIndex(self.orders)
        items = sorted(self.orders.items)
        components = [(i,) for i in range(len(items))]
        components.extend(combinations(range(len(items)), 2))
        components.extend(z for z in combinations(range(len(items)), 3)
                          if self.orders.mask(items[i] for i in z).bit_count() >= 20)
        assert len(components) == len(self.direction.masks)
        labels = [tuple(items[i] for i in item) for item in components]
        self.rules = [
            Rule(rid, labels[a], labels[c][0])
            for rid, a, c in zip(self.direction.ids, self.direction.antecedent, self.direction.consequent)
        ]
        self.overall = np.array([mask.bit_count() for mask in self.direction.masks], dtype=np.int32)
        self.global_ranks = self.rank(self.orders.all)
        self.global_native = {r.key: r for r in self.global_ranks}
        self.ids = {r.identifier: i for i, r in enumerate(self.rules)}

    def rank(self, mask):
        if mask.bit_count() < 20:
            return []
        _, selected, _ = next(self.direction.ranks(mask, mask.bit_count(), {"P5": P5}))
        if not selected:
            return []
        counts = np.array([(hit & mask).bit_count() for hit in self.direction.masks], dtype=np.int32)
        n = mask.bit_count()
        idx = np.array(selected)
        j = counts[self.direction.joint[idx]]
        a = counts[self.direction.antecedent[idx]]
        c = counts[self.direction.consequent[idx]]
        oa = self.overall[self.direction.antecedent[idx]] - a
        oj = self.overall[self.direction.joint[idx]] - j
        conf = j / a
        base = c / n
        outside = np.divide(oj, oa, where=oa >= 20, out=np.full(len(a), np.nan))
        return [Ranked(*row) for row in zip(selected, map(int, j), map(int, a), conf, conf / base,
                                           conf - base, conf - outside)]

    def scopes(self, labels):
        return split_masks(labels, GROUPS)

    def local(self, labels):
        scopes = self.scopes(labels)
        return scopes, {group: self.rank(scope) for group, scope in scopes.items()}

    def prior(self, key):
        j = int(self.overall[self.direction.joint[key]])
        a = int(self.overall[self.direction.antecedent[key]])
        return (j + .5) / (a + 1)


def split_masks(labels, groups):
    masks = dict.fromkeys(groups, 0)
    for i, label in enumerate(labels):
        if label in masks:
            masks[label] |= 1 << i
    return masks


def quotas(size, budget):
    total = sum(size.values())
    weights = {g: divmod(budget * n, total) for g, n in size.items()}
    result = {g: x[0] for g, x in weights.items()}
    for group in sorted(weights, key=lambda g: (-weights[g][1], g))[:budget - sum(result.values())]:
        result[group] += 1
    return result


def native(r):
    return (r.joint, r.confidence, r.lift)


def scored(book, ranks, strategy, excluded=(), m=0):
    excluded = set(excluded)
    candidates = [r for r in ranks if r.key not in excluded]
    if strategy == "native":
        return [(r, float(r.confidence)) for r in candidates]
    if strategy == "gap":
        candidates = [r for r in candidates if np.isfinite(r.gap)]
    values = []
    for r in candidates:
        if strategy == "added":
            score = r.added
        elif strategy == "gap":
            score = r.gap
        elif strategy == "shrunk":
            p = (r.joint + m * book.prior(r.key)) / (r.total + m)
            score = p - (r.confidence - r.added)
        else:
            raise ValueError(strategy)
        values.append((r, float(score)))
    return sorted(values, key=lambda pair: (-pair[1], *[-n for n in native(pair[0])],
                                             book.rules[pair[0].key].identifier))


def select(book, ranks, sizes, budget, identity="direction"):
    """Allocate first, keep the picked identities and refill left-over unique slots."""
    def identity_of(r):
        return r.key if identity == "direction" else book.rules[r.key].combination

    limits = quotas(sizes, budget)
    pool, keys = [], set()
    contributed = dict.fromkeys(ranks, 0)

    def append(group, r, score):
        key = identity_of(r)
        if key in keys:
            return
        pool.append(Pick(group, r, score))
        contributed[group] += 1
        keys.add(key)

    cursors = {}
    for group, ordering in ranks.items():
        quota = min(limits[group], len(ordering))
        for r, score in ordering[:quota]:
            append(group, r, score)
        cursors[group] = quota
    while len(pool) < budget:
        available = []
        for group, ordering in ranks.items():
            i = cursors[group]
            while i < len(ordering) and identity_of(ordering[i][0]) in keys:
                i += 1
            cursors[group] = i
            if i < len(ordering):
                available.append(group)
        if not available:
            break
        group = min(available, key=lambda g: (Fraction(contributed[g], max(sizes[g], 1)), g))
        i = cursors[group]
        r, score = ranks[group][i]
        append(group, r, score)
        cursors[group] += 1
    return pool


def direct_pool(ranked, group="GLOBAL"):
    return [Pick(group, r, score) for r, score in ranked]


def greedy(book, picks, objective, budget, val_scopes, shared=True):
    candidates = []
    for pick in picks:
        rule = book.rules[pick.stats.key]
        scope = objective.all if shared else val_scopes[pick.group]
        hit = objective.mask(rule.combination) & scope
        candidates.append((pick, hit))
    covered, used, output = 0, set(), []
    for _ in range(min(budget, len(candidates))):
        possible = [(pick, mask) for pick, mask in candidates if book.rules[pick.stats.key].combination not in used]
        if not possible:
            break
        pick, mask = max(possible, key=lambda pair: ((pair[1] & ~covered).bit_count(), *native(pair[0].stats),
                                                   -int(book.rules[pair[0].stats.key].identifier, 16)))
        covered |= mask
        used.add(book.rules[pick.stats.key].combination)
        output.append(pick)
    return output


def full_hits(book, pool, val_index, val_scopes=None):
    return union(
        val_index.mask(book.rules[pick.stats.key].combination)
        & (val_index.all if val_scopes is None else val_scopes[pick.group])
        for pick in pool
    )


class SharedQuality:
    """Original quality_v1 evidence and BY correction on each de-duplicated system's family."""
    def __init__(self, book, validation, repo_runtime):
        _, Evidence, self.adjust, self.classify, _ = repo_runtime
        definitions = {str(i): (r.antecedent, (r.consequent,)) for i, r in enumerate(book.rules)}
        self.evidence = Evidence(validation, book.orders, {}, definitions)
        self.book = book

    def evaluate(self, pool):
        evidence = [self.evidence.get("GLOBAL", str(pick.stats.key)) for pick in pool]
        q = self.adjust([row["p_combined"] for row in evidence], "BY")
        accepted = [pick for pick, record, value in zip(pool, evidence, q)
                    if self.classify({**record, "q_BY": value}, QUALITY) == "accepted"]
        return full_hits(self.book, accepted, self.evidence.index), len(accepted)


class Arena:
    def __init__(self, view):
        self.view = view
        self.n = len(view)
        self.all = 0
        self.observed = defaultdict(int)
        self.target = defaultdict(int)
        for i, row in enumerate(view.itertuples(index=False)):
            if not row.target:
                continue
            bit = 1 << i
            self.all |= bit
            self.target[row.target] |= bit
            for item in row.observed:
                self.observed[item] |= bit

    @lru_cache(maxsize=None)
    def antecedent(self, items):
        mask = self.all
        for item in items:
            mask &= self.observed[item]
        return mask

    def proposals(self, book, pool, scopes=None):
        output = []
        for pick in sorted(pool, key=lambda x: (-x.score, -x.stats.joint, -x.stats.lift,
                                                book.rules[x.stats.key].identifier, x.group)):
            rule = book.rules[pick.stats.key]
            scope = self.all if scopes is None else scopes[pick.group]
            output.append((rule.consequent, self.antecedent(rule.antecedent) & ~self.observed[rule.consequent] & scope))
        return output

    def popular(self, book, training_scopes=None, output_scopes=None):
        if training_scopes is None:
            training_scopes, output_scopes = {"GLOBAL": book.orders.all}, {"GLOBAL": self.all}
        result = []
        for group, scope in training_scopes.items():
            freq = {item: (mask & scope).bit_count() for item, mask in book.orders.items.items()}
            result.extend((category, output_scopes[group] & self.all & ~self.observed[category])
                          for category in sorted(freq, key=lambda c: (-freq[c], c)) if freq[category])
        return result

    def replay(self, proposals):
        rank_hits = [0] * 5
        rank_masks = [self.all] + [0] * 5
        first4, fifth = defaultdict(int), defaultdict(int)
        for category, mask in proposals:
            mask &= ~first4[category] & ~fifth[category] & ~rank_masks[5]
            if not mask:
                continue
            in5 = mask & rank_masks[4]
            fifth[category] |= in5
            first4[category] |= mask & ~in5
            hit = mask & self.target[category]
            for k in range(5, 0, -1):
                rank_hits[k - 1] |= hit & rank_masks[k - 1] & ~rank_masks[k]
                rank_masks[k] |= mask & rank_masks[k - 1]
        return rank_hits, rank_masks, first4, fifth

    def slot5(self, baseline, proposals):
        hits, masks, first4, fifth = baseline
        chosen = changed = correct = 0
        for category, mask in proposals:
            new = mask & masks[5] & ~chosen & ~first4[category]
            chosen |= new
            changed |= new & ~fifth[category]
            correct |= new & self.target[category]
        assert chosen & ~masks[5] == 0
        return union(hits[:4]) | (hits[4] & ~chosen) | correct, changed, chosen

    def subset(self, selection):
        return split_masks(np.where(selection, "yes", "no"), ["yes"])["yes"] & self.all


def report_hits(row, system, baseline, scope):
    before, after = baseline & scope, system & scope
    n = scope.bit_count()
    wins, losses = (after & ~before).bit_count(), (before & ~after).bit_count()
    return {**row, "orders": n, "baseline_hits": before.bit_count(), "hits": after.bit_count(),
            "rate": portion(after.bit_count(), n), "new_hits": wins, "lost_hits": losses,
            "net_orders": wins - losses, "delta_pp": 100 * portion(wins - losses, n)}


class Paired:
    """Resample identified customers. Use dates as blocks for otherwise unlinked anonymous orders."""
    def __init__(self, frame, scope, repeats=1500):
        self.n = len(frame)
        labels = np.where(frame.customer_id.ne(""), "C:" + frame.customer_id, "DATE:" + frame.date.str[:10])
        _, codes = np.unique(labels, return_inverse=True)
        active = self.vector(scope)
        self.groups, self.codes = np.unique(codes[active], return_inverse=True)
        n = len(self.groups)
        self.active = active
        self.weights = np.random.default_rng(1122).multinomial(n, np.ones(n) / n, size=repeats)
        self.weights = self.weights.astype(np.float64)
        self.den = self.weights @ np.bincount(self.codes, minlength=n)

    def vector(self, mask):
        bit_bytes = mask.to_bytes((self.n + 7) // 8, "little")
        return np.unpackbits(np.frombuffer(bit_bytes, dtype=np.uint8), count=self.n, bitorder="little").astype(bool)

    def interval(self, left, right):
        lv = self.vector(left)[self.active].astype(int)
        rv = self.vector(right)[self.active].astype(int)
        counts = np.bincount(self.codes, weights=lv - rv, minlength=len(self.groups))
        values = 100 * (self.weights @ counts) / self.den
        lo, hi = np.quantile(values, [.025, .975])
        return dict(low95_pp=float(lo), high95_pp=float(hi), resampling_blocks=len(self.groups))

