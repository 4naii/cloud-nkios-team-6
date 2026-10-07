import json, threading, unittest, urllib.request, urllib.error
import numpy as np, pandas as pd
from app import ROOT, Predictor, make_server
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(port=0);threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}';cls.sample=json.loads((ROOT/'example_request.json').read_text())
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close()
    def post(self,data):
        req=urllib.request.Request(self.url+'/api/predict',json.dumps(data).encode(),{'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_prediction_matches_saved_model(self):
        status,r=self.post(self.sample);self.assertEqual(status,200)
        predictor=Predictor();p=float(predictor.model.predict_proba(pd.DataFrame([self.sample]))[0,1])
        self.assertAlmostEqual(r['survival_probability'],p);self.assertEqual(r['survived'],int(p>=.5))
    def test_schema_and_ui(self):
        with urllib.request.urlopen(self.url+'/api/schema') as r: schema=json.load(r)
        self.assertEqual({f['name'] for f in schema['fields']},set(self.sample))
        with urllib.request.urlopen(self.url+'/') as r:self.assertIn('api/predict',r.read().decode())
    def test_missing_extra_category_and_nonfinite(self):
        for payload in [{},dict(self.sample,survived=1),dict(self.sample,gender='unknown'),dict(self.sample,age=float('nan')),dict(self.sample,age=True),dict(self.sample,age=-1),dict(self.sample,**{'class':1.5})]:
            with self.subTest(payload=payload):self.assertEqual(self.post(payload)[0],422)
    def test_nullable(self):
        status,r=self.post(dict(self.sample,cabin_deck=None,emergency_response_time=None));self.assertEqual(status,200);self.assertTrue(0<=r['survival_probability']<=1)
    def test_literal_none_preserved(self):
        from train import load_data
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w',suffix='.csv') as f:
            f.write('medical_condition,survived\nNone,0\nAsthma,1\n');f.flush();_,X,_=load_data(f.name)
            self.assertEqual(X.medical_condition.iloc[0],'None')
if __name__=='__main__':unittest.main()
