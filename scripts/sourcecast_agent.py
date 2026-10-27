#!/usr/bin/env python3
"""Read-only Sourcecast memory CLI and stdio tools. Standard library only."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def read_pack(path):
    pack = json.loads(Path(path).read_text(encoding='utf-8'))
    if pack.get('schema') not in ('sourcecast.memory/1', 'sourcecast.personal/1'):
        raise ValueError('Expected sourcecast.memory/1 or sourcecast.personal/1')
    return pack


def search(pack, query, limit=10):
    terms = str(query).lower().split()
    rows = []
    for node in pack['nodes']:
        hay = json.dumps(node, ensure_ascii=False).lower()
        if terms and all(t in hay for t in terms):
            rows.append(node)
    return rows[:max(1, min(int(limit), 50))]


def context(pack, node_id):
    by_id = {n['id']: n for n in pack['nodes']}
    if node_id not in by_id:
        raise ValueError('Unknown node id')
    edges = [e for e in pack['edges'] if node_id in (e['from'], e['to'])]
    ids = {e[k] for e in edges for k in ('from', 'to')}
    return {'node': by_id[node_id], 'neighbors': [by_id[i] for i in sorted(ids) if i in by_id and i != node_id], 'edges': edges}


TOOLS = [
    {'name': 'sourcecast_search', 'description': 'Search sourced podcast judgments, episodes, repositories and explicitly exported local topics. Judgments are opinions, not verified facts.', 'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50}}, 'required': ['query']}},
    {'name': 'sourcecast_context', 'description': 'Read a memory node and its direct source relationships. Keyword links are lexical associations, not factual entailment.', 'inputSchema': {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id']}},
]


def stdio(pack):
    """JSON-RPC, newline framing, no stdout diagnostics (MCP stdio transport)."""
    for line in sys.stdin:
        req = None
        try:
            req = json.loads(line)
            if 'id' not in req:  # Notifications do not get responses.
                continue
            method = req.get('method')
            if method == 'initialize':
                result = {'protocolVersion': req.get('params', {}).get('protocolVersion', '2024-11-05'), 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'sourcecast-local-memory', 'version': '1.0.0'}}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                params = req.get('params', {})
                args = params.get('arguments', {})
                try:
                    if params.get('name') == 'sourcecast_search':
                        data = search(pack, args.get('query', ''), args.get('limit', 10))
                    elif params.get('name') == 'sourcecast_context':
                        data = context(pack, args.get('id', ''))
                    else:
                        raise ValueError('Unknown tool')
                    result = {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}]}
                except (TypeError, ValueError) as exc:
                    result = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
            else:
                print(json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'error': {'code': -32601, 'message': 'Method not found'}}), flush=True)
                continue
            print(json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'result': result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({'jsonrpc': '2.0', 'id': req.get('id') if isinstance(req, dict) else None, 'error': {'code': -32700, 'message': str(exc)}}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--memory', default=str(Path(__file__).resolve().parent.parent / 'sourcecast.memory.json'))
    p.add_argument('--stdio', action='store_true')
    p.add_argument('query', nargs='?', default='记忆')
    args = p.parse_args()
    pack = read_pack(args.memory)
    if args.stdio:
        stdio(pack)
    else:
        print(json.dumps(search(pack, args.query), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
