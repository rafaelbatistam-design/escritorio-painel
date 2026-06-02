#!/usr/bin/env python3
"""
Monitor STJ — Marquez Advogados
3ª e 4ª Turmas + 2ª Seção. Conclusos e Distribuídos.
Gera stj/data.js e stj/index.html.
"""
 
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, date, timedelta
 
API_KEY = os.environ.get("DATAJUD_API_KEY", "")
API_URL = "https://api-publica.datajud.cnj.jus.br/api_publica_stj/_search"
 
# ── Apenas 3ª e 4ª Turmas ────────────────────────────────────────────────────
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
    76776: "Maria Isabel Gallotti",   # código corrigido
}
 
CODIGO_PARA_ORGAO = {}
for cod, nome in TERCEIRA_TURMA.items():
    CODIGO_PARA_ORGAO[cod] = ("3ª Turma", nome)
for cod, nome in QUARTA_TURMA.items():
    if cod not in CODIGO_PARA_ORGAO:
        CODIGO_PARA_ORGAO[cod] = ("4ª Turma", nome)
 
TODOS_CODIGOS = set(TERCEIRA_TURMA) | set(QUARTA_TURMA)
 
MOV_DISTRIBUIDO = 26
MOV_CONCLUSO    = 51
 
# Classes processuais criminais — excluir
CLASSES_CRIMINAIS = {
    "HC","RHC","CC","APn","Inq","QCr","HC-MC","Pet",
    "RMS","MS","MI",   # MS e MI em turmas cíveis às vezes aparecem de matérias outras
}
# Classes que definitivamente queremos
CLASSES_CIVEIS = {
    "REsp","AREsp","AgInt","AgRg","EREsp","EAREsp",
    "AgInt no AREsp","AgInt no REsp","Ag","EAg",
}
 
# Áreas — classificação automática, SEM exclusão (mostra tudo)
AREAS = {
    "Empresarial / Societário": [
        "societári","sócio","dissolução parcial","apuração de haveres","holding",
        "recuperação judicial","falência","fusão","cisão","incorporação de empresa",
        "concorrência desleal","marca","patente","título de crédito","cheque",
        "duplicata","nota promissória","protesto","letra de câmbio",
    ],
    "Contratos": [
        "contrato","inadimplemento","rescisão contratual","resolução contratual",
        "fornecimento","empreitada","prestação de serviços","cláusula penal",
        "revisão contratual","onerosidade excessiva","vício redibitório",
        "promessa de compra e venda","fiança","seguro","leasing","factoring",
        "cessão de crédito","novação","transação","take or pay",
    ],
    "Imobiliário": [
        "incorporação imobiliária","locação","aluguel","compra e venda de imóvel",
        "loteamento","condomínio","reintegração de posse","usucapião",
        "financiamento imobiliário","alienação fiduciária de imóvel",
        "registro de imóveis","despejo","corretagem imobiliária",
        "multipropriedade","posse","esbulho","turbação","built to suit",
    ],
    "Civil / Responsabilidade": [
        "responsabilidade civil","dano moral","dano material","dano estético",
        "indenização","responsabilidade médica","erro médico","hospital",
        "acidente de trânsito","nexo causal","perda de uma chance",
        "código de defesa do consumidor","consumidor","negativação indevida",
        "fraude bancária","phishing","clonagem de cartão","produto defeituoso",
    ],
    "Família e Sucessões": [
        "inventário","herança","sucessão","testamento","união estável",
        "divórcio","alimentos","guarda","holding familiar","regime de bens",
        "meação","partilha","herdeiro","filiação","bem de família","doação",
        "adoção","paternidade","colação",
    ],
    "Arbitragem / ADR": [
        "arbitragem","sentença arbitral","cláusula compromissória",
        "dispute board","mediação","anulação de sentença arbitral",
        "câmara arbitral","árbitro",
    ],
    "Bancário / Financeiro": [
        "contrato bancário","mútuo bancário","financiamento","empréstimo",
        "juros","capitalização de juros","anatocismo","cartão de crédito",
        "busca e apreensão","alienação fiduciária","sigilo bancário",
        "cédula de crédito","conta bancária","spread bancário",
    ],
    "Tributário / Fiscal": [
        "tributo","imposto","taxa","contribuição","fisco","execução fiscal",
        "icms","iss","ipi","ir ","csll","pis","cofins","simples nacional",
        "lançamento fiscal","crédito tributário",
    ],
    "Trabalhista / Previdenciário": [
        "trabalhista","vínculo empregatício","horas extras","fgts","inss",
        "benefício previdenciário","aposentadoria","pensão por morte",
        "auxílio-doença","regime próprio",
    ],
    "Processo Civil": [
        "coisa julgada","litispendência","competência","legitimidade",
        "prescrição","decadência","tutela antecipada","execução",
        "cumprimento de sentença","penhora","ação rescisória",
        "honorários advocatícios","litigância de má-fé","embargos",
    ],
    "Propriedade Intelectual": [
        "propriedade intelectual","direito autoral","software","patente de invenção",
        "marca registrada","indicação geográfica","cultivar",
    ],
    "Ambiental / Regulatório": [
        "ambiental","licença ambiental","dano ambiental","agência reguladora",
        "anatel","aneel","ans","anvisa","antaq","concession",
    ],
}
 
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)
 
