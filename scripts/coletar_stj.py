#!/usr/bin/env python3
"""
Monitor STJ — Marquez Advogados
Consulta Datajud por código de gabinete, gera stj/index.html.
"""
 
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, date, timedelta
from collections import Counter
 
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
    """
    Retorna (situacao, data_inclusao).
    Mantém processo como 'pautado' se teve mov.417 e não houve
    cancelamento (12106), retirada (897) ou julgamento (193) posterior.
    Remove restrição de 60 dias na inclusão — o que importa é estar ativo.
    """
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
 
def query_gabinete_pautados(codigo):
    return post_api({
        "size": 200,
        "query": {
            "bool": {
                "must": [
                    {"term": {"orgaoJulgador.codigo": codigo}},
                    {"term": {"movimentos.codigo": MOV_PAUTADO}},
                ]
            }
        },
        "_source": ["numeroProcesso", "classe", "orgaoJulgador",
                    "assuntos", "movimentos", "dataAjuizamento"],
    })
 
def query_gabinete_distribuidos(codigo, since_iso):
    """Busca processos com distribuição recente usando dataAjuizamento como proxy."""
    return post_api({
        "size": 200,
        "query": {
            "bool": {
                "must": [
                    {"term": {"orgaoJulgador.codigo": codigo}},
                    {"term": {"movimentos.codigo": MOV_DISTRIBUIDO}},
                    {"range": {"dataAjuizamento": {"gte": since_iso}}},
                ]
            }
        },
        "_source": ["numeroProcesso", "classe", "orgaoJulgador",
                    "assuntos", "movimentos", "dataAjuizamento"],
        "sort": [{"dataAjuizamento": {"order": "desc"}}],
    })
 
# ── Coleta ────────────────────────────────────────────────────────────────────
def coletar():
    pautados    = []
    distribuidos = []
    vistos_p    = set()
    vistos_d    = set()
 
    # ── Pautados (mov.417, últimos 60 dias) ──────────────────────────────────
    log("=== Coletando pautados (mov. 417) ===")
    for codigo in sorted(TODOS_CODIGOS):
        orgao_str, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query_gabinete_pautados(codigo)
        if not dados:
            continue
        hits  = dados.get("hits", {}).get("hits", [])
        total = dados.get("hits", {}).get("total", {}).get("value", 0)
        log(f"  {orgao_str} — {ministro} (cód.{codigo}): {total} com mov.417, analisando {len(hits)}")
        for hit in hits:
            src    = hit.get("_source", {})
            numero = src.get("numeroProcesso", "")
            if numero in vistos_p:
                continue
            vistos_p.add(numero)
            assuntos   = extrair_assuntos(src.get("assuntos", []))
            area       = classificar_area(assuntos)
            if area in AREAS_EXCLUIR:
                continue
            situacao, data_pauta = analisar_pauta(src.get("movimentos", []))
            if situacao != "pautado":
                continue
            urgencia = calcular_urgencia(data_pauta)
            pautados.append({
                "numero":     numero,
                "orgao":      orgao_str,
                "ministro":   ministro,
                "area":       area,
                "assuntos":   assuntos,
                "data_pauta": fmt_data(data_pauta),
                "data_sort":  data_pauta,
                "urgencia":   urgencia,
                "link":       stj_link(numero),
                "tipo":       "pautado",
            })
        time.sleep(0.3)
 
    # ── Distribuídos (mov.26, dataAjuizamento últimos 45 dias) ───────────────
    log("=== Coletando distribuídos (mov. 26, últimos 45 dias) ===")
    since = (date.today() - timedelta(days=45)).isoformat()
    for codigo in sorted(TODOS_CODIGOS):
        orgao_str, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query_gabinete_distribuidos(codigo, since)
        if not dados:
            continue
        hits  = dados.get("hits", {}).get("hits", [])
        total = dados.get("hits", {}).get("total", {}).get("value", 0)
        log(f"  {orgao_str} — {ministro} (cód.{codigo}): {total} nos últimos 45d, analisando {len(hits)}")
        for hit in hits:
            src    = hit.get("_source", {})
            numero = src.get("numeroProcesso", "")
            if numero in vistos_d or numero in vistos_p:
                continue
            vistos_d.add(numero)
            assuntos = extrair_assuntos(src.get("assuntos", []))
            area     = classificar_area(assuntos)
            if area in AREAS_EXCLUIR:
                continue
            data_aj = src.get("dataAjuizamento", "")[:10]
            distribuidos.append({
                "numero":    numero,
                "orgao":     orgao_str,
                "ministro":  ministro,
                "area":      area,
                "assuntos":  assuntos,
                "data_dist": fmt_data(data_aj),
                "data_sort": data_aj,
                "urgencia":  "—",
                "link":      stj_link(numero),
                "tipo":      "distribuido",
            })
        time.sleep(0.3)
 
    pautados.sort(key=lambda x: (
        {"Alta": 0, "Média": 1, "Baixa": 2}.get(x["urgencia"], 3),
        x["data_sort"]
    ))
    distribuidos.sort(key=lambda x: x["data_sort"], reverse=True)
    return pautados, distribuidos
 
