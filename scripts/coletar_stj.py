#!/usr/bin/env python3
"""
Monitor STJ — Marquez Advogados
Consulta o Datajud por código de gabinete (método comprovado no notebook),
gera stj/index.html para GitHub Pages.
"""
 
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, date, timedelta
from collections import Counter
 
# ── Configuração ──────────────────────────────────────────────────────────────
API_KEY  = os.environ.get("DATAJUD_API_KEY", "")
API_URL  = "https://api-publica.datajud.cnj.jus.br/api_publica_stj/_search"
 
TERCEIRA_TURMA = {
    76747: "Antonio Carlos Ferreira",
    76761: "Marco Aurélio Bellizze",
    76768: "Moura Ribeiro",
    76764: "Nancy Andrighi",
    76779: "Ricardo Villas Bôas Cueva",
}
QUARTA_TURMA = {
    76762: "Marco Buzzi",
    76766: "Luis Felipe Salomão",
    76769: "João Otávio de Noronha",
    76772: "Raul Araújo Filho",
    76764: "Maria Isabel Gallotti",
}
CORTE_ESPECIAL = {
    76749: "Assusete Magalhães",
    76750: "Benedito Gonçalves",
    76753: "Francisco Falcão",
    76754: "Herman Benjamin",
    76756: "Humberto Martins",
    76759: "Laurita Hilário Vaz",
    76769: "João Otávio de Noronha",
    76770: "Og Fernandes",
    76772: "Raul Araújo Filho",
    76764: "Maria Isabel Gallotti",
    76766: "Luis Felipe Salomão",
}
 
# Mapa código → (órgão, ministro) — igual ao notebook
CODIGO_PARA_ORGAO = {}
for cod, nome in TERCEIRA_TURMA.items():
    CODIGO_PARA_ORGAO[cod] = ("3ª Turma", nome)
for cod, nome in QUARTA_TURMA.items():
    if cod not in CODIGO_PARA_ORGAO:
        CODIGO_PARA_ORGAO[cod] = ("4ª Turma", nome)
for cod, nome in CORTE_ESPECIAL.items():
    if cod not in CODIGO_PARA_ORGAO:
        CODIGO_PARA_ORGAO[cod] = ("Corte Especial", nome)
 
TODOS_CODIGOS = set(TERCEIRA_TURMA) | set(QUARTA_TURMA) | set(CORTE_ESPECIAL)
 
MOV_PAUTADO    = 417
MOV_DISTRIBUIDO = 26
CODIGOS_CANCELAMENTO = {12106, 897, 193}
 
AREAS_EXCLUIR = {"Tributário / Fiscal", "Trabalhista / Previdenciário"}
 
