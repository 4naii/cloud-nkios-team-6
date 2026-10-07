"""Reproducible training: validation selects model, held-out test evaluates once."""
import os
os.environ.setdefault('OMP_NUM_THREADS','4')
import argparse, hashlib, json, platform
from pathlib import Path
import joblib, numpy as np, pandas as pd, sklearn
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix
from sklearn.base import clone

ROOT=Path(__file__).resolve().parent
EXCLUDE=['full_name','name','survived','survival_probability','family_survival_rate']
def load_data(path):
    # Literal "None" means no occupation/medical condition, not a missing value.
    df=pd.read_csv(path,keep_default_na=False,na_values=[''])
    if 'survived' not in df or df.survived.isna().any() or not set(df.survived.unique()) <= {0,1}:
        raise ValueError('survived must contain non-missing 0/1 labels')
    X=df.drop(columns=[c for c in df if c in EXCLUDE or c.startswith('Unnamed:')])
    return df,X,df.survived.astype(int)

def metrics(y,p):
    pred=(p>=.5).astype(int)
    acc=float(accuracy_score(y,pred));n=len(y);z=1.96
    center=(acc+z*z/(2*n))/(1+z*z/n)
    half=z*np.sqrt(acc*(1-acc)/n+z*z/(4*n*n))/(1+z*z/n)
    return dict(accuracy=acc,accuracy_ci95=[float(center-half),float(center+half)],balanced_accuracy=float(balanced_accuracy_score(y,pred)),precision=float(precision_score(y,pred,zero_division=0)),recall=float(recall_score(y,pred,zero_division=0)),f1=float(f1_score(y,pred,zero_division=0)),roc_auc=float(roc_auc_score(y,p)),confusion_matrix=confusion_matrix(y,pred,labels=[0,1]).tolist())

def main(path):
    out=ROOT/'artifacts';out.mkdir(exist_ok=True)
    df,X,y=load_data(path)
    # Preserve original notebook's exact held-out 20% split for comparability.
    Xdev,Xtest,ydev,ytest=train_test_split(X,y,test_size=.2,random_state=42)
    Xt,Xv,yt,yv=train_test_split(Xdev,ydev,test_size=.25,random_state=43,stratify=ydev)
    cats=X.select_dtypes(include=['object']).columns.tolist();nums=[c for c in X if c not in cats]
    catpipe=make_pipeline(SimpleImputer(strategy='constant',fill_value='__missing__'),OrdinalEncoder(handle_unknown='use_encoded_value',unknown_value=-1))
    ordinal=ColumnTransformer([('numeric',SimpleImputer(strategy='median'),nums),('category',catpipe,cats)])
    onehot=ColumnTransformer([('numeric',make_pipeline(SimpleImputer(strategy='median'),StandardScaler()),nums),('category',make_pipeline(SimpleImputer(strategy='constant',fill_value='__missing__'),OneHotEncoder(handle_unknown='ignore')),cats)])
    mask=[False]*len(nums)+[True]*len(cats)
    candidates={
      'random_forest_depth5':make_pipeline(clone(ordinal),RandomForestClassifier(n_estimators=100,max_depth=5,random_state=42,n_jobs=4)),
      'logistic_regression':make_pipeline(onehot,LogisticRegression(C=1,max_iter=1000)),
      'hist_gradient_7leaves':make_pipeline(clone(ordinal),HistGradientBoostingClassifier(max_iter=300,max_leaf_nodes=7,learning_rate=.05,l2_regularization=10,categorical_features=mask,random_state=42)),
      'hist_gradient_15leaves':make_pipeline(clone(ordinal),HistGradientBoostingClassifier(max_iter=300,max_leaf_nodes=15,learning_rate=.05,l2_regularization=10,categorical_features=mask,random_state=42)),
      'hist_gradient_31leaves':make_pipeline(clone(ordinal),HistGradientBoostingClassifier(max_iter=200,max_leaf_nodes=31,learning_rate=.05,l2_regularization=10,categorical_features=mask,random_state=42))}
    results=[]
    for name,model in candidates.items():
        model.fit(Xt,yt);score=metrics(yv,model.predict_proba(Xv)[:,1]);results.append(dict(model=name,**score));print(name,score['accuracy'],flush=True)
    winner=max(results,key=lambda r:r['accuracy'])['model']
    final=clone(candidates[winner]);final.fit(Xdev,ydev)
    test=metrics(ytest,final.predict_proba(Xtest)[:,1])
    baseline=clone(candidates['random_forest_depth5']);baseline.fit(Xdev,ydev)
    base_metrics=metrics(ytest,baseline.predict_proba(Xtest)[:,1])
    p=df.survival_probability.to_numpy() if 'survival_probability' in df else None
    diagnostic={} if p is None else {'probability_threshold_accuracy_all_rows':float(np.mean((p>=.5)==y)), 'expected_accuracy_if_labels_are_bernoulli':float(np.mean(np.maximum(p,1-p))), 'interpretation':'Conditional diagnostic, NOT a proven ceiling. Only applies if supplied probability is the true P(y=1|X). Not used for training or model selection.'}
    report={'rows':len(df),'features':X.columns.tolist(),'excluded':[c for c in df if c not in X], 'split':{'train':len(Xt),'validation':len(Xv),'test':len(Xtest),'test_seed':42,'validation_seed':43,'final_fit_rows':len(Xdev)},'selection':'Validation accuracy; threshold fixed at 0.5. Final winner refit on train+validation; test not used to select.','validation_candidates':results,'selected_model':winner,'test':test,'corrected_baseline_test':base_metrics,'original_notebook_saved_accuracy':.7353,'original_notebook_saved_improved_accuracy':.7430,'target_accuracy':.85,'target_met':test['accuracy']>=.85,'probability_diagnostic':diagnostic,'csv_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'versions':{'python':platform.python_version(),'sklearn':sklearn.__version__,'pandas':pd.__version__,'numpy':np.__version__,'joblib':joblib.__version__},'missingness':{'development':Xdev.isna().sum().to_dict(),'test':Xtest.isna().sum().to_dict()},'scope':'Educational evacuation scenario: lifeboat_access, emergency_response_time, evacuation_priority must be available at prediction time. Not a pre-boarding survival forecast; provenance of family_risk_score must be confirmed.'}
    fields=[]
    example_row=Xdev.dropna().iloc[0]
    for c in X:
        s=Xdev[c]
        if c in cats:
            choices=sorted(s.dropna().unique().tolist())
            fields.append({'name':c,'type':'category','choices':choices,'default':str(example_row[c]),'nullable':bool(X[c].isna().any())})
        else:
            integer=pd.api.types.is_integer_dtype(s.dtype)
            fields.append({'name':c,'type':'integer' if integer else 'number','min':float(s.min()),'max':float(s.max()),'default':int(example_row[c]) if integer else float(example_row[c]),'nullable':bool(X[c].isna().any())})
    schema={'fields':fields,'output':{'survived':'0 or 1','survival_probability':'model-estimated probability between 0 and 1'},'threshold':.5,'model':winner,'test_accuracy':test['accuracy'],'target_met':report['target_met'],'scenario':'대피 상황 정보가 주어진 교육용 생존 예측'}
    joblib.dump(final,out/'model.joblib',compress=3)
    for name,obj in [('metrics.json',report),('schema.json',schema)]: (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    example={f['name']:f['default'] for f in fields}
    (ROOT/'example_request.json').write_text(json.dumps(example,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'selected':winner,'test':test,'target_met':report['target_met']},indent=2),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',default=str(ROOT/'data'/'6.csv'));args=parser.parse_args();main(args.data)
