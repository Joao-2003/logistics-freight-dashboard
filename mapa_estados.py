"""Aba "Transportadoras por estado": dados por UF e o mapa do Brasil (SVG do dashboard de vendas).

Critérios (o estado é sempre o do destino nas saídas e o da origem nas entradas):
- peso:  kg transportados (SAP, notas fiscais com a transportadora preenchida);
- notas: número de notas fiscais (SAP);
- frete: frete pago (Pipefy: valor do CT-e ou, sem CT-e, o da cotação selecionada);
- rkg:   R$ por kg (Pipefy: frete ÷ peso da carga), a menor ganha; mínimo de fretes por transportadora;
- cte:   frete dos CT-e recebidos no SAP (YY1_RELATORIO_FRETE, entrada com parceiro = fornecedor de frete).
         O CT-e no SAP não traz o destino: o estado é o da filial da transportadora que emitiu,
         que em geral é a origem da carga. Por isso só aparece em Entradas.
"""
import json
import os

import pandas as pd

from config import AQUI, ARQ_FORNECEDORES, FROTAS_PROPRIAS, UF_NOMES, UNIDADES
from fontes import normalizar_transportadora, tratar_codigo_cotacao

CRITERIOS = {
    "peso": {"rotulo": "Peso transportado", "fonte": "SAP · notas fiscais", "fmt": "kg", "menor": False},
    "notas": {"rotulo": "Nº de notas", "fonte": "SAP · notas fiscais", "fmt": "n", "menor": False},
    "frete": {"rotulo": "Frete pago", "fonte": "Pipefy · CT-e", "fmt": "brl", "menor": False},
    "rkg": {"rotulo": "Menor R$/kg", "fonte": "Pipefy · CT-e ÷ peso da carga", "fmt": "rkg", "menor": True},
    "cte": {"rotulo": "Frete CT-e (SAP)", "fonte": "SAP · CT-e recebidos · UF da filial que emitiu o CT-e", "fmt": "brl",
            "menor": False, "so": "entradas",
            "aviso": "O CT-e no SAP não traz o destino da carga, só a filial que emitiu. Veja em Entradas (UF de origem)."},
}
CATEGORIAS_FRETE = ["Transportadora", "Autônomo", "Mudança", "Internacional"]
UFS = set(UF_NOMES)


def _uf(v):
    v = str(v or "").strip().upper()
    return v if v in UFS else None


def _ranking(df, uf_col, transp_col, valor_col, extras, menor=False, min_n=1, razao=None):
    out = {}
    if df.empty:
        return out
    agg = {"n": (valor_col, "size"), **{k: (c, "sum") for k, c in extras.items()}}
    if razao is None:
        agg["v"] = (valor_col, "sum")
    g = df.groupby([uf_col, transp_col]).agg(**agg).reset_index()
    if razao is not None:
        num, den = razao
        g["v"] = g[num] / g[den].where(g[den] > 0)
        g = g[g["v"].notna() & (g["n"] >= min_n)]
    for uf, gg in g.groupby(uf_col):
        gg = gg.sort_values("v", ascending=menor)
        out[uf] = [{"t": r[transp_col], "v": round(float(r["v"]), 4), "n": int(r["n"]),
                    **{k: round(float(r[k]), 2) for k in extras}} for _, r in gg.iterrows()]
    return out


