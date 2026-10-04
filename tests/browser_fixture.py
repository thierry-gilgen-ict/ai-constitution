"""Synthetic demo server. No account reads, model inference or external setup."""
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_control.core import Control
from local_control.server import Server, Handler
from local_control.storage import atomic
from local_control import updates, monitoring, project_vault


def main():
    with tempfile.TemporaryDirectory(prefix='constitution-browser-') as directory:
        base = Path(directory).resolve(); root = base / 'control'
        project = base / 'projects/demo-web'; project.mkdir(parents=True); (project / '.git').mkdir()
        (project / 'package.json').write_text('{"dependencies":{"next":"15.0.0","better-auth":"1.0.0","resend":"4.0.0","pg":"8.0.0"}}')
        (project / '.env.example').write_text('RESEND_API_KEY=\n')
        second = base / 'projects/demo-api'; second.mkdir(); (second / '.git').mkdir()
        config = base / 'configs/demo'; config.mkdir(parents=True); (config / '.env').write_text('EXAMPLE=synthetic-fixture')
        def rpc(node, path, body=None, **_):
            if path == '/api/version': return {'version':'fixture'}
            if path == '/api/tags': return {'models':[{'name':'fixture:latest','size':1024**3,'details':{'parameter_size':'1B'}}]}
            if path == '/api/ps': return {'models':[]}
            return {'status':'fixture'}
        control=Control(root,rpc)
        # This isolated loopback fixture deliberately uses recognizable test-only
        # credentials. Failure traces must never contain generated bearer secrets.
        control.config.update(token='fixture', gateway_token='fixture-gateway')
        control.config['primary']={'node':'local','model':'fixture:latest','contract':{'level':'protocol-tested'}};control.save()
        atomic(root/'updates.json',{'schema':1,'automatic_check':False,'latest':'99.0.0','checked_at':time.time(),
            'notes':'Synthetic demonstration release. This is not a real release.','url':updates.REPOSITORY+'/releases'})
        monitoring.configure(root,{'account':{'provider':'openai','login':'demo@example.com','label':'Demonstration subscription','plan':'Fixture','projects':[str(project)]}})
        project_vault.configure(root,{'config_root':str(config.parent),'backup_root':str(base/'backups'),
            'entry':{'id':'demo','name':'Demo configuration','folder':str(config)}})
        atomic(root/'restic.json',{'schema':1,'repository':str(base/'encrypted'),'password_file':'','password_env':'FIXTURE_BACKUP_PASSWORD','tag':'fixture','keep_last':5,'enabled':False})
        fixture={'token':control.config['token'],'project':str(project),'second':str(second),'search_root':str(project.parent),'config':str(config),'restore':str(base/'restored')}
        class FixtureHandler(Handler):
            def dispatch(self, post):
                if self.path == '/test/fixture' and not post:
                    self.reply(fixture);return
                return super().dispatch(post)
        control.driver_check_all=lambda progress=lambda _:None: {'status':'fixture'}
        control.setup_status=lambda: {'runtime':{'ollama':True},'note':'Synthetic fixture'}
        server=Server(('127.0.0.1',18766),control);server.RequestHandlerClass=FixtureHandler
        with patch('local_control.hardware.run_fit',return_value={'system':{'gpu_name':'Fixture GPU','gpu_vram_gb':16,'total_ram_gb':32},'models':[]}), \
             patch('local_control.launcher.open_project',return_value={'status':'fixture-launched','note':'Synthetic local session; no inference was sent'}):
            try: server.serve_forever()
            finally: server.server_close();control.pool.shutdown()


if __name__=='__main__': main()
