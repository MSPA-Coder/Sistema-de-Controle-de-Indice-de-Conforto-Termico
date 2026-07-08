// =============================================================================
// Sistema de Controle dos Índices de Conforto Térmico — front-end
// =============================================================================

const CONFIG_APP = window.CONFIG_APP;

const CLASSE_STATUS = {
  "Conforto": "conforto",
  "Alerta": "alerta",
  "Perigo": "perigo",
  "Emergência": "emergencia",
};

const COR_STATUS = {
  "Conforto": "#3E8E5B",
  "Alerta": "#E3A73E",
  "Perigo": "#C1443C",
  "Emergência": "#FF6B5E",
};

// Quantos ícones exibir por equipamento LIGADO, conforme a intensidade
// informada pelo servidor (Conforto=desligado não entra aqui).
const CONTAGEM_INTENSIDADE = { baixa: 1, média: 2, máxima: 3 };

// Glifos simples (SVG, herdam a cor via currentColor) usados no bloco de
// equipamentos — desenhados à mão para não depender de nenhum ícone externo.
const ICONE_VENTILADOR =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
  '<circle cx="12" cy="12" r="2.1"/>' +
  '<path d="M12.6 10.3c-.2-3.1 1.2-6.5 4.1-7.4 2-.6 3.9.9 3.4 3-.7 3-3.9 4.9-7 4.9-.3 0-.5-.2-.5-.5z"/>' +
  '<path d="M13.7 12.6c3.1-.2 6.5 1.2 7.4 4.1.6 2-.9 3.9-3 3.4-3-.7-4.9-3.9-4.9-7 0-.3.2-.5.5-.5z"/>' +
  '<path d="M10.3 11.4c-3.1.2-6.5-1.2-7.4-4.1-.6-2 .9-3.9 3-3.4 3 .7 4.9 3.9 4.9 7 0 .3-.2.5-.5.5z"/>' +
  "</svg>";

const ICONE_NEBULIZADOR =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
  '<path d="M12 2.2c-3.3 4.8-6.2 8.9-6.2 12.2 0 3.6 2.9 6.6 6.2 6.6s6.2-3 6.2-6.6c0-3.3-2.9-7.4-6.2-12.2z"/>' +
  "</svg>";

const estado = { especie: "frangos", indice: "ITU" };

let graficoIndice = null;
let graficoEntradas = null;
let assinaturaGraficos = "";
let autoAtivo = false; // Modo automático ligado/desligado (checado antes de CADA ciclo)
let autoEmExecucao = false; // true enquanto um ciclo está em andamento (evita sobreposição)
let autoTimeoutId = null; // id do próximo ciclo agendado (setTimeout), se houver
let audioCtx = null;

// ---------------------------------------------------------------------------
// Seletores de espécie / índice
// ---------------------------------------------------------------------------
function renderSeletorEspecie() {
  const container = document.getElementById("seletor-especie");
  container.innerHTML = "";
  Object.keys(CONFIG_APP.indicesPorEspecie).forEach((especie) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rocker-botao" + (especie === estado.especie ? " ativo" : "");
    btn.textContent = CONFIG_APP.nomeEspecie[especie].split(" (")[0];
    btn.title = CONFIG_APP.nomeEspecie[especie];
    btn.addEventListener("click", () => selecionarEspecie(especie));
    container.appendChild(btn);
  });
}

function renderSeletorIndice() {
  const container = document.getElementById("seletor-indice");
  container.innerHTML = "";
  const indices = CONFIG_APP.indicesPorEspecie[estado.especie];
  if (!indices.includes(estado.indice)) {
    estado.indice = indices[0];
  }
  indices.forEach((indice) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rocker-botao" + (indice === estado.indice ? " ativo" : "");
    btn.textContent = indice;
    btn.title = CONFIG_APP.nomeIndice[indice];
    btn.addEventListener("click", () => selecionarIndice(indice));
    container.appendChild(btn);
  });
}