def dados_sap(df_nf):
    """peso e notas por UF, separado em saídas (destino) e entradas (origem)."""
    res = {"saidas": {}, "entradas": {}}
    if df_nf is None or df_nf.empty:
        return res, {}
    d = df_nf[~df_nf["Cancelada"]].copy()
    d["UF"] = d["BR_NFPartnerRegionCode"].map(_uf)
    d["Transp"] = d["BR_NFPartnerName1"].map(normalizar_transportadora)
    sem = d[d["Transp"] == "Vazio"].groupby(["Direcao", "UF"]).size()
    d = d[(d["Transp"] != "Vazio") & d["UF"].notna()]
    for chave, direcao in (("saidas", "2"), ("entradas", "1")):
        x = d[d["Direcao"] == direcao]
        x = x.drop_duplicates(subset=["BR_NotaFiscal", "BR_NFPartner_1", "Transp"])
        res[chave]["peso"] = _ranking(x, "UF", "Transp", "Peso_kg", {"kg": "Peso_kg", "valor": "Valor"})
        res[chave]["notas"] = _ranking(x.assign(um=1), "UF", "Transp", "um", {"kg": "Peso_kg", "valor": "Valor"})
    sem_transp = {("saidas" if k[0] == "2" else "entradas") + "|" + str(k[1]): int(v) for k, v in sem.items() if k[1]}

    # CT-e recebidos: nota de entrada cujo parceiro é um fornecedor de frete da lista
    forn = pd.read_csv(ARQ_FORNECEDORES, sep=";", dtype=str, encoding="utf-8-sig")
    forn = forn[forn["Categoria"].isin(["Transportadora", "Autônomo", "Internacional"])]
    nomes = dict(zip(forn["Supplier"].str.lstrip("0"), forn["Nome_exibicao"].fillna(forn["Nome_SAP"])))
    e = df_nf[~df_nf["Cancelada"] & (df_nf["Direcao"] == "1")].copy()
    e["Transp"] = e["BR_NFPartner_1"].astype(str).str.lstrip("0").map(nomes)
    e["UF"] = e["BR_NFPartnerRegionCode"].map(_uf)
    e = e[e["Transp"].notna() & e["UF"].notna() & (e["Valor"] > 0)]
    res["entradas"]["cte"] = _ranking(e, "UF", "Transp", "Valor", {})
    return res, sem_transp


def _uf_ponto(row, sufixo):
    uf = _uf(row.get(f"UF ({sufixo}):"))
    if uf:
        return uf
    un = str(row.get(f"Unidade de {sufixo.lower()}:") or "").strip().upper()
    return UNIDADES[un][1] if un in UNIDADES else None


def fretes_pipefy(df_cards, df_cot):
    """Um frete por card: UF de origem/destino, sentido, transportadora, valor e peso."""
    if df_cards is None or df_cards.empty:
        return pd.DataFrame()
    cot = df_cot.drop_duplicates("Nº da cotação").set_index("Nº da cotação") if not df_cot.empty else pd.DataFrame()
    linhas = []
    for _, r in df_cards.iterrows():
        frota = str(r.get("Qual a frota utilizada?") or "").strip().upper()
        if frota in FROTAS_PROPRIAS or frota.startswith("RETIRADO"):
            continue
        sel = tratar_codigo_cotacao(r.get("Qual a cotação selecionada?"))
        q = cot.loc[sel] if sel and not cot.empty and sel in cot.index else None
        transp = normalizar_transportadora(q["Transportadora:"]) if q is not None else "Vazio"
        if transp == "Vazio":
            transp = normalizar_transportadora(r.get("Nome da transportadora"))
        valor = float(r.get("Valor CTE:") or 0) or (float(q["Valor:"]) if q is not None else 0.0)
        if transp in ("Vazio", "FROTA PRÓPRIA") or valor <= 0:
            continue
        emb_un = str(r.get("Unidade de embarque:") or "").strip().upper() in UNIDADES
        des_un = str(r.get("Unidade de desembarque:") or "").strip().upper() in UNIDADES
        uf_o, uf_d = _uf_ponto(r, "Embarque"), _uf_ponto(r, "Desembarque")
        if emb_un or not des_un:
            sentido, uf = "saidas", uf_d
        else:
            sentido, uf = "entradas", uf_o
        if not uf:
            continue
        linhas.append({"sentido": sentido, "UF": uf, "Transp": transp, "Frete": valor,
                       "Peso": float(r.get("Peso total da carga:") or 0)})
    return pd.DataFrame(linhas)