# ── HTML ──────────────────────────────────────────────────────────────────────
# IMPORTANTE: usamos string normal (não f-string) para evitar conflito
# com as chaves {} do CSS e JavaScript. Substituição via .replace().
 
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor STJ · Marquez Advogados</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0f1117;--sur:#1a1d2e;--sur2:#22263a;--bdr:#2e3250;
  --acc:#6c7bff;--text:#e2e8f0;--mut:#8892b0;
  --alt:#f87171;--med:#fbbf24;--ok:#4ade80;--inf:#60a5fa;
  --font:'Inter',system-ui,sans-serif
}
body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:14px}
header{
  background:var(--sur);border-bottom:1px solid var(--bdr);
  padding:18px 32px;display:flex;align-items:center;
  justify-content:space-between;gap:12px;flex-wrap:wrap
}
.logo-wrap{display:flex;align-items:center;gap:12px}
.logo-box{width:36px;height:36px;background:var(--acc);border-radius:9px;
  display:grid;place-items:center;font-size:17px}
.logo-wrap h1{font-size:16px;font-weight:700}
.logo-wrap p{font-size:11px;color:var(--mut);margin-top:1px}
.badge-up{
  background:var(--sur2);border:1px solid var(--bdr);border-radius:8px;
  padding:5px 12px;font-size:11px;color:var(--mut);display:flex;
  align-items:center;gap:6px
}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);
  animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.cards{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));
  gap:12px;padding:22px 32px
}
.card{
  background:var(--sur);border:1px solid var(--bdr);border-radius:12px;
  padding:14px;position:relative;overflow:hidden
}
.c-lbl{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.7px;margin-bottom:6px}
.c-val{font-size:26px;font-weight:800;line-height:1}
.c-bar{position:absolute;bottom:0;left:0;right:0;height:3px;border-radius:0 0 12px 12px}
.ca .c-val{color:var(--acc)} .ca .c-bar{background:var(--acc)}
.cd .c-val{color:var(--alt)} .cd .c-bar{background:var(--alt)}
.cm .c-val{color:var(--med)} .cm .c-bar{background:var(--med)}
.cb .c-val{color:var(--ok)}  .cb .c-bar{background:var(--ok)}
.ci .c-val{color:var(--inf)} .ci .c-bar{background:var(--inf)}
.tabs{
  display:flex;gap:4px;padding:0 32px;
  border-bottom:1px solid var(--bdr);margin-top:4px
}
.tab{
  padding:8px 16px;border-radius:8px 8px 0 0;cursor:pointer;
  font-size:13px;font-weight:500;color:var(--mut);
  border:1px solid transparent;border-bottom:none;background:transparent
}
.tab.on{
  background:var(--sur);border-color:var(--bdr);
  border-bottom:1px solid var(--sur);color:var(--text);margin-bottom:-1px
}
.tab:hover:not(.on){background:var(--sur2);color:var(--text)}
.bar{
  display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  padding:14px 32px;background:var(--sur);border-bottom:1px solid var(--bdr)
}
.sw{position:relative;flex:1;min-width:180px;max-width:320px}
.sw input{
  width:100%;background:var(--sur2);border:1px solid var(--bdr);
  border-radius:8px;padding:7px 10px 7px 30px;color:var(--text);
  font-size:13px;outline:none
}
.sw input:focus{border-color:var(--acc)}
.sw::before{content:"🔍";position:absolute;left:9px;top:50%;transform:translateY(-50%);font-size:11px}
select{
  background:var(--sur2);border:1px solid var(--bdr);border-radius:8px;
  color:var(--text);padding:7px 10px;font-size:13px;cursor:pointer;outline:none
}
.cnt{
  margin-left:auto;background:var(--sur2);border:1px solid var(--bdr);
  border-radius:6px;padding:4px 10px;font-size:11px;color:var(--mut);white-space:nowrap
}
.twrap{overflow-x:auto;padding:0 32px 40px}
table{width:100%;border-collapse:collapse;margin-top:14px}
thead th{
  text-align:left;padding:9px 10px;font-size:10px;font-weight:600;
  color:var(--mut);text-transform:uppercase;letter-spacing:.6px;
  border-bottom:1px solid var(--bdr);white-space:nowrap;cursor:pointer
}
thead th:hover{color:var(--text)}
.sa::after{content:" ▲";color:var(--acc)} .sd::after{content:" ▼";color:var(--acc)}
tbody tr{border-bottom:1px solid var(--bdr);transition:background .1s}
tbody tr:hover{background:var(--sur2)}
tbody td{padding:11px 10px;vertical-align:top}
.num{color:var(--acc);text-decoration:none;font-weight:600;font-size:13px;white-space:nowrap}
.num:hover{color:#a78bfa;text-decoration:underline}
.bp{
  display:inline-block;padding:2px 8px;border-radius:20px;
  font-size:11px;font-weight:600;white-space:nowrap
}
.u-Alta{background:rgba(248,113,113,.15);color:#f87171;border:1px solid rgba(248,113,113,.3)}
.u-Media{background:rgba(251,191,36,.15);color:#fbbf24;border:1px solid rgba(251,191,36,.3)}
.u-Baixa{background:rgba(74,222,128,.15);color:#4ade80;border:1px solid rgba(74,222,128,.3)}
.u-dist{background:rgba(96,165,250,.1);color:#60a5fa;border:1px solid rgba(96,165,250,.2)}
.orgpill{
  display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;
  background:var(--sur2);border:1px solid var(--bdr);color:var(--mut)
}
.muted{font-size:12px;color:var(--mut);max-width:260px}
.empty{text-align:center;padding:60px 20px;color:var(--mut)}
.empty .ico{font-size:36px;margin-bottom:10px}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}
@media(max-width:700px){
  header,.cards,.tabs,.bar,.twrap{padding-left:14px;padding-right:14px}
}
</style>
</head>
<body>
 
<header>
  <div class="logo-wrap">
    <div class="logo-box">&#x2696;&#xFE0F;</div>
    <div>
      <h1>Monitor STJ</h1>
      <p>Marquez Advogados &middot; Prospec&ccedil;&atilde;o Ativa</p>
    </div>
  </div>
  <div class="badge-up">
    <span class="dot"></span>
    Atualizado em <strong style="margin-left:4px">__ATUALIZADO__</strong>
  </div>
</header>
 
<div class="cards">
  <div class="card ca"><div class="c-lbl">Total</div><div class="c-val">__TOTAL__</div><div class="c-bar"></div></div>
  <div class="card cd"><div class="c-lbl">Alta urg&ecirc;ncia</div><div class="c-val">__ALTA__</div><div class="c-bar"></div></div>
  <div class="card cm"><div class="c-lbl">M&eacute;dia urg&ecirc;ncia</div><div class="c-val">__MEDIA__</div><div class="c-bar"></div></div>
  <div class="card cb"><div class="c-lbl">Baixa urg&ecirc;ncia</div><div class="c-val">__BAIXA__</div><div class="c-bar"></div></div>
  <div class="card ci"><div class="c-lbl">Distribu&iacute;dos 45d</div><div class="c-val">__NDIST__</div><div class="c-bar"></div></div>
  <div class="card ca"><div class="c-lbl">3&ordf; Turma</div><div class="c-val">__N3T__</div><div class="c-bar"></div></div>
  <div class="card ca"><div class="c-lbl">4&ordf; Turma</div><div class="c-val">__N4T__</div><div class="c-bar"></div></div>
  <div class="card ca"><div class="c-lbl">Corte Especial</div><div class="c-val">__NCE__</div><div class="c-bar"></div></div>
</div>
 
<div class="tabs">
  <div class="tab on"  onclick="mudarTab('pautado',this)">&#x1F4CB; Pautados (__NPAUT__)</div>
  <div class="tab"     onclick="mudarTab('distribuido',this)">&#x1F4E8; Distribu&iacute;dos (__NDIST__)</div>
  <div class="tab"     onclick="mudarTab('todos',this)">&#x1F4C2; Todos (__TOTAL__)</div>
</div>
 
<div class="bar">
  <div class="sw"><input id="q" type="text" placeholder="N&uacute;mero, ministro, assunto&hellip;" oninput="render()"></div>
  <select id="fo" onchange="render()">
    <option value="">Todos os &oacute;rg&atilde;os</option>
    <option>3&ordf; Turma</option><option>4&ordf; Turma</option><option>Corte Especial</option>
  </select>
  <select id="fa" onchange="render()"><option value="">Todas as &aacute;reas</option></select>
  <select id="fu" onchange="render()">
    <option value="">Todas urg&ecirc;ncias</option>
    <option value="Alta">Alta</option>
    <option value="Media">M&eacute;dia</option>
    <option value="Baixa">Baixa</option>
  </select>
  <span class="cnt" id="cnt">carregando&hellip;</span>
</div>
 
<div class="twrap">
  <table><thead id="th"></thead><tbody id="tb"></tbody></table>
  <div class="empty" id="emp" style="display:none">
    <div class="ico">&#x1F50D;</div><p>Nenhum processo com esses filtros.</p>
  </div>
</div>
 
<!-- Dados injetados em tag separada para evitar conflito com </script> no texto jurídico -->
<script type="application/json" id="dados-stj">__DADOS_JSON__</script>
 
<script>
var DADOS = JSON.parse(document.getElementById("dados-stj").textContent);
 
var tabAtual = "pautado";
var sCol = "data_sort";
var sDir = -1;
 
var COLS_PAUT = [
  {k:"numero",l:"N\u00famero"},
  {k:"orgao",l:"\u00d3rg\u00e3o"},
  {k:"ministro",l:"Ministro/a"},
  {k:"area",l:"\u00c1rea"},
  {k:"assuntos",l:"Assuntos"},
  {k:"data_pauta",l:"Data Pauta"},
  {k:"urgencia",l:"Urg\u00eancia"}
];
var COLS_DIST = [
  {k:"numero",l:"N\u00famero"},
  {k:"orgao",l:"\u00d3rg\u00e3o"},
  {k:"ministro",l:"Ministro/a"},
  {k:"area",l:"\u00c1rea"},
  {k:"assuntos",l:"Assuntos"},
  {k:"data_dist",l:"Distribu\u00eddo em"}
];
 
function mudarTab(t, el) {
  tabAtual = t;
  var tabs = document.querySelectorAll(".tab");
  for (var i=0; i<tabs.length; i++) tabs[i].classList.remove("on");
  el.classList.add("on");
  sCol = "data_sort"; sDir = -1;
  render();
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
      var urg = p.urgencia === "M\u00e9dia" ? "Media" : p.urgencia;
      if (urg !== fu) return false;
    }
    if (q) {
      var h = [p.numero, p.ministro, p.assuntos, p.area, p.orgao].join(" ").toLowerCase();
      if (h.indexOf(q) === -1) return false;
    }
    return true;
  });
}
 
function ordenado(arr) {
  return arr.slice().sort(function(a, b) {
    var va = a[sCol] || "", vb = b[sCol] || "";
    return sDir * (va > vb ? 1 : va < vb ? -1 : 0);
  });
}
 
function setSort(col) {
  if (sCol === col) { sDir *= -1; } else { sCol = col; sDir = -1; }
  render();
}
 
function badge(u) {
  if (u === "Alta")  return '<span class="bp u-Alta">&#x1F534; Alta</span>';
  if (u === "M\u00e9dia") return '<span class="bp u-Media">&#x1F7E1; M\u00e9dia</span>';
  if (u === "Baixa") return '<span class="bp u-Baixa">&#x1F7E2; Baixa</span>';
  return '<span class="bp u-dist">&#x1F4E8; Dist.</span>';
}
 
function render() {
  var rows = ordenado(filtrado());
  var cols = (tabAtual === "distribuido") ? COLS_DIST : COLS_PAUT;
 
  var thHTML = "<tr>";
  for (var i=0; i<cols.length; i++) {
    var c = cols[i];
    var cl = (sCol === c.k) ? (sDir === -1 ? "sd" : "sa") : "";
    thHTML += '<th class="' + cl + '" onclick="setSort(\'' + c.k + '\')">' + c.l + '</th>';
  }
  thHTML += "</tr>";
  document.getElementById("th").innerHTML = thHTML;
 
  var emp = document.getElementById("emp");
  if (!rows.length) {
    document.querySelector("table").style.display = "none";
    emp.style.display = "block";
    document.getElementById("cnt").textContent = "0 processos";
    return;
  }
  document.querySelector("table").style.display = "table";
  emp.style.display = "none";
  document.getElementById("cnt").textContent = rows.length + " processo" + (rows.length !== 1 ? "s" : "");
 
  var tbHTML = "";
  for (var r=0; r<rows.length; r++) {
    var p = rows[r];
    var useCols = (p.tipo === "distribuido" && tabAtual !== "pautado") ? COLS_DIST : COLS_PAUT;
    tbHTML += "<tr>";
    for (var j=0; j<useCols.length; j++) {
      var ck = useCols[j].k;
      if (ck === "numero") {
        tbHTML += '<td><a class="num" href="' + p.link + '" target="_blank">' + p.numero + '</a></td>';
      } else if (ck === "orgao") {
        tbHTML += '<td><span class="orgpill">' + p.orgao + '</span></td>';
      } else if (ck === "urgencia") {
        tbHTML += '<td>' + badge(p.urgencia) + '</td>';
      } else if (ck === "assuntos") {
        var txt = (p.assuntos || "");
        var short = txt.length > 70 ? txt.slice(0, 70) + "\u2026" : txt;
        tbHTML += '<td class="muted" title="' + txt + '">' + (short || "\u2014") + '</td>';
      } else {
        tbHTML += '<td>' + (p[ck] || "\u2014") + '</td>';
      }
    }
    tbHTML += "</tr>";
  }
  document.getElementById("tb").innerHTML = tbHTML;
}
 
function initAreas() {
  var areas = [];
  var seen = {};
  for (var i=0; i<DADOS.length; i++) {
    var a = DADOS[i].area;
    if (!seen[a]) { seen[a] = true; areas.push(a); }
  }
  areas.sort();
  var sel = document.getElementById("fa");
  for (var i=0; i<areas.length; i++) {
    var o = document.createElement("option");
    o.value = areas[i]; o.text = areas[i];
    sel.appendChild(o);
  }
}
 
initAreas();
render();
</script>
</body>
</html>"""
 
 
def gerar_html(pautados, distribuidos, atualizado):
    todos   = pautados + distribuidos
    total   = len(todos)
    n_alta  = sum(1 for p in pautados if p["urgencia"] == "Alta")
    n_media = sum(1 for p in pautados if p["urgencia"] == "Média")
    n_baixa = sum(1 for p in pautados if p["urgencia"] == "Baixa")
    n_dist  = len(distribuidos)
    n_3t    = sum(1 for p in todos if p["orgao"] == "3ª Turma")
    n_4t    = sum(1 for p in todos if p["orgao"] == "4ª Turma")
    n_ce    = sum(1 for p in todos if p["orgao"] == "Corte Especial")
    n_paut  = len(pautados)
 
    # ensure_ascii=True converte todos os caracteres especiais para \uXXXX
    # replace('</', '<\/') evita que </script> quebre o HTML parser do navegador
    dados_json = json.dumps(todos, ensure_ascii=True).replace("</", "<\\/")
 
 
    html = HTML_TEMPLATE
    html = html.replace("__ATUALIZADO__", atualizado)
    html = html.replace("__TOTAL__",  str(total))
    html = html.replace("__ALTA__",   str(n_alta))
    html = html.replace("__MEDIA__",  str(n_media))
    html = html.replace("__BAIXA__",  str(n_baixa))
    html = html.replace("__NDIST__",  str(n_dist))
    html = html.replace("__N3T__",    str(n_3t))
    html = html.replace("__N4T__",    str(n_4t))
    html = html.replace("__NCE__",    str(n_ce))
    html = html.replace("__NPAUT__",  str(n_paut))
    html = html.replace("__DADOS_JSON__", dados_json)
    return html
 
 
# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pautados, distribuidos = coletar()
 
    log(f"Pautados: {len(pautados)} | "
        f"Alta: {sum(1 for p in pautados if p['urgencia']=='Alta')} | "
        f"Média: {sum(1 for p in pautados if p['urgencia']=='Média')} | "
        f"Baixa: {sum(1 for p in pautados if p['urgencia']=='Baixa')}")
    log(f"Distribuídos (45d): {len(distribuidos)}")
 
    # GitHub Actions roda em UTC — converte para BRT (UTC-3)
    atualizado = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M") + " (BRT)"
    html = gerar_html(pautados, distribuidos, atualizado)
 
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stj")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"HTML gerado com sucesso → {out}")
 
 
if __name__ == "__main__":
    main()
 