function selecionarEspecie(especie) {
  estado.especie = especie;
  renderSeletorEspecie();
  renderSeletorIndice();
  renderCamposEntrada();
  resetarPainelResultado();
  carregarHistorico();
}

function selecionarIndice(indice) {
  estado.indice = indice;
  renderSeletorIndice();
  renderCamposEntrada();
  resetarPainelResultado();
  carregarHistorico();
}

// ---------------------------------------------------------------------------
// Campos de entrada dinâmicos
// ---------------------------------------------------------------------------
function renderCamposEntrada() {
  const container = document.getElementById("campos-entrada");
  container.innerHTML = "";
  const campos = CONFIG_APP.camposPorIndice[estado.indice];
  campos.forEach((campo) => {
    const meta = CONFIG_APP.campoMetadados[campo];
    const wrap = document.createElement("div");
    wrap.className = "campo-entrada";

    const label = document.createElement("label");
    label.setAttribute("for", "campo-" + campo);
    label.textContent = meta.label + " (" + meta.unidade + ")";

    const input = document.createElement("input");
    input.type = "number";
    input.id = "campo-" + campo;
    input.step = meta.passo;
    input.min = meta.min;
    input.max = meta.max;
    input.placeholder = "Ex.: " + (((meta.min + meta.max) / 2).toFixed(1));

    wrap.appendChild(label);
    wrap.appendChild(input);
    container.appendChild(wrap);
  });
}

function coletarEntradas() {
  const campos = CONFIG_APP.camposPorIndice[estado.indice];
  const entradas = {};
  campos.forEach((campo) => {
    const input = document.getElementById("campo-" + campo);
    entradas[campo] = input ? input.value : "";
  });
  return entradas;
}

function preencherEntradas(dados) {
  Object.entries(dados).forEach(([campo, valor]) => {
    const input = document.getElementById("campo-" + campo);
    if (input) input.value = valor;
  });
}

function coletarConfig() {
  return {
    coletarDados: document.getElementById("cfg-coletar").checked,
    habilitarSons: document.getElementById("cfg-sons").checked,
    enviarEmails: document.getElementById("cfg-emails").checked,
    habilitarEquipamentos: document.getElementById("cfg-equipamentos").checked,
    emailDestino: document.getElementById("email-destino").value,
  };
}

// ---------------------------------------------------------------------------
// Chamadas à API
// ---------------------------------------------------------------------------
async function calcular() {
  esconderErro();
  const entradas = coletarEntradas();
  const config = coletarConfig();

  let dados;
  try {
    const resposta = await fetch("/api/calcular", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ especie: estado.especie, indice: estado.indice, entradas, config }),
    });
    let corpo;
    try {
      corpo = await resposta.json();
    } catch (erroJson) {
      throw new Error(
        "O servidor respondeu com status " + resposta.status +
        ", mas não em formato JSON. Veja o terminal onde o Flask está rodando para o erro completo."
      );
    }
    if (!resposta.ok) {
      mostrarErro(corpo.erro || "Não foi possível calcular. Confira os dados informados.");
      return;
    }
    dados = corpo;
  } catch (erro) {
    // Esta captura é exclusivamente para falhas de REDE (fetch não completou,
    // ou a resposta não era JSON válido) — nunca para erros ocorridos depois,
    // ao atualizar a tela.
    console.error("Erro de comunicação com /api/calcular:", erro);
    mostrarErro(
      erro && erro.message && erro.message.includes("Flask")
        ? erro.message
        : "Falha de comunicação com o servidor. Verifique se o Flask está em execução (python app.py) e se a página foi aberta em http://127.0.0.1:5000."
    );
    return;
  }

  // A requisição foi concluída com sucesso. Qualquer erro a partir daqui é de
  // ATUALIZAÇÃO DA TELA (ex.: gráficos), não de comunicação — tratado à parte
  // dentro de atualizarResultado(), para nunca ser confundido com o caso acima.
  atualizarResultado(dados);
}