AREAS = {
    "Empresarial / Societário": [
        "societári","sócio","dissolução parcial","apuração de haveres","holding",
        "recuperação judicial","falência","fusão","cisão","incorporação de empresa",
        "concorrência desleal","propriedade intelectual","marca","patente",
        "título de crédito","cheque","duplicata","nota promissória","protesto",
    ],
    "Contratos": [
        "contrato","inadimplemento","rescisão contratual","resolução contratual",
        "fornecimento","empreitada","prestação de serviços","cláusula penal",
        "revisão contratual","onerosidade excessiva","vício redibitório",
        "promessa de compra e venda","fiança","seguro","leasing","factoring",
        "cessão de crédito","novação","transação",
    ],
    "Imobiliário": [
        "incorporação imobiliária","locação","aluguel","compra e venda de imóvel",
        "loteamento","condomínio","reintegração de posse","usucapião",
        "financiamento imobiliário","alienação fiduciária de imóvel",
        "registro de imóveis","despejo","corretagem imobiliária",
        "multipropriedade","posse","esbulho","turbação",
    ],
    "Civil / Responsabilidade": [
        "responsabilidade civil","dano moral","dano material","dano estético",
        "indenização","responsabilidade médica","erro médico",
        "acidente de trânsito","nexo causal","perda de uma chance",
        "código de defesa do consumidor","consumidor","negativação indevida",
        "fraude bancária","phishing","clonagem de cartão",
    ],
    "Família e Sucessões": [
        "inventário","herança","sucessão","testamento","união estável",
        "divórcio","alimentos","guarda","holding familiar","regime de bens",
        "meação","partilha","herdeiro","filiação","bem de família","doação",
    ],
    "Arbitragem / ADR": [
        "arbitragem","sentença arbitral","cláusula compromissória",
        "dispute board","mediação","anulação de sentença arbitral",
    ],
    "Bancário / Financeiro": [
        "contrato bancário","mútuo bancário","financiamento","empréstimo",
        "juros","capitalização de juros","anatocismo","cartão de crédito",
        "busca e apreensão","alienação fiduciária","sigilo bancário",
    ],
    "Tributário / Fiscal": [
        "tributo","imposto","taxa","contribuição","fisco","execução fiscal",
        "icms","iss","ipi","ir ","csll","pis","cofins","simples nacional",
    ],
    "Trabalhista / Previdenciário": [
        "trabalhista","vínculo empregatício","horas extras","fgts","inss",
        "benefício previdenciário","aposentadoria","pensão por morte",
    ],
    "Processo Civil": [
        "coisa julgada","litispendência","competência","legitimidade",
        "prescrição","tutela antecipada","execução","cumprimento de sentença",
        "penhora","ação rescisória","honorários advocatícios",
    ],
}
 
# ── Utilitários ───────────────────────────────────────────────────────────────
def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)
 
def classificar_area(texto):
    t = (texto or "").lower()
    for area, kws in AREAS.items():
        if any(k in t for k in kws):
            return area
    return "Outros / Verificar"
 
def extrair_assuntos(assuntos):
    if not assuntos: return ""
    nomes = []
    for a in assuntos[:4]:
        if isinstance(a, dict): nomes.append(a.get("nome",""))
        elif isinstance(a, str): nomes.append(a)
    return "; ".join(n for n in nomes if n)
 
def analisar_pauta(movimentos):
    """Mesma lógica do notebook: retorna (situacao, data_inclusao)"""
    if not movimentos: return "sem_pauta", ""
    movs = sorted(movimentos, key=lambda m: m.get("dataHora",""))
    ultimo_idx, ultima_data = None, ""
    for i, m in enumerate(movs):
        if m.get("codigo") == MOV_PAUTADO:
            data_mov = m.get("dataHora","")[:10]
            try:
                dt_mov = datetime.strptime(data_mov, "%Y-%m-%d").date()
                if (date.today() - dt_mov).days > 60: continue
            except: continue
            ultimo_idx, ultima_data = i, data_mov
    if ultimo_idx is None: return "sem_pauta", ""
    for m in movs[ultimo_idx + 1:]:
        if m.get("codigo") in CODIGOS_CANCELAMENTO:
            return "cancelado", ultima_data
    return "pautado", ultima_data
 
def calcular_urgencia(data_inclusao):
    if not data_inclusao: return "Baixa"
    try:
        dias = (date.today() - datetime.strptime(data_inclusao, "%Y-%m-%d").date()).days
        if dias <= 7:  return "Alta"
        if dias <= 30: return "Média"
        return "Baixa"
    except: return "Baixa"
 
def data_fmt(d):
    if not d: return ""
    try: return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except: return d
 
def data_dist_mais_recente(movimentos):
    """Retorna a data mais recente do movimento de distribuição (26)."""
    datas = [m.get("dataHora","")[:10] for m in (movimentos or []) if m.get("codigo") == MOV_DISTRIBUIDO]
    return max(datas) if datas else ""
 
