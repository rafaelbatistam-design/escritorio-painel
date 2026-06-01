#!/usr/bin/env python3
"""
Monitor STJ — Marquez Advogados
Gera stj/data.json e stj/index.html para GitHub Pages.
JSON separado do HTML elimina qualquer risco de quebra de JavaScript.
"""
 
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, date, timedelta
 
# ── Configuração ──────────────────────────────────────────────────────────────
API_KEY = os.environ.get("DATAJUD_API_KEY", "")
API_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_stj/_search"
 
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
 
MOV_PAUTADO     = 417
MOV_DISTRIBUIDO = 26
MOV_CONCLUSO    = 51
CODIGOS_CANCEL  = {12106, 897, 193}
 
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
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)
 
def classificar_area(texto):
    t = (texto or "").lower()
    for area, kws in AREAS.items():
        if any(k in t for k in kws):
            return area
    return "Outros / Verificar"
 
def extrair_assuntos(assuntos):
    if not assuntos:
        return ""
    nomes = []
    for a in assuntos[:4]:
        if isinstance(a, dict):
            nomes.append(a.get("nome", ""))
        elif isinstance(a, str):
            nomes.append(a)
    return "; ".join(n for n in nomes if n)
 
def analisar_pauta(movimentos):
    if not movimentos:
        return "sem_pauta", ""
    movs = sorted(movimentos, key=lambda m: m.get("dataHora", ""))
    ultimo_idx, ultima_data = None, ""
    for i, m in enumerate(movs):
        if m.get("codigo") == MOV_PAUTADO:
            ultima_data = m.get("dataHora", "")[:10]
            ultimo_idx  = i
    if ultimo_idx is None:
        return "sem_pauta", ""
    for m in movs[ultimo_idx + 1:]:
        if m.get("codigo") in CODIGOS_CANCEL:
            return "cancelado", ultima_data
    return "pautado", ultima_data
 
def data_mais_recente_mov(movimentos, codigo_mov):
    datas = [m.get("dataHora", "")[:10]
             for m in (movimentos or []) if m.get("codigo") == codigo_mov]
    return max(datas) if datas else ""
 
def calcular_urgencia(data_inclusao):
    if not data_inclusao:
        return "Baixa"
    try:
        dias = (date.today() - datetime.strptime(data_inclusao, "%Y-%m-%d").date()).days
        if dias <= 7:  return "Alta"
        if dias <= 30: return "Média"
        return "Baixa"
    except:
        return "Baixa"
 
def fmt_data(d):
    if not d:
        return ""
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        return d
 
def stj_link(numero):
    return ("https://processo.stj.jus.br/processo/pesquisa/"
            "?aplicacao=processos.ea&tipoPesquisa=tipoPesquisaNumeroUnico"
            f"&termo={urllib.parse.quote(numero)}")
 