async function simularSensor() {
  try {
    const resposta = await fetch(
      "/api/sensor?especie=" + encodeURIComponent(estado.especie) +
      "&indice=" + encodeURIComponent(estado.indice)
    );
    const dados = await resposta.json();
    if (resposta.ok) preencherEntradas(dados);
  } catch (erro) {
    mostrarErro("Não foi possível simular a leitura do sensor.");
  }
}

async function carregarHistorico() {
  try {
    const query = "?especie=" + encodeURIComponent(estado.especie) + "&indice=" + encodeURIComponent(estado.indice);
    const [resposta, respostaGrafico] = await Promise.all([
      fetch("/api/historico" + query),
      fetch("/api/historico-grafico" + query),
    ]);
    const historico = await resposta.json();
    const historicoGrafico = respostaGrafico.ok ? await respostaGrafico.json() : historico;
    atualizarGraficos(historicoGrafico);
    atualizarTabela(historico);
  } catch (erro) {
    /* não crítico */
  }
}

async function limparHistorico() {
  try {
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ especie: estado.especie, indice: estado.indice }),
    });
  } catch (erro) {
    /* ignora */
  }
  resetarPainelResultado();
  atualizarGraficos([]);
  atualizarTabela([]);
}

// ---------------------------------------------------------------------------
// Atualização da interface
// ---------------------------------------------------------------------------
function resetarPainelResultado() {
  const readoutValor = document.getElementById("readout-valor");
  readoutValor.textContent = "--,--";
  readoutValor.className = "readout-valor";
  document.getElementById("readout-indice").textContent = estado.indice;

  const faixa = document.getElementById("faixa-status");
  faixa.className = "faixa-status faixa-status--vazio";
  document.getElementById("faixa-status-texto").textContent = "AGUARDANDO CÁLCULO";

  document.getElementById("mensagem-orientacao").innerHTML =
    "Preencha os dados e clique em <strong>Calcular</strong> para ver o status do lote.";

  atualizarEquipamento(null);
  atualizarEmail(null);
  esconderErro();
}

function atualizarResultado(dados) {
  const classe = CLASSE_STATUS[dados.status] || "";

  // 1) Elementos essenciais primeiro — nunca dependem de bibliotecas externas,
  //    então sempre devem atualizar mesmo se algo mais adiante falhar.
  const readoutValor = document.getElementById("readout-valor");
  readoutValor.textContent = dados.valor.toFixed(2).replace(".", ",");
  readoutValor.className = "readout-valor cor-" + classe;
  document.getElementById("readout-indice").textContent = estado.indice;

  const faixa = document.getElementById("faixa-status");
  faixa.className = "faixa-status faixa-" + classe;
  document.getElementById("faixa-status-texto").textContent = dados.status.toUpperCase();

  document.getElementById("mensagem-orientacao").innerHTML =
    "<strong>" + dados.status + ":</strong> " + dados.mensagem +
    (dados.aviso ? "<br><em>" + dados.aviso + "</em>" : "");

  atualizarEquipamento(dados.equipamento);
  atualizarEmail(dados.email);

  // 2) Gráficos e tabela: isolados em try/catch próprios. Se a biblioteca de
  //    gráficos não carregar por qualquer motivo, o restante do painel acima
  //    já está atualizado e continua funcionando normalmente.
  try {
    atualizarGraficos(dados.historico_grafico || dados.historico);
  } catch (erro) {
    console.error("Erro ao desenhar os gráficos:", erro);
    mostrarErro(
      "O valor foi calculado normalmente (" + dados.valor.toFixed(2).replace(".", ",") +
      ", " + dados.status + "), mas os gráficos não puderam ser desenhados. " +
      "Detalhes no console do navegador (F12 → Console)."
    );
  }

  try {
    atualizarTabela(dados.historico);
  } catch (erro) {
    console.error("Erro ao atualizar a tabela de histórico:", erro);
  }

  if (dados.tocarSom) {
    try {
      tocarSom(dados.status);
    } catch (erro) {
      console.error("Erro ao tocar som de alerta:", erro);
    }
  }
}

