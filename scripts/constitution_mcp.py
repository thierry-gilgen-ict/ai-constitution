#!/usr/bin/env python3
"""Optional stdio MCP entry point. Explicit project/profile grant required."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_control.audit_mcp import server
from local_control.storage import private_root

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,default=private_root())
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--profile',required=True,help='Exact locally granted client-profile ID')
    args=parser.parse_args()
    server(args.state_dir,args.project,args.profile).run(transport='stdio')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as error:
        print(str(error) if isinstance(error,ValueError) else 'MCP state unavailable',file=sys.stderr)
        raise SystemExit(1)
