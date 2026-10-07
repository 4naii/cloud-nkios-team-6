"""Local educational JSON API + same-origin web UI (Python standard library)."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
import argparse, json, math, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import joblib, pandas as pd
ROOT=Path(__file__).resolve().parent
class Predictor:
    def __init__(self):
        self.model=joblib.load(ROOT/'artifacts/model.joblib')
        self.schema=json.loads((ROOT/'artifacts/schema.json').read_text(encoding='utf-8'))
        self.lock=threading.Lock()
    def predict(self,payload):
        if not isinstance(payload,dict): raise ValueError('JSON 객체를 보내주세요.')
        fields=self.schema['fields']; names={f['name'] for f in fields}
        extra=set(payload)-names; missing=names-set(payload)
        if extra: raise ValueError('허용되지 않은 항목: '+', '.join(sorted(extra)))
        if missing: raise ValueError('누락된 항목: '+', '.join(sorted(missing)))
        row={}
        for f in fields:
            k=f['name'];v=payload[k]
            if v is None:
                if not f['nullable']: raise ValueError(k+': 필수 입력입니다.')
                row[k]=float('nan');continue
            if f['type']=='category':
                if not isinstance(v,str) or v not in f['choices']: raise ValueError(k+': 허용된 선택지를 사용하세요.')
            else:
                if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v): raise ValueError(k+': 유한한 숫자를 입력하세요.')
                if f['type']=='integer' and int(v)!=v: raise ValueError(k+': 정수를 입력하세요.')
                if not f['min']<=v<=f['max']: raise ValueError(f"{k}: 학습 범위 {f['min']} ~ {f['max']} 안에서 입력하세요.")
            row[k]=v
        frame=pd.DataFrame([row],columns=[f['name'] for f in fields])
        for f in fields:
            if f['type']=='category': frame[f['name']]=frame[f['name']].astype(object)
        with self.lock:
            p=float(self.model.predict_proba(frame)[0,1])
        survived=int(p>=self.schema['threshold'])
        return {'survived':survived,'label':'생존 예측' if survived else '비생존 예측','survival_probability':p,'threshold':self.schema['threshold'],'model':self.schema['model']}

def make_server(host='127.0.0.1',port=8000):
    predictor=Predictor()
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,body,mime='application/json; charset=utf-8'):
            if not isinstance(body,bytes): body=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            path=urlsplit(self.path).path.rstrip('/') or '/'
            if path=='/': self.send(200,(ROOT/'static/index.html').read_bytes(),'text/html; charset=utf-8')
            elif path=='/api/schema': self.send(200,predictor.schema)
            elif path=='/api/metrics': self.send(200,json.loads((ROOT/'artifacts/metrics.json').read_text(encoding='utf-8')))
            elif path=='/api/health': self.send(200,{'status':'ok','model_loaded':True})
            else: self.send(404,{'error':'경로를 찾을 수 없습니다.'})
        def do_POST(self):
            if urlsplit(self.path).path.rstrip('/')!='/api/predict': return self.send(404,{'error':'경로를 찾을 수 없습니다.'})
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json': return self.send(415,{'error':'Content-Type은 application/json이어야 합니다.'})
            try: size=int(self.headers.get('Content-Length','0'))
            except ValueError: return self.send(400,{'error':'잘못된 Content-Length'})
            if not 0<size<=32768: return self.send(413,{'error':'요청 크기는 1~32768바이트여야 합니다.'})
            try:
                self.connection.settimeout(10)
                payload=json.loads(self.rfile.read(size).decode('utf-8'))
                result=predictor.predict(payload)
            except (ValueError,UnicodeError,TimeoutError) as e: return self.send(422,{'error':str(e)})
            except Exception:
                self.log_error('prediction failed');return self.send(500,{'error':'예측 처리 중 오류가 발생했습니다.'})
            self.send(200,result)
    return ThreadingHTTPServer((host,port),Handler)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8000);args=parser.parse_args()
    try: server=make_server(args.host,args.port)
    except FileNotFoundError: raise SystemExit('학습 파일이 없습니다. 먼저 python train.py --data data/6.csv 를 실행하세요.')
    print(f'Open http://{args.host}:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