def classificar_area(texto):
    t = (texto or "").lower()
    for area, kws in AREAS.items():
        if any(k in t for k in kws):
            return area
    return "Outros"
 
def extrair_assuntos(assuntos):
    if not assuntos: return ""
    nomes = []
    for a in assuntos[:5]:
        if isinstance(a, dict): nomes.append(a.get("nome",""))
        elif isinstance(a, str): nomes.append(a)
    return "; ".join(n for n in nomes if n)
 
def extrair_classe(src):
    classe = src.get("classe",{})
    if isinstance(classe, dict):
        return classe.get("nome","") or ""
    return ""
 
def is_criminal(nome_classe):
    if not nome_classe: return False
    partes = nome_classe.split()
    sigla = partes[0] if partes else ""
    return sigla in CLASSES_CRIMINAIS
 
def data_mais_recente_mov(movimentos, codigo_mov):
    datas = [m.get("dataHora","")[:10] for m in (movimentos or []) if m.get("codigo") == codigo_mov]
    return max(datas) if datas else ""
 
def fmt_data(d):
    if not d: return ""
    try: return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except: return d
 
def stj_link(numero):
    return ("https://processo.stj.jus.br/processo/pesquisa/"
            "?aplicacao=processos.ea&tipoPesquisa=tipoPesquisaNumeroUnico"
            f"&termo={urllib.parse.quote(numero)}")
 
def post_api(body):
    if not API_KEY:
        log("ERRO: DATAJUD_API_KEY não definida.")
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
 
def query(codigo_gabinete, codigo_mov, since_iso=None):
    must = [
        {"term": {"orgaoJulgador.codigo": codigo_gabinete}},
        {"term": {"movimentos.codigo": codigo_mov}},
    ]
    if since_iso:
        must.append({"range": {"dataAjuizamento": {"gte": since_iso}}})
    return post_api({
        "size": 200,
        "query": {"bool": {"must": must}},
        "_source": ["numeroProcesso","classe","orgaoJulgador",
                    "assuntos","movimentos","dataAjuizamento"],
        "sort": [{"dataAjuizamento": {"order": "desc"}}],
    })
 
def processar_hit(hit, orgao, ministro, tipo, data_ref_fn):
    src    = hit.get("_source",{})
    numero = src.get("numeroProcesso","")
    classe = extrair_classe(src)
    if is_criminal(classe):
        return None
    assuntos = extrair_assuntos(src.get("assuntos",[]))
    area     = classificar_area(assuntos)
    data_r   = data_ref_fn(src)
    return {
        "numero":    numero,
        "classe":    classe,
        "orgao":     orgao,
        "ministro":  ministro,
        "area":      area,
        "assuntos":  assuntos,
        "data_ref":  fmt_data(data_r),
        "data_sort": data_r,
        "link":      stj_link(numero),
        "tipo":      tipo,
    }
 
