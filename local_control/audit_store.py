"""Private SQLite evidence, consistent backups, and non-replaying request receipts."""
import json
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager, closing
from .permissions import directory, protect
from . import locations
from scripts.paths import no_links


class Store:
    def __init__(self, root):
        for parent in (Path(root),*Path(root).parents):
            if (parent/'.git').exists():raise ValueError('Private evidence must stay outside Git repositories')
        self.folder=directory(Path(root)/'audit')
        self.path=self.folder/'evidence.sqlite3';no_links(self.path)
        with self.connect() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1):raise ValueError('Unknown evidence schema; preserve it before upgrading')
            db.execute('CREATE TABLE IF NOT EXISTS evidence (kind TEXT, id TEXT, created REAL, body TEXT, PRIMARY KEY(kind,id))')
            db.execute('PRAGMA user_version=1')
        protect(self.path)

    @contextmanager
    def connect(self):
        no_links(self.path)
        db=sqlite3.connect(self.path,timeout=10)
        db.execute('PRAGMA busy_timeout=10000')
        try:
            with db: yield db
        finally:db.close()

    def put(self, kind, key, body):
        text=json.dumps(body,ensure_ascii=False)
        if len(text.encode())>8*1024*1024:raise ValueError('Evidence exceeds its bound')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO evidence VALUES (?,?,?,?)',(kind,key,time.time(),text))
        return body

    def get(self, kind, key, default=None):
        with self.connect() as db:row=db.execute('SELECT body FROM evidence WHERE kind=? AND id=?',(kind,key)).fetchone()
        return json.loads(row[0]) if row else default

    def list(self, kind, limit=50):
        with self.connect() as db:rows=db.execute('SELECT body FROM evidence WHERE kind=? ORDER BY created DESC LIMIT ?',(kind,min(max(int(limit),1),200))).fetchall()
        return [json.loads(row[0]) for row in rows]

    def begin(self, key, signature, principal=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT body FROM evidence WHERE kind='request' AND id=?",(key,)).fetchone()
            if row:
                value=json.loads(row[0])
                if value['signature']!=signature:raise ValueError('Request ID belongs to different input')
                return value
            value={'id':key,'signature':signature,'principal':principal,'status':'started','created_at':time.time()}
            db.execute('INSERT INTO evidence VALUES (?,?,?,?)',('request',key,time.time(),json.dumps(value)))
            return None

    def usage(self):
        import shutil
        size=self.path.stat().st_size;free=shutil.disk_usage(self.folder).free
        return {'bytes':size,'free_bytes':free,'pressure':size>256*1024*1024 or free<512*1024*1024,
                'note':'Protected proposal and rollback evidence is retained; export history or change private storage when capacity is low.'}

    def backup(self, destination):
        destination=locations.destination(str(destination))
        if destination.exists():raise ValueError('Choose a new backup directory')
        directory(destination)
        target=destination/'evidence.sqlite3'
        with self.connect() as source,closing(sqlite3.connect(target)) as output:source.backup(output)
        protect(target)
        return {'directory':str(destination),'sha256':__import__('scripts.audit',fromlist=['fingerprint']).fingerprint(target),
                'note':'Private evidence only; permissions, schedules and active instructions are excluded.'}

    def restore(self, source):
        path=Path(source)/'evidence.sqlite3';no_links(path)
        if not path.is_file() or path.stat().st_size>256*1024*1024:raise ValueError('Evidence backup unavailable or exceeds the restore bound')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as original:
            if original.execute('PRAGMA user_version').fetchone()[0]!=1:raise ValueError('Unsupported evidence backup')
            definition=original.execute("SELECT type,sql FROM sqlite_master WHERE name='evidence'").fetchone()
            if not definition or definition[0]!='table' or 'VIRTUAL' in (definition[1] or '').upper():raise ValueError('Unsupported evidence table')
            if [r[1] for r in original.execute('PRAGMA table_info(evidence)')]!=['kind','id','created','body']:raise ValueError('Unsupported evidence columns')
            if original.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]>100000 or (original.execute('SELECT MAX(length(body)) FROM evidence').fetchone()[0] or 0)>8*1024*1024:raise ValueError('Evidence backup exceeds record bounds')
            rows=original.execute('SELECT kind,id,body FROM evidence').fetchall()
            parsed=[(k,i,json.loads(b)) for k,i,b in rows if k in ('report','disposition','receipt','loading')]
            if any(not isinstance(b,dict) or b.get('schema',1)!=1 for k,i,b in parsed):raise ValueError('Unsupported historical evidence record')
        for kind,key,body in parsed:self.put(kind,key,body)
        return {'restored':len(parsed),'note':'History restored; grants, jobs, proposals and schedules remain inactive.'}

    def prune(self, days=90):
        # Referenced reports and rollback receipts remain protected.
        protected=set()
        with self.connect() as db:proposals=[json.loads(row[0]) for row in db.execute("SELECT body FROM evidence WHERE kind='proposal'").fetchall()]
        for value in proposals:
            if value.get('status') not in ('rejected','rolled-back'):protected.add(value.get('report'))
        with self.connect() as db:
            rows=db.execute("SELECT id FROM evidence WHERE kind='report' AND created<?",(time.time()-days*86400,)).fetchall()
            for (key,) in rows:
                if key not in protected:db.execute("DELETE FROM evidence WHERE kind='report' AND id=?",(key,))
