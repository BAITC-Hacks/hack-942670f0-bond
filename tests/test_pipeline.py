import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import networkx as nx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
import solution as s
import build_viz
import server

def fixture(pairs,isolates=()):
    ids=sorted(set(isolates)|{i for u,v,w in pairs for i in [u,v]})
    nodes=pd.DataFrame({"gid":pd.Series(ids,dtype="int64"),"depth":[1]*len(ids),"is_seed":[False]*len(ids)})
    edges=pd.DataFrame([(u,v,w,1,1) for u,v,w in pairs],columns=["src","dst","sum_kzt","n_tx","depth"])
    for c in ["src","dst","n_tx","depth"]: edges[c]=edges[c].astype("int64")
    edges["sum_kzt"]=edges.sum_kzt.astype(float)
    tx=edges[["src","dst","sum_kzt"]].copy();tx["date"]=pd.Timestamp("2026-07-01")
    return edges,nodes,tx

def role_row(**kw):
    data=dict(gid=1,depth=1,is_seed=False,in_deg=1,out_deg=1,in_kzt=100.,out_kzt=100.,
        in_tx=1,out_tx=1,pagerank=.1,hub=.1,authority=.1,betweenness=.1,pass_through=1.,
        truncated_by_depth=False,n_seed_in=0,in_cycle=False,turnover_days=0.,net_kzt=0.)
    data.update(kw)
    return pd.DataFrame([data])

T=dict(IN_DEG_HI=3,OUT_DEG_HI=16.35,BTW_P98=1.,PR_P90=1.,KZT_P90=1e8,PT_LO=.7,PT_HI=1.3)

class HeuristicTests(unittest.TestCase):
    def test_seed_never_transit_or_amount_evidence(self):
        for pt in [.6,1.,53.]:
            result=s.assign_roles(role_row(is_seed=True,pass_through=pt),T).iloc[0]
            self.assertNotEqual(result.role,"transit")
            self.assertNotIn("KZT",result.evidence)
    def test_truncation_precedes_consolidation(self):
        r=s.assign_roles(role_row(in_deg=10,out_deg=0,depth=4,truncated_by_depth=True),T).iloc[0]
        self.assertEqual((r.role,r.role_score),("terminal",.35))
        self.assertIn("5-го",r.evidence)
    def test_terminal_precedes_consolidation(self):
        r=s.assign_roles(role_row(in_deg=10,out_deg=0),T).iloc[0]
        self.assertEqual(r.role,"terminal")
    def test_fractional_percentile_is_not_floored(self):
        for degree,role in [(16,"peripheral"),(17,"distributor")]:
            r=s.assign_roles(role_row(in_deg=0,out_deg=degree),T).iloc[0]
            self.assertEqual(r.role,role)
    def test_consolidator_fixed_structure(self):
        r=s.assign_roles(role_row(in_deg=3,out_deg=2,is_seed=True),T).iloc[0]
        self.assertEqual(r.role,"consolidator")
    def test_transit_bounds_and_fallback(self):
        for pt,role in [(.49,"peripheral"),(.5,"transit"),(.7,"transit"),(1.3,"transit"),(2.,"transit")]:
            self.assertEqual(s.assign_roles(role_row(pass_through=pt),T).role.iloc[0],role)
    def test_coordinator(self):
        self.assertEqual(s.assign_roles(role_row(betweenness=1.,pagerank=1.),T).role.iloc[0],"coordinator")

class GraphTests(unittest.TestCase):
    def test_weighted_hits_and_isolate(self):
        e,n,t=fixture([(1,2,9.),(1,3,1.)],isolates=[4]);G=s.build_graph(e,n);f=s.features(G,n,t).set_index("gid")
        self.assertAlmostEqual(f.loc[2,"authority"]/f.loc[3,"authority"],9.,places=6)
        self.assertGreater(f.loc[4,"pagerank"],0.)
    def test_weighted_distance_betweenness(self):
        e,n,t=fixture([(1,2,100.),(2,3,100.),(1,3,1.)]);G=s.build_graph(e,n)
        f=s.features(G,n,t).set_index("gid")
        self.assertGreater(f.loc[2,"betweenness"],nx.betweenness_centrality(G,weight=None)[2])
    def test_exact_cycle_edges(self):
        e,n,t=fixture([(1,2,1.),(2,1,1.),(3,4,1.),(4,3,1.),(2,3,1.)])
        G=s.build_graph(e,n);s.features(G,n,t)
        self.assertFalse(G[2][3]["in_cycle"])
        self.assertEqual(sum(d["in_cycle"] for _,_,d in G.edges(data=True)),4)
    def test_undirected_projection_sums_reciprocals(self):
        e,n,t=fixture([(1,2,9.),(2,1,1.)],isolates=[3]);G=s.build_graph(e,n)
        captured={}
        def community(UG,**kwargs):
            captured.update(graph=UG,kwargs=kwargs)
            return [{1,2},{3}]
        with patch.object(nx.community,"louvain_communities",side_effect=community):
            s.cluster(G,n)
        self.assertFalse(captured["graph"].is_directed())
        self.assertEqual(captured["graph"][1][2]["weight"],10.)
        self.assertEqual(captured["kwargs"]["seed"],42)
    def test_all_isolates(self):
        e,n,t=fixture([],isolates=[1,2]);G=s.build_graph(e,n)
        f=s.features(G,n,t);f=s.priority(s.cluster(G,s.assign_roles(f,s.thresholds(f))))
        self.assertEqual(set(f.role),{"peripheral"})
        self.assertTrue(np.isfinite(f.priority_score).all())
    def test_turnover_uses_previous_not_future(self):
        tx=pd.DataFrame({"src":[1,1,2,2],"dst":[2,2,3,3],
            "date":pd.to_datetime(["2026-07-02","2026-07-06","2026-07-01","2026-07-04"])})
        got=s._turnover_days(None,tx,pd.DataFrame({"gid":[2,3]}))
        self.assertEqual(list(got),[2.,-1.])
    def test_resilience_chain(self):
        G=nx.DiGraph([(1,2),(2,3)])
        df=pd.DataFrame({"gid":[1,2,3],"priority_score":[.1,1.,.2]})
        rows=s.resilience(G,df,3)
        self.assertEqual(rows[1]["removed"],["2"])
        self.assertEqual(rows[1]["components"],2)
        self.assertEqual(rows[3]["largest_component"],0)