def coletar():
    distribuidos, conclusos = [], []
    vistos = set()
 
    # ── Distribuídos (mov.26, últimos 60d) ───────────────────────────────────
    log("=== Distribuídos (mov.26, últimos 60d) ===")
    since60 = (date.today() - timedelta(days=60)).isoformat()
    for codigo in sorted(TODOS_CODIGOS):
        orgao, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query(codigo, MOV_DISTRIBUIDO, since60)
        if not dados: continue
        hits  = dados.get("hits",{}).get("hits",[])
        total = dados.get("hits",{}).get("total",{}).get("value",0)
        log(f"  {orgao} — {ministro}: {total} distribuídos")
        for hit in hits:
            src    = hit.get("_source",{})
            numero = src.get("numeroProcesso","")
            if numero in vistos: continue
            data_ref_fn = lambda s: s.get("dataAjuizamento","")[:10]
            p = processar_hit(hit, orgao, ministro, "distribuido", data_ref_fn)
            if p:
                vistos.add(numero)
                distribuidos.append(p)
        time.sleep(0.3)
 
    # ── Conclusos (mov.51) ────────────────────────────────────────────────────
    log("=== Conclusos (mov.51) ===")
    for codigo in sorted(TODOS_CODIGOS):
        orgao, ministro = CODIGO_PARA_ORGAO.get(codigo, ("Outro", str(codigo)))
        dados = query(codigo, MOV_CONCLUSO)
        if not dados: continue
        hits  = dados.get("hits",{}).get("hits",[])
        total = dados.get("hits",{}).get("total",{}).get("value",0)
        log(f"  {orgao} — {ministro}: {total} conclusos")
        for hit in hits:
            src    = hit.get("_source",{})
            numero = src.get("numeroProcesso","")
            if numero in vistos: continue
            movimentos = src.get("movimentos",[])
            def data_ref_fn(s, movs=movimentos):
                dc = data_mais_recente_mov(movs, MOV_CONCLUSO)
                return dc or s.get("dataAjuizamento","")[:10]
            p = processar_hit(hit, orgao, ministro, "concluso", data_ref_fn)
            if p:
                vistos.add(numero)
                conclusos.append(p)
        time.sleep(0.3)
 
    distribuidos.sort(key=lambda x: x["data_sort"], reverse=True)
    conclusos.sort(key=lambda x: x["data_sort"], reverse=True)
    return distribuidos, conclusos
 
# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Monitor STJ - Marquez Advogados</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0f1117;--sur:#1a1d2e;--sur2:#22263a;--bdr:#2e3250;--acc:#6c7bff;
  --text:#e2e8f0;--mut:#8892b0;--alt:#f87171;--ok:#4ade80;--inf:#60a5fa;--warn:#fb923c}