def dados_pipefy(df_fretes, min_fretes=3):
    res = {"saidas": {}, "entradas": {}}
    if df_fretes.empty:
        return res
    for chave in res:
        x = df_fretes[df_fretes["sentido"] == chave]
        res[chave]["frete"] = _ranking(x, "UF", "Transp", "Frete", {"kg": "Peso"})
        y = x[x["Peso"] > 0]
        res[chave]["rkg"] = _ranking(y, "UF", "Transp", "Frete", {"frete": "Frete", "kg": "Peso"}, menor=True,
                                     min_n=min_fretes, razao=("frete", "kg"))
    return res


def montar(df_nf, df_cards, df_cot, min_fretes=3):
    sap, sem_transp = dados_sap(df_nf)
    pip = dados_pipefy(fretes_pipefy(df_cards, df_cot), min_fretes)
    dados = {s: {**sap.get(s, {}), **pip.get(s, {})} for s in ("saidas", "entradas")}
    return dados, sem_transp


def tabela_ranking(dados):
    """Formato longo para download."""
    linhas = []
    for sentido, crits in dados.items():
        for crit, ufs in crits.items():
            for uf, lst in ufs.items():
                for pos, it in enumerate(lst, 1):
                    linhas.append({"Sentido": "Saídas (UF destino)" if sentido == "saidas" else "Entradas (UF origem)",
                                   "Critério": CRITERIOS[crit]["rotulo"], "UF": uf, "Posição": pos,
                                   "Transportadora": it["t"], "Valor do critério": it["v"], "Registros": it["n"],
                                   "Peso (kg)": it.get("kg"), "Frete (R$)": it.get("frete")})
    return pd.DataFrame(linhas)


def html_mapa(dados, sem_transp, min_fretes, altura=640):
    geo = json.load(open(os.path.join(AQUI, "mapa_brasil.json"), encoding="utf-8"))
    payload = json.dumps({"dados": dados, "sem": sem_transp, "crit": CRITERIOS, "ufn": UF_NOMES,
                          "geo": geo, "minf": min_fretes}, ensure_ascii=False)
    return MAPA_HTML.replace("__PAYLOAD__", payload).replace("__ALTURA__", str(altura))


