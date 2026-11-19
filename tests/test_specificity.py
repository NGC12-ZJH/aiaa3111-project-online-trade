import unittest
import numpy as np
import pandas as pd
from online_trade.evaluation.specificity import diff_test,content_row,FamilyStats,PeriodVectors,measure
from online_trade.evaluation.validation import BasketIndex


class SpecificitySemantics(unittest.TestCase):
    def test_disjoint_group_variances_and_direction(self):
        d,lo,hi,p=diff_test(.6,.02,100,.3,.03,200)
        self.assertAlmostEqual(d,.3);self.assertLess(lo,d);self.assertGreater(hi,d);self.assertLess(p,.001)
        inverse=diff_test(.3,.03,200,.6,.02,100);self.assertAlmostEqual(inverse[0],-.3);self.assertGreater(inverse[-1],.999)

    def test_global_includes_target_and_pooled_rest_is_disjoint(self):
        index=BasketIndex(['u','v','w','z'],[{'a','b'},{'a'},{'b'},set()])
        engine=FamilyStats(PeriodVectors(index),{'u':'0','v':'0','w':'1','z':'2'},{'r':(('a',),('b',))})
        c=engine.get('0','r');rest=engine.get('rest0','r');g=engine.get('GLOBAL','r')
        for k in ['n','a','c','j']:self.assertEqual(c[k]+rest[k],g[k])
        self.assertEqual(c['confidence'],.5);self.assertTrue(np.isnan(rest['confidence']))

    def test_rule_overlap_is_not_group_specificity(self):
        a=pd.DataFrame({'rule_id':['x','x','y'],'combination_id':['xy','xy','yz']})
        g=pd.DataFrame({'rule_id':['x','z'],'combination_id':['xy','zx']})
        d=content_row(a,g,{'x','y','z'},'system')
        self.assertEqual(d['local_slots'],3);self.assertEqual(d['local_unique_rules'],2)
        self.assertAlmostEqual(d['jaccard_rules'],1/3);self.assertEqual(d['local_novel_share'],.5)
        self.assertEqual(d['local_rules_absent_G100'],0)

    def test_degenerate_variance_is_not_infinite_evidence(self):
        d,lo,hi,p=diff_test(.8,0,20,.2,0,20)
        self.assertAlmostEqual(d,.6);self.assertEqual(p,1.);self.assertTrue(np.isnan(lo))

    def test_group_masks_keep_every_order_of_repeated_customer(self):
        index=BasketIndex(['u','v','u','w'],[{'a','b'},{'a'},{'a','c'},{'c'}])
        engine=FamilyStats(PeriodVectors(index),{'u':'0','v':'1','w':'2'},{'r':(('a',),('b',))})
        self.assertEqual(engine.masks['0'],0b0101)
        self.assertEqual(engine.masks['rest0'],0b1010)
        self.assertEqual(engine.masks['GLOBAL'],0b1111)

    def test_higher_confidence_due_to_popularity_is_not_advantage(self):
        customers=[];baskets=[];mapping={}
        def add(group,n,a,c,j):
            group_baskets=[{'a','b'}]*j+[{'a'}]*(a-j)+[{'b'}]*(c-j)+[set()]*(n-a-c+j)
            for i,b in enumerate(group_baskets):
                customer=f'{group}_{i}';customers.append(customer);baskets.append(b);mapping[customer]=group
        add('0',200,50,100,30);add('1',100,25,10,7);add('2',100,25,10,8)
        engine=FamilyStats(PeriodVectors(BasketIndex(customers,baskets)),mapping,{'r':(('a',),('b',))})
        thresholds=dict(min_antecedent_orders=20,min_joint_orders=10,min_antecedent_customers=10,min_joint_customers=5,
                        max_customer_joint_share=.5,min_confidence_uplift=.05,min_lift=1.2,min_triple_increment_pp=5)
        result=measure(engine,'0','r',thresholds)
        self.assertAlmostEqual(result['confidence_gap_vs_rest_pp'],30)
        self.assertAlmostEqual(result['association_gap_vs_rest_pp'],-10)
        self.assertFalse(result['advantage_candidate'])


if __name__=='__main__':unittest.main()