body{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;font-size:14px}
header{background:var(--sur);border-bottom:1px solid var(--bdr);padding:16px 28px;
  display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.lw{display:flex;align-items:center;gap:12px}
.lb{width:34px;height:34px;background:var(--acc);border-radius:8px;display:grid;place-items:center;font-size:17px}
.lw h1{font-size:15px;font-weight:700}.lw p{font-size:11px;color:var(--mut)}
.upd{background:var(--sur2);border:1px solid var(--bdr);border-radius:7px;
  padding:5px 11px;font-size:11px;color:var(--mut);display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:9px;padding:18px 28px}
.card{background:var(--sur);border:1px solid var(--bdr);border-radius:9px;padding:12px;position:relative;overflow:hidden}
.cl2{font-size:9px;color:var(--mut);text-transform:uppercase;letter-spacing:.6px;margin-bottom:5px}
.cv{font-size:22px;font-weight:800;line-height:1}
.cb{position:absolute;bottom:0;left:0;right:0;height:3px}
.ct .cv{color:var(--acc)}.ct .cb{background:var(--acc)}
.ci .cv{color:var(--inf)}.ci .cb{background:var(--inf)}
.cw .cv{color:var(--warn)}.cw .cb{background:var(--warn)}
.tabs{display:flex;gap:3px;padding:0 28px;border-bottom:1px solid var(--bdr)}
.tab{padding:8px 14px;border-radius:8px 8px 0 0;cursor:pointer;font-size:13px;font-weight:500;
  color:var(--mut);border:1px solid transparent;border-bottom:none;background:transparent}
.tab.on{background:var(--sur);border-color:var(--bdr);border-bottom:1px solid var(--sur);color:var(--text);margin-bottom:-1px}
.tab:hover:not(.on){background:var(--sur2);color:var(--text)}
.bar{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:11px 28px;
  background:var(--sur);border-bottom:1px solid var(--bdr)}
.sw{position:relative;flex:1;min-width:150px;max-width:260px}
.sw input{width:100%;background:var(--sur2);border:1px solid var(--bdr);border-radius:7px;
  padding:6px 10px 6px 26px;color:var(--text);font-size:13px;outline:none}
.sw input:focus{border-color:var(--acc)}
.sw::before{content:"";position:absolute;left:9px;top:50%;transform:translateY(-50%);
  width:10px;height:10px;border:1.5px solid var(--mut);border-radius:50%}
select{background:var(--sur2);border:1px solid var(--bdr);border-radius:7px;
  color:var(--text);padding:6px 10px;font-size:13px;cursor:pointer;outline:none;max-width:200px}
.cnt{margin-left:auto;background:var(--sur2);border:1px solid var(--bdr);
  border-radius:6px;padding:3px 10px;font-size:11px;color:var(--mut);white-space:nowrap}
.twrap{overflow-x:auto;padding:0 28px 40px}
table{width:100%;border-collapse:collapse;margin-top:12px}
th{text-align:left;padding:8px 10px;font-size:10px;font-weight:600;color:var(--mut);
  text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--bdr);
  white-space:nowrap;cursor:pointer;user-select:none}
th:hover{color:var(--text)}
th.sa::after{content:" \25b2";color:var(--acc)}th.sd::after{content:" \25bc";color:var(--acc)}
tr{border-bottom:1px solid var(--bdr)}tbody tr:hover{background:var(--sur2)}
td{padding:9px 10px;vertical-align:top;font-size:13px}
.nl{color:var(--acc);text-decoration:none;font-weight:600;font-size:12px;
  font-family:monospace;letter-spacing:.3px;white-space:nowrap}
.nl:hover{color:#a78bfa;text-decoration:underline}
.cls-pill{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;
  font-weight:600;background:rgba(108,123,255,.15);color:var(--acc);
  border:1px solid rgba(108,123,255,.3);white-space:nowrap}
.op{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;
  background:var(--sur2);border:1px solid var(--bdr);color:var(--mut)}
.mt{font-size:11px;color:var(--mut);max-width:220px;line-height:1.4}
.area-txt{font-size:12px;color:var(--inf)}
.empty{text-align:center;padding:50px;color:var(--mut);font-size:13px}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}
</style>
</head>
<body>
<header>
  <div class="lw">
    <div class="lb">&#9878;</div>
    <div><h1>Monitor STJ</h1><p>Marquez Advogados &middot; 3&ordf; e 4&ordf; Turmas &middot; Prospec&ccedil;&atilde;o Ativa</p></div>
  </div>
  <div class="upd"><span class="dot"></span>Atualizado em&nbsp;<strong id="upd-txt"></strong></div>
</header>
 
<div class="cards" id="cards-el"></div>
<div class="tabs"  id="tabs-el"></div>
 
