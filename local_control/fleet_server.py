"""A separate, deliberately narrow controller TLS listener; no UI or inference API."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import ssl
import threading
import time
from urllib.parse import urlsplit
from . import fleet,plans
from .setup import certificate


class Listener(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,control):
        self.control=control;self.slots=threading.BoundedSemaphore(8)
        super().__init__(address,Handler)
    def process_request(self,request,address):
        if not self.slots.acquire(False):request.close();return
        super().process_request(request,address)
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()
    def service_actions(self):
        if hasattr(self,'heartbeat') and time.time()-getattr(self,'last_heartbeat',0)>30:
            self.heartbeat();self.last_heartbeat=time.time()


class Handler(BaseHTTPRequestHandler):
    server_version='LocalControlPeer'
    def log_message(self,*_):pass
    def setup(self):super().setup();self.connection.settimeout(10)
    def reply(self,value,status=200):
        data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):self.dispatch(True)
    def do_GET(self):self.dispatch(False)
    def dispatch(self,post):
        try:
            root=self.server.control.root
            if self.headers.get('Origin') or self.headers.get('Host')!=self.server.origin:raise ValueError('Peer origin refused')
            if self.path=='/node/fleet/pair' and post:
                if self.headers.get('Transfer-Encoding'):raise ValueError('Transfer encoding refused')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2000:raise ValueError('Invalid invitation size')
                value=json.loads(self.rfile.read(size))
                if not isinstance(value,dict):raise ValueError('Invalid invitation')
                self.reply(fleet.redeem(root,value));return
            token=self.headers.get('Authorization','').removeprefix('Bearer ');grant=fleet.principal(root,token)
            if not grant:self.reply({'error':'Controller scope required'},401);return
            if self.path=='/node/fleet/snapshot' and not post:self.reply(fleet.snapshot(self.server.control,grant));return
            self.reply({'error':'This listener exposes only scoped controller snapshots'},404)
        except Exception:self.reply({'error':'Controller request refused; review pairing or private state locally'},400)


def start(control,address,port):
    import ipaddress
    ip=ipaddress.ip_address(address)
    if not ip.is_private or ip.is_unspecified or ip.version!=4:raise ValueError('Choose an explicit private IPv4 address for controller pairing')
    cert,key,pin=certificate(control.root/'workspace/controller-tls',address)
    server=Listener((address,port),control);server.origin=f'{address}:{server.server_address[1]}'
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(cert,key)
    server.socket=context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
    server.thread=threading.Thread(target=server.serve_forever,name='controller-peers',daemon=True);server.thread.start()
    def heartbeat():
        plans.write(control.root,'fleet-listener.json',{'schema':1,'url':'https://'+server.origin,'fingerprint':pin,'heartbeat':time.time()})
    server.heartbeat=heartbeat;heartbeat();return server
