import sys
import unittest
from pathlib import Path
import pandas as pd
import networkx as nx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from cases import transaction_records, build_cases, validate_cases
from solution import weighted_hits

class CaseTests(unittest.TestCase):
    def fixture(self):
        df=pd.DataFrame(dict(gid=[1,2],cluster_id=[0,0],role=["consolidator","terminal"],priority_score=[.8,.3],evidence=["3 входа","нет выхода"]))
        clusters=pd.DataFrame(dict(cluster_id=[0],n_seed=[0],sum_kzt_internal=[20.],hypothesis=["Гипотеза: консолидация"]))
        tx=pd.DataFrame(dict(src=[1,1],dst=[2,2],sum_kzt=[10.,10.],date=pd.to_datetime(["2026-01-01"]*2)))
        return df,clusters,tx
    def test_duplicate_transfers_preserved(self):
        df,c,tx=self.fixture()
        cases=build_cases(df,c,tx)
        self.assertEqual(len(cases[0]["logs"]),2)
        self.assertNotEqual(cases[0]["logs"][0]["tx_id"],cases[0]["logs"][1]["tx_id"])
        validate_cases(cases,df,tx)
    def test_stable_cases_with_shuffled_rows(self):
        df,c,tx=self.fixture()
        self.assertEqual(build_cases(df,c,tx),build_cases(df.iloc[::-1],c,tx.iloc[::-1]))
    def test_fabricated_log_rejected(self):
        df,c,tx=self.fixture();cases=build_cases(df,c,tx)
        cases[0]["logs"][0]["sum_kzt"]=999.
        with self.assertRaises(ValueError):validate_cases(cases,df,tx)
    def test_hits_nonconvergence_raises(self):
        G=nx.DiGraph();G.add_edge(1,2,sum_kzt=2.);G.add_edge(2,3,sum_kzt=1.)
        with self.assertRaises(nx.PowerIterationFailedConvergence):weighted_hits(G,max_iter=0)