function renderizarIconesEquipamento(containerId, svgIcone, nomeEquipamento, ligado, intensidade) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  // Desligado (ou o outro equipamento é que está ligado): mostra 1 ícone
  // apagado, só para manter o rótulo com uma âncora visual. Ligado: mostra
  // 1/2/3 ícones acesos, conforme a intensidade — nunca os dois ao mesmo
  // tempo, então se só um equipamento vier ligado no estado, os ícones
  // múltiplos/acesos aparecem apenas naquele.
  const quantidade = ligado ? CONTAGEM_INTENSIDADE[intensidade] || 1 : 1;

  for (let i = 0; i < quantidade; i++) {
    const badge = document.createElement("span");
    badge.className = "icone-equip" + (ligado ? " ativo" : "");
    badge.innerHTML = svgIcone;
    container.appendChild(badge);
  }

  const estadoTexto = ligado ? `ligado (intensidade ${intensidade || "baixa"})` : "desligado";
  container.setAttribute("aria-label", `${nomeEquipamento} ${estadoTexto}`);
}

function atualizarEquipamento(equip) {
  const ventiladorLigado = !!(equip && equip.ventilador);
  const nebulizadorLigado = !!(equip && equip.nebulizador);
  const intensidade = (equip && equip.intensidade) || null;

  renderizarIconesEquipamento("icones-ventilador", ICONE_VENTILADOR, "Ventilador", ventiladorLigado, intensidade);
  renderizarIconesEquipamento("icones-nebulizador", ICONE_NEBULIZADOR, "Nebulizador", nebulizadorLigado, intensidade);

  document.getElementById("intensidade-valor").textContent = intensidade || "desligado";
}

function atualizarEmail(emailInfo) {
  const secao = document.getElementById("secao-email");
  if (!emailInfo) {
    secao.classList.add("oculto");
    return;
  }
  secao.classList.remove("oculto");
  const status = emailInfo.enviado_de_verdade
    ? "E-mail enviado de verdade para " + emailInfo.destino + " (SMTP configurado)."
    : "Modo simulado — nenhum servidor SMTP configurado (variável SMTP_HOST ausente). Pré-visualização do aviso que seria enviado a " +
      emailInfo.destino + ":";
  document.getElementById("email-status").textContent = status;
  document.getElementById("email-conteudo").textContent = emailInfo.conteudo;
}

function formatarHora(isoString) {
  const data = new Date(isoString);
  return data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function opcoesGrafico(comEixoSecundario) {
  const opcoes = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { labels: { color: "#F2ECE1", font: { family: "IBM Plex Mono", size: 11 } } },
    },
    scales: {
      x: { ticks: { color: "#A79C8C", font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.05)" } },
      y: {
        beginAtZero: true,
        ticks: { color: "#A79C8C", font: { size: 10 } },
        grid: { color: "rgba(255,255,255,0.05)" },
      },
    },
  };
  if (comEixoSecundario) {
    opcoes.scales.y1 = {
      position: "right",
      beginAtZero: true,
      ticks: { color: "#A79C8C", font: { size: 10 } },
      grid: { display: false },
    };
  }
  return opcoes;
}

function assinaturaDoHistorico(historico) {
  const campos = CONFIG_APP.camposPorIndice[estado.indice] || [];
  return [
    estado.especie,
    estado.indice,
    campos.join(","),
    historico.map((h) => [
      h.criado_em,
      h.valor,
      h.status,
      campos.map((campo) => h.entradas[campo]).join(","),
    ].join(":")).join("|"),
  ].join(";");
}

function criarOuAtualizarGrafico(grafico, canvasId, configuracao) {
  if (!grafico) {
    return new Chart(document.getElementById(canvasId).getContext("2d"), configuracao);
  }

  grafico.data.labels = configuracao.data.labels;
  grafico.data.datasets = configuracao.data.datasets;
  grafico.options = configuracao.options;
  grafico.update("none");
  return grafico;
}

