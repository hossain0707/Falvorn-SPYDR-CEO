"""Integration tests use a deterministic stub model — no network, keys, or paid calls."""
import json
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import pytest

from agentcompany.config import Config
from agentcompany.db import init, audit, transaction, verify_chain
from agentcompany.model import ModelReply, ModelError, parse_json_object, validate_plan, classify_risk
from agentcompany.security import password_hash, verify_password
from agentcompany.server import CompanyHTTPServer, Handler


class StubModel:
    def configured(self): return True
    def complete(self, system, user, max_tokens=None):
        if 'CEO agent' in system:
            return ModelReply(json.dumps({'overview':'Detailed product launch plan for owner review.', 'tasks':[
                {'title':'Build MVP architecture','description':'Design an architecture, API outline, and a test plan.','role':'Engineering','risk':'low','estimated_usd':0.01},
                {'title':'Plan marketing strategy','description':'Write ethical campaign concepts and success criteria.','role':'Marketing','risk':'medium','estimated_usd':0.01}]}),200,300)
        return ModelReply('## Verified deliverable\n\nScope and acceptance criteria addressed.\n\nVerification: human must review.',120,190)


@pytest.fixture
def client(tmp_path):
    cfg=replace(Config(), database=tmp_path/'instance.sqlite3', port=0, api_key='test-key', monthly_budget_usd=1)
    server=CompanyHTTPServer(('127.0.0.1',0),Handler,cfg,model=StubModel())
    th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
    class Client:
        token=None
        csrf=None
        def call(self, method, path, body=None, csrf=True, authenticated=True):
            headers={}
            if body is not None:headers['Content-Type']='application/json'
            if authenticated and self.token:headers['Cookie']='ac_session='+self.token
            if csrf and self.csrf:headers['X-CSRF-Token']=self.csrf
            req=Request(f'http://127.0.0.1:{server.server_port}'+path,method=method,
                        data=json.dumps(body).encode() if body is not None else None,headers=headers)
            try:r=urlopen(req,timeout=5)
            except HTTPError as exc:r=exc
            payload=json.loads(r.read())
            if r.headers.get('Set-Cookie'):
                self.token=r.headers.get('Set-Cookie').split('=',1)[1].split(';',1)[0]
            if payload.get('csrf'):self.csrf=payload['csrf']
            return r.status,payload
        def onboard(self):
            return self.call('POST','/api/setup',{'email':'owner@example.com','password':'very-secure-password-123','company':'Northstar Lab'})
    test_client=Client()
    yield test_client
    server.shutdown();server.server_close();th.join(timeout=5)


def test_password_hash_and_check():
    p=password_hash('a-secure-password-24')
    assert verify_password('a-secure-password-24',p)
    assert not verify_password('wrong',p)
    with pytest.raises(ValueError):password_hash('short')


def test_planner_validation():
    good={'overview':'A valid meaningful strategy','tasks':[{'title':'Build project plan','description':'Deliver a detailed testable technical plan','role':'Engineering','risk':'low','estimated_usd':.2}]}
    assert validate_plan(good)['tasks'][0]['title']=='Build project plan'
    with pytest.raises(ModelError):validate_plan({**good,'tasks':[{**good['tasks'][0],'role':'Superuser'}]})
    assert parse_json_object('```json\n{"a":1}\n```')=={'a':1}


def test_initial_setup_auth_and_csrf(client):
    status,session=client.call('GET','/api/session')
    assert status==200 and session['setup_required']
    assert client.call('GET','/api/state')[0]==401
    assert client.onboard()[0]==201
    assert client.call('POST','/api/setup',{'email':'new@example.com','password':'really-long-pass999','company':'Other'})[0]==409
    assert client.call('POST','/api/goals',{'title':'Launch a new app','description':'Design a real application with tests'},csrf=False)[0]==403
    status,detail=client.call('GET','/api/state')
    assert status==200 and detail['company']['name']=='Northstar Lab'
    assert len(detail['agents'])==7 and detail['tasks']==[]
    assert client.call('POST','/api/logout',{},csrf=True)[0]==200
    assert client.call('GET','/api/state')[0]==401
    assert client.call('POST','/api/login',{'email':'owner@example.com','password':'wrong-password'})[0]==401
    assert client.call('POST','/api/login',{'email':'owner@example.com','password':'very-secure-password-123'})[0]==200


def test_manual_approval_execution_and_audit(client):
    assert client.onboard()[0]==201
    status,goal=client.call('POST','/api/goals',{'title':'Ship a new platform','description':'Implement an accessible and measurable prototype'})
    assert status==201
    gid=goal['id']
    plan={'overview':'A manual strategy for engineering and quality verification.','tasks':[
        {'title':'Specify engineering milestones','description':'Write an implementation plan and acceptance tests.','role':'Engineering','risk':'low','estimated_usd':0.01},
        {'title':'Review the implementation quality','description':'Inspect scope and write risk mitigation suggestions.','role':'Quality','risk':'medium','estimated_usd':0.01}]}
    status,result=client.call('POST',f'/api/goals/{gid}/manual-plan',plan)
    assert status==201
    approval=result['approval_id']
    assert client.call('GET','/api/state')[1]['tasks']==[]
    assert client.call('POST',f'/api/approvals/{approval}/decision',{'decision':'approved'})[0]==200
    assert client.call('POST',f'/api/approvals/{approval}/decision',{'decision':'approved'})[0]==409
    current=client.call('GET','/api/state')[1]
    assert len(current['tasks'])==2
    for t in current['tasks']:
        status,result=client.call('POST',f"/api/tasks/{t['id']}/run",{})
        assert status==200 and 'Verified deliverable' in result['output']
        assert client.call('POST',f"/api/tasks/{t['id']}/run",{})[0]==409
    final=client.call('GET','/api/state')[1]
    assert final['goals'][0]['status']=='completed'
    assert all(t['status']=='completed' for t in final['tasks'])
    assert final['company']['spent_usd']>0
    assert client.call('GET','/api/audit/verify')[1]['valid']


def test_ai_plan_rejection_and_budget(client):
    assert client.onboard()[0]==201
    gid=client.call('POST','/api/goals',{'title':'Develop a brand story','description':'Plan two specialist deliverables for new brand'})[1]['id']
    status,result=client.call('POST',f'/api/goals/{gid}/plan',{})
    assert status==201
    approval=result['approval_id']
    assert len(result['plan']['tasks'])==2
    assert client.call('POST',f'/api/approvals/{approval}/decision',{'decision':'rejected'})[0]==200
    assert client.call('GET','/api/state')[1]['tasks']==[]
    assert client.call('PATCH','/api/company',{'monthly_budget_usd':0.01})[0]==200
    assert client.call('POST',f'/api/goals/{gid}/plan',{})[0]==409


def test_tamper_evident_audit(tmp_path):
    db=tmp_path/'test.sqlite3';init(db)
    with transaction(db) as con:audit(con,'owner','example.event','item',{'x':1})
    assert verify_chain(db)==(True,1)
    with sqlite3.connect(db) as con:con.execute("UPDATE audit SET event='changed' WHERE id=1")
    assert verify_chain(db)[0] is False


def test_conservative_risk_classification():
    assert classify_risk('Prepare to delete customer records from a database', 'low') == 'high'
    assert classify_risk('Review privacy and data retention requirements', 'low') == 'medium'
    assert classify_risk('Create a UI color palette', 'low') == 'low'