# ── API ───────────────────────────────────────────────────────────────────────
def query_gabinete(codigo_orgao, movimento, size=200):
    if not API_KEY:
        log("ERRO: variável DATAJUD_API_KEY não definida.")
        sys.exit(1)
    body = {
        "size": size,
        "query": {
            "bool": {
                "must": [
                    {"term": {"orgaoJulgador.codigo": codigo_orgao}},
                    {"term": {"movimentos.codigo": movimento}},
                ]
            }
        },
        "_source": [
            "numeroProcesso","classe","orgaoJulgador",
            "assuntos","movimentos","dataAjuizamento"
        ],
    }
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"APIKey {API_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        log(f"  HTTP {e.code} no gabinete {codigo_orgao}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        log(f"  Erro no gabinete {codigo_orgao}: {e}")
        return None
 
# ── Coleta ────────────────────────────────────────────────────────────────────
def coletar():
    pautados, distribuidos, vistos_p, vistos_d = [], [], set(), set()
 
    # ── Pautados (movimento 417, últimos 60 dias) ──
    log("=== Coletando pautados (mov. 417) ===")
    for codigo in sorted(TODOS_CODIGOS):
        orgao_str, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query_gabinete(codigo, MOV_PAUTADO)
        if not dados: continue
        hits = dados.get("hits",{}).get("hits",[])
        total = dados.get("hits",{}).get("total",{}).get("value",0)
        log(f"  {orgao_str} — {ministro} (cód.{codigo}): {total} com mov.417, analisando {len(hits)}")
        for hit in hits:
            src    = hit.get("_source",{})
            numero = src.get("numeroProcesso","")
            if numero in vistos_p: continue
            vistos_p.add(numero)
            assuntos   = extrair_assuntos(src.get("assuntos",[]))
            area       = classificar_area(assuntos)
            if area in AREAS_EXCLUIR: continue
            movimentos = src.get("movimentos",[])
            situacao, data_pauta = analisar_pauta(movimentos)
            if situacao != "pautado": continue
            urgencia = calcular_urgencia(data_pauta)
            link = (f"https://processo.stj.jus.br/processo/pesquisa/"
                    f"?aplicacao=processos.ea&tipoPesquisa=tipoPesquisaNumeroUnico&termo={urllib.parse.quote(numero)}")
            pautados.append({
                "numero":      numero,
                "orgao":       orgao_str,
                "ministro":    ministro,
                "area":        area,
                "assuntos":    assuntos,
                "data_pauta":  data_fmt(data_pauta),
                "data_sort":   data_pauta,
                "urgencia":    urgencia,
                "link":        link,
                "tipo":        "pautado",
            })
        time.sleep(0.3)
 
    # ── Distribuídos (movimento 26, últimos 30 dias) ──
    log("=== Coletando distribuídos (mov. 26) ===")
    since = (date.today() - timedelta(days=30)).isoformat()
    for codigo in sorted(TODOS_CODIGOS):
        orgao_str, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query_gabinete(codigo, MOV_DISTRIBUIDO)
        if not dados: continue
        hits = dados.get("hits",{}).get("hits",[])
        total = dados.get("hits",{}).get("total",{}).get("value",0)
        log(f"  {orgao_str} — {ministro} (cód.{codigo}): {total} com mov.26, analisando {len(hits)}")
        for hit in hits:
            src    = hit.get("_source",{})
            numero = src.get("numeroProcesso","")
            if numero in vistos_d or numero in vistos_p: continue
            movimentos = src.get("movimentos",[])
            data_d = data_dist_mais_recente(movimentos)
            if data_d < since: continue          # filtra só últimos 30 dias
            vistos_d.add(numero)
            assuntos = extrair_assuntos(src.get("assuntos",[]))
            area     = classificar_area(assuntos)
            if area in AREAS_EXCLUIR: continue
            link = (f"https://processo.stj.jus.br/processo/pesquisa/"
                    f"?aplicacao=processos.ea&tipoPesquisa=tipoPesquisaNumeroUnico&termo={urllib.parse.quote(numero)}")
            distribuidos.append({
                "numero":      numero,
                "orgao":       orgao_str,
                "ministro":    ministro,
                "area":        area,
                "assuntos":    assuntos,
                "data_dist":   data_fmt(data_d),
                "data_sort":   data_d,
                "urgencia":    "—",
                "link":        link,
                "tipo":        "distribuido",
            })
        time.sleep(0.3)
 
    pautados.sort(key=lambda x: ({"Alta":0,"Média":1,"Baixa":2}.get(x["urgencia"],3), x["data_sort"]))
    distribuidos.sort(key=lambda x: x["data_sort"], reverse=True)
    return pautados, distribuidos
 