# ── API ───────────────────────────────────────────────────────────────────────
def post_api(body):
    if not API_KEY:
        log("ERRO: variável DATAJUD_API_KEY não definida.")
        sys.exit(1)
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"APIKey {API_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        log(f"  HTTP {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        log(f"  Erro: {e}")
        return None
 
def query_por_movimento(codigo_gabinete, codigo_mov, since_iso=None):
    must = [
        {"term": {"orgaoJulgador.codigo": codigo_gabinete}},
        {"term": {"movimentos.codigo": codigo_mov}},
    ]
    if since_iso:
        must.append({"range": {"dataAjuizamento": {"gte": since_iso}}})
    return post_api({
        "size": 200,
        "query": {"bool": {"must": must}},
        "_source": ["numeroProcesso", "classe", "orgaoJulgador",
                    "assuntos", "movimentos", "dataAjuizamento"],
        "sort": [{"dataAjuizamento": {"order": "desc"}}],
    })
 
# ── Coleta ────────────────────────────────────────────────────────────────────
def coletar():
    pautados    = []
    distribuidos = []
    conclusos   = []
    vistos      = set()
 
    # ── 1. Pautados (mov.417) ─────────────────────────────────────────────────
    log("=== Pautados (mov.417) ===")
    for codigo in sorted(TODOS_CODIGOS):
        orgao, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query_por_movimento(codigo, MOV_PAUTADO)
        if not dados: continue
        hits  = dados.get("hits", {}).get("hits", [])
        total = dados.get("hits", {}).get("total", {}).get("value", 0)
        log(f"  {orgao} — {ministro}: {total} com mov.417")
        for hit in hits:
            src    = hit.get("_source", {})
            numero = src.get("numeroProcesso", "")
            if numero in vistos: continue
            assuntos = extrair_assuntos(src.get("assuntos", []))
            area     = classificar_area(assuntos)
            if area in AREAS_EXCLUIR: continue
            situacao, data_p = analisar_pauta(src.get("movimentos", []))
            if situacao != "pautado": continue
            vistos.add(numero)
            pautados.append({
                "numero":     numero,
                "orgao":      orgao,
                "ministro":   ministro,
                "area":       area,
                "assuntos":   assuntos,
                "data_ref":   fmt_data(data_p),
                "data_sort":  data_p,
                "urgencia":   calcular_urgencia(data_p),
                "link":       stj_link(numero),
                "tipo":       "pautado",
            })
        time.sleep(0.3)
 
    # ── 2. Distribuídos recentes (mov.26, últimos 45d) ────────────────────────
    log("=== Distribuídos (mov.26, últimos 45d) ===")
    since45 = (date.today() - timedelta(days=45)).isoformat()
    for codigo in sorted(TODOS_CODIGOS):
        orgao, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query_por_movimento(codigo, MOV_DISTRIBUIDO, since45)
        if not dados: continue
        hits  = dados.get("hits", {}).get("hits", [])
        total = dados.get("hits", {}).get("total", {}).get("value", 0)
        log(f"  {orgao} — {ministro}: {total} distribuídos nos últimos 45d")
        for hit in hits:
            src    = hit.get("_source", {})
            numero = src.get("numeroProcesso", "")
            if numero in vistos: continue
            assuntos = extrair_assuntos(src.get("assuntos", []))
            area     = classificar_area(assuntos)
            if area in AREAS_EXCLUIR: continue
            data_aj = src.get("dataAjuizamento", "")[:10]
            vistos.add(numero)
            distribuidos.append({
                "numero":    numero,
                "orgao":     orgao,
                "ministro":  ministro,
                "area":      area,
                "assuntos":  assuntos,
                "data_ref":  fmt_data(data_aj),
                "data_sort": data_aj,
                "urgencia":  "—",
                "link":      stj_link(numero),
                "tipo":      "distribuido",
            })
        time.sleep(0.3)
 
    # ── 3. Conclusos (mov.51) — aguardando julgamento ─────────────────────────
    log("=== Conclusos (mov.51) ===")
    for codigo in sorted(TODOS_CODIGOS):
        orgao, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query_por_movimento(codigo, MOV_CONCLUSO)
        if not dados: continue
        hits  = dados.get("hits", {}).get("hits", [])
        total = dados.get("hits", {}).get("total", {}).get("value", 0)
        log(f"  {orgao} — {ministro}: {total} com mov.51")
        for hit in hits:
            src    = hit.get("_source", {})
            numero = src.get("numeroProcesso", "")
            if numero in vistos: continue
            assuntos = extrair_assuntos(src.get("assuntos", []))
            area     = classificar_area(assuntos)
            if area in AREAS_EXCLUIR: continue
            data_c = data_mais_recente_mov(src.get("movimentos", []), MOV_CONCLUSO)
            data_aj = src.get("dataAjuizamento", "")[:10]
            vistos.add(numero)
            conclusos.append({
                "numero":    numero,
                "orgao":     orgao,
                "ministro":  ministro,
                "area":      area,
                "assuntos":  assuntos,
                "data_ref":  fmt_data(data_c or data_aj),
                "data_sort": data_c or data_aj,
                "urgencia":  "—",
                "link":      stj_link(numero),
                "tipo":      "concluso",
            })
        time.sleep(0.3)
 
    pautados.sort(key=lambda x: (
        {"Alta":0,"Média":1,"Baixa":2}.get(x["urgencia"],3), x["data_sort"]))
    distribuidos.sort(key=lambda x: x["data_sort"], reverse=True)
    conclusos.sort(key=lambda x: x["data_sort"], reverse=True)
    return pautados, distribuidos, conclusos
 
# ── Geração de arquivos ───────────────────────────────────────────────────────
HTML = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor STJ - Marquez Advogados</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0f1117;--sur:#1a1d2e;--sur2:#22263a;--bdr:#2e3250;
  --acc:#6c7bff;--text:#e2e8f0;--mut:#8892b0;
  --alt:#f87171;--med:#fbbf24;--ok:#4ade80;--inf:#60a5fa;--warn:#fb923c
}
body{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;font-size:14px}
header{background:var(--sur);border-bottom:1px solid var(--bdr);padding:18px 28px;
  display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.lw{display:flex;align-items:center;gap:12px}
.lb{width:36px;height:36px;background:var(--acc);border-radius:9px;display:grid;place-items:center;font-size:18px}
.lw h1{font-size:16px;font-weight:700}
.lw p{font-size:11px;color:var(--mut)}
.upd{background:var(--sur2);border:1px solid var(--bdr);border-radius:8px;
  padding:5px 12px;font-size:11px;color:var(--mut);display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;padding:20px 28px}
.card{background:var(--sur);border:1px solid var(--bdr);border-radius:10px;padding:13px;position:relative;overflow:hidden}
.cl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px;margin-bottom:5px}
.cv{font-size:24px;font-weight:800;line-height:1}
.cb2{position:absolute;bottom:0;left:0;right:0;height:3px}
.ct .cv{color:var(--acc)} .ct .cb2{background:var(--acc)}
.ca .cv{color:var(--alt)}  .ca .cb2{background:var(--alt)}
.cm .cv{color:var(--med)}  .cm .cb2{background:var(--med)}
.cg .cv{color:var(--ok)}   .cg .cb2{background:var(--ok)}
.ci .cv{color:var(--inf)}  .ci .cb2{background:var(--inf)}
.cw .cv{color:var(--warn)} .cw .cb2{background:var(--warn)}
.tabs{display:flex;gap:3px;padding:0 28px;border-bottom:1px solid var(--bdr)}
.tab{padding:8px 14px;border-radius:8px 8px 0 0;cursor:pointer;font-size:13px;
  font-weight:500;color:var(--mut);border:1px solid transparent;border-bottom:none;background:transparent}
