import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from local_control import claude, messages, auditing
from local_control.audit_store import Store
from scripts import constitution as kit
from tests.test_workspace_workflows import Fixture


class ClaudeRuntime(Fixture):
    def setUp(self):
        super().setUp()
        kit.install(self.library,self.state,project=self.project,selected_clients=['claude-code'])
        self.profile=self.base/'profile';self.profile.mkdir()
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':[{'id':'claude','client':'claude-code','home':str(self.profile),'client_version':'2.1.286'}]}})

    def test_enrollment_preview_rejects_stale_plan_and_preserves_pin(self):
        v=claude.enroll(self.root,{'project':str(self.project)})
        (self.project/'CLAUDE.md').write_text((self.project/'CLAUDE.md').read_text()+'\nOwner note')
        with self.assertRaisesRegex(ValueError,'changed'):claude.enroll(self.root,{'project':str(self.project),'plan':v['plan']},apply=True)
        kit.install(self.library,self.state,project=self.project,pin=True)
        with self.assertRaisesRegex(ValueError,'pin'):claude.enroll(self.root,{'project':str(self.project)})

    def test_auth_collection_keeps_only_supported_fields(self):
        claude.configure(self.root,{'monitoring':True})
        fake=lambda *a,**kw:SimpleNamespace(stdout=json.dumps({'loggedIn':True,'email':'sample@example.test','authMethod':'claude.ai','accessToken':'private-value'}),returncode=0)
        with patch('local_control.claude.shutil.which',return_value='fake-claude'):
            result=claude.collect(self.root,'claude',runner=fake)
        self.assertNotIn('accessToken',result['account'])
        self.assertIsNone(result['allowance'])
        with self.assertRaises(ValueError):claude.configure(self.root,{'api_key_env':'a real key here'})

    def test_multiple_profiles_collect_independently(self):
        claude.configure(self.root,{'monitoring':True})
        profiles=[{'id':name,'client':'claude-code','home':str(self.profile)} for name in ('one','two')]
        auditing.configure(self.root,{'scope':{'projects':[str(self.project)],'profiles':profiles}})
        with patch('local_control.claude.collect',side_effect=lambda root,identity:{'status':'available','profile':identity}):
            result=claude.collect_all(self.root)
        self.assertEqual(set(result),{'one','two'})

    def test_telemetry_is_opt_in_bounded_redacted_and_deduplicated(self):
        with self.assertRaises(ValueError):claude.telemetry(self.root,{})
        claude.configure(self.root,{'telemetry':True})
        def body(number,end):return {'resourceMetrics':[{'scopeMetrics':[{'metrics':[{'name':'claude_code.token.usage','sum':{'aggregationTemporality':2,'dataPoints':[{'asInt':str(number),'timeUnixNano':str(end),'startTimeUnixNano':'1','attributes':[{'key':'private-path','value':{'stringValue':'never-store-this'}}]}]}}]}]}]}
        claude.telemetry(self.root,body(10,2));claude.telemetry(self.root,body(10,2));claude.telemetry(self.root,body(15,3))
        text=(self.root/'claude-metrics.json').read_text()
        self.assertNotIn('never-store-this',text);self.assertEqual(json.loads(text)['totals']['claude_code.token.usage'],15)

    def test_isolated_review_uses_no_tools_and_produces_candidate_only(self):
        report=auditing.scan(self.root);claude.configure(self.root,{'automated_reviews':True,'api_key_env':'REVIEW_TEST_KEY'})
        before=(self.project/'AGENTS.md').read_bytes()
        def run(argv,**kw):
            self.assertIn('--bare',argv);self.assertEqual(argv[argv.index('--tools')+1],'')
            self.assertEqual(kw['env']['ANTHROPIC_API_KEY'],'fixture-only')
            self.assertNotIn('ANTHROPIC_AUTH_TOKEN',kw['env'])
            snapshot=json.loads(kw['input'].split('\n',1)[1])['id']
            return SimpleNamespace(returncode=0,stdout=json.dumps({'structured_output':{'schema':1,'snapshot':snapshot,'findings':[],'edits':[]}}))
        with patch('local_control.claude.clients.probe',return_value={'version':'2.1.286'}),patch('local_control.claude.shutil.which',return_value='fake'),patch.dict('os.environ',{'REVIEW_TEST_KEY':'fixture-only','ANTHROPIC_AUTH_TOKEN':'must-not-inherit'}):
            claude.review(self.control(),{'report':report['id'],'profile':'claude'},runner=run)
        self.assertEqual(before,(self.project/'AGENTS.md').read_bytes())

    def test_subscription_automation_is_rejected(self):
        claude.configure(self.root,{'automated_reviews':True});report=auditing.scan(self.root)
        with patch('local_control.claude.clients.probe',return_value={'version':'2.1.286'}):
            with self.assertRaisesRegex(ValueError,'subscription'):claude.review(self.control(),{'report':report['id'],'profile':'claude','execution':'subscription'})

    def test_messages_contract_does_not_accept_responses_evidence(self):
        control=self.control();endpoint={'node':'local','model':'test'}
        self.assertFalse(messages.current(control,endpoint))
        Store(self.root).put('messages-contract',messages.identity(endpoint),{'id':messages.identity(endpoint),'checked_at':__import__('time').time(),'context':control.config['context'],'runtime_version':'1','model_digest':'old'})
        control.rpc=lambda node,path,*a,**kw:{'version':'2'} if path=='/api/version' else {'models':[{'name':'test','digest':'new'}]}
        self.assertFalse(messages.current(control,endpoint,refresh=True))

    def test_messages_subset_is_explicit(self):
        valid={'model':'constitution-local','max_tokens':100,'messages':[{'role':'user','content':'Hello'}]}
        messages.validate(valid)
        for extra in ({'metadata':{'extra':'unsupported'}},{'tool_choice':{'type':'any'}},{'max_tokens':0}):
            with self.assertRaises(ValueError):messages.validate({**valid,**extra})

    def test_launch_command_does_not_contain_credentials(self):
        result=claude.launch_command(self.root,{'project':str(self.project),'profile':'claude','mode':'local'})
        self.assertIn('claude',result['command']);self.assertNotIn('token',result['command'])

    def test_native_output_is_stopped_at_its_bound(self):
        import sys
        with self.assertRaisesRegex(ValueError,'bound'):
            claude.bounded_run([sys.executable,'-c','print("x" * 600000)'],timeout=5)

    def test_protocol_qualification_respects_gaming(self):
        control=self.control();control.config['primary']={'node':'local','model':'test'}
        control.mode='gaming'
        with self.assertRaisesRegex(ValueError,'Gaming'):messages.qualify(control,{'role':'primary'})

    def test_scheduled_api_review_keeps_prose_review_gate(self):
        from unittest.mock import patch
        claude.configure(self.root,{'automated_reviews':True})
        auditing.configure(self.root,{'semantic':{'enabled':True,'client':'claude-code','profile':'claude','execution':'api'}})
        with patch('local_control.claude.review',return_value={'id':'candidate','status':'needs-review'}) as execute:
            result=auditing.scheduled(self.root)
        execute.assert_called_once();self.assertEqual(result['reviews'][0]['status'],'needs-review')

    def test_named_profile_grant_and_mcp_scope(self):
        from local_control.audit_mcp import Access
        auditing.configure(self.root,{'mcp_projects':[{'project':str(self.project),'profiles':['claude']}]})
        auditing.scan(self.root)
        result=Access(self.root,self.project,'claude').report()
        self.assertTrue(all(c['client']=='claude-code' for c in result['chains']))
        kit.install(kit.ROOT,self.state,platform='claude-code',home=self.base,claude_dir=self.profile)
        target=next(t for t in kit.state_load(self.state)['targets'].values() if t['kind']=='claude-code')
        grant={'profiles':['claude'],'roots':[str(self.base)],'permissions':['preview']}
        self.assertTrue(auditing.target_allowed(target,grant,root=self.root))
        grant['profiles']=[];self.assertFalse(auditing.target_allowed(target,grant,root=self.root))

    def test_cancellation_preserves_other_tasks(self):
        import sys
        with self.assertRaisesRegex(ValueError,'cancelled'):
            claude.bounded_run([sys.executable,'-c','import time; time.sleep(10)'],timeout=5,cancelled=lambda:True)

    def test_gateway_credentials_do_not_authorize_telemetry_or_admin(self):
        from local_control.server import Handler
        control=self.control();claude.configure(self.root,{'telemetry':True})
        receiver=object.__new__(Handler);receiver.server=SimpleNamespace(control=control,worker=False)
        receiver.path='/api/claude/telemetry';receiver.headers={'Authorization':'Bearer '+control.config['gateway_token']}
        self.assertFalse(receiver.authenticated())
        token=kit.read_json(self.root/'claude-telemetry-token.json')['token']
        receiver.headers={'Authorization':'Bearer '+token};self.assertTrue(receiver.authenticated())
        receiver.path='/api/claude/settings';self.assertFalse(receiver.authenticated())
        receiver.path='/v1/messages';receiver.headers={'x-api-key':control.config['gateway_token']};self.assertTrue(receiver.authenticated())

    def test_messages_lease_preserves_protocol_fields(self):
        import time
        control=self.control();endpoint={'node':'local','model':'test'};control.config['primary']=endpoint
        Store(self.root).put('messages-contract',messages.identity(endpoint),{'id':messages.identity(endpoint),'checked_at':time.time(),'context':control.config['context']})
        body={'model':'constitution-local','messages':[{'role':'user','content':'Hi'}],'max_tokens':30}
        with control.lease(body,api='messages') as (node,payload):
            self.assertEqual(payload['model'],'test');self.assertNotIn('store',payload);self.assertNotIn('truncation',payload)
            self.assertEqual(sum(control.active.values()),1)
        self.assertEqual(sum(control.active.values()),0)

    def test_messages_errors_use_native_envelope(self):
        import io
        from local_control.server import Handler
        handler=object.__new__(Handler);handler.path='/v1/messages';handler.wfile=io.BytesIO()
        handler.send_response=lambda *a:None;handler.headers_common=lambda *a:None;handler.send_header=lambda *a:None;handler.end_headers=lambda:None
        handler.reply({'error':'Credential rejected'},403)
        body=json.loads(handler.wfile.getvalue())
        self.assertEqual(body['type'],'error');self.assertEqual(body['error']['type'],'authentication_error')

    def test_messages_qualification_checks_full_history_and_sse(self):
        control=self.control();control.config['primary']={'node':'local','model':'fixture'};roundtrips=[]
        def rpc(node,path,body=None,**kw):
            if path=='/api/show':return {'capabilities':['tools']}
            if path=='/api/version':return {'version':'test-runtime'}
            if path=='/api/tags':return {'models':[{'name':'fixture','digest':'fixture-digest'}]}
            if path=='/api/ps':return {'models':[{'name':'fixture','context_length':control.config['context']}]}
            roundtrips.append(body)
            if len(roundtrips)==1:return {'content':[{'type':'tool_use','id':'tool-1','name':'constitution_probe','input':{'value':'ready'}}]}
            self.assertEqual(body['messages'][-1]['content'][0]['tool_use_id'],'tool-1')
            return {'content':[{'type':'text','text':'LOCAL_TOOL_OK'}]}
        control.rpc=rpc
        conn=SimpleNamespace(close=lambda:None)
        response=SimpleNamespace(read=lambda limit:b'event: message_start\ndata: {"type":"message_start"}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n')
        with patch('local_control.messages.connect',return_value=(conn,response)):
            record=messages.qualify(control,{'role':'primary'})
        self.assertEqual(record['api'],'messages');self.assertEqual(record['level'],'protocol-tested')
        self.assertEqual(len(roundtrips),2);self.assertTrue(messages.current(control,control.config['primary'],refresh=True))