# ── HTML ─────────────────────────────────────────────────────────────────────
def gerar_html(pautados, distribuidos, atualizado):
    todos = pautados + distribuidos
    total      = len(todos)
    n_alta     = sum(1 for p in pautados if p["urgencia"]=="Alta")
    n_media    = sum(1 for p in pautados if p["urgencia"]=="Média")
    n_baixa    = sum(1 for p in pautados if p["urgencia"]=="Baixa")
    n_dist     = len(distribuidos)
    n_3t       = sum(1 for p in todos if p["orgao"]=="3ª Turma")
    n_4t       = sum(1 for p in todos if p["orgao"]=="4ª Turma")
    n_ce       = sum(1 for p in todos if p["orgao"]=="Corte Especial")
 
    dados_json = json.dumps(todos, ensure_ascii=False)
 
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor STJ · Marquez Advogados</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#0f1117;--sur:#1a1d2e;--sur2:#22263a;--bdr:#2e3250;
  --acc:#6c7bff;--text:#e2e8f0;--mut:#8892b0;
  --alt:#f87171;--med:#fbbf24;--ok:#4ade80;--inf:#60a5fa;
  --font:'Inter',system-ui,sans-serif
}}
body{{background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px}}
/* ── header ── */
header{{
  background:var(--sur);border-bottom:1px solid var(--bdr);
  padding:18px 32px;display:flex;align-items:center;
  justify-content:space-between;gap:12px;flex-wrap:wrap
}}
.logo-wrap{{display:flex;align-items:center;gap:12px}}
.logo-box{{width:36px;height:36px;background:var(--acc);border-radius:9px;
  display:grid;place-items:center;font-size:17px}}
.logo-wrap h1{{font-size:16px;font-weight:700}}
.logo-wrap p{{font-size:11px;color:var(--mut);margin-top:1px}}
.badge-up{{
  background:var(--sur2);border:1px solid var(--bdr);border-radius:8px;
  padding:5px 12px;font-size:11px;color:var(--mut);display:flex;
  align-items:center;gap:6px
}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--ok);
  animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