.tab.on{background:var(--sur);border-color:var(--bdr);border-bottom:1px solid var(--sur);
  color:var(--text);margin-bottom:-1px}
.tab:hover:not(.on){background:var(--sur2);color:var(--text)}
.bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:12px 28px;
  background:var(--sur);border-bottom:1px solid var(--bdr)}
.sw{position:relative;flex:1;min-width:160px;max-width:300px}
.sw input{width:100%;background:var(--sur2);border:1px solid var(--bdr);border-radius:7px;
  padding:7px 10px 7px 28px;color:var(--text);font-size:13px;outline:none}
.sw input:focus{border-color:var(--acc)}
.sw::before{content:"?";position:absolute;left:9px;top:50%;transform:translateY(-50%);font-size:11px;color:var(--mut)}
select{background:var(--sur2);border:1px solid var(--bdr);border-radius:7px;
  color:var(--text);padding:7px 10px;font-size:13px;cursor:pointer;outline:none}
.cnt{margin-left:auto;background:var(--sur2);border:1px solid var(--bdr);
  border-radius:6px;padding:4px 10px;font-size:11px;color:var(--mut);white-space:nowrap}
.notice{background:var(--sur2);border-left:3px solid var(--warn);margin:12px 28px;
  padding:8px 14px;border-radius:0 7px 7px 0;font-size:12px;color:var(--mut)}
