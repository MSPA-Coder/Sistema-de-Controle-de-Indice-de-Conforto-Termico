// =============================================================================
// Front-end do sistema de conforto termico
// =============================================================================

const CONFIG_APP = window.CONFIG_APP;

const CLASSE_STATUS = {
  "Conforto": "conforto",
  "Alerta": "alerta",
  "Perigo": "perigo",
  "Emergencia": "emergencia",
};

const COR_STATUS = {
  "Conforto": "#3E8E5B",
  "Alerta": "#E3A73E",
  "Perigo": "#C1443C",
  "Emergencia": "#FF6B5E",
};

const STATUS_HISTORICO = ["Conforto", "Alerta", "Perigo", "Emerg\u00eancia"];
const CORES_CAMPOS_ENTRADA = ["#4F8A93", "#D9A441", "#8FBF9F", "#C1443C", "#9E7BB5", "#6FA8DC"];
const HISTORICO_LINHAS_POR_PAGINA = 20;

function normalizarChaveTexto(valor) {
  return String(valor || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function classeStatus(status) {
  return CLASSE_STATUS[normalizarChaveTexto(status)] || "";
}

function corStatus(status, fallback = "#4F8A93") {
  return COR_STATUS[normalizarChaveTexto(status)] || fallback;
}

function corCampoEntrada(campo) {
  const indice = camposDaEspecie().indexOf(campo);
  return CORES_CAMPOS_ENTRADA[Math.max(0, indice) % CORES_CAMPOS_ENTRADA.length];
}

// Quantos icones acender por equipamento ligado, conforme a intensidade
// informada pelo servidor. Cada nivel ocupa duas posicoes no conjunto fixo.
const TOTAL_ICONES_EQUIPAMENTO = 6;
const CONTAGEM_INTENSIDADE = { baixa: 2, media: 4, maxima: 6 };

function quantidadePorIntensidade(intensidade) {
  const chave = normalizarChaveTexto(intensidade).toLowerCase();
  return CONTAGEM_INTENSIDADE[chave] || 2;
}

function rotuloIntensidade(intensidade) {
  const rotulos = { baixa: "baixa", media: "m\u00e9dia", maxima: "m\u00e1xima" };
  return rotulos[intensidade] || intensidade;
}

// Glifos SVG proprios, inspirados em equipamentos agropecuarios reais: exaustor
// axial em moldura/grade e bico nebulizador em linha pressurizada.
const ICONE_VENTILADOR =
  '<svg class="equip-svg fan-svg" viewBox="0 0 32 32" aria-hidden="true">' +
  '<rect class="fan-frame" x="3.5" y="3.5" width="25" height="25" rx="2.3"/>' +
  '<circle class="fan-ring" cx="16" cy="16" r="10.4"/>' +
  '<circle class="fan-ring fan-ring--inner" cx="16" cy="16" r="6.8"/>' +
  '<path class="fan-grill" d="M16 5.7v20.6M5.7 16h20.6M8.7 8.7l14.6 14.6M23.3 8.7L8.7 23.3"/>' +
  '<g class="fan-rotor">' +
  '<path d="M16.8 14.9c1.3-4 4.4-6.2 6.7-5.2 1.7.8 1.6 3.2-.1 4.8-1.5 1.4-3.9 2.1-6.6.4z"/>' +
  '<path d="M17.1 16.8c4 1.3 6.2 4.4 5.2 6.7-.8 1.7-3.2 1.6-4.8-.1-1.4-1.5-2.1-3.9-.4-6.6z"/>' +
  '<path d="M15.2 17.1c-1.3 4-4.4 6.2-6.7 5.2-1.7-.8-1.6-3.2.1-4.8 1.5-1.4 3.9-2.1 6.6-.4z"/>' +
  '<path d="M14.9 15.2c-4-1.3-6.2-4.4-5.2-6.7.8-1.7 3.2-1.6 4.8.1 1.4 1.5 2.1 3.9.4 6.6z"/>' +
  "</g>" +
  '<circle class="fan-hub" cx="16" cy="16" r="2.2"/>' +
  "</svg>";

const ICONE_NEBULIZADOR =
  '<svg class="equip-svg mist-svg" viewBox="0 0 32 32" aria-hidden="true">' +
  '<path class="mist-pipe" d="M4.5 7.2h15.2"/>' +
  '<rect class="mist-body" x="18.2" y="5.2" width="6.1" height="4.1" rx="0.8"/>' +
  '<path class="mist-nozzle" d="M20.2 9.1h4.5l-1.2 3.5h-2.1z"/>' +
  '<path class="mist-jet mist-jet--top" d="M21.8 13.1C18.7 14.7 15.1 16.4 10 18.5"/>' +
  '<path class="mist-jet mist-jet--mid" d="M22.5 13.1C19.5 16.1 16.1 19.2 11.8 23.2"/>' +
  '<path class="mist-jet mist-jet--low" d="M23.2 13.1c-.1 3.9-.5 7.4-1.3 11.6"/>' +
  '<circle class="mist-drop mist-drop--one" cx="14.8" cy="17.8" r="1"/>' +
  '<circle class="mist-drop mist-drop--two" cx="17.6" cy="21.5" r="0.9"/>' +
  '<circle class="mist-drop mist-drop--three" cx="22.8" cy="23.5" r="0.8"/>' +
  "</svg>";

const ICONE_SENSOR =
  '<svg class="equip-svg sensor-svg" viewBox="0 0 32 32" aria-hidden="true">' +
  '<path class="sensor-wave sensor-wave--left" d="M10.2 8.9c-1.4 1.3-2.2 3-2.2 5"/>' +
  '<path class="sensor-wave sensor-wave--right" d="M21.8 8.9c1.4 1.3 2.2 3 2.2 5"/>' +
  '<path class="sensor-stem" d="M16 12.4V8.6"/>' +
  '<circle class="sensor-tip" cx="16" cy="7" r="1.4"/>' +
  '<rect class="sensor-body" x="9.5" y="12.3" width="13" height="11.4" rx="2.2"/>' +
  '<circle class="sensor-led" cx="16" cy="18" r="2.1"/>' +
  '<path class="sensor-base" d="M12.2 25h7.6"/>' +
  "</svg>";

const estado = { especie: "frangos", indice: "ITU" };

let graficosPorIndice = new Map();
let graficoEntradas = null;
let assinaturaGraficos = "";
let ultimosResultados = null;
let ultimosHistoricosGrafico = {};
let historicoLeiturasBase = [];
let historicoLeiturasAtuais = [];
let historicoPaginaAtual = 1;
let filtroHistoricoIndice = "";
let filtroHistoricoStatus = "";
let autoAtivo = false; // Modo automatico ligado/desligado (checado antes de CADA ciclo)
let autoEmExecucao = false; // true enquanto um ciclo esta em andamento (evita sobreposicao)
let autoTimeoutId = null; // id do proximo ciclo agendado (setTimeout), se houver
let salvamentoConfigTimeoutId = null;
let audioCtx = null;

// ---------------------------------------------------------------------------
// Seletores de especie / indice
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

function indicesDaEspecie() {
  return CONFIG_APP.indicesPorEspecie[estado.especie] || [];
}

function camposDaEspecie() {
  const campos = [];
  indicesDaEspecie().forEach((indice) => {
    (CONFIG_APP.camposPorIndice[indice] || []).forEach((campo) => {
      if (!campos.includes(campo)) campos.push(campo);
    });
  });
  if (campos.includes("tbs") && campos.includes("tbu") && !campos.includes("ur")) {
    campos.push("ur");
  }
  const ordemInterface = ["tbs", "tbu", "tgn", "tpo", "ur", "v"];
  return campos.sort((a, b) => ordemInterface.indexOf(a) - ordemInterface.indexOf(b));
}

function pontoOrvalhoCalculado() {
  return document.getElementById("cfg-ponto-orvalho")?.value === "calculado";
}

function umidadeRelativaCalculada() {
  return document.getElementById("cfg-umidade-relativa")?.value !== "medido";
}

function campoCalculado(campo) {
  return (campo === "ur" && umidadeRelativaCalculada()) || (campo === "tpo" && pontoOrvalhoCalculado());
}

function lerNumeroEntrada(campo) {
  const valor = Number(document.getElementById("campo-" + campo)?.value);
  return Number.isFinite(valor) ? valor : null;
}

function lerAltitudeMetros() {
  return lerNumeroConfiguracao("cfg-altitude", 0, -500);
}

function pressaoAtmosferica(altitudeM) {
  const altitude = Math.min(9000, Math.max(-500, altitudeM));
  return 101.325 * ((1 - 2.25577e-5 * altitude) ** 5.2559);
}

function pressaoVaporSaturado(temperaturaC) {
  return 0.61078 * Math.exp((17.27 * temperaturaC) / (temperaturaC + 237.3));
}

function pressaoVaporAtual(tbs, tbu, altitudeM) {
  const constantePsicrometrica = 0.00066 * (1 + 0.00115 * tbu);
  return Math.max(
    0.001,
    pressaoVaporSaturado(tbu) - constantePsicrometrica * pressaoAtmosferica(altitudeM) * (tbs - tbu)
  );
}

function calcularUmidadeRelativa(tbs, tbu, altitudeM) {
  return Math.min(100, Math.max(0, 100 * pressaoVaporAtual(tbs, tbu, altitudeM) / pressaoVaporSaturado(tbs)));
}

function calcularPontoOrvalho(tbs, tbu, altitudeM) {
  const fator = Math.log(pressaoVaporAtual(tbs, tbu, altitudeM) / 0.61078);
  return (237.3 * fator) / (17.27 - fator);
}

function selecionarEspecie(especie) {
  estado.especie = especie;
  ultimosResultados = null;
  historicoPaginaAtual = 1;
  renderSeletorEspecie();
  renderSeletorIndice();
  renderCamposEntrada();
  resetarPainelResultado();
  carregarHistorico();
}

function selecionarIndice(indice) {
  estado.indice = indice;
  renderSeletorIndice();
  atualizarCamposEntrada();
  atualizarCamposCalculados();
  if (ultimosResultados && ultimosResultados[estado.indice]) {
    atualizarPainelIndiceSelecionado(ultimosResultados[estado.indice]);
  } else {
    resetarPainelResultado();
  }
  atualizarGraficos(ultimosHistoricosGrafico);
}

// ---------------------------------------------------------------------------
// Campos de entrada dinamicos
// ---------------------------------------------------------------------------
function renderCamposEntrada() {
  const container = document.getElementById("campos-entrada");
  container.innerHTML = "";
  const campos = camposDaEspecie();
  campos.forEach((campo) => {
    const meta = CONFIG_APP.campoMetadados[campo];
    const wrap = document.createElement("div");
    wrap.className = "campo-entrada";
    wrap.id = "campo-wrap-" + campo;

    const label = document.createElement("label");
    label.setAttribute("for", "campo-" + campo);
    label.textContent = meta.label + " (" + meta.unidade + ")";
    label.style.color = corCampoEntrada(campo);

    const input = document.createElement("input");
    input.type = "number";
    input.id = "campo-" + campo;
    input.step = meta.passo;
    input.min = meta.min;
    input.max = meta.max;
    input.placeholder = "Ex.: " + (((meta.min + meta.max) / 2).toFixed(1));
    input.addEventListener("input", atualizarCamposCalculados);

    wrap.appendChild(label);
    wrap.appendChild(input);
    container.appendChild(wrap);
  });
  atualizarCamposEntrada();
  atualizarCamposCalculados();
}

function camposDoIndiceAtual() {
  const campos = [...(CONFIG_APP.camposPorIndice[estado.indice] || [])];
  if (estado.indice === "IGNU" && pontoOrvalhoCalculado()) {
    ["tbs", "tbu"].forEach((campo) => {
      if (!campos.includes(campo)) campos.push(campo);
    });
  }
  if (campos.includes("tbs") && campos.includes("tbu") && !campos.includes("ur")) {
    campos.push("ur");
  }
  if (!umidadeRelativaCalculada() && !campos.includes("ur")) {
    campos.push("ur");
  }
  return campos;
}

function atualizarCamposEntrada() {
  const camposAtivos = camposDoIndiceAtual();
  camposDaEspecie().forEach((campo) => {
    const wrap = document.getElementById("campo-wrap-" + campo);
    const input = document.getElementById("campo-" + campo);
    const ativo = camposAtivos.includes(campo);
    const calculado = campoCalculado(campo);
    if (wrap) {
      wrap.classList.toggle("campo-entrada--inativo", !ativo);
      wrap.classList.toggle("campo-entrada--calculado", ativo && calculado);
    }
    if (input) {
      input.disabled = !ativo;
      input.readOnly = ativo && calculado;
      input.required = ativo && !calculado;
      input.setAttribute("aria-disabled", String(!ativo));
    }
  });
}

function atualizarCamposCalculados() {
  const tbs = lerNumeroEntrada("tbs");
  const tbu = lerNumeroEntrada("tbu");
  const altitude = lerAltitudeMetros();
  const urInput = document.getElementById("campo-ur");
  const tpoInput = document.getElementById("campo-tpo");
  const podeCalcular = tbs !== null && tbu !== null && tbu <= tbs;

  if (urInput && !urInput.disabled && umidadeRelativaCalculada()) {
    urInput.value = podeCalcular ? calcularUmidadeRelativa(tbs, tbu, altitude).toFixed(1) : "";
  }

  if (tpoInput && pontoOrvalhoCalculado()) {
    tpoInput.value = podeCalcular ? calcularPontoOrvalho(tbs, tbu, altitude).toFixed(1) : "";
  }
}

function coletarEntradas(incluirDesabilitados = false) {
  const campos = camposDaEspecie();
  const entradas = {};
  campos.forEach((campo) => {
    const input = document.getElementById("campo-" + campo);
    if (input && (incluirDesabilitados || !input.disabled)) entradas[campo] = input.value;
  });
  return entradas;
}

function preencherEntradas(dados) {
  Object.entries(dados).forEach(([campo, valor]) => {
    const input = document.getElementById("campo-" + campo);
    if (input) input.value = valor;
  });
  atualizarCamposCalculados();
}

function lerNumeroConfiguracao(id, padrao, minimo) {
  const input = document.getElementById(id);
  if (!input) return padrao;

  const valor = Number(input.value);
  const normalizado = Number.isFinite(valor) ? Math.max(minimo, valor) : padrao;
  input.value = String(normalizado);
  return normalizado;
}

function obterIntervaloLeituraMs() {
  return lerNumeroConfiguracao("cfg-intervalo-leitura", 1, 1) * 1000;
}

function coletarConfig() {
  return {
    coletarDados: document.getElementById("cfg-coletar").checked,
    habilitarSons: document.getElementById("cfg-sons").checked,
    enviarEmails: document.getElementById("cfg-emails").checked,
    habilitarEquipamentos: document.getElementById("cfg-equipamentos").checked,
    emailDestino: document.getElementById("email-destino").value,
    modoAutomatico: document.getElementById("cfg-auto").checked,
    intervaloLeituraSegundos: lerNumeroConfiguracao("cfg-intervalo-leitura", 1, 1),
    intervaloGravacaoMinutos: lerNumeroConfiguracao("cfg-intervalo-gravacao", 1, 0),
    modoPontoOrvalho: document.getElementById("cfg-ponto-orvalho").value,
    modoUmidadeRelativa: document.getElementById("cfg-umidade-relativa").value,
    altitudeMetros: lerAltitudeMetros(),
    limiteUmidadeNebulizador: lerNumeroConfiguracao("cfg-limite-umidade-nebulizador", 70, 0),
  };
}

function definirValorConfiguracao(id, valor) {
  const elemento = document.getElementById(id);
  if (!elemento || valor === undefined || valor === null) return;

  if (elemento.type === "checkbox") {
    elemento.checked = !!valor;
  } else {
    elemento.value = String(valor);
  }
}

function aplicarConfiguracoes(config) {
  definirValorConfiguracao("cfg-coletar", config.coletarDados);
  definirValorConfiguracao("cfg-sons", config.habilitarSons);
  definirValorConfiguracao("cfg-emails", config.enviarEmails);
  definirValorConfiguracao("cfg-equipamentos", config.habilitarEquipamentos);
  definirValorConfiguracao("email-destino", config.emailDestino);
  definirValorConfiguracao("cfg-auto", config.modoAutomatico);
  definirValorConfiguracao("cfg-intervalo-leitura", config.intervaloLeituraSegundos);
  definirValorConfiguracao("cfg-intervalo-gravacao", config.intervaloGravacaoMinutos);
  definirValorConfiguracao("cfg-ponto-orvalho", config.modoPontoOrvalho);
  definirValorConfiguracao("cfg-umidade-relativa", config.modoUmidadeRelativa);
  definirValorConfiguracao("cfg-altitude", config.altitudeMetros);
  definirValorConfiguracao("cfg-limite-umidade-nebulizador", config.limiteUmidadeNebulizador);

  if (document.getElementById("cfg-auto").checked) {
    document.getElementById("cfg-coletar").checked = true;
  }
  document.getElementById("wrap-email-destino").classList.toggle(
    "oculto",
    !document.getElementById("cfg-emails").checked
  );
  document.getElementById("btn-simular").disabled = !document.getElementById("cfg-coletar").checked;
}

async function carregarConfiguracoesPersistidas() {
  try {
    const resposta = await fetch("/api/configuracoes");
    if (!resposta.ok) return;
    aplicarConfiguracoes(await resposta.json());
  } catch (erro) {
    console.error("Nao foi possivel carregar configuracoes persistidas:", erro);
  }
}

async function salvarConfiguracoesPersistidas() {
  try {
    await fetch("/api/configuracoes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(coletarConfig()),
    });
  } catch (erro) {
    console.error("Nao foi possivel salvar configuracoes:", erro);
  }
}

function agendarSalvarConfiguracoes() {
  if (salvamentoConfigTimeoutId) clearTimeout(salvamentoConfigTimeoutId);
  salvamentoConfigTimeoutId = setTimeout(salvarConfiguracoesPersistidas, 250);
}

// ---------------------------------------------------------------------------
// Chamadas a API
// ---------------------------------------------------------------------------
async function calcular(opcoes = {}) {
  esconderErro();
  const entradas = coletarEntradas(!!opcoes.incluirCamposDesabilitados);
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
    // Esta captura e exclusivamente para falhas de rede (fetch nao completou,
    // ou a resposta nao era JSON valido) - nunca para erros ocorridos depois,
    // ao atualizar a tela.
    console.error("Erro de comunicacao com /api/calcular:", erro);
    mostrarErro(
      erro && erro.message && erro.message.includes("Flask")
        ? erro.message
        : "Falha de comunicação com o servidor. Verifique se o Flask está em execução (python app.py) e se a página foi aberta em http://127.0.0.1:5000."
    );
    return;
  }

  // A requisicao foi concluida com sucesso. Qualquer erro a partir daqui e de
  // atualizacao da tela (ex.: graficos), nao de comunicacao - tratado a parte
  // dentro de atualizarResultado(), para nunca ser confundido com o caso acima.
  atualizarResultado(dados);
}

