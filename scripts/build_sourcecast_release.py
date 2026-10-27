#!/usr/bin/env python3
"""Build the explicit public source allowlist and a portable memory/Agent bundle."""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web' / 'library'


def main():
    data = json.loads((WEB / 'data' / 'episodes.json').read_text())
    nodes, edges = [], []
    repos = set()
    for ep in data['episodes']:
        eid = f"ep{ep['no']}"
        nodes.append({**{k:ep.get(k) for k in ('slug','title','date','series','question','one_liner','chars','repos')}, 'id':eid, 'type':'episode'})
        if ep.get('series'):
            edges.append({'from':eid,'to':f"series:{ep['series']}",'rel':'belongs_to'})
        for i,t in enumerate(ep.get('judgments',[]),1):
            jid=f'{eid}-j{i}'; nodes.append({'id':jid,'type':'judgment','text':t,'source':eid})
            edges.append({'from':jid,'to':eid,'rel':'judgment_of'})
        for repo in ep.get('repos',[]):
            if repo not in repos: nodes.append({'id':f'repo:{repo}','type':'repository','name':repo}); repos.add(repo)
            edges.append({'from':eid,'to':f'repo:{repo}','rel':'discusses'})
        by_slug={e['slug']:e['no'] for e in data['episodes']}
        for slug in ep.get('related',[]):
            if slug in by_slug: edges.append({'from':eid,'to':f'ep{by_slug[slug]}','rel':'related_to'})
    nodes.extend({'id':f"series:{m['name']}",'type':'series',**m} for m in data['series_meta'])
    pack={'schema':'sourcecast.memory/1','source':'https://wql18902-ux.github.io/sourcecast/','counts':{'episodes':data['count'],'judgments':data['judgment_count'],'repos':len(repos)},'nodes':nodes,'edges':edges,'usage':'Judgments are sourced opinions. Relationship edges preserve provenance; they do not establish facts.'}
    ids={n['id'] for n in nodes}
    assert all(e['from'] in ids and e['to'] in ids for e in edges)
    memory=WEB/'sourcecast.memory.json';memory.write_text(json.dumps(pack,ensure_ascii=False,indent=2))
    paths=['index.html','styles.css','tokens.css','neon-tokens.css','studio-next.css','experience.css','neon.css','griffin.css','shell.css','knowledge-refinement.css','player-refinement.css','rail.css','rail.js','workspace.css','workspace-v3.css','DESIGN.md','app.js','studio.js','personal.js','knowledge.js','experience.js','data.js','data/styles.js','data/cloud.js','data/auditions.js','vendor/cloud-sdk.js','sourcecast.memory.json','README.md']
    paths += [str(p.relative_to(WEB)) for p in sorted((WEB/'vendor').rglob('*')) if p.is_file() and str(p.relative_to(WEB)) not in paths]
    paths += [str(p.relative_to(WEB)) for p in sorted((WEB/'assets').rglob('*')) if p.is_file()]
    readme='''# Sourcecast · portable source and Agent kit

Frontend: `python3 -m http.server 8793` in this folder. Open http://127.0.0.1:8793.
The source archive excludes audio samples, reference voices, personal memory and secrets.
Original MiMo demo previews are in the full WorkBuddy bundle. This source archive omits media; provide your own samples or use your own TTS service. Old Doubao previews are withdrawn.
The default model route is the visitor's own API. data/cloud.js retains the existing optional WorkBuddy application binding. Do not ship private keys in this file.

## Agent / CLI

`python3 scripts/sourcecast_agent.py 记忆`
`python3 scripts/sourcecast_agent.py --memory /absolute/path/sourcecast.memory.json --stdio`

MCP client configuration (replace the absolute paths):
```json
{"mcpServers":{"sourcecast":{"command":"python3","args":["/absolute/path/scripts/sourcecast_agent.py","--memory","/absolute/path/sourcecast.memory.json","--stdio"]}}}
```
Tools: sourcecast_search(query, limit) and sourcecast_context(id). Read only. Standard library only.
Use the website's exported memory JSON to include your own derived local topics. The website does not export your original documents.

## Your own voice (macOS)

`python3 scripts/cloud_tts.py set-secret --help`
Configure your own MiMo provider credential in macOS Keychain, then run:
`python3 scripts/voice_bridge.py`
The bridge binds to 127.0.0.1:8794; the UI at port 8793 and the official Pages domain are allowed.
It uses your own provider quota, with a local daily limit of 5 successful generations and 400 characters per request. Reference audio is submitted to your configured provider when you click Generate. No third-party voices are included.
Optional VoxCPM2 local synthesis requires an existing engine installation. Set SOURCECAST_LOCAL_TTS_TOOLS to your tools folder before starting the bridge; no model is downloaded by this source package.
ffmpeg and ffprobe must be installed for voice synthesis. No background task is installed.

Browser Agent API: window.Sourcecast.search(query), exportMemory(), styles(), getDraft().
Read-only WebMCP search is registered when navigator.modelContext is available.
Personal notes export sourcecast.personal/1; the same CLI accepts --memory pointing to that file.
'''
    target=WEB/'sourcecast-source.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name in paths: z.write(WEB/name,name)
        for source in sorted((ROOT/'frontend').rglob('*')):
            if source.is_file() and 'node_modules' not in source.parts:
                z.write(source,source.relative_to(ROOT))
        z.write(ROOT/'scripts'/'build_library_components.mjs','scripts/build_library_components.mjs')
        z.write(ROOT/'scripts'/'generate_sourcecast_showcase.py','scripts/generate_sourcecast_showcase.py')
        for name in ['DESIGN.md','COMPONENTS.md','MOTION.md','REVIEW.md','manifest.json','tokens.css','neon-tokens.css']:
            z.write(ROOT/'design-system'/name,'design-system/'+name)
        for name in ['sourcecast_agent.py','voice_bridge.py','cloud_tts.py']: z.write(ROOT/'scripts'/name,'scripts/'+name)
        local_source=(ROOT/'scripts'/'tts_local.py').read_text().replace('<VoxCPM2 引擎目录>/tools','./tts-tools')
        z.writestr('scripts/tts_local.py',local_source)
        z.writestr('AGENT-START.md',readme)
    print(f'Built {target.name}: {target.stat().st_size:,} bytes; {len(nodes)} nodes / {len(edges)} edges. Audio and personal files excluded.')

if __name__=='__main__': main()