function atualizarGraficos(historico) {
  if (typeof Chart === "undefined") {
    throw new Error(
      "A biblioteca Chart.js não foi carregada (static/js/vendor/chart.umd.js). " +
      "Confira se a pasta 'static/js/vendor' foi copiada junto com o projeto."
    );
  }

  const novaAssinatura = assinaturaDoHistorico(historico);
  if (novaAssinatura === assinaturaGraficos && graficoIndice && graficoEntradas) {
    return;
  }
  assinaturaGraficos = novaAssinatura;

  const rotulos = historico.map((h) => formatarHora(h.criado_em));
  const valores = historico.map((h) => h.valor);
  const cores = historico.map((h) => COR_STATUS[h.status] || "#4F8A93");
  const datasetIndice = graficoIndice ? graficoIndice.data.datasets[0] : {};
  Object.assign(datasetIndice, {
    label: estado.indice,
    data: valores,
    backgroundColor: cores,
    borderRadius: 3,
    maxBarThickness: 26,
  });

  graficoIndice = criarOuAtualizarGrafico(graficoIndice, "grafico-indice", {
    type: "bar",
    data: {
      labels: rotulos,
      datasets: [datasetIndice],
    },
    options: opcoesGrafico(false),
  });

  const campos = CONFIG_APP.camposPorIndice[estado.indice];
  const paleta = ["#4F8A93", "#D9A441", "#8FBF9F"];
  const temVelocidade = campos.includes("v");
  const datasetsAtuaisEntradas = new Map(
    graficoEntradas ? graficoEntradas.data.datasets.map((dataset) => [dataset.campo, dataset]) : []
  );
  const datasetsEntradas = campos.map((campo, i) => {
    const cor = paleta[i % paleta.length];
    const dataset = datasetsAtuaisEntradas.get(campo) || {};
    Object.assign(dataset, {
      campo,
      label: CONFIG_APP.campoMetadados[campo].label,
      data: historico.map((h) => h.entradas[campo]),
      borderColor: cor,
      backgroundColor: cor + "33",
      tension: 0.35,
      cubicInterpolationMode: "monotone",
      pointRadius: 2,
      pointHoverRadius: 4,
      fill: campo !== "v",
      yAxisID: campo === "v" ? "y1" : "y",
    });
    return dataset;
  });

  graficoEntradas = criarOuAtualizarGrafico(graficoEntradas, "grafico-entradas", {
    type: "line",
    data: { labels: rotulos, datasets: datasetsEntradas },
    options: opcoesGrafico(temVelocidade),
  });
}