async function simularSensor() {
  try {
    const respostas = await Promise.all(
      indicesDaEspecie().map((indice) =>
        fetch(
          "/api/sensor?especie=" + encodeURIComponent(estado.especie) +
          "&indice=" + encodeURIComponent(indice)
        )
      )
    );
    const leituras = await Promise.all(respostas.map((resposta) => resposta.json()));
    if (respostas.every((resposta) => resposta.ok)) {
      preencherEntradas(Object.assign({}, ...leituras));
    }
  } catch (erro) {
    mostrarErro("Não foi possível simular a leitura do sensor.");
  }
}

async function carregarHistorico() {
  try {
    const query = "?especie=" + encodeURIComponent(estado.especie);
    const [resposta, respostaGrafico] = await Promise.all([
      fetch("/api/historico-todos" + query),
      fetch("/api/historico-grafico-todos" + query),
    ]);
    const historico = await resposta.json();
    const historicoGrafico = respostaGrafico.ok ? await respostaGrafico.json() : historico;
    ultimosHistoricosGrafico = historicoGrafico;
    atualizarGraficos(historicoGrafico);
    atualizarTabela(historico);
  } catch (erro) {
    /* nao critico */
  }
}

async function limparHistorico() {
  try {
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ especie: estado.especie }),
    });
  } catch (erro) {
    /* ignora */
  }
  resetarPainelResultado();
  ultimosHistoricosGrafico = {};
  atualizarGraficos({});
  atualizarTabela({});
}

