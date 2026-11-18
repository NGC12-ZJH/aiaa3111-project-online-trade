import unittest
import numpy as np
from online_trade.evaluation.quality import adjust_fdr,ratio_contrast,classify,QualityEvidence
from online_trade.evaluation.validation import BasketIndex


class QualitySemantics(unittest.TestCase):
    def test_by_known_adjusted_values_and_order(self):
        p=[.04,.001,.01]
        np.testing.assert_allclose(adjust_fdr(p,'BH'),[.04,.003,.015])
        np.testing.assert_allclose(adjust_fdr(p,'BY'),np.array([.04,.003,.015])*(1+1/2+1/3))

    def test_cluster_variance_direct_calculation(self):
        x=np.array([2.,1.,0.]);d=np.array([3.,2.,1.]);y=np.array([3.,1.,1.]);e=np.array([5.,3.,2.])
        delta,se,lo,hi,p=ratio_contrast(x,d,y,e)
        expected=(x-.5*d)/6-(y-.5*e)/10
        self.assertAlmostEqual(delta,0.)
        self.assertAlmostEqual(se,np.sqrt(1.5*sum(expected**2)))
        self.assertAlmostEqual(p,.5)
        self.assertLess(lo,0);self.assertGreater(hi,0)

    def test_undefined_antecedent_not_positive_evidence(self):
        result=ratio_contrast(np.zeros(3),np.zeros(3),np.ones(3),np.ones(3))
        self.assertTrue(np.isnan(result[0]));self.assertEqual(result[-1],1.)

    def test_shared_recomputed_in_global_scope(self):
        idx=BasketIndex(['u','v','w','z'],[{'a','b'},{'a','b'},{'a'},{'b'}])
        q=QualityEvidence(idx,idx,{}, {'r':(('a',),('b',))})
        q.set_scope('small',{'u':'0','v':'0','w':'1','z':'1'},'0')
        small=q.get('small','r');glob=q.get('GLOBAL','r')
        self.assertEqual(small['confidence'],1)
        self.assertAlmostEqual(glob['confidence'],2/3)
        self.assertEqual(small['n_baskets'],2);self.assertEqual(glob['n_baskets'],4)

    def test_concentration_and_unresolved_are_not_failures(self):
        t=dict(min_antecedent_orders=20,min_joint_orders=10,min_antecedent_customers=10,min_joint_customers=5,
               max_customer_joint_share=.5,min_confidence_uplift=.05,min_lift=1.2,min_triple_increment_pp=5,
               adjustment='BY',alpha=.05)
        e=dict(antecedent_count=30,joint_count=12,antecedent_customers=15,joint_customers=5,max_customer_joint_share=.4,
               confidence_uplift=.1,lift=1.4,length=2,q_BY=.01)
        self.assertEqual(classify(e,t),'accepted')
        self.assertEqual(classify(dict(e,max_customer_joint_share=.7),t),'insufficient_evidence')
        self.assertEqual(classify(dict(e,q_BY=.1),t),'uncertainty_unresolved')
        self.assertEqual(classify(dict(e,length=3,triple_increment_pp=4),t),'increment_below_minimum')


if __name__=='__main__':unittest.main()