MAPA_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600&family=JetBrains+Mono:wght@300;400;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0c1810;--card:#141f17;--card2:#192419;--bdr:#1d2f20;--bdr2:#253828;--G:#3ecf6e;--A:#f5a623;--R:#f06060;--B:#5ba4cf;
--t:#dff0e4;--t2:#8aab94;--t3:#4a6652;--FH:'Playfair Display',Georgia,serif;--FM:'JetBrains Mono',monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:transparent;color:var(--t);font-family:var(--FM);font-size:12px;overflow:hidden}
.wrap{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:14px;height:__ALTURA__px}
.panel{background:var(--card);border:1px solid var(--bdr);border-radius:6px;padding:12px 14px;position:relative;overflow:hidden}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px}
.lbl{font-size:9px;letter-spacing:1.3px;text-transform:uppercase;color:var(--t2);margin-right:4px}
.mbtn{padding:4px 11px;border:1px solid var(--bdr2);border-radius:3px;background:none;color:var(--t2);font-family:var(--FM);font-size:10px;letter-spacing:.8px;text-transform:uppercase;cursor:pointer}
.mbtn.on{background:var(--G);border-color:var(--G);color:#0c1810;font-weight:700}
.mbtn:hover:not(.on){border-color:var(--G);color:var(--t)}
#map{position:relative;width:100%;height:calc(100% - 64px)}
#map svg{width:100%;height:100%;display:block}
.src{font-size:9px;color:var(--t3);letter-spacing:.6px}
#tt{position:absolute;background:rgba(6,16,10,.97);border:1px solid var(--bdr2);border-radius:4px;padding:9px 13px;font-size:11px;pointer-events:none;display:none;z-index:40;min-width:190px;box-shadow:0 4px 18px rgba(0,0,0,.7)}
.tts{font-family:var(--FH);font-size:.95rem;margin-bottom:6px;color:var(--G)}
.ttr{display:flex;justify-content:space-between;gap:12px;margin-bottom:2px;color:var(--t2);font-size:10px}
.ttv{color:var(--t);font-weight:600}
h3{font-family:var(--FH);font-weight:600;font-size:1rem;margin-bottom:8px}
.leg{max-height:calc(100% - 30px);overflow:auto}
.li{display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--bdr);font-size:10.5px}
.sw{width:11px;height:11px;border-radius:2px;flex:none}
.li .q{margin-left:auto;color:var(--t2)}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;z-index:99}
.mbox{background:var(--card);border:1px solid var(--bdr2);border-radius:8px;width:min(620px,94vw);max-height:86vh;overflow:auto;padding:18px 20px;box-shadow:0 10px 40px rgba(0,0,0,.8)}
.mhd{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px}
.x{background:none;border:1px solid var(--bdr2);color:var(--t2);border-radius:3px;cursor:pointer;font-family:var(--FM);padding:2px 9px}
.sub{color:var(--t2);font-size:10px;margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-size:11px}
th{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--t2);text-align:left;padding:6px 6px;border-bottom:1px solid var(--bdr2)}
td{padding:6px;border-bottom:1px solid var(--bdr);vertical-align:middle}
td.n{text-align:right;white-space:nowrap}
.bb{height:6px;border-radius:3px;background:var(--G);opacity:.85}
.first td{color:var(--G);font-weight:600}
</style></head><body>
<div class="wrap">
 <div class="panel">
  <div class="bar"><span class="lbl">Sentido</span>
   <button class="mbtn on" data-s="saidas">Saídas · UF destino</button><button class="mbtn" data-s="entradas">Entradas · UF origem</button></div>
  <div class="bar" id="cbar"><span class="lbl">Critério</span></div>
  <div id="map"><div id="tt"></div></div>
 </div>
 <div class="panel"><h3>Principal por estado</h3><div class="src" id="src"></div><div class="leg" id="leg"></div></div>
</div>
<div id="modal"><div class="mbox" id="mbox"></div></div>
<script>
const P=__PAYLOAD__;
const PAL=['#3ecf6e','#5ba4cf','#f5a623','#f06060','#b48ef0','#4fd1c5','#e8c547','#ef8fb6','#8fbf5a','#7aa7ff','#d9895b','#9ad4a0','#c9a0dc','#6fc3d9'];
let S='saidas',C='peso';
const fN=new Intl.NumberFormat('pt-BR',{maximumFractionDigits:0}), fB=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0}),
      fK=new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:2,maximumFractionDigits:2});
function fmt(v,f){if(f==='kg')return v>=1000?fN.format(v/1000)+' t':fN.format(v)+' kg';if(f==='n')return fN.format(v)+' notas';if(f==='brl')return fB.format(v);return fK.format(v)+'/kg';}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function cur(){return ((P.dados[S]||{})[C])||{};}
function cores(){const cnt={};Object.values(cur()).forEach(l=>{if(l.length)cnt[l[0].t]=(cnt[l[0].t]||0)+1;});
  const ord=Object.entries(cnt).sort((a,b)=>b[1]-a[1]);const m={};ord.forEach(([t],i)=>m[t]=PAL[i%PAL.length]);return [m,ord];}