.twrap{overflow-x:auto;padding:0 28px 40px}
table{width:100%;border-collapse:collapse;margin-top:12px}
th{text-align:left;padding:8px 10px;font-size:10px;font-weight:600;color:var(--mut);
  text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--bdr);
  white-space:nowrap;cursor:pointer;user-select:none}
th:hover{color:var(--text)}
th.sa::after{content:" a";color:var(--acc)} th.sd::after{content:" v";color:var(--acc)}
tr{border-bottom:1px solid var(--bdr)}
tbody tr:hover{background:var(--sur2)}
td{padding:10px 10px;vertical-align:top;font-size:13px}
.nl{color:var(--acc);text-decoration:none;font-weight:600;white-space:nowrap}
.nl:hover{color:#a78bfa;text-decoration:underline}
.bp{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;white-space:nowrap}
.uA{background:rgba(248,113,113,.15);color:#f87171;border:1px solid rgba(248,113,113,.3)}
.uM{background:rgba(251,191,36,.15);color:#fbbf24;border:1px solid rgba(251,191,36,.3)}
.uB{background:rgba(74,222,128,.15);color:#4ade80;border:1px solid rgba(74,222,128,.3)}
.uD{background:rgba(96,165,250,.1);color:#60a5fa;border:1px solid rgba(96,165,250,.2)}
.op{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;
  background:var(--sur2);border:1px solid var(--bdr);color:var(--mut)}
.mt{font-size:12px;color:var(--mut);max-width:240px}
.empty{text-align:center;padding:50px 20px;color:var(--mut)}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}
@media(max-width:680px){header,.cards,.tabs,.bar,.twrap{padding-left:12px;padding-right:12px}}
</style>
</head>
<body>
<header>
  <div class="lw">
    <div class="lb">&#9878;</div>
    <div><h1>Monitor STJ</h1><p>Marquez Advogados &middot; Prospec&ccedil;&atilde;o Ativa</p></div>
  </div>
  <div class="upd"><span class="dot"></span>Atualizado em <strong id="upd-txt" style="margin-left:4px"></strong></div>
</header>
<div class="cards" id="cards"></div>
<div class="tabs" id="tabs"></div>
<div class="bar">
  <div class="sw"><input id="q" type="text" placeholder="N&uacute;mero, ministro, assunto..." oninput="render()"></div>
  <select id="fo" onchange="render()">
    <option value="">Todos os &oacute;rg&atilde;os</option>
    <option>3&ordf; Turma</option><option>4&ordf; Turma</option><option>Corte Especial</option>
  </select>
  <select id="fa" onchange="render()"><option value="">Todas as &aacute;reas</option></select>
  <select id="fu" onchange="render()">
    <option value="">Todas urg&ecirc;ncias</option>
    <option value="Alta">Alta</option><option value="Media">M&eacute;dia</option><option value="Baixa">Baixa</option>
  </select>
  <span class="cnt" id="cnt">carregando...</span>
</div>
<div id="notice" class="notice" style="display:none"></div>
<div class="twrap"><table><thead id="th"></thead><tbody id="tb"></tbody></table>
<div class="empty" id="emp" style="display:none">Nenhum processo com esses filtros.</div></div>
 
<script>
var META = {atualizado:"__ATUALIZADO__"};
var tabAtual = "pautado", sCol = "data_sort", sDir = -1;
var DADOS = [];
 
var TABS = [
  {id:"pautado",    label:"Pautados"},
  {id:"distribuido",label:"Distribu&iacute;dos"},
  {id:"concluso",   label:"Conclusos"},
  {id:"todos",      label:"Todos"}
];
var COLS_P = ["numero","orgao","ministro","area","assuntos","data_ref","urgencia"];
var COLS_D = ["numero","orgao","ministro","area","assuntos","data_ref"];
var LABELS = {numero:"N\u00famero",orgao:"\u00d3rg\u00e3o",ministro:"Ministro/a",
  area:"\u00c1rea",assuntos:"Assuntos",data_ref:"Data Ref.",urgencia:"Urg\u00eancia"};
 
document.getElementById("upd-txt").textContent = META.atualizado;
 
function buildTabs() {
  var el = document.getElementById("tabs");
  TABS.forEach(function(t) {
    var d = document.createElement("div");
    d.className = "tab" + (t.id === tabAtual ? " on" : "");
    d.innerHTML = t.label + ' (<span class="tc-' + t.id + '">...</span>)';
    d.onclick = function() {
      tabAtual = t.id; sCol = "data_sort"; sDir = -1;
      document.querySelectorAll(".tab").forEach(function(x){x.classList.remove("on");});
      d.classList.add("on");
      render();
    };
    el.appendChild(d);
  });
}
 
function updateTabCounts() {
  ["pautado","distribuido","concluso","todos"].forEach(function(t) {
    var n = t === "todos" ? DADOS.length : DADOS.filter(function(p){return p.tipo===t;}).length;
    var els = document.querySelectorAll(".tc-" + t);
    els.forEach(function(e){e.textContent = n;});
  });
}
 
function buildCards() {
  var p = DADOS.filter(function(x){return x.tipo==="pautado";});
  var d = DADOS.filter(function(x){return x.tipo==="distribuido";});
  var c = DADOS.filter(function(x){return x.tipo==="concluso";});
  var by = function(t,v){return DADOS.filter(function(x){return x[t]===v;}).length;};
  var cards = [
    {cls:"ct",lbl:"Total",val:DADOS.length},
    {cls:"ca",lbl:"Alta Urg\u00eancia",val:p.filter(function(x){return x.urgencia==="Alta";}).length},
    {cls:"cm",lbl:"M\u00e9dia Urg\u00eancia",val:p.filter(function(x){return x.urgencia==="M\u00e9dia";}).length},
    {cls:"cg",lbl:"Baixa Urg\u00eancia",val:p.filter(function(x){return x.urgencia==="Baixa";}).length},
    {cls:"ci",lbl:"Distribu\u00eddos 45d",val:d.length},
    {cls:"cw",lbl:"Conclusos",val:c.length},
    {cls:"ct",lbl:"3\u00aa Turma",val:by("orgao","3\u00aa Turma")},
    {cls:"ct",lbl:"4\u00aa Turma",val:by("orgao","4\u00aa Turma")},
    {cls:"ct",lbl:"Corte Especial",val:by("orgao","Corte Especial")},
  ];
  document.getElementById("cards").innerHTML = cards.map(function(c){
    return '<div class="card '+c.cls+'"><div class="cl">'+c.lbl+'</div>'+
           '<div class="cv">'+c.val+'</div><div class="cb2"></div></div>';
  }).join("");
}
 
function buildAreaFilter() {
  var seen = {}, areas = [];
  DADOS.forEach(function(p){if(!seen[p.area]){seen[p.area]=true;areas.push(p.area);}});
  areas.sort();
  var sel = document.getElementById("fa");
  areas.forEach(function(a){
    var o = document.createElement("option"); o.value=a; o.text=a; sel.appendChild(o);
  });
}
 
function filtrado() {
  var q  = document.getElementById("q").value.toLowerCase();
  var fo = document.getElementById("fo").value;
  var fa = document.getElementById("fa").value;
  var fu = document.getElementById("fu").value;
  return DADOS.filter(function(p) {
    if (tabAtual !== "todos" && p.tipo !== tabAtual) return false;
    if (fo && p.orgao !== fo) return false;
    if (fa && p.area  !== fa) return false;
    if (fu) {
      var u = p.urgencia === "M\u00e9dia" ? "Media" : p.urgencia;
      if (u !== fu) return false;
    }
    if (q) {
      var hay = [p.numero,p.ministro,p.assuntos,p.area,p.orgao].join(" ").toLowerCase();
      if (hay.indexOf(q) < 0) return false;
    }
    return true;
  });
}
 
function ordenado(arr) {
  return arr.slice().sort(function(a,b){
    var va=a[sCol]||"", vb=b[sCol]||"";
    return sDir*(va>vb?1:va<vb?-1:0);
  });
}
 
function badge(u) {
  if (u==="Alta")  return '<span class="bp uA">Alta</span>';
  if (u==="M\u00e9dia") return '<span class="bp uM">M\u00e9dia</span>';
  if (u==="Baixa") return '<span class="bp uB">Baixa</span>';
  return '<span class="bp uD">-</span>';
}
 
function render() {
  var rows = ordenado(filtrado());
  var cols = (tabAtual==="pautado" || tabAtual==="todos") ? COLS_P : COLS_D;
  var thead = "<tr>";
  cols.forEach(function(k){
    var cl = sCol===k ? (sDir===-1?"sd":"sa") : "";
    thead += '<th class="'+cl+'" onclick="ss(\''+k+'\')">'+LABELS[k]+"</th>";
  });
  thead += "</tr>";
  document.getElementById("th").innerHTML = thead;
  var emp = document.getElementById("emp");
  if (!rows.length) {
    document.querySelector("table").style.display="none";
    emp.style.display="block";
    document.getElementById("cnt").textContent="0 processos";
    return;
  }
  document.querySelector("table").style.display="table";
  emp.style.display="none";
  document.getElementById("cnt").textContent=rows.length+" processo"+(rows.length!==1?"s":"");
  var useCols = (tabAtual==="pautado") ? COLS_P : (tabAtual==="todos" ? COLS_P : COLS_D);
  var html = "";
  rows.forEach(function(p){
    var c2 = (p.tipo==="distribuido"||p.tipo==="concluso") && tabAtual!=="pautado" && tabAtual!=="todos" ? COLS_D : COLS_P;
    html += "<tr>";
    c2.forEach(function(k){
      if (k==="numero")   html += '<td><a class="nl" href="'+p.link+'" target="_blank">'+p.numero+'</a></td>';
      else if (k==="orgao")    html += '<td><span class="op">'+p.orgao+'</span></td>';
      else if (k==="urgencia") html += '<td>'+badge(p.urgencia)+'</td>';
      else if (k==="assuntos") {
        var t=p.assuntos||""; var s=t.length>65?t.slice(0,65)+"...":t;
        html += '<td class="mt" title="'+t+'">'+(s||"-")+'</td>';
      }
      else html += '<td>'+(p[k]||"-")+'</td>';
    });
    html += "</tr>";
  });
  document.getElementById("tb").innerHTML = html;
}
 
function ss(col){sCol===col?sDir*=-1:(sCol=col,sDir=-1);render();}
 
// Carrega dados do arquivo JSON separado — sem injeção no HTML
fetch("data.json")
  .then(function(r){
    if(!r.ok) throw new Error("HTTP "+r.status);
    return r.json();
  })
  .then(function(data){
    DADOS = data;
    buildTabs();
    buildCards();
    buildAreaFilter();
    updateTabCounts();
    render();
  })
  .catch(function(err){
    document.getElementById("cnt").textContent = "Erro ao carregar dados: "+err.message;
    console.error(err);
  });
</script>
</body>
</html>'''
 
 
def main():
    pautados, distribuidos, conclusos = coletar()
    todos = pautados + distribuidos + conclusos
 
    log(f"Pautados: {len(pautados)} | Alta: {sum(1 for p in pautados if p['urgencia']=='Alta')} | "
        f"Media: {sum(1 for p in pautados if p['urgencia']=='Media')} | "
        f"Baixa: {sum(1 for p in pautados if p['urgencia']=='Baixa')}")
    log(f"Distribuidos: {len(distribuidos)} | Conclusos: {len(conclusos)} | Total: {len(todos)}")
 
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stj")
    os.makedirs(out_dir, exist_ok=True)
 
    # Grava data.json separado — 100% seguro, sem injeção no HTML
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False)
    log("data.json gravado")
 
    # BRT = UTC-3
    atualizado = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M") + " (BRT)"
    html = HTML.replace("__ATUALIZADO__", atualizado)
 
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    log("index.html gravado")
 
 
if __name__ == "__main__":
    main()
 
