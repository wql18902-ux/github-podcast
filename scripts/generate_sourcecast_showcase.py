"""Generate original vector artwork for the website's local 3D showcase."""
from pathlib import Path
from html import escape
import math

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web/library' if (ROOT / 'web/library/index.html').exists() else ROOT
OUT = WEB / 'assets/showcase'
ART = [
    ('book-orbits', 'BOOK / READING', 'THE SHAPE', 'OF IDEAS', '思维的形状', '#8eadff', 'orbit'),
    ('paper-attention', 'PAPER / RESEARCH', 'A BETTER', 'QUESTION', '一个好问题，从这里开始', '#8de7ef', 'paper'),
    ('project-open', 'OPEN SOURCE / PROJECT', 'OPEN', 'POSSIBILITIES', '从实现里，看见思路', '#baa4ff', 'code'),
    ('notes-patterns', 'NOTEBOOK / THINKING', 'MAKE IT', 'YOUR OWN', '让新的理解，留下来', '#f2c3dc', 'notes'),
    ('audio-signal', 'AUDIO / LISTENING', 'LISTEN.', 'THINK AGAIN.', '换一种方式，听懂它', '#96cfff', 'wave'),
    ('map-nodes', 'MIND MAP / CONNECTIONS', 'CONNECT', 'THE DOTS.', '一个想法，遇见另一个', '#c5d3ff', 'graph'),
    ('book-futures', 'BOOK / EXPLORATION', 'POSSIBLE', 'FUTURES', '下一次理解，从好奇开始', '#c5e8ad', 'orbit'),
    ('paper-method', 'PAPER / EVIDENCE', 'BEYOND', 'THE ABSTRACT', '从问题，到证据与判断', '#96baff', 'paper'),
    ('project-context', 'OPEN SOURCE / CONTEXT', 'READ THE', 'SOURCE.', '读代码，也读背后的取舍', '#a0dfde', 'code'),
]

def artwork(kind, accent):
    if kind == 'orbit':
        return ''.join(f'<ellipse cx="735" cy="325" rx="{r}" ry="{r//2}" fill="none" stroke="{accent}" stroke-opacity=".6" stroke-width="1.5" transform="rotate({a} 735 325)"/>' for r,a in [(175,0),(175,60),(175,120),(115,30)]) + f'<circle cx="735" cy="325" r="7" fill="{accent}"/>'
    if kind == 'wave':
        return ''.join(f'<rect x="{560+i*11}" y="{340-(h:=18+abs(math.sin(i*.45))*110)/2:.1f}" width="3" height="{h:.1f}" rx="1.5" fill="{accent}" opacity="{.4+.6*i/30:.2f}"/>' for i in range(32))
    if kind == 'graph':
        pts=[(675,190),(865,240),(625,420),(850,440),(740,325)]
        return ''.join(f'<path d="M740 325 {x} {y}" stroke="{accent}" stroke-opacity=".5"/>' for x,y in pts[:-1])+''.join(f'<circle cx="{x}" cy="{y}" r="{16 if i<4 else 43}" fill="#101b30" stroke="{accent}" stroke-width="1.5"/>' for i,(x,y) in enumerate(pts))
    if kind == 'code':
        lines=['const knowledge = {','  books: curiosity,','  papers: evidence,','  code: possibility,','};','','connect(knowledge);']
        return '<rect x="555" y="160" width="350" height="310" rx="15" fill="#101726" stroke="#35405b"/>'+''.join(f'<circle cx="{578+i*13}" cy="182" r="3" fill="{accent}" opacity=".6"/>' for i in range(3))+''.join(f'<text x="578" y="{228+i*29}" font-family="ui-monospace,monospace" font-size="16" fill="{accent if i in [0,6] else "#a8b7d4"}">{escape(t)}</text>' for i,t in enumerate(lines))
    if kind == 'paper':
        return '<g transform="translate(600 145) rotate(7 150 170)"><rect width="280" height="365" rx="10" fill="#dce5f7"/><rect x="24" y="30" width="110" height="5" rx="2" fill="#7787a6"/><text x="24" y="66" font-size="17" fill="#18223d">THE QUESTION IS THE START.</text>'+''.join(f'<rect x="24" y="{92+i*17}" width="{185 if i%3 else 225}" height="3" fill="#899ab8" opacity=".55"/>' for i in range(5))+f'<path d="M25 275 65 240 110 255 160 203 220 222 255 190" fill="none" stroke="#496dc1" stroke-width="3"/>'+''.join(f'<rect x="24" y="{305+i*12}" width="{210 if i%2 else 178}" height="3" fill="#899ab8" opacity=".55"/>' for i in range(3))+'</g>'
    return f'<rect x="560" y="180" width="340" height="270" rx="13" fill="#111a2a" stroke="#35405b"/><text x="590" y="225" fill="{accent}" font-size="19">YOUR NEXT CONNECTION.</text>'+''.join(f'<path d="M590 {265+i*32}h{230 if i%2 else 180}" stroke="#7e8da9" stroke-opacity=".65" stroke-width="2"/>' for i in range(4))+f'<rect x="590" y="392" width="145" height="25" rx="6" fill="#26334e"/><text x="600" y="410" fill="{accent}" font-size="12">[[ connect an idea ]]</text>'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for name,kind,line1,line2,chinese,accent,shape in ART:
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="970" height="700" viewBox="0 0 970 700"><defs><radialGradient id="halo"><stop stop-color="{accent}" stop-opacity=".2"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient></defs><rect width="970" height="700" rx="22" fill="#0b111f"/><circle cx="750" cy="340" r="340" fill="url(#halo)"/><rect x="1" y="1" width="968" height="698" rx="22" fill="none" stroke="#303b52"/><path d="M40 101H930M40 586H930" stroke="#303b52"/><g fill="#a9b8d0" font-family="system-ui,sans-serif"><text x="44" y="62" font-size="14" letter-spacing="3">SOURCECAST / {kind}</text><text x="920" y="62" text-anchor="end" font-size="13">SC.</text><text x="45" y="274" font-family="system-ui,sans-serif" font-size="64" font-weight="600" letter-spacing="-3" fill="#eff3fd">{line1}</text><text x="45" y="350" font-family="system-ui,sans-serif" font-size="64" font-weight="600" letter-spacing="-3" fill="{accent}">{line2}</text><text x="47" y="407" font-size="20">{chinese}</text><text x="44" y="642" font-size="12" letter-spacing="2">YOUR CURIOSITY, CONNECTED.</text><text x="923" y="642" text-anchor="end" font-size="12">原创功能示意 / EXAMPLE</text></g>{artwork(shape,accent)}</svg>'''
        (OUT/(name+'.svg')).write_text(svg)
    print('Generated',len(ART),'original local showcase SVGs; no remote artwork used.')

if __name__=='__main__':main()
