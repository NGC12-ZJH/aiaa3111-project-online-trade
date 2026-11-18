"""Independent small examples for denominator, scope and zero-count semantics."""
import unittest
import numpy as np
from online_trade.evaluation.validation import BasketIndex, rule_evidence, bootstrap_pairs


class ValidationSemantics(unittest.TestCase):
    def setUp(self):
        self.index = BasketIndex(['u', 'u', 'v', 'w'], [{'a', 'b'}, {'a'}, {'b'}, set()])
        self.thresholds = dict(min_antecedent_count=1, min_joint_count=1, support=.1,
                               confidence=.2, lift=.5, triple_increment_pp=float('nan'))

    def test_counts_keep_empty_and_single_baskets(self):
        e = rule_evidence(self.index, self.index.all, ['a'], ['b'], self.thresholds)
        self.assertEqual((e['n_baskets'], e['antecedent_count'], e['joint_count']), (4, 2, 1))
        self.assertEqual(e['support'], .25)
        self.assertEqual(e['confidence'], .5)
        self.assertEqual(e['lift'], 1.)

    def test_restricted_does_not_apply_other_group_rule(self):
        scope = self.index.scope({'u': '0', 'v': '1', 'w': '1'}, '1')
        e = rule_evidence(self.index, scope, ['a'], ['b'], self.thresholds)
        self.assertEqual(e['n_baskets'], 2)
        self.assertTrue(np.isnan(e['confidence']))
        self.assertTrue(np.isnan(e['lift']))
        self.assertEqual(e['fate'], 'not_triggered')

    def test_no_future_joint_is_distinct_from_not_triggered(self):
        e = rule_evidence(self.index, self.index.all, ['a'], ['unseen'], self.thresholds)
        self.assertEqual(e['confidence'], 0)
        self.assertTrue(np.isnan(e['lift']))
        self.assertEqual(e['fate'], 'triggered_no_joint')

    def test_union_counts_order_once_and_direction_differs(self):
        a = self.index.mask(['a']); b = self.index.mask(['b'])
        self.assertEqual(((a & b) | (b & a)).bit_count(), 1)
        self.assertEqual(a.bit_count(), 2)
        self.assertEqual(b.bit_count(), 2)

    def test_customer_bootstrap_preserves_repeat_orders(self):
        # One replicate with each active customer exactly once must recover point estimates.
        r = bootstrap_pairs(self.index, 1, 4, np.ones((1, 3)))
        self.assertAlmostEqual(r['L_minus_G', 'order'][0], 0)
        self.assertAlmostEqual(r['G', 'customer_macro'][0], 1 / 6)
        self.assertAlmostEqual(r['L', 'customer_macro'][0], 1 / 3)

    def test_triple_increment_recomputes_single_antecedents(self):
        idx = BasketIndex(['1', '2', '3', '4'], [{'a','b','c'}, {'a','c'}, {'b'}, set()])
        t = dict(self.thresholds, triple_increment_pp=5)
        e = rule_evidence(idx, idx.all, ['a','b'], ['c'], t)
        self.assertEqual(e['confidence'], 1)
        self.assertEqual(e['confidence_increment_pp'], 0)
        self.assertEqual(e['fate'], 'observed_below_threshold')


if __name__ == '__main__':
    unittest.main()