// ---------------------------------------------------------------------------
// Atualizacao da interface
// ---------------------------------------------------------------------------
function resetarPainelResultado() {
  ultimosResultados = null;
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

function atualizarPainelIndiceSelecionado(resultado, avisoGeral) {
  const classe = classeStatus(resultado.status);
  const readoutValor = document.getElementById("readout-valor");
  readoutValor.textContent = resultado.valor.toFixed(2).replace(".", ",");
  readoutValor.className = "readout-valor cor-" + classe;
  document.getElementById("readout-indice").textContent = estado.indice;

  const faixa = document.getElementById("faixa-status");
  faixa.className = "faixa-status faixa-" + classe;
  document.getElementById("faixa-status-texto").textContent = resultado.status.toUpperCase();

  document.getElementById("mensagem-orientacao").innerHTML =
    "<strong>" + resultado.status + ":</strong> " + resultado.mensagem +
    (avisoGeral ? "<br><em>" + avisoGeral + "</em>" : "");
}

function historicosDosResultados(resultados, tipo) {
  const historicos = {};
  Object.entries(resultados || {}).forEach(([indice, resultado]) => {
    historicos[indice] = resultado[tipo] || resultado.historico || [];
  });
  return historicos;
}

function atualizarResultado(dados) {
  ultimosResultados = dados.indices || { [estado.indice]: dados };
  const selecionado = ultimosResultados[estado.indice] || dados;
  const classe = classeStatus(selecionado.status);

  // 1) Elementos essenciais primeiro - nunca dependem de bibliotecas externas,
  //    entao sempre devem atualizar mesmo se algo mais adiante falhar.
  const readoutValor = document.getElementById("readout-valor");
  readoutValor.textContent = selecionado.valor.toFixed(2).replace(".", ",");
  readoutValor.className = "readout-valor cor-" + classe;
  document.getElementById("readout-indice").textContent = estado.indice;

  const faixa = document.getElementById("faixa-status");
  faixa.className = "faixa-status faixa-" + classe;
  document.getElementById("faixa-status-texto").textContent = selecionado.status.toUpperCase();

  document.getElementById("mensagem-orientacao").innerHTML =
    "<strong>" + selecionado.status + ":</strong> " + selecionado.mensagem +
    (dados.aviso ? "<br><em>" + dados.aviso + "</em>" : "");

  atualizarEquipamento(dados.equipamento);
  atualizarEmail(dados.email);

  // 2) Graficos e tabela: isolados em try/catch proprios. Se a biblioteca de
  //    graficos nao carregar por qualquer motivo, o restante do painel acima
  //    ja esta atualizado e continua funcionando normalmente.
  try {
    ultimosHistoricosGrafico = historicosDosResultados(ultimosResultados, "historico_grafico");
    atualizarGraficos(ultimosHistoricosGrafico);
  } catch (erro) {
    console.error("Erro ao desenhar os graficos:", erro);
    mostrarErro(
      "O valor foi calculado normalmente (" + selecionado.valor.toFixed(2).replace(".", ",") +
      ", " + selecionado.status + "), mas os gráficos não puderam ser desenhados. " +
      "Detalhes no console do navegador (F12 → Console)."
    );
  }

  try {
    atualizarTabela(historicosDosResultados(ultimosResultados, "historico"));
  } catch (erro) {
    console.error("Erro ao atualizar a tabela de historico:", erro);
  }

  if (dados.tocarSom && selecionado.status !== "Conforto") {
    try {
      tocarSom(selecionado.status);
    } catch (erro) {
      console.error("Erro ao tocar som de alerta:", erro);
    }
  }
}

function renderizarIconesEquipamento(containerId, svgIcone, nomeEquipamento, ligado, intensidade, quantidadeForcada) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";

  const quantidadeBase = Number.isFinite(quantidadeForcada)
    ? quantidadeForcada
    : quantidadePorIntensidade(intensidade);
  const quantidadeAtiva = ligado ? Math.min(TOTAL_ICONES_EQUIPAMENTO, quantidadeBase) : 0;

  for (let i = 0; i < TOTAL_ICONES_EQUIPAMENTO; i++) {
    const badge = document.createElement("span");
    badge.className = "icone-equip" + (i < quantidadeAtiva ? " ativo" : "");
    badge.innerHTML = svgIcone;
    container.appendChild(badge);
  }

  const estadoTexto = ligado
    ? intensidade
      ? `ligado (intensidade ${rotuloIntensidade(intensidade)}, ${quantidadeAtiva} de ${TOTAL_ICONES_EQUIPAMENTO} ativos)`
      : `ligado (${quantidadeAtiva} de ${TOTAL_ICONES_EQUIPAMENTO} ativos)`
    : `desligado, 0 de ${TOTAL_ICONES_EQUIPAMENTO} ativos`;
  container.setAttribute("aria-label", `${nomeEquipamento} ${estadoTexto}`);
}