const NS='http://www.w3.org/2000/svg';
function build(){
  const map=document.getElementById('map'),tt=document.getElementById('tt');
  map.querySelectorAll('svg').forEach(s=>s.remove());
  const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox',P.geo.viewBox);svg.setAttribute('preserveAspectRatio','xMidYMid meet');
  const byP={};Object.entries(P.geo.uf_path).forEach(([u,i])=>byP[i]=u);
  const [cm,ord]=cores();const d=cur();const crit=P.crit[C];
  P.geo.paths.forEach((pd,i)=>{const uf=byP[i];const l=d[uf]||[];
    const p=document.createElementNS(NS,'path');p.setAttribute('d',pd);
    p.setAttribute('fill',l.length?cm[l[0].t]:'#141f17');p.setAttribute('stroke','rgba(0,0,0,.45)');p.setAttribute('stroke-width','1.2');
    p.style.cursor=l.length?'pointer':'default';
    p.addEventListener('mouseenter',e=>{p.setAttribute('stroke','#fff');p.setAttribute('stroke-width','2');showTT(e,uf,l,crit);});
    p.addEventListener('mousemove',e=>moveTT(e));
    p.addEventListener('mouseleave',()=>{p.setAttribute('stroke','rgba(0,0,0,.45)');p.setAttribute('stroke-width','1.2');tt.style.display='none';});
    p.addEventListener('click',()=>{if(l.length)openModal(uf,l,crit);});
    svg.appendChild(p);
    const co=[...pd.matchAll(/([-\d.]+)\s+([-\d.]+)/g)].map(m=>[+m[1],+m[2]]);
    if(uf&&co.length){const cx=co.reduce((s,c)=>s+c[0],0)/co.length,cy=co.reduce((s,c)=>s+c[1],0)/co.length;
      const t=document.createElementNS(NS,'text');t.setAttribute('x',cx);t.setAttribute('y',cy);t.setAttribute('text-anchor','middle');
      t.setAttribute('font-family','JetBrains Mono,monospace');t.setAttribute('font-size','9');t.setAttribute('font-weight','600');
      t.setAttribute('fill',l.length?'#0c1810':'rgba(255,255,255,.5)');t.setAttribute('pointer-events','none');t.textContent=uf;svg.appendChild(t);
      if(l.length){const t2=document.createElementNS(NS,'text');t2.setAttribute('x',cx);t2.setAttribute('y',cy+10);t2.setAttribute('text-anchor','middle');
        t2.setAttribute('font-family','JetBrains Mono,monospace');t2.setAttribute('font-size','6.5');t2.setAttribute('fill','rgba(12,24,16,.85)');
        t2.setAttribute('pointer-events','none');t2.textContent=l[0].t.split(' ')[0].slice(0,10);svg.appendChild(t2);}}
  });
  map.insertBefore(svg,tt);
  const leg=document.getElementById('leg');
  if(crit.so&&crit.so!==S){leg.innerHTML=`<div class="sub">${esc(crit.aviso)}</div>`;document.getElementById('src').textContent='Fonte: '+crit.fonte;return;}
  leg.innerHTML=ord.length?ord.map(([t,q])=>`<div class="li"><span class="sw" style="background:${cm[t]}"></span>${esc(t)}<span class="q">${q} UF${q>1?'s':''}</span></div>`).join('')
    :'<div class="sub">Sem dados para este critério no período.</div>';
  document.getElementById('src').textContent='Fonte: '+crit.fonte+(C==='rkg'?` · mín. ${P.minf} fretes`:'')+' · clique no estado para a lista completa';
}
function showTT(e,uf,l,crit){const tt=document.getElementById('tt');if(!uf)return;
  let h=`<div class="tts">${esc(P.ufn[uf]||uf)}</div>`;
  if(!l.length){h+='<div class="ttr"><span>Sem dados</span></div>';}
  else{h+=`<div class="ttr"><span>${esc(l[0].t)}</span><span class="ttv">${fmt(l[0].v,crit.fmt)}</span></div>`;
    if(l[1])h+=`<div class="ttr"><span>2º ${esc(l[1].t)}</span><span>${fmt(l[1].v,crit.fmt)}</span></div>`;
    h+=`<div class="ttr"><span>Transportadoras</span><span>${l.length}</span></div>`;}
  const sem=P.sem[S+'|'+uf];if(sem&&(C==='peso'||C==='notas'))h+=`<div class="ttr"><span>Notas sem transportadora</span><span>${fN.format(sem)}</span></div>`;
  tt.innerHTML=h;tt.style.display='block';moveTT(e);}