class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e,cls.n,cls.t=s.load(ROOT/"data")
        cls.G=s.build_graph(cls.e,cls.n);f=s.features(cls.G,cls.n,cls.t)
        cls.f=s.priority(s.cluster(cls.G,s.assign_roles(f,s.thresholds(f))))
        cls.c=s.cluster_table(cls.f,cls.G);cls.top=s.top_nodes(cls.f)
    def test_dataset_contract_and_artifacts(self):
        f=self.f
        self.assertEqual(len(f),2248)
        self.assertEqual(int(f.truncated_by_depth.sum()),444)
        self.assertTrue(f.loc[f.truncated_by_depth,"role"].eq("terminal").all())
        self.assertTrue(f.loc[f.truncated_by_depth,"role_score"].eq(.35).all())
        self.assertFalse((f.is_seed&f.role.eq("transit")).any())
        self.assertTrue(f.loc[f.is_seed,"pass_through"].eq(-1).all())
        self.assertTrue(f.evidence.str.len().lt(200).all())
        s.validate_outputs(f,self.c,self.top,self.n.gid)
    def test_reordered_inputs_are_deterministic(self):
        e=self.e.sample(frac=1,random_state=8);n=self.n.sample(frac=1,random_state=9).sort_values("gid").reset_index(drop=True)
        G=s.build_graph(e,n);f=s.features(G,n,self.t.sample(frac=1,random_state=7))
        f=s.priority(s.cluster(G,s.assign_roles(f,s.thresholds(f))))
        pd.testing.assert_frame_equal(self.f,f)
    def test_csv_json_html_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);s.write_outputs(self.f,self.c,self.top,self.G,out)
            s.write_json(out/"summary.json",dict(n_nodes=len(self.f)))
            self.assertEqual(sorted(p.name for p in out.glob("*.csv")),["clusters.csv","nodes_roles.csv","top_nodes.csv"])
            frame=pd.read_csv(out/"nodes_roles.csv")
            self.assertEqual(list(frame.columns),s.NODE_COLS)
            self.assertFalse(frame.isna().any().any())
            self.assertEqual(set(frame.gid),set(self.n.gid))
            artifact=build_viz.build(out,ROOT/"viz/vendor")
            html=artifact.read_text(encoding="utf-8")
            self.assertIn("Симуляция удаления",html)
            self.assertNotIn("/*__DATA__*/",html)
            self.assertNotIn('<script src=',html)
    def test_schema_rejects_missing_evidence(self):
        bad=self.f.copy();bad.loc[0,"evidence"]=""
        with self.assertRaises(ValueError): s.validate_outputs(bad,self.c,self.top)

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.graph={"nodes":[dict(id="100000000000000001",role="consolidator",cluster=1,
            priority=.8,in_kzt=10.,out_kzt=2.,n_seed_in=2,in_cycle=False,truncated=False,evidence="2 плательщика")]}
        self.query=dict(role="consolidator",metric="n_seed_in",gid="",cluster_id=-1,seed_payers=True,cycles=False,truncated=False,limit=5)
    def test_grounded_chat_and_unknown_gid(self):
        with patch.object(server,"ask_openai",return_value=self.query):
            answer=server.chat_answer(self.graph,"Кто сборщик от seed?")
        self.assertEqual(answer["gids"],["100000000000000001"])
        self.query["gid"]="not-real"
        with self.assertRaises(ValueError): server.select_nodes(self.graph,self.query)
    def test_model_cannot_inject_arbitrary_metric(self):
        self.query["metric"]="__dict__"
        with self.assertRaises(ValueError): server.select_nodes(self.graph,self.query)
    def test_key_is_server_only(self):
        with patch.dict("os.environ",{},clear=True):
            self.assertFalse(server.available())
            with self.assertRaises(ValueError): server.ask_openai("",{},{})
    def test_responses_request_and_structured_reply(self):
        payload={"status":"completed","output":[{"content":[{"type":"output_text","text":json.dumps(self.query)}]}]}
        response=io.BytesIO(json.dumps(payload).encode())
        with patch.dict("os.environ",{"OPENAI_API_KEY":"test-secret","OPENAI_MODEL":"test-model"}), \
             patch.object(server,"urlopen",return_value=response) as call:
            result=server.ask_openai("instructions",{"question":"test"},server.QUERY_SCHEMA)
        request=call.call_args.args[0]
        body=json.loads(request.data)
        self.assertEqual(request.full_url,"https://api.openai.com/v1/responses")
        self.assertFalse(body["store"])
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertNotIn("test-secret",request.data.decode())
        self.assertEqual(result,self.query)
    def test_incomplete_response_is_not_fabricated(self):
        with patch.dict("os.environ",{"OPENAI_API_KEY":"test","OPENAI_MODEL":"test"}), \
             patch.object(server,"urlopen",return_value=io.BytesIO(b'{"status":"incomplete"}')):
            with self.assertRaises(ValueError): server.ask_openai("",{},server.QUERY_SCHEMA)

if __name__=="__main__": unittest.main()
