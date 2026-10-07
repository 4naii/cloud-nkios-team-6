// Lightweight DOM harness: executes the actual page JavaScript against the real API.
// This checks request/response wiring, not browser layout or Colab's iframe proxy.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const elements=new Map();
class Element{
  constructor(tag){this.tag=tag;this.children=[];this.value='';this.disabled=false;this.textContent='';}
  set id(v){this._id=v;elements.set(v,this)} get id(){return this._id}
  append(...els){this.children.push(...els)} replaceChildren(...els){this.children=els}
  setAttribute(k,v){this[k]=v}
}
for(const name of ['form','fields','submit','reset','accuracy','status','result','request','response','error']){const e=new Element('div');e.id=name;}elements.get('submit').disabled=true;
const html=fs.readFileSync(new URL('static/index.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const ctx=vm.createContext({document:{getElementById:k=>elements.get(k),createElement:t=>new Element(t),createTextNode:t=>({textContent:t})},fetch,URL,location:{href:process.env.API_URL||'http://127.0.0.1:8001/'},console});
vm.runInContext(script,ctx);
for(let n=0;n<50&&elements.get('submit').disabled;n++)await new Promise(r=>setTimeout(r,100));
assert.equal(elements.get('submit').disabled,false,elements.get('error').textContent);
assert.equal(elements.get('fields').children.length,23);
await elements.get('form').onsubmit({preventDefault(){}});
let response=JSON.parse(elements.get('response').textContent);assert.ok(response.survival_probability>=0&&response.survival_probability<=1);assert.equal(elements.get('result').children.length,3);
elements.get('f_age').value='-1';await elements.get('form').onsubmit({preventDefault(){}});assert.match(elements.get('error').textContent,/age/);
elements.get('reset').onclick();assert.ok(Number(elements.get('f_age').value)>=0);
console.log('PASS: 23 fields, actual API prediction, displayed result, error handling, reset. Visual layout not tested.');