function moveTT(e){const tt=document.getElementById('tt'),b=document.getElementById('map').getBoundingClientRect();
  let x=e.clientX-b.left+14,y=e.clientY-b.top+14;if(x+220>b.width)x-=236;if(y+120>b.height)y-=130;tt.style.left=x+'px';tt.style.top=y+'px';}
function openModal(uf,l,crit){
  const mx=crit.menor?Math.max(...l.map(i=>i.v)):l[0].v;const tot=l.reduce((s,i)=>s+i.v,0);
  const extra=(C==='peso'||C==='notas')?['Notas','Peso','Valor das notas']:(C==='frete'?['Fretes','Peso (Pipefy)']:(C==='cte'?['CT-e']:['Fretes','Frete','Peso']));
  const rows=l.map((i,k)=>{const w=Math.max(3,100*(crit.menor?(mx?i.v/mx:0):(mx?i.v/mx:0)));
    let ex=(C==='peso'||C==='notas')?`<td class="n">${fN.format(i.n)}</td><td class="n">${fmt(i.kg,'kg')}</td><td class="n">${fB.format(i.valor||0)}</td>`
      :C==='cte'?`<td class="n">${fN.format(i.n)}</td>`
      :(C==='frete'?`<td class="n">${fN.format(i.n)}</td><td class="n">${i.kg?fmt(i.kg,'kg'):'—'}</td>`:`<td class="n">${fN.format(i.n)}</td><td class="n">${fB.format(i.frete)}</td><td class="n">${fmt(i.kg,'kg')}</td>`);
    const pct=(!crit.menor&&tot)?` <span style="color:var(--t2)">(${(100*i.v/tot).toFixed(1)}%)</span>`:'';
    return `<tr class="${k?'':'first'}"><td>${k+1}º</td><td>${esc(i.t)}</td><td class="n">${fmt(i.v,crit.fmt)}${pct}</td><td style="width:90px"><div class="bb" style="width:${w}%"></div></td>${ex}</tr>`;}).join('');
  document.getElementById('mbox').innerHTML=`<div class="mhd"><h3>${esc(P.ufn[uf]||uf)} · ${esc(crit.rotulo)}</h3><button class="x" onclick="closeM()">fechar ✕</button></div>
   <div class="sub">${C==='cte'?'CT-e emitidos por filiais de transportadoras neste estado':(S==='saidas'?'Saídas para o estado (destino)':'Entradas vindas do estado (origem)')} · ${esc(crit.fonte)} · ${crit.menor?'ordem crescente (mais barata primeiro)':'ordem decrescente'}</div>
   <table><thead><tr><th>#</th><th>Transportadora</th><th style="text-align:right">${esc(crit.rotulo)}</th><th></th>${extra.map(x=>`<th style="text-align:right">${x}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`;
  document.getElementById('modal').style.display='flex';}
function closeM(){document.getElementById('modal').style.display='none';}
document.getElementById('modal').addEventListener('click',e=>{if(e.target.id==='modal')closeM();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeM();});
const cb=document.getElementById('cbar');
Object.entries(P.crit).forEach(([k,c])=>{const b=document.createElement('button');b.className='mbtn'+(k===C?' on':'');b.dataset.c=k;b.textContent=c.rotulo;
  b.onclick=()=>{C=k;cb.querySelectorAll('.mbtn').forEach(x=>x.classList.toggle('on',x.dataset.c===C));build();};cb.appendChild(b);});
document.querySelectorAll('[data-s]').forEach(b=>b.onclick=()=>{S=b.dataset.s;document.querySelectorAll('[data-s]').forEach(x=>x.classList.toggle('on',x.dataset.s===S));build();});
build();
</script></body></html>"""