function atualizarEquipamento(equip) {
  const ventiladorLigado = !!(equip && equip.ventilador);
  const nebulizadorLigado = !!(equip && equip.nebulizador);
  const intensidade = (equip && equip.intensidade) || null;

  renderizarIconesEquipamento("icones-ventilador", ICONE_VENTILADOR, "Ventilador", ventiladorLigado, intensidade);
  renderizarIconesEquipamento("icones-nebulizador", ICONE_NEBULIZADOR, "Nebulizador", nebulizadorLigado, intensidade);

  document.getElementById("intensidade-valor").textContent = intensidade ? rotuloIntensidade(intensidade) : "desligado";
}

function atualizarSensorRemoto() {
  const checkboxColeta = document.getElementById("cfg-coletar");
  const sensorLigado = !!(checkboxColeta && checkboxColeta.checked);

  renderizarIconesEquipamento(
    "icones-sensor",
    ICONE_SENSOR,
    "Sensor",
    sensorLigado,
    null,
    TOTAL_ICONES_EQUIPAMENTO
  );
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

function normalizarHistoricosPorIndice(historicos) {
  if (Array.isArray(historicos)) return { [estado.indice]: historicos };

  const normalizados = {};
  indicesDaEspecie().forEach((indice) => {
    normalizados[indice] = (historicos && historicos[indice]) || [];
  });
  return normalizados;
}

function chavesCronologicas(historicosPorIndice) {
  return [...new Set(
    Object.values(historicosPorIndice)
      .flat()
      .map((leitura) => leitura.criado_em)
  )].sort();
}

function assinaturaDoHistorico(historicos) {
  return JSON.stringify({
    especie: estado.especie,
    indices: indicesDaEspecie(),
    historicos: normalizarHistoricosPorIndice(historicos),
  });
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

function atualizarGraficosLegado(historico) {
  if (typeof Chart === "undefined") {
    throw new Error(
      "A biblioteca Chart.js não foi carregada (conforto_termico/static/js/vendor/chart.umd.js). " +
      "Confira se a pasta 'conforto_termico/static/js/vendor' foi copiada junto com o projeto."
    );
  }

  const novaAssinatura = assinaturaDoHistorico(historico);
  if (novaAssinatura === assinaturaGraficos && graficoIndice && graficoEntradas) {
    return;
  }
  assinaturaGraficos = novaAssinatura;

  const rotulos = historico.map((h) => formatarHora(h.criado_em));
  const valores = historico.map((h) => h.valor);
  const cores = historico.map((h) => corStatus(h.status));
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
  const temEixoSecundario = campos.some((campo) => campo === "v" || campo === "ur");
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
      fill: campo !== "v" && campo !== "ur",
      yAxisID: campo === "v" || campo === "ur" ? "y1" : "y",
    });
    return dataset;
  });

  graficoEntradas = criarOuAtualizarGrafico(graficoEntradas, "grafico-entradas", {
    type: "line",
    data: { labels: rotulos, datasets: datasetsEntradas },
    options: opcoesGrafico(temEixoSecundario),
  });
}