/* ── cards ── */
.cards{{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
  gap:12px;padding:22px 32px
}}
.card{{
  background:var(--sur);border:1px solid var(--bdr);border-radius:12px;
  padding:14px;position:relative;overflow:hidden;transition:border-color .2s
}}
.card:hover{{border-color:var(--acc)}}
.c-lbl{{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px}}
.c-val{{font-size:26px;font-weight:800;line-height:1}}
.c-bar{{position:absolute;bottom:0;left:0;right:0;height:3px;border-radius:0 0 12px 12px}}
.ca .c-val{{color:var(--acc)}} .ca .c-bar{{background:var(--acc)}}
.cd .c-val{{color:var(--alt)}} .cd .c-bar{{background:var(--alt)}}
.cm .c-val{{color:var(--med)}} .cm .c-bar{{background:var(--med)}}
.cb .c-val{{color:var(--ok)}}  .cb .c-bar{{background:var(--ok)}}
.ci .c-val{{color:var(--inf)}} .ci .c-bar{{background:var(--inf)}}
/* ── tabs ── */
.tabs{{
  display:flex;gap:4px;padding:0 32px;
  border-bottom:1px solid var(--bdr);margin-top:4px
}}
.tab{{
  padding:8px 16px;border-radius:8px 8px 0 0;cursor:pointer;
  font-size:13px;font-weight:500;color:var(--mut);
  border:1px solid transparent;border-bottom:none;background:transparent
}}
.tab.on{{
  background:var(--sur);border-color:var(--bdr);
  border-bottom:1px solid var(--sur);color:var(--text);margin-bottom:-1px
}}
.tab:hover:not(.on){{background:var(--sur2);color:var(--text)}}
/* ── toolbar ── */
.bar{{
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:14px 32px;background:var(--sur);border-bottom:1px solid var(--bdr)
}}
.sw{{position:relative;flex:1;min-width:180px;max-width:320px}}
.sw input{{
  width:100%;background:var(--sur2);border:1px solid var(--bdr);
  border-radius:8px;padding:7px 10px 7px 30px;color:var(--text);
  font-size:13px;outline:none
}}
.sw input:focus{{border-color:var(--acc)}}
.sw::before{{content:"🔍";position:absolute;left:9px;top:50%;transform:translateY(-50%);font-size:11px}}
select{{
  background:var(--sur2);border:1px solid var(--bdr);border-radius:8px;
  color:var(--text);padding:7px 10px;font-size:13px;cursor:pointer;outline:none
}}
.cnt{{
  margin-left:auto;background:var(--sur2);border:1px solid var(--bdr);
  border-radius:6px;padding:4px 10px;font-size:11px;color:var(--mut);white-space:nowrap
}}
/* ── table ── */
.twrap{{overflow-x:auto;padding:0 32px 40px}}
table{{width:100%;border-collapse:collapse;margin-top:14px}}
thead th{{
  text-align:left;padding:9px 10px;font-size:10px;font-weight:600;
  color:var(--mut);text-transform:uppercase;letter-spacing:.6px;
  border-bottom:1px solid var(--bdr);white-space:nowrap;cursor:pointer
}}
thead th:hover{{color:var(--text)}}
.sa::after{{content:" ▲";color:var(--acc)}} .sd::after{{content:" ▼";color:var(--acc)}}
tbody tr{{border-bottom:1px solid var(--bdr);transition:background .1s}}
tbody tr:hover{{background:var(--sur2)}}
tbody td{{padding:11px 10px;vertical-align:top}}
.num{{color:var(--acc);text-decoration:none;font-weight:600;font-size:13px;white-space:nowrap}}
.num:hover{{color:#a78bfa;text-decoration:underline}}
.bp{{
  display:inline-block;padding:2px 8px;border-radius:20px;
  font-size:11px;font-weight:600;white-space:nowrap
}}
.u-Alta{{background:rgba(248,113,113,.15);color:#f87171;border:1px solid rgba(248,113,113,.3)}}
.u-Média{{background:rgba(251,191,36,.15);color:#fbbf24;border:1px solid rgba(251,191,36,.3)}}
.u-Baixa{{background:rgba(74,222,128,.15);color:#4ade80;border:1px solid rgba(74,222,128,.3)}}
.u-—{{background:rgba(96,165,250,.1);color:#60a5fa;border:1px solid rgba(96,165,250,.2)}}
.orgpill{{
  display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;
  background:var(--sur2);border:1px solid var(--bdr);color:var(--mut)
}}
.muted{{font-size:12px;color:var(--mut);max-width:260px}}
.empty{{text-align:center;padding:60px 20px;color:var(--mut)}}
.empty .ico{{font-size:36px;margin-bottom:10px}}
::-webkit-scrollbar{{width:5px;height:5px}}
::-webkit-scrollbar-track{{background:var(--bg)}}
::-webkit-scrollbar-thumb{{background:var(--bdr);border-radius:3px}}
@media(max-width:700px){{
  header,.cards,.tabs,.bar,.twrap{{padding-left:14px;padding-right:14px}}
}}
</style>
</head>
<body>
 
<header>
  <div class="logo-wrap">
    <div class="logo-box">⚖️</div>
    <div>
      <h1>Monitor STJ</h1>
      <p>Marquez Advogados · Prospecção Ativa</p>
    </div>
  </div>
  <div class="badge-up">
    <span class="dot"></span>
    Atualizado em <strong style="margin-left:4px">{atualizado}</strong>
  </div>
</header>
 
<div class="cards">
  <div class="card ca"><div class="c-lbl">Total</div><div class="c-val">{total}</div><div class="c-bar"></div></div>
  <div class="card cd"><div class="c-lbl">Alta urgência</div><div class="c-val">{n_alta}</div><div class="c-bar"></div></div>
  <div class="card cm"><div class="c-lbl">Média urgência</div><div class="c-val">{n_media}</div><div class="c-bar"></div></div>
  <div class="card cb"><div class="c-lbl">Baixa urgência</div><div class="c-val">{n_baixa}</div><div class="c-bar"></div></div>
  <div class="card ci"><div class="c-lbl">Distribuídos 30d</div><div class="c-val">{n_dist}</div><div class="c-bar"></div></div>
  <div class="card ca"><div class="c-lbl">3ª Turma</div><div class="c-val">{n_3t}</div><div class="c-bar"></div></div>
  <div class="card ca"><div class="c-lbl">4ª Turma</div><div class="c-val">{n_4t}</div><div class="c-bar"></div></div>
  <div class="card ca"><div class="c-lbl">Corte Especial</div><div class="c-val">{n_ce}</div><div class="c-bar"></div></div>
</div>
 
<div class="tabs">
  <div class="tab on"  onclick="tab('pautado',this)">📋 Pautados ({len(pautados)})</div>
  <div class="tab"     onclick="tab('distribuido',this)">📨 Distribuídos ({len(distribuidos)})</div>
  <div class="tab"     onclick="tab('todos',this)">📂 Todos ({total})</div>
</div>
 
<div class="bar">
  <div class="sw"><input id="q" type="text" placeholder="Número, ministro, assunto…" oninput="render()"></div>
  <select id="fo" onchange="render()">
    <option value="">Todos os órgãos</option>
    <option>3ª Turma</option><option>4ª Turma</option><option>Corte Especial</option>
  </select>
  <select id="fa" onchange="render()"><option value="">Todas as áreas</option></select>
  <select id="fu" onchange="render()">
    <option value="">Todas urgências</option>
    <option value="Alta">🔴 Alta</option>
    <option value="Média">🟡 Média</option>
    <option value="Baixa">🟢 Baixa</option>
  </select>
  <span class="cnt" id="cnt">— processos</span>
</div>
 
<div class="twrap">
  <table><thead id="th"></thead><tbody id="tb"></tbody></table>
  <div class="empty" id="emp" style="display:none">
    <div class="ico">🔍</div><p>Nenhum processo com esses filtros.</p>
  </div>
</div>
 
<script>
const D={dados};
let tabAtual="pautado",sCol="data_sort",sDir=-1;
const CPAUT=[
  {{k:"numero",l:"Número"}},{{k:"orgao",l:"Órgão"}},{{k:"ministro",l:"Ministro/a"}},
  {{k:"area",l:"Área"}},{{k:"assuntos",l:"Assuntos"}},
  {{k:"data_pauta",l:"Data Pauta"}},{{k:"urgencia",l:"Urgência"}}
];
const CDIST=[
  {{k:"numero",l:"Número"}},{{k:"orgao",l:"Órgão"}},{{k:"ministro",l:"Ministro/a"}},
  {{k:"area",l:"Área"}},{{k:"assuntos",l:"Assuntos"}},{{k:"data_dist",l:"Distribuído em"}}
];
function tab(t,el){{
  tabAtual=t;document.querySelectorAll(".tab").forEach(x=>x.classList.remove("on"));
  el.classList.add("on");sCol="data_sort";sDir=-1;render();
}}
function filtered(){{
  const q=document.getElementById("q").value.toLowerCase();
  const fo=document.getElementById("fo").value;
  const fa=document.getElementById("fa").value;
  const fu=document.getElementById("fu").value;
  return D.filter(p=>{{
    if(tabAtual!=="todos"&&p.tipo!==tabAtual)return false;
    if(fo&&p.orgao!==fo)return false;
    if(fa&&p.area!==fa)return false;
    if(fu&&p.urgencia!==fu)return false;
    if(q){{
      const h=[p.numero,p.ministro,p.assuntos,p.area,p.orgao].join(" ").toLowerCase();
      if(!h.includes(q))return false;
    }}
    return true;
  }});
}}
function sorted(arr){{
  return[...arr].sort((a,b)=>{{
    let va=a[sCol]||"",vb=b[sCol]||"";
    return sDir*(va>vb?1:va<vb?-1:0);
  }});
}}
function setSort(col){{sCol===col?sDir*=-1:(sCol=col,sDir=-1);render();}}
function badge(u){{
  return`<span class="bp u-${{u}}">${{u==="Alta"?"🔴 Alta":u==="Média"?"🟡 Média":u==="Baixa"?"🟢 Baixa":"📨 Dist."}}</span>`;
}}
function render(){{
  const rows=sorted(filtered());
  const cols=tabAtual==="distribuido"?CDIST:CPAUT;
  document.getElementById("th").innerHTML="<tr>"+cols.map(c=>{{
    let cl=sCol===c.k?(sDir===-1?"sd":"sa"):"";
    return`<th class="${{cl}}" onclick="setSort('${{c.k}}')">${{c.l}}</th>`;
  }}).join("")+"</tr>";
  const emp=document.getElementById("emp");
  if(!rows.length){{
    document.querySelector("table").style.display="none";
    emp.style.display="block";
    document.getElementById("cnt").textContent="0 processos";
    return;
  }}
  document.querySelector("table").style.display="table";
  emp.style.display="none";
  document.getElementById("cnt").textContent=rows.length+" processo"+(rows.length!==1?"s":"");
  const useCols=tabAtual==="distribuido"?CDIST:CPAUT;
  document.getElementById("tb").innerHTML=rows.map(p=>
    "<tr>"+useCols.map(c=>{{
      if(c.k==="numero")return`<td><a class="num" href="${{p.link}}" target="_blank">${{p.numero}}</a></td>`;
      if(c.k==="orgao")return`<td><span class="orgpill">${{p.orgao}}</span></td>`;
      if(c.k==="urgencia")return`<td>${{badge(p.urgencia)}}</td>`;
      if(c.k==="assuntos")return`<td class="muted" title="${{p.assuntos}}">${{(p.assuntos||"").length>70?p.assuntos.slice(0,70)+"…":p.assuntos||"—"}}</td>`;
      return`<td>${{p[c.k]||"—"}}</td>`;
    }}).join("")+"</tr>"
  ).join("");
}}
function initAreas(){{
  const ar=[...new Set(D.map(p=>p.area))].sort();
  const s=document.getElementById("fa");
  ar.forEach(a=>{{const o=document.createElement("option");o.value=a;o.text=a;s.appendChild(o);}});
}}
initAreas();render();
</script>
</body></html>""".replace("{dados}", dados_json)
 
# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pautados, distribuidos = coletar()
 
    log(f"Pautados: {len(pautados)} | Alta: {sum(1 for p in pautados if p['urgencia']=='Alta')} | "
        f"Média: {sum(1 for p in pautados if p['urgencia']=='Média')} | "
        f"Baixa: {sum(1 for p in pautados if p['urgencia']=='Baixa')}")
    log(f"Distribuídos (30d): {len(distribuidos)}")
 
    atualizado = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = gerar_html(pautados, distribuidos, atualizado)
 
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stj")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"HTML salvo → {out}")
 
if __name__ == "__main__":
    main()
 