<div class="bar">
  <div class="sw"><input id="q" type="text" placeholder="N&uacute;mero, ministro, assunto..." oninput="render()"></div>
  <select id="fo" onchange="render()">
    <option value="">Todos os &oacute;rg&atilde;os</option>
    <option>3&ordf; Turma</option>
    <option>4&ordf; Turma</option>
  </select>
  <select id="fm" onchange="render()"><option value="">Todos os ministros</option></select>
  <select id="fa" onchange="render()"><option value="">Todas as &aacute;reas</option></select>
  <span class="cnt" id="cnt">carregando...</span>
</div>
 
<div class="twrap">
  <table><thead id="th"></thead><tbody id="tb"></tbody></table>
  <div class="empty" id="emp" style="display:none">Nenhum processo com esses filtros.</div>
</div>
 
<!-- data.js carregado com cache-busting via timestamp embutido no nome -->
<script src="data.js?v=__VERSION__"></script>
<script>
(function(){
  if (!window.STJ_DADOS) {
    document.getElementById("cnt").textContent = "Erro: data.js nao carregou.";
    return;
  }
 
  var D = window.STJ_DADOS;
  var M = window.STJ_META;
  var tabAtual = "distribuido", sCol = "data_sort", sDir = -1;
 
  document.getElementById("upd-txt").textContent = M.atualizado;
 
  // ── Tabs ──
  var TABS = [
    {id:"distribuido", lbl:"Distribu\u00eddos"},
    {id:"concluso",    lbl:"Conclusos"},
    {id:"todos",       lbl:"Todos"},
  ];
  var tabsEl = document.getElementById("tabs-el");
  TABS.forEach(function(t){
    var d = document.createElement("div");
    d.className = "tab" + (t.id===tabAtual?" on":"");
    var n = t.id==="todos" ? D.length : D.filter(function(p){return p.tipo===t.id;}).length;
    d.textContent = t.lbl + " (" + n + ")";
    d.onclick = function(){
      tabAtual=t.id; sCol="data_sort"; sDir=-1;
      document.querySelectorAll(".tab").forEach(function(x){x.classList.remove("on");});
      d.classList.add("on"); render();
    };
    tabsEl.appendChild(d);
  });
 
  // ── Cards ──
  var di = D.filter(function(x){return x.tipo==="distribuido";});
  var co = D.filter(function(x){return x.tipo==="concluso";});
  var by = function(k,v){return D.filter(function(x){return x[k]===v;}).length;};
  var cardsData = [
    {c:"ct",l:"Total",v:D.length},
    {c:"ci",l:"Distribu\u00eddos 60d",v:di.length},
    {c:"cw",l:"Conclusos",v:co.length},
    {c:"ct",l:"3\u00aa Turma",v:by("orgao","3\u00aa Turma")},
    {c:"ct",l:"4\u00aa Turma",v:by("orgao","4\u00aa Turma")},
  ];
  document.getElementById("cards-el").innerHTML = cardsData.map(function(c){
    return '<div class="card '+c.c+'"><div class="cl2">'+c.l+'</div>'+
           '<div class="cv">'+c.v+'</div><div class="cb"></div></div>';
  }).join("");
 
  // ── Filtros de Ministro e Área ──
  function populateSelect(id, values) {
    var sel = document.getElementById(id);
    values.sort().forEach(function(v){
      var o=document.createElement("option"); o.value=v; o.text=v; sel.appendChild(o);
    });
  }
  var seenM={}, seenA={}, ministros=[], areas=[];
  D.forEach(function(p){
    if(!seenM[p.ministro]){seenM[p.ministro]=true; ministros.push(p.ministro);}
    if(!seenA[p.area]){seenA[p.area]=true; areas.push(p.area);}
  });
  populateSelect("fm", ministros);
  populateSelect("fa", areas);
 
  // ── Colunas ──
  var COLS = ["classe","numero","orgao","ministro","area","assuntos","data_ref"];
  var LBL  = {
    classe:"Classe", numero:"N\u00famero CNJ", orgao:"\u00d3rg\u00e3o",
    ministro:"Ministro/a", area:"\u00c1rea", assuntos:"Assuntos", data_ref:"Data"
  };
 
  function filtrado(){
    var q  = document.getElementById("q").value.toLowerCase();
    var fo = document.getElementById("fo").value;
    var fm = document.getElementById("fm").value;
    var fa = document.getElementById("fa").value;
    return D.filter(function(p){
      if (tabAtual!=="todos" && p.tipo!==tabAtual) return false;
      if (fo && p.orgao!==fo)       return false;
      if (fm && p.ministro!==fm)    return false;
      if (fa && p.area!==fa)        return false;
      if (q){
        var h=[p.numero,p.ministro,p.assuntos,p.area,p.classe].join(" ").toLowerCase();
        if(h.indexOf(q)<0) return false;
      }
      return true;
    });
  }
 
  function render(){
    var rows = filtrado().sort(function(a,b){
      var va=a[sCol]||"", vb=b[sCol]||"";
      return sDir*(va>vb?1:va<vb?-1:0);
    });
    // thead
    var th="<tr>";
    COLS.forEach(function(k){
      var cl=sCol===k?(sDir===-1?"sd":"sa"):"";
      th+='<th class="'+cl+'" onclick="ss(\''+k+'\')">'+LBL[k]+"</th>";
    });
    document.getElementById("th").innerHTML=th+"</tr>";
    // estado vazio
    var emp=document.getElementById("emp");
    if(!rows.length){
      document.querySelector("table").style.display="none";
      emp.style.display="block";
      document.getElementById("cnt").textContent="0 processos";
      return;
    }
    document.querySelector("table").style.display="table";
    emp.style.display="none";
    document.getElementById("cnt").textContent=rows.length+" processo"+(rows.length!==1?"s":"");
    // tbody
    var html="";
    rows.forEach(function(p){
      html+="<tr>";
      COLS.forEach(function(k){
        switch(k){
          case "classe":
            html+='<td><span class="cls-pill">'+(p.classe||"?")+'</span></td>'; break;
          case "numero":
            html+='<td><a class="nl" href="'+p.link+'" target="_blank">'+p.numero+'</a></td>'; break;
          case "orgao":
            html+='<td><span class="op">'+p.orgao+'</span></td>'; break;
          case "area":
            html+='<td class="area-txt">'+p.area+'</td>'; break;
          case "assuntos":
            var t=p.assuntos||""; var s=t.length>65?t.slice(0,65)+"...":t;
            html+='<td class="mt" title="'+t.replace(/"/g,"&quot;")+'">'+s+'</td>'; break;
          default:
            html+='<td>'+(p[k]||"-")+'</td>';
        }
      });
      html+="</tr>";
    });
    document.getElementById("tb").innerHTML=html;
  }
 
  window.ss = function(col){sCol===col?sDir*=-1:(sCol=col,sDir=-1); render();};
  window.render = render;
  render();
})();
</script>
</body>
</html>"""
 
 
def main():
    distribuidos, conclusos = coletar()
    todos = distribuidos + conclusos
 
    log(f"Distribuídos: {len(distribuidos)} | Conclusos: {len(conclusos)} | Total: {len(todos)}")
 
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stj")
    os.makedirs(out_dir, exist_ok=True)
 
    # BRT = UTC-3
    atualizado = (datetime.utcnow() - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M") + " (BRT)"
    version    = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y%m%d%H%M")
 
    # data.js — define window.STJ_META e window.STJ_DADOS
    dados_js = (
        "window.STJ_META=" + json.dumps({"atualizado": atualizado}, ensure_ascii=False) + ";\n"
        "window.STJ_DADOS=" + json.dumps(todos, ensure_ascii=False) + ";\n"
    )
    with open(os.path.join(out_dir, "data.js"), "w", encoding="utf-8") as f:
        f.write(dados_js)
    log(f"data.js gravado ({len(todos)} processos, {len(dados_js)//1024}KB)")
 
    # index.html — injeta só o version para cache-busting, sem dados
    html = HTML.replace("__VERSION__", version)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    log("index.html gravado")
 
 
if __name__ == "__main__":
    main()
 