function atualizarGraficosCombinadoLegado(historicos) {
  if (typeof Chart === "undefined") {
    throw new Error(
      "A biblioteca Chart.js não foi carregada (conforto_termico/static/js/vendor/chart.umd.js). " +
      "Confira se a pasta 'conforto_termico/static/js/vendor' foi copiada junto com o projeto."
    );
  }

  const historicosPorIndice = normalizarHistoricosPorIndice(historicos);
  const novaAssinatura = assinaturaDoHistorico(historicosPorIndice);
  if (novaAssinatura === assinaturaGraficos && graficoIndice && graficoEntradas) {
    return;
  }
  assinaturaGraficos = novaAssinatura;

  const chaves = chavesCronologicas(historicosPorIndice);
  const rotulos = chaves.map((chave) => formatarHora(chave));
  const datasetsAtuaisIndice = new Map(
    graficoIndice ? graficoIndice.data.datasets.map((dataset) => [dataset.indice, dataset]) : []
  );
  const datasetsIndice = indicesDaEspecie().map((indice) => {
    const leiturasPorChave = new Map((historicosPorIndice[indice] || []).map((h) => [h.criado_em, h]));
    const dataset = datasetsAtuaisIndice.get(indice) || {};
    Object.assign(dataset, {
      indice,
      label: indice,
      data: chaves.map((chave) => leiturasPorChave.get(chave)?.valor ?? null),
      backgroundColor: chaves.map((chave) => corStatus(leiturasPorChave.get(chave)?.status)),
      borderRadius: 3,
      maxBarThickness: 24,
    });
    return dataset;
  });

  graficoIndice = criarOuAtualizarGrafico(graficoIndice, "grafico-indice", {
    type: "bar",
    data: { labels: rotulos, datasets: datasetsIndice },
    options: opcoesGrafico(false),
  });

  const entradasPorChave = new Map();
  Object.values(historicosPorIndice).flat().forEach((leitura) => {
    const entradas = entradasPorChave.get(leitura.criado_em) || {};
    Object.assign(entradas, leitura.entradas);
    entradasPorChave.set(leitura.criado_em, entradas);
  });

  const campos = camposDaEspecie();
  const paleta = ["#4F8A93", "#D9A441", "#8FBF9F", "#C1443C", "#9E7BB5"];
  const temEixoSecundario = campos.some((campo) => campo === "v" || campo === "ur");
  const datasetsAtuaisEntradas = new Map(
    graficoEntradas ? graficoEntradas.data.datasets.map((dataset) => [dataset.campo, dataset]) : []
  );
  const datasetsEntradas = campos.map((campo, i) => {
    const cor = paleta[i % paleta.length];
    const dataset = datasetsAtuaisEntradas.get(campo) || {};
    Object.assign(dataset, {
      campo,
      label: CONFIG_APP.campoMetadados[campo].label,
      data: chaves.map((chave) => entradasPorChave.get(chave)?.[campo] ?? null),
      borderColor: cor,
      backgroundColor: cor + "33",
      tension: 0.35,
      cubicInterpolationMode: "monotone",
      pointRadius: 2,
      pointHoverRadius: 4,
      fill: campo !== "v" && campo !== "ur",
      yAxisID: campo === "v" || campo === "ur" ? "y1" : "y",
    });
    return dataset;
  });

  graficoEntradas = criarOuAtualizarGrafico(graficoEntradas, "grafico-entradas", {
    type: "line",
    data: { labels: rotulos, datasets: datasetsEntradas },
    options: opcoesGrafico(temEixoSecundario),
  });
}

function indicesOrdenadosParaGraficos() {
  return [
    estado.indice,
    ...indicesDaEspecie().filter((indice) => indice !== estado.indice),
  ];
}

function idGraficoIndice(indice) {
  return "grafico-indice-" + indice.toLowerCase();
}