function atualizarTabela(historico) {
  const tbody = document.querySelector("#tabela-historico tbody");
  const tabela = document.getElementById("tabela-historico");
  const vazio = document.getElementById("tabela-vazia");
  tbody.innerHTML = "";

  if (!historico.length) {
    tabela.classList.add("oculto");
    vazio.classList.remove("oculto");
    return;
  }
  tabela.classList.remove("oculto");
  vazio.classList.add("oculto");

  [...historico].reverse().forEach((h) => {
    const tr = document.createElement("tr");
    const entradasTexto = Object.entries(h.entradas)
      .map(([k, v]) => k + "=" + v)
      .join(", ");
    const classe = "status-" + (CLASSE_STATUS[h.status] || "");

    const tdHora = document.createElement("td");
    tdHora.textContent = formatarHora(h.criado_em);
    const tdEntradas = document.createElement("td");
    tdEntradas.textContent = entradasTexto;
    const tdValor = document.createElement("td");
    tdValor.textContent = h.valor.toFixed(2).replace(".", ",");
    const tdStatus = document.createElement("td");
    tdStatus.textContent = h.status;
    tdStatus.className = classe;

    tr.append(tdHora, tdEntradas, tdValor, tdStatus);
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------------
// Som de alerta (Web Audio API - nenhum arquivo de áudio necessário)
// ---------------------------------------------------------------------------
function tocarSom(status) {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const sequencias = {
      Conforto: [660],
      Alerta: [520, 520],
      Perigo: [420, 420, 420],
      "Emergência": [300, 300, 300, 300],
    };
    const seq = sequencias[status] || [440];
    let tempo = audioCtx.currentTime;
    seq.forEach((freq) => {
      const osc = audioCtx.createOscillator();
      const ganho = audioCtx.createGain();
      osc.type = "square";
      osc.frequency.value = freq;
      ganho.gain.setValueAtTime(0.0001, tempo);
      ganho.gain.exponentialRampToValueAtTime(0.12, tempo + 0.02);
      ganho.gain.exponentialRampToValueAtTime(0.0001, tempo + 0.16);
      osc.connect(ganho).connect(audioCtx.destination);
      osc.start(tempo);
      osc.stop(tempo + 0.18);
      tempo += 0.22;
    });
  } catch (erro) {
    /* Web Audio indisponível neste navegador - ignora silenciosamente */
  }
}

// ---------------------------------------------------------------------------
// Relógio e modo automático
// ---------------------------------------------------------------------------
function iniciarRelogio() {
  const el = document.getElementById("relogio");
  const atualizar = () => {
    el.textContent = new Date().toLocaleTimeString("pt-BR");
  };
  atualizar();
  setInterval(atualizar, 1000);
}

function alternarModoAutomatico(ativo) {
  autoAtivo = ativo;

  // Cancela qualquer próximo ciclo já agendado. Se um ciclo já estiver EM
  // EXECUÇÃO neste exato momento (aguardando resposta do servidor), ele vai
  // terminar sozinho — mas por causa da checagem de `autoAtivo` dentro de
  // `cicloAutomatico()`, ele não vai agendar um próximo. Ou seja, desmarcar
  // sempre para o monitoramento em, no máximo, a duração de UM ciclo (nunca
  // fica "gerando dados" indefinidamente).
  if (autoTimeoutId) {
    clearTimeout(autoTimeoutId);
    autoTimeoutId = null;
  }

  if (ativo && !autoEmExecucao) {
    cicloAutomatico();
  }
}

async function cicloAutomatico() {
  if (!autoAtivo) return;
  autoEmExecucao = true;
  try {
    await simularSensor();
    await calcular();
  } catch (erro) {
    console.error("Erro no ciclo do modo automático:", erro);
  } finally {
    autoEmExecucao = false;
  }
  // Só agenda o PRÓXIMO ciclo depois que este terminou por completo — nunca
  // dispara um novo ciclo antes do anterior ter concluído (o que era a causa
  // do modo automático "não desligar": ciclos podiam se sobrepor e continuar
  // rodando mesmo depois de desmarcar a caixa).
  if (autoAtivo) {
    autoTimeoutId = setTimeout(cicloAutomatico, 1000);
  }
}

// ---------------------------------------------------------------------------
// Erros
// ---------------------------------------------------------------------------
function mostrarErro(msg) {
  const el = document.getElementById("mensagem-erro");
  el.textContent = msg;
  el.classList.remove("oculto");
}

function esconderErro() {
  document.getElementById("mensagem-erro").classList.add("oculto");
}

// ---------------------------------------------------------------------------
// Inicialização
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  renderSeletorEspecie();
  renderSeletorIndice();
  renderCamposEntrada();
  iniciarRelogio();
  carregarHistorico();

  document.getElementById("btn-calcular").addEventListener("click", calcular);
  document.getElementById("btn-simular").addEventListener("click", simularSensor);
  document.getElementById("btn-limpar").addEventListener("click", limparHistorico);

  document.getElementById("cfg-coletar").addEventListener("change", (e) => {
    document.getElementById("btn-simular").disabled = !e.target.checked;
  });
  document.getElementById("cfg-emails").addEventListener("change", (e) => {
    document.getElementById("wrap-email-destino").classList.toggle("oculto", !e.target.checked);
  });
  document.getElementById("cfg-auto").addEventListener("change", (e) => {
    if (e.target.checked) document.getElementById("cfg-coletar").checked = true;
    alternarModoAutomatico(e.target.checked);
  });
});
