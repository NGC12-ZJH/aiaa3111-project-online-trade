import unittest
from online_trade.evaluation.hybrid import merge_lists,union_mask
from online_trade.evaluation.validation import BasketIndex


class HybridRules(unittest.TestCase):
    def test_deduplicate_without_refill_and_match_actual_k(self):
        g=[str(i) for i in range(100)]
        l=['0']*40+['80']*5+['81']*5
        hybrid,matched=merge_lists(g[:50],l,g)
        self.assertEqual(len(hybrid),52);self.assertEqual(matched,g[:52])
        self.assertEqual(set(hybrid)-set(g[:50]),{'80','81'})

    def test_no_new_rules_means_identical_comparison(self):
        g=[str(i) for i in range(100)]
        hybrid,matched=merge_lists(g[:50],g[:25]*2,g)
        self.assertEqual(hybrid,matched)

    def test_new_rules_do_not_guarantee_better_coverage(self):
        idx=BasketIndex(['x','y','z'],[{'a','b'},{'a','c'},{'d'}])
        definitions={'ab':(('a',),('b',)),'ba':(('b',),('a',)),'ac':(('a',),('c',))}
        self.assertEqual(union_mask(idx,definitions,['ab','ba']).bit_count(),1)
        self.assertEqual(union_mask(idx,definitions,['ab','ac']).bit_count(),2)


if __name__=='__main__':unittest.main()