function entradasPorChaveDosHistoricos(historicosPorIndice) {
  const entradasPorChave = new Map();
  Object.values(historicosPorIndice).flat().forEach((leitura) => {
    const entradas = entradasPorChave.get(leitura.criado_em) || {};
    Object.assign(entradas, leitura.entradas);
    entradasPorChave.set(leitura.criado_em, entradas);
  });
  return entradasPorChave;
}

function atualizarGraficoEntradas(historicosPorIndice) {
  const canvas = document.getElementById("grafico-entradas");
  if (!canvas) return;

  const chaves = chavesCronologicas(historicosPorIndice);
  const entradasPorChave = entradasPorChaveDosHistoricos(historicosPorIndice);
  const campos = camposDaEspecie();
  const temEixoSecundario = campos.some((campo) => campo === "v" || campo === "ur");
  const datasetsAtuais = new Map(
    graficoEntradas ? graficoEntradas.data.datasets.map((dataset) => [dataset.campo, dataset]) : []
  );
  const datasets = campos.map((campo) => {
    const cor = corCampoEntrada(campo);
    const dataset = datasetsAtuais.get(campo) || {};
    Object.assign(dataset, {
      campo,
      label: CONFIG_APP.campoMetadados[campo].label,
      data: chaves.map((chave) => entradasPorChave.get(chave)?.[campo] ?? null),
      borderColor: cor,
      backgroundColor: cor + "33",
      tension: 0.35,
      cubicInterpolationMode: "monotone",
      pointRadius: 2,
      pointHoverRadius: 4,
      fill: campo !== "v" && campo !== "ur",
      yAxisID: campo === "v" || campo === "ur" ? "y1" : "y",
    });
    return dataset;
  });

  const opcoes = opcoesGrafico(temEixoSecundario);
  opcoes.plugins.legend.display = false;

  graficoEntradas = criarOuAtualizarGrafico(graficoEntradas, "grafico-entradas", {
    type: "line",
    data: {
      labels: chaves.map((chave) => formatarHora(chave)),
      datasets,
    },
    options: opcoes,
  });
}

function garantirBlocosGraficos(indices) {
  const container = document.getElementById("graficos-indices");
  if (!container) return;

  const idsAtivos = new Set(indices.map(idGraficoIndice));
  [...container.querySelectorAll(".grafico-bloco-indice")].forEach((bloco) => {
    if (!idsAtivos.has(bloco.dataset.canvasId)) bloco.remove();
  });

  indices.forEach((indice) => {
    const canvasId = idGraficoIndice(indice);
    let bloco = container.querySelector(`[data-canvas-id="${canvasId}"]`);
    if (!bloco) {
      bloco = document.createElement("div");
      bloco.className = "grafico-bloco grafico-bloco-indice";
      bloco.dataset.canvasId = canvasId;

      const titulo = document.createElement("p");
      titulo.className = "grafico-titulo";
      titulo.textContent = "Valor do " + indice + " por leitura";

      const wrap = document.createElement("div");
      wrap.className = "grafico-canvas-wrap";

      const canvas = document.createElement("canvas");
      canvas.id = canvasId;

      wrap.appendChild(canvas);
      bloco.append(titulo, wrap);
    }
    container.appendChild(bloco);
  });
}

function atualizarGraficos(historicos) {
  if (typeof Chart === "undefined") {
    throw new Error(
      "A biblioteca Chart.js não foi carregada (conforto_termico/static/js/vendor/chart.umd.js). " +
      "Confira se a pasta 'conforto_termico/static/js/vendor' foi copiada junto com o projeto."
    );
  }

  const historicosPorIndice = normalizarHistoricosPorIndice(historicos);
  const indices = indicesOrdenadosParaGraficos();
  const novaAssinatura = assinaturaDoHistorico(historicosPorIndice) + ";" + estado.indice;
  if (novaAssinatura === assinaturaGraficos && graficosPorIndice.size) {
    return;
  }
  assinaturaGraficos = novaAssinatura;

  atualizarGraficoEntradas(historicosPorIndice);
  garantirBlocosGraficos(indices);

  const indicesAtivos = new Set(indices);
  graficosPorIndice.forEach((grafico, indice) => {
    if (!indicesAtivos.has(indice)) {
      grafico.destroy();
      graficosPorIndice.delete(indice);
    }
  });

  indices.forEach((indice) => {
    const historico = historicosPorIndice[indice] || [];
    const canvasId = idGraficoIndice(indice);
    const dataset = graficosPorIndice.get(indice)?.data.datasets[0] || {};
    Object.assign(dataset, {
      label: indice,
      data: historico.map((h) => h.valor),
      backgroundColor: historico.map((h) => corStatus(h.status)),
      borderRadius: 3,
      maxBarThickness: 26,
    });

    const grafico = criarOuAtualizarGrafico(graficosPorIndice.get(indice), canvasId, {
      type: "bar",
      data: {
        labels: historico.map((h) => formatarHora(h.criado_em)),
        datasets: [dataset],
      },
      options: opcoesGrafico(false),
    });
    graficosPorIndice.set(indice, grafico);
  });
}

function atualizarTabelaLegado(historico) {
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
    const classe = "status-" + classeStatus(h.status);

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

function leiturasTabela(historicos) {
  const historicosPorIndice = normalizarHistoricosPorIndice(historicos);
  return Object.entries(historicosPorIndice)
    .flatMap(([indice, leituras]) => leituras.map((leitura) => ({ ...leitura, indice })))
    .sort((a, b) => {
      const porData = new Date(b.criado_em) - new Date(a.criado_em);
      if (porData !== 0) return porData;
      return a.indice.localeCompare(b.indice);
    });
}

function preencherSelectHistorico(select, opcoes, valorAtual) {
  if (!select) return;

  select.innerHTML = "";
  const todos = document.createElement("option");
  todos.value = "";
  todos.textContent = "Todos";
  select.appendChild(todos);

  opcoes.forEach((opcao) => {
    const option = document.createElement("option");
    option.value = opcao;
    option.textContent = opcao;
    select.appendChild(option);
  });

  select.value = valorAtual;
}

function renderizarFiltrosHistorico() {
  const indices = indicesDaEspecie();
  if (filtroHistoricoIndice && !indices.includes(filtroHistoricoIndice)) {
    filtroHistoricoIndice = "";
  }
  if (filtroHistoricoStatus && !STATUS_HISTORICO.includes(filtroHistoricoStatus)) {
    filtroHistoricoStatus = "";
  }

  preencherSelectHistorico(
    document.getElementById("filtro-historico-indice"),
    indices,
    filtroHistoricoIndice
  );
  preencherSelectHistorico(
    document.getElementById("filtro-historico-status"),
    STATUS_HISTORICO,
    filtroHistoricoStatus
  );
}

function aplicarFiltrosHistorico(resetarPagina) {
  historicoLeiturasAtuais = historicoLeiturasBase.filter((leitura) => {
    const indiceOk = !filtroHistoricoIndice || leitura.indice === filtroHistoricoIndice;
    const statusOk = !filtroHistoricoStatus || leitura.status === filtroHistoricoStatus;
    return indiceOk && statusOk;
  });

  if (resetarPagina) historicoPaginaAtual = 1;
  renderizarPaginaHistorico();
}

function atualizarFiltroHistorico() {
  filtroHistoricoIndice = document.getElementById("filtro-historico-indice")?.value || "";
  filtroHistoricoStatus = document.getElementById("filtro-historico-status")?.value || "";
  aplicarFiltrosHistorico(true);
}

function renderizarPaginaHistorico() {
  const tbody = document.querySelector("#tabela-historico tbody");
  const tabela = document.getElementById("tabela-historico");
  const vazio = document.getElementById("tabela-vazia");
  const paginacao = document.getElementById("historico-paginacao");
  const paginaInfo = document.getElementById("historico-pagina-info");
  const btnAnterior = document.getElementById("btn-historico-anterior");
  const btnProximo = document.getElementById("btn-historico-proximo");
  tbody.innerHTML = "";

  const totalPaginas = Math.max(1, Math.ceil(historicoLeiturasAtuais.length / HISTORICO_LINHAS_POR_PAGINA));
  historicoPaginaAtual = Math.min(Math.max(1, historicoPaginaAtual), totalPaginas);

  if (!historicoLeiturasAtuais.length) {
    tabela.classList.add("oculto");
    vazio.textContent = historicoLeiturasBase.length
      ? "Nenhuma leitura encontrada para os filtros selecionados."
      : "Nenhuma leitura registrada ainda para esta espécie.";
    vazio.classList.remove("oculto");
    if (paginacao) paginacao.classList.add("oculto");
    return;
  }
  tabela.classList.remove("oculto");
  vazio.classList.add("oculto");
  if (paginacao) paginacao.classList.toggle("oculto", totalPaginas <= 1);
  if (paginaInfo) paginaInfo.textContent = `Página ${historicoPaginaAtual} de ${totalPaginas}`;
  if (btnAnterior) btnAnterior.disabled = historicoPaginaAtual <= 1;
  if (btnProximo) btnProximo.disabled = historicoPaginaAtual >= totalPaginas;

  const inicio = (historicoPaginaAtual - 1) * HISTORICO_LINHAS_POR_PAGINA;
  const leituras = historicoLeiturasAtuais.slice(inicio, inicio + HISTORICO_LINHAS_POR_PAGINA);

  leituras.forEach((h) => {
    const tr = document.createElement("tr");
    const entradasTexto = Object.entries(h.entradas)
      .map(([k, v]) => k + "=" + v)
      .join(", ");
    const classe = "status-" + classeStatus(h.status);

    const tdHora = document.createElement("td");
    tdHora.textContent = formatarHora(h.criado_em);
    const tdIndice = document.createElement("td");
    tdIndice.textContent = h.indice;
    const tdEntradas = document.createElement("td");
    tdEntradas.textContent = entradasTexto;
    const tdValor = document.createElement("td");
    tdValor.textContent = h.valor.toFixed(2).replace(".", ",");
    const tdStatus = document.createElement("td");
    tdStatus.textContent = h.status;
    tdStatus.className = classe;

    tr.append(tdHora, tdIndice, tdEntradas, tdValor, tdStatus);
    tbody.appendChild(tr);
  });
}

function atualizarTabela(historicos) {
  historicoLeiturasBase = leiturasTabela(historicos);
  renderizarFiltrosHistorico();
  aplicarFiltrosHistorico(false);
}

function alternarHistorico() {
  const corpo = document.getElementById("historico-corpo");
  const botao = document.getElementById("btn-toggle-historico");
  if (!corpo || !botao) return;

  const expandido = corpo.classList.toggle("oculto");
  const aberto = !expandido;
  botao.textContent = aberto ? "Recolher" : "Expandir";
  botao.setAttribute("aria-expanded", aberto ? "true" : "false");
}

function paginaHistorico(delta) {
  historicoPaginaAtual += delta;
  renderizarPaginaHistorico();
}

function inicializarHistorico() {
  renderizarFiltrosHistorico();
  document.getElementById("btn-toggle-historico")?.addEventListener("click", alternarHistorico);
  document.getElementById("btn-historico-anterior")?.addEventListener("click", () => paginaHistorico(-1));
  document.getElementById("btn-historico-proximo")?.addEventListener("click", () => paginaHistorico(1));
  document.getElementById("filtro-historico-indice")?.addEventListener("change", atualizarFiltroHistorico);
  document.getElementById("filtro-historico-status")?.addEventListener("change", atualizarFiltroHistorico);
}

// ---------------------------------------------------------------------------
// Som de alerta (Web Audio API - nenhum arquivo de audio necessario)
// ---------------------------------------------------------------------------
function tocarSom(status) {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const sequencias = {
      Conforto: [660],
      Alerta: [520, 520],
      Perigo: [420, 420, 420],
      "Emergencia": [300, 300, 300, 300],
    };
    const seq = sequencias[normalizarChaveTexto(status)] || [440];
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
    /* Web Audio indisponivel neste navegador - ignora silenciosamente */
  }
}

// ---------------------------------------------------------------------------
// Abas e organizacao dos cards
// ---------------------------------------------------------------------------
function inicializarAbas() {
  const botoes = document.querySelectorAll("[data-aba]");
  const conteudos = document.querySelectorAll("[data-aba-conteudo]");

  botoes.forEach((botao) => {
    botao.addEventListener("click", () => {
      const aba = botao.dataset.aba;

      botoes.forEach((item) => {
        const ativo = item.dataset.aba === aba;
        item.classList.toggle("ativo", ativo);
        item.setAttribute("aria-selected", ativo ? "true" : "false");
      });

      conteudos.forEach((conteudo) => {
        conteudo.classList.toggle("oculto", conteudo.dataset.abaConteudo !== aba);
      });

      if (aba === "principal") {
        setTimeout(() => {
          graficosPorIndice.forEach((grafico) => grafico.resize());
          if (graficoEntradas) graficoEntradas.resize();
        }, 0);
      }
    });
  });
}

function moverControlesParaConfiguracoes() {
  const configuracoesApp = document.getElementById("configuracoes-app");
  const configuracoesSensores = document.getElementById("configuracoes-sensores");
  const configuracoesCalculos = document.getElementById("configuracoes-calculos");
  const configuracoesHistorico = document.getElementById("configuracoes-historico");
  const historicoAcoes = document.getElementById("historico-acoes");
  const historicoPaginacao = document.getElementById("historico-paginacao");

  const email = document.getElementById("wrap-email-destino");
  const limparHistorico = document.getElementById("btn-limpar");

  const criarGradeChecks = (container) => {
    if (!container) return null;
    let grade = container.querySelector(".config-grade");
    if (!grade) {
      grade = document.createElement("div");
      grade.className = "config-grade";
      container.appendChild(grade);
    }
    return grade;
  };
  const criarGradeCampos = (container) => {
    if (!container) return null;
    let grade = container.querySelector(".campos-config");
    if (!grade) {
      grade = document.createElement("div");
      grade.className = "campos-config";
      container.appendChild(grade);
    }
    return grade;
  };
  const moverCheck = (id, container) => {
    const controle = document.getElementById(id);
    const label = controle?.closest("label");
    const grade = criarGradeChecks(container);
    if (label && grade) grade.appendChild(label);
  };
  const moverCampo = (id, container) => {
    const controle = document.getElementById(id);
    const campo = controle?.closest(".campo-config");
    const grade = criarGradeCampos(container);
    if (campo && grade) grade.appendChild(campo);
  };

  moverCheck("cfg-emails", configuracoesApp);
  moverCheck("cfg-sons", configuracoesApp);
  moverCheck("cfg-equipamentos", configuracoesApp);
  if (configuracoesApp && email) configuracoesApp.appendChild(email);

  moverCheck("cfg-coletar", configuracoesSensores);
  moverCheck("cfg-auto", configuracoesSensores);
  moverCampo("cfg-intervalo-leitura", configuracoesSensores);

  moverCampo("cfg-ponto-orvalho", configuracoesCalculos);
  moverCampo("cfg-umidade-relativa", configuracoesCalculos);
  moverCampo("cfg-altitude", configuracoesCalculos);
  moverCampo("cfg-limite-umidade-nebulizador", configuracoesCalculos);

  if (historicoAcoes && historicoPaginacao) historicoAcoes.appendChild(historicoPaginacao);
  if (configuracoesHistorico && limparHistorico) configuracoesHistorico.appendChild(limparHistorico);

  document.querySelectorAll(".entrada-painel .acao-linha").forEach((linha) => {
    if (!linha.querySelector("button, input, label")) linha.remove();
  });
}

// ---------------------------------------------------------------------------
// Relogio e modo automatico
// ---------------------------------------------------------------------------
function iniciarRelogio() {
  const el = document.getElementById("relogio");
  if (!el) return;
  const atualizar = () => {
    el.textContent = new Date().toLocaleTimeString("pt-BR");
  };
  atualizar();
  setInterval(atualizar, 1000);
}

function alternarModoAutomatico(ativo) {
  autoAtivo = ativo;

  // Cancela qualquer proximo ciclo ja agendado. Se um ciclo ja estiver em
  // execucao neste exato momento (aguardando resposta do servidor), ele vai
  // terminar sozinho - mas por causa da checagem de `autoAtivo` dentro de
  // `cicloAutomatico()`, ele nao vai agendar um proximo. Ou seja, desmarcar
  // sempre para o monitoramento em, no maximo, a duracao de um ciclo (nunca
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
    await calcular({ incluirCamposDesabilitados: true });
  } catch (erro) {
    console.error("Erro no ciclo do modo automatico:", erro);
  } finally {
    autoEmExecucao = false;
  }
  // So agenda o proximo ciclo depois que este terminou por completo - nunca
  // dispara um novo ciclo antes do anterior ter concluido (o que era a causa
  // do modo automatico "nao desligar": ciclos podiam se sobrepor e continuar
  // rodando mesmo depois de desmarcar a caixa).
  if (autoAtivo) {
    autoTimeoutId = setTimeout(cicloAutomatico, obterIntervaloLeituraMs());
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
// Inicializacao
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  moverControlesParaConfiguracoes();
  inicializarAbas();
  inicializarHistorico();
  await carregarConfiguracoesPersistidas();
  renderSeletorEspecie();
  renderSeletorIndice();
  renderCamposEntrada();
  carregarHistorico();
  atualizarEquipamento(null);
  atualizarSensorRemoto();

  document.getElementById("btn-calcular").addEventListener("click", calcular);
  document.getElementById("btn-simular").addEventListener("click", simularSensor);
  document.getElementById("btn-limpar").addEventListener("click", limparHistorico);

  document.getElementById("cfg-coletar").addEventListener("change", (e) => {
    document.getElementById("btn-simular").disabled = !e.target.checked;
    atualizarSensorRemoto();
  });
  document.getElementById("cfg-emails").addEventListener("change", (e) => {
    document.getElementById("wrap-email-destino").classList.toggle("oculto", !e.target.checked);
  });
  document.getElementById("cfg-auto").addEventListener("change", (e) => {
    if (e.target.checked) {
      document.getElementById("cfg-coletar").checked = true;
      document.getElementById("btn-simular").disabled = false;
      atualizarSensorRemoto();
    }
    alternarModoAutomatico(e.target.checked);
  });
  document.getElementById("cfg-intervalo-leitura").addEventListener("change", () => {
    if (autoAtivo && autoTimeoutId) {
      clearTimeout(autoTimeoutId);
      autoTimeoutId = setTimeout(cicloAutomatico, obterIntervaloLeituraMs());
    }
  });
  document.getElementById("cfg-ponto-orvalho").addEventListener("change", () => {
    atualizarCamposEntrada();
    atualizarCamposCalculados();
  });
  document.getElementById("cfg-umidade-relativa").addEventListener("change", () => {
    atualizarCamposEntrada();
    atualizarCamposCalculados();
  });
  document.getElementById("cfg-altitude").addEventListener("input", atualizarCamposCalculados);
  document.querySelectorAll("#aba-configuracoes input, #aba-configuracoes select").forEach((controle) => {
    controle.addEventListener("change", agendarSalvarConfiguracoes);
    if (["number", "email"].includes(controle.type)) {
      controle.addEventListener("input", agendarSalvarConfiguracoes);
    }
  });
  if (document.getElementById("cfg-auto").checked) {
    alternarModoAutomatico(true);
  }
});
