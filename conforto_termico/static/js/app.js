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
  "Emergencia": "#E1261C",
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

// Um icone por equipamento cadastrado. A intensidade nao muda a quantidade;
// ela muda o destaque visual dos icones ativos.
const ICONES_POR_EQUIPAMENTO_ATUADOR = 1;
const ICONES_POR_SENSOR = 1;

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

const estado = { especie: "frangos", indice: "ITU", zonaId: null };

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
let smtpSenhaJaConfigurada = false;
let audioCtx = null;

// ---------------------------------------------------------------------------
// Seletores de especie / indice
// ---------------------------------------------------------------------------
function renderSeletorEspecie() {
  const container = document.getElementById("seletor-especie");
  if (!container) return;
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
  if (!container) return;
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
  return estado.indice ? [estado.indice] : [];
}

function camposDaEspecie() {
  const campos = camposDoIndiceAtual();
  const temBulbos = campos.includes("tbs") && campos.includes("tbu");
  if (temBulbos && umidadeRelativaCalculada() && !campos.includes("ur")) campos.push("ur");
  if (temBulbos && pontoOrvalhoCalculado() && !campos.includes("tpo")) campos.push("tpo");
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
  agendarSalvarConfiguracoes();
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
  agendarSalvarConfiguracoes();
}

// ---------------------------------------------------------------------------
// Campos de entrada dinamicos
// ---------------------------------------------------------------------------
function renderCamposEntrada() {
  const container = document.getElementById("campos-entrada");
  if (!container) return;
  container.innerHTML = "";
  if (!zonaPrincipalSelecionada()) return;
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
  if (campos.includes("tbs") && campos.includes("tbu") && pontoOrvalhoCalculado() && !campos.includes("tpo")) {
    campos.push("tpo");
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

function atualizarCamposCalculados(opcoes = {}) {
  const tbs = lerNumeroEntrada("tbs");
  const tbu = lerNumeroEntrada("tbu");
  const altitude = lerAltitudeMetros();
  const urInput = document.getElementById("campo-ur");
  const tpoInput = document.getElementById("campo-tpo");
  const podeCalcular = tbs !== null && tbu !== null && tbu <= tbs;
  const preservarValoresExistentes = !!opcoes.preservarValoresExistentes;

  if (
    urInput &&
    !urInput.disabled &&
    umidadeRelativaCalculada() &&
    !(preservarValoresExistentes && urInput.value !== "")
  ) {
    urInput.value = podeCalcular ? calcularUmidadeRelativa(tbs, tbu, altitude).toFixed(1) : "";
  }

  if (
    tpoInput &&
    pontoOrvalhoCalculado() &&
    !(preservarValoresExistentes && tpoInput.value !== "")
  ) {
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

function preencherEntradas(dados, opcoes = {}) {
  const entradas = dados || {};
  Object.entries(entradas).forEach(([campo, valor]) => {
    const input = document.getElementById("campo-" + campo);
    if (input) input.value = valor;
  });
  if (opcoes.recalcularDerivados === false) return;
  atualizarCamposCalculados();
}

function preencherEntradasDoResultado(dados) {
  if (!dados || !dados.entradas) return;
  renderCamposEntrada();
  preencherEntradas(dados.entradas, { recalcularDerivados: false });
  atualizarCamposCalculados({ preservarValoresExistentes: true });
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
    especie: estado.especie,
    indice: estado.indice,
    smtpHost: document.getElementById("cfg-smtp-host")?.value || "",
    smtpPorta: lerNumeroConfiguracao("cfg-smtp-porta", 587, 1),
    smtpUsuario: document.getElementById("cfg-smtp-usuario")?.value || "",
    // Campo somente-escrita: o servidor nunca devolve a senha real (ver
    // web._configuracoes_publicas), entao so enviamos algo aqui quando o
    // usuario de fato digitou uma senha nova nesta sessao. Deixar em
    // branco significa "nao mexer na senha ja salva" - tratado do lado do
    // servidor em database.salvar_configuracoes.
    smtpSenha: document.getElementById("cfg-smtp-senha")?.value || "",
    modoSimuladoZonas: document.getElementById("cfg-zonas-simulado")?.checked ?? true,
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

function refletirStatusSmtp() {
  const status = document.getElementById("smtp-status");
  if (!status) return;
  const host = (document.getElementById("cfg-smtp-host")?.value || "").trim();
  const senhaDigitadaAgora = (document.getElementById("cfg-smtp-senha")?.value || "").trim();

  if (!host) {
    status.textContent =
      "Sem host SMTP configurado, o envio funciona em modo simulado (o e-mail é montado e mostrado na tela, mas nada é enviado de fato).";
  } else if (senhaDigitadaAgora || smtpSenhaJaConfigurada) {
    status.textContent =
      "SMTP configurado (" + host + "). Uma senha já está salva; deixe o campo de senha em branco para mantê-la.";
  } else {
    status.textContent =
      "Host SMTP definido, mas ainda sem senha salva. Informe a senha para habilitar o envio real.";
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
  definirValorConfiguracao("cfg-smtp-host", config.smtpHost);
  definirValorConfiguracao("cfg-smtp-porta", config.smtpPorta);
  definirValorConfiguracao("cfg-smtp-usuario", config.smtpUsuario);
  definirValorConfiguracao("cfg-zonas-simulado", config.modoSimuladoZonas);
  // cfg-smtp-senha propositalmente NAO e preenchido aqui: o servidor nunca
  // devolve a senha real, entao o campo fica vazio ate o usuario digitar
  // uma senha nova.

  // Especie/indice persistidos (agora configurados na aba Configuracoes,
  // nao mais na Principal). So aceita valores que a propria tabela
  // indicesPorEspecie reconhece - protege contra um valor antigo/invalido
  // vindo do banco.
  if (CONFIG_APP.indicesPorEspecie[config.especie]) {
    estado.especie = config.especie;
  }
  const indicesDaEspecieConfig = CONFIG_APP.indicesPorEspecie[estado.especie] || [];
  if (indicesDaEspecieConfig.includes(config.indice)) {
    estado.indice = config.indice;
  }

  if (document.getElementById("cfg-auto").checked) {
    document.getElementById("cfg-coletar").checked = true;
  }
  document.getElementById("wrap-email-destino").classList.toggle(
    "oculto",
    !document.getElementById("cfg-emails").checked
  );

  smtpSenhaJaConfigurada = !!config.smtpSenhaConfigurada;
  refletirStatusSmtp();
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
    const resposta = await fetch("/api/configuracoes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(coletarConfig()),
    });
    if (!resposta.ok) return;
    const salvo = await resposta.json();
    smtpSenhaJaConfigurada = !!salvo.smtpSenhaConfigurada;
    // Uma vez salva, a senha nao precisa continuar visivel no campo -- o
    // status abaixo do card ja confirma que ela esta configurada.
    const campoSenha = document.getElementById("cfg-smtp-senha");
    if (campoSenha) campoSenha.value = "";
    refletirStatusSmtp();
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
  const zona = zonaPrincipalSelecionada();
  if (!zona) {
    mostrarErro("Selecione uma zona ativa antes de calcular.");
    return;
  }
  await salvarConfiguracoesPersistidas();
  const usarSensores = document.getElementById("cfg-coletar").checked || document.getElementById("cfg-auto").checked;

  let dados;
  try {
    let resposta;
    if (usarSensores) {
      resposta = await fetch("/api/zonas/calcular-ativas", { method: "POST" });
    } else {
      resposta = await fetch("/api/zonas/" + zona.id + "/calcular", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entradas: coletarEntradas(!!opcoes.incluirCamposDesabilitados) }),
      });
    }
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
    if (usarSensores) {
      const resultados = corpo.resultados || [];
      const resultadoSelecionado = resultados.find((resultado) => resultado.zona_id === zona.id);
      if (!resultadoSelecionado) {
        mostrarErro("Nenhum resultado foi retornado para a zona selecionada.");
        return;
      }
      if (resultadoSelecionado.erro) {
        mostrarErro(resultadoSelecionado.erro);
        await carregarHistorico();
        return;
      }
      dados = resultadoSelecionado;
    } else {
      dados = corpo;
    }
  } catch (erro) {
    // Esta captura e exclusivamente para falhas de rede (fetch nao completou,
    // ou a resposta nao era JSON valido) - nunca para erros ocorridos depois,
    // ao atualizar a tela.
    console.error("Erro de comunicacao ao calcular zonas:", erro);
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
  const zona = zonaPrincipalSelecionada();
  if (!zona) {
    ultimosHistoricosGrafico = {};
    graficosPorIndice.forEach((grafico) => grafico.destroy());
    graficosPorIndice.clear();
    if (graficoEntradas) {
      graficoEntradas.destroy();
      graficoEntradas = null;
    }
    document.getElementById("graficos-indices").textContent = "";
    assinaturaGraficos = "";
    atualizarTabela({});
    return;
  }
  try {
    const resposta = await fetch("/api/zonas/" + zona.id + "/historico");
    const historico = await resposta.json();
    ultimosHistoricosGrafico = { [zona.indice]: historico };
    atualizarGraficos(ultimosHistoricosGrafico);
    atualizarTabela(historico);
  } catch (erro) {
    /* nao critico */
  }
}

async function limparHistorico() {
  mostrarErro("A limpeza do histórico por zona ainda não está disponível; as leituras persistidas são preservadas.");
  resetarPainelResultado();
}

// ---------------------------------------------------------------------------
// Atualizacao da interface
// ---------------------------------------------------------------------------

// NOTA DE SEGURANCA: `resultado.status`, `resultado.mensagem` e o texto de
// aviso vem da resposta JSON do servidor. Hoje sao sempre valores fixos
// (um enum de status e mensagens pre-definidas em thermal_indices.py), mas
// concatena-los direto em `innerHTML` como estava antes e um padrao fragil:
// se qualquer um desses campos um dia passar a incluir texto proveniente
// de uma configuracao editavel pelo usuario, isso abriria uma injecao de
// HTML/script (XSS) sem que nada no front-end precisasse mudar para
// "ativar" o problema. `definirMensagemOrientacao` monta os mesmos
// elementos (<strong>, <br>, <em>) via DOM real com `textContent`, que
// nunca interpreta o conteudo como marcacao, entao o resultado visual e
// identico mas nao ha superficie de injecao.
function definirMensagemOrientacao(status, mensagem, aviso) {
  const container = document.getElementById("mensagem-orientacao");
  container.textContent = "";

  const destaque = document.createElement("strong");
  destaque.textContent = status + ":";
  container.appendChild(destaque);
  container.appendChild(document.createTextNode(" " + mensagem));

  if (aviso) {
    container.appendChild(document.createElement("br"));
    const em = document.createElement("em");
    em.textContent = aviso;
    container.appendChild(em);
  }
}

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
    "Selecione uma zona ativa e clique em <strong>Ler zona agora</strong> para ver o status do lote.";

  atualizarEquipamento(null, null);
  atualizarSensorRemoto();
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

  definirMensagemOrientacao(resultado.status, resultado.mensagem, avisoGeral);
}

function historicosDosResultados(resultados, tipo) {
  const historicos = {};
  Object.entries(resultados || {}).forEach(([indice, resultado]) => {
    historicos[indice] = resultado[tipo] || resultado.historico || [];
  });
  return historicos;
}

function atualizarResultado(dados) {
  estado.especie = dados.especie || estado.especie;
  estado.indice = dados.indice || estado.indice;
  preencherEntradasDoResultado(dados);
  ultimosResultados = { [estado.indice]: dados };
  const selecionado = dados;
  const classe = classeStatus(selecionado.status);

  // 1) Elementos essenciais primeiro - nunca dependem de bibliotecas externas,
  //    entao sempre devem atualizar mesmo se algo mais adiante falhar.
  const readoutValor = document.getElementById("readout-valor");
  readoutValor.textContent = selecionado.valor.toFixed(2).replace(".", ",");
  readoutValor.className = "readout-valor cor-" + classe;
  document.getElementById("readout-indice").textContent = selecionado.indice || estado.indice;

  const faixa = document.getElementById("faixa-status");
  faixa.className = "faixa-status faixa-" + classe;
  document.getElementById("faixa-status-texto").textContent = selecionado.status.toUpperCase();

  definirMensagemOrientacao(selecionado.status, selecionado.mensagem, dados.aviso);

  atualizarEquipamento(dados.equipamento, selecionado.status);
  atualizarEmail(dados.email);

  // 2) Graficos e tabela: isolados em try/catch proprios. Se a biblioteca de
  //    graficos nao carregar por qualquer motivo, o restante do painel acima
  //    ja esta atualizado e continua funcionando normalmente.
  try {
    const historicoZona = selecionado.historico_grafico || [];
    ultimosHistoricosGrafico = { [estado.indice]: historicoZona };
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
    atualizarTabela(selecionado.historico_grafico || []);
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

function renderizarIconesEquipamento(
  containerId,
  svgIcone,
  nomeEquipamento,
  ligado,
  intensidade,
  status,
  totalIcones,
  quantidadeForcada
) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";
  container.classList.remove(
    "equip-intensidade-baixa",
    "equip-intensidade-media",
    "equip-intensidade-maxima",
    "equip-status-conforto",
    "equip-status-alerta",
    "equip-status-perigo",
    "equip-status-emergencia"
  );
  const classeDoStatus = classeStatus(status);
  if (ligado && classeDoStatus) {
    container.classList.add("equip-status-" + classeDoStatus);
  }
  const chaveIntensidade = normalizarChaveTexto(intensidade).toLowerCase();
  if (ligado && ["baixa", "media", "maxima"].includes(chaveIntensidade)) {
    container.classList.add("equip-intensidade-" + chaveIntensidade);
  }

  const total = Math.max(0, Number.isFinite(totalIcones) ? totalIcones : 0);
  const quantidadeAtiva = ligado
    ? Math.min(total, Math.max(0, Number.isFinite(quantidadeForcada) ? quantidadeForcada : total))
    : 0;

  for (let i = 0; i < total; i++) {
    const badge = document.createElement("span");
    badge.className = "icone-equip" + (i < quantidadeAtiva ? " ativo" : "");
    badge.innerHTML = svgIcone;
    container.appendChild(badge);
  }

  const estadoTexto = ligado
    ? intensidade
      ? `ligado (intensidade ${rotuloIntensidade(intensidade)}, ${quantidadeAtiva} de ${total} ativos)`
      : `ligado (${quantidadeAtiva} de ${total} ativos)`
    : `desligado, 0 de ${total} ativos`;
  container.setAttribute("aria-label", `${nomeEquipamento} ${estadoTexto}`);
}

function atualizarEquipamento(equip, status) {
  const ventiladorLigado = !!(equip && equip.ventilador);
  const nebulizadorLigado = !!(equip && equip.nebulizador);
  const intensidade = (equip && equip.intensidade) || null;
  const totalVentiladores = equipamentosDaZonaSelecionada("ventilador").length * ICONES_POR_EQUIPAMENTO_ATUADOR;
  const totalNebulizadores = equipamentosDaZonaSelecionada("nebulizador").length * ICONES_POR_EQUIPAMENTO_ATUADOR;

  renderizarIconesEquipamento(
    "icones-ventilador",
    ICONE_VENTILADOR,
    "Ventilador",
    ventiladorLigado,
    intensidade,
    status,
    totalVentiladores,
    ventiladorLigado ? totalVentiladores : 0
  );
  renderizarIconesEquipamento(
    "icones-nebulizador",
    ICONE_NEBULIZADOR,
    "Nebulizador",
    nebulizadorLigado,
    intensidade,
    status,
    totalNebulizadores,
    nebulizadorLigado ? totalNebulizadores : 0
  );

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
    null,
    equipamentosDaZonaSelecionada("sensor").length * ICONES_POR_SENSOR,
    sensorLigado ? equipamentosDaZonaSelecionada("sensor").length * ICONES_POR_SENSOR : 0
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
    zonaId: estado.zonaId,
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
      : "Nenhuma leitura registrada ainda para esta zona.";
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

      if (aba === "zonas") {
        carregarZonas();
      }
    });
  });
}

function moverControlesParaConfiguracoes() {
  const configuracoesApp = document.getElementById("configuracoes-app");
  const configuracoesEmail = document.getElementById("configuracoes-email");
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

  moverCheck("cfg-sons", configuracoesApp);
  moverCheck("cfg-equipamentos", configuracoesApp);

  moverCheck("cfg-emails", configuracoesEmail);
  if (configuracoesEmail && email) configuracoesEmail.appendChild(email);

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
    await calcular();
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
// Zonas Modbus
// ---------------------------------------------------------------------------
// NOTA DE SEGURANCA: nomes de zona/equipamento sao texto digitado pelo
// usuario. Toda a renderizacao abaixo usa createElement + textContent (o
// mesmo padrao adotado em definirMensagemOrientacao), nunca concatenacao
// de string em innerHTML -- protege contra XSS mesmo que um nome de zona
// contenha algo como "<script>".
let zonasCache = [];
let zonaEmEdicaoId = null; // null = criando uma nova zona
let equipamentoEmEdicao = null; // { zonaId, equipamentoId | null }
let zonaCadastroSelecionadaId = null;
let filtroZonaCadastro = "todas";

const ROTULOS_TIPO_EQUIPAMENTO = {
  sensor: "Sensores",
  ventilador: "Ventiladores",
  nebulizador: "Nebulizadores",
};

function zonasAtivas() {
  return zonasCache.filter((zona) => zona.ativa);
}

function zonaPrincipalSelecionada() {
  return zonasCache.find((zona) => zona.id === estado.zonaId && zona.ativa) || null;
}

function equipamentosDaZonaSelecionada(tipo) {
  const zona = zonaPrincipalSelecionada();
  if (!zona) return [];
  return (zona.equipamentos || []).filter((equipamento) => equipamento.tipo === tipo);
}

function atualizarResumoZonaPrincipal(zona) {
  const resumo = document.getElementById("zona-principal-resumo");
  if (!resumo) return;
  if (!zona) {
    resumo.textContent = "Nenhuma zona ativa selecionada.";
    return;
  }
  const especie = CONFIG_APP.nomeEspecie[zona.especie] || zona.especie;
  resumo.textContent = zona.nome + " · " + especie + " · " + zona.indice;
}

function renderizarSelectZonaPrincipal() {
  const select = document.getElementById("zona-principal");
  if (!select) return;

  const ativas = zonasAtivas();
  const zonaAtualAindaValida = ativas.some((zona) => zona.id === estado.zonaId);
  if (!zonaAtualAindaValida) {
    estado.zonaId = ativas.length ? ativas[0].id : null;
  }

  select.textContent = "";
  if (!ativas.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Nenhuma zona ativa cadastrada";
    select.appendChild(option);
    select.disabled = true;
    document.getElementById("btn-calcular").disabled = true;
    atualizarResumoZonaPrincipal(null);
    renderCamposEntrada();
    atualizarEquipamento(null, null);
    atualizarSensorRemoto();
    return;
  }

  select.disabled = false;
  document.getElementById("btn-calcular").disabled = false;
  ativas.forEach((zona) => {
    const option = document.createElement("option");
    option.value = String(zona.id);
    option.textContent = zona.nome + " (" + zona.indice + ")";
    select.appendChild(option);
  });
  select.value = String(estado.zonaId);

  const zona = zonaPrincipalSelecionada();
  if (zona) {
    estado.especie = zona.especie;
    estado.indice = zona.indice;
  }
  atualizarResumoZonaPrincipal(zona);
  renderCamposEntrada();
  resetarPainelResultado();
}

async function selecionarZonaPrincipal(zonaId) {
  const id = Number(zonaId);
  estado.zonaId = Number.isFinite(id) ? id : null;
  const zona = zonaPrincipalSelecionada();
  if (zona) {
    estado.especie = zona.especie;
    estado.indice = zona.indice;
  }
  assinaturaGraficos = "";
  historicoPaginaAtual = 1;
  atualizarResumoZonaPrincipal(zona);
  renderCamposEntrada();
  resetarPainelResultado();
  await carregarHistorico();
}

function zonaCadastroSelecionada() {
  return zonasCadastroFiltradas().find((zona) => zona.id === zonaCadastroSelecionadaId) || null;
}

function renderizarSelectZonaCadastro() {
  const select = document.getElementById("zona-cadastro");
  if (!select) return;

  const filtro = document.getElementById("filtro-zona-cadastro");
  if (filtro) filtro.value = filtroZonaCadastro;

  const zonasFiltradas = zonasCadastroFiltradas();
  const zonaAtualAindaExiste = zonasFiltradas.some((zona) => zona.id === zonaCadastroSelecionadaId);
  if (!zonaAtualAindaExiste) {
    zonaCadastroSelecionadaId = zonasFiltradas.length ? zonasFiltradas[0].id : null;
  }

  select.textContent = "";
  if (!zonasFiltradas.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = zonasCache.length ? "Nenhuma zona neste filtro" : "Nenhuma zona cadastrada";
    select.appendChild(option);
    select.disabled = true;
    return;
  }

  select.disabled = false;
  zonasFiltradas.forEach((zona) => {
    const option = document.createElement("option");
    option.value = String(zona.id);
    option.textContent = zona.nome + (zona.ativa ? "" : " (inativa)");
    select.appendChild(option);
  });
  select.value = String(zonaCadastroSelecionadaId);
}

function zonasCadastroFiltradas() {
  if (filtroZonaCadastro === "ativas") return zonasCache.filter((zona) => zona.ativa);
  if (filtroZonaCadastro === "inativas") return zonasCache.filter((zona) => !zona.ativa);
  return [...zonasCache];
}

function selecionarFiltroZonaCadastro(valor) {
  filtroZonaCadastro = ["todas", "ativas", "inativas"].includes(valor) ? valor : "todas";
  renderizarSelectZonaCadastro();
  renderizarZonas();
}

function selecionarZonaCadastro(zonaId) {
  const id = zonaId === "" ? null : Number(zonaId);
  zonaCadastroSelecionadaId = Number.isFinite(id) ? id : null;
  renderizarZonas();
}

async function carregarZonas() {
  try {
    const resposta = await fetch("/api/zonas");
    if (!resposta.ok) return;
    zonasCache = await resposta.json();
    renderizarSelectZonaPrincipal();
    renderizarSelectZonaCadastro();
    renderizarZonas();
    await carregarHistorico();
  } catch (erro) {
    console.error("Não foi possível carregar as zonas:", erro);
  }
}

function renderizarZonas() {
  const lista = document.getElementById("zonas-lista");
  const vazio = document.getElementById("zonas-vazio");

  lista.textContent = "";
  const zona = zonaCadastroSelecionada();
  vazio.classList.toggle("oculto", !!zona);
  vazio.textContent = zonasCache.length
    ? "Nenhuma zona encontrada para o filtro selecionado."
    : "Nenhuma zona cadastrada ainda.";

  if (zona) {
    lista.appendChild(construirCartaoZona(zona));
  }
}

function construirCartaoZona(zona) {
  const cartao = document.createElement("section");
  cartao.className = "painel zona-cartao";
  cartao.dataset.zonaId = zona.id;

  const cabecalho = document.createElement("div");
  cabecalho.className = "zona-cartao-cabecalho";

  const tituloGrupo = document.createElement("div");
  tituloGrupo.className = "zona-titulo-grupo";

  const nome = document.createElement("h3");
  nome.className = "zona-nome";
  nome.textContent = zona.nome;
  tituloGrupo.appendChild(nome);

  const badgeEspecie = document.createElement("span");
  badgeEspecie.className = "zona-badge";
  badgeEspecie.textContent = CONFIG_APP.nomeEspecie[zona.especie] || zona.especie;
  tituloGrupo.appendChild(badgeEspecie);

  if (!zona.ativa) {
    const badgeInativa = document.createElement("span");
    badgeInativa.className = "zona-badge zona-badge--inativa";
    badgeInativa.textContent = "INATIVA";
    tituloGrupo.appendChild(badgeInativa);
  }
  cabecalho.appendChild(tituloGrupo);

  const acoes = document.createElement("div");
  acoes.className = "zona-acoes";

  const btnEditar = document.createElement("button");
  btnEditar.type = "button";
  btnEditar.className = "botao botao--fantasma botao--compacto";
  btnEditar.textContent = "Editar";
  btnEditar.addEventListener("click", () => abrirDialogZona(zona));
  acoes.appendChild(btnEditar);

  const btnExcluir = document.createElement("button");
  btnExcluir.type = "button";
  btnExcluir.className = "botao botao--texto";
  btnExcluir.textContent = "Excluir";
  btnExcluir.addEventListener("click", () => excluirZona(zona));
  acoes.appendChild(btnExcluir);

  cabecalho.appendChild(acoes);
  cartao.appendChild(cabecalho);

  const grade = document.createElement("div");
  grade.className = "zona-equipamentos";
  ["sensor", "ventilador", "nebulizador"].forEach((tipo) => {
    grade.appendChild(construirGrupoEquipamento(zona, tipo));
  });
  cartao.appendChild(grade);

  return cartao;
}

function construirGrupoEquipamento(zona, tipo) {
  const grupo = document.createElement("div");
  grupo.className = "zona-equip-grupo";

  const equipamentosDoTipo = (zona.equipamentos || []).filter((e) => e.tipo === tipo);

  const titulo = document.createElement("div");
  titulo.className = "zona-equip-grupo-titulo";
  const rotulo = document.createElement("span");
  rotulo.textContent = ROTULOS_TIPO_EQUIPAMENTO[tipo] + " (" + equipamentosDoTipo.length + ")";
  titulo.appendChild(rotulo);

  const btnAdicionar = document.createElement("button");
  btnAdicionar.type = "button";
  btnAdicionar.className = "botao botao--texto";
  btnAdicionar.textContent = "+ adicionar";
  btnAdicionar.addEventListener("click", () => abrirDialogEquipamento(zona.id, null, tipo));
  titulo.appendChild(btnAdicionar);
  grupo.appendChild(titulo);

  const listaEquip = document.createElement("div");
  listaEquip.className = "zona-equip-lista";

  if (equipamentosDoTipo.length === 0) {
    const vazio = document.createElement("p");
    vazio.className = "zona-equip-vazio";
    vazio.textContent = "Nenhum cadastrado.";
    listaEquip.appendChild(vazio);
  } else {
    equipamentosDoTipo.forEach((equipamento) => {
      listaEquip.appendChild(construirItemEquipamento(zona.id, equipamento));
    });
  }
  grupo.appendChild(listaEquip);
  return grupo;
}

function resumoConexaoEquipamento(equipamento) {
  const partes = [];
  if (equipamento.modo_conexao === "tcp") {
    partes.push(equipamento.host + ":" + equipamento.porta);
  } else {
    partes.push(equipamento.porta_serial + " @ " + equipamento.baud_rate + "bps");
  }
  partes.push("id " + equipamento.unidade_id);
  partes.push(equipamento.tipo_registrador + "[" + equipamento.endereco_registrador + "]");
  if (equipamento.campo_medido) {
    const meta = CONFIG_APP.campoMetadados[equipamento.campo_medido];
    partes.push(meta ? meta.label : equipamento.campo_medido);
  }
  return partes.join(" · ");
}

function construirItemEquipamento(zonaId, equipamento) {
  const item = document.createElement("div");
  item.className = "zona-equip-item";

  const info = document.createElement("div");
  const nome = document.createElement("span");
  nome.className = "zona-equip-nome";
  nome.textContent = equipamento.nome;
  info.appendChild(nome);

  const conexao = document.createElement("span");
  conexao.className = "zona-equip-conexao";
  conexao.textContent = resumoConexaoEquipamento(equipamento);
  info.appendChild(conexao);
  item.appendChild(info);

  const acoes = document.createElement("div");
  acoes.className = "zona-equip-item-acoes";

  const btnEditar = document.createElement("button");
  btnEditar.type = "button";
  btnEditar.className = "botao botao--fantasma botao--compacto";
  btnEditar.textContent = "Editar";
  btnEditar.addEventListener("click", () => abrirDialogEquipamento(zonaId, equipamento));
  acoes.appendChild(btnEditar);

  const btnExcluir = document.createElement("button");
  btnExcluir.type = "button";
  btnExcluir.className = "botao botao--texto";
  btnExcluir.textContent = "Excluir";
  btnExcluir.addEventListener("click", () => excluirEquipamento(zonaId, equipamento));
  acoes.appendChild(btnExcluir);

  item.appendChild(acoes);
  return item;
}

// --- Dialog de zona ---------------------------------------------------------
function esconderErroDialog(id) {
  const el = document.getElementById(id);
  el.textContent = "";
  el.classList.add("oculto");
}

function mostrarErroDialog(id, mensagem) {
  const el = document.getElementById(id);
  el.textContent = mensagem;
  el.classList.remove("oculto");
}

function popularSelectEspecieZona() {
  const select = document.getElementById("zona-especie");
  select.textContent = "";
  Object.keys(CONFIG_APP.indicesPorEspecie).forEach((especie) => {
    const option = document.createElement("option");
    option.value = especie;
    option.textContent = CONFIG_APP.nomeEspecie[especie] || especie;
    select.appendChild(option);
  });
}

function atualizarSelectIndiceZona() {
  const especie = document.getElementById("zona-especie").value;
  const select = document.getElementById("zona-indice");
  const valorAtual = select.value;
  select.textContent = "";
  (CONFIG_APP.indicesPorEspecie[especie] || []).forEach((indice) => {
    const option = document.createElement("option");
    option.value = indice;
    option.textContent = CONFIG_APP.nomeIndice[indice] || indice;
    select.appendChild(option);
  });
  if ([...select.options].some((o) => o.value === valorAtual)) {
    select.value = valorAtual;
  }
}

function abrirDialogZona(zona = null) {
  zonaEmEdicaoId = zona ? zona.id : null;
  document.getElementById("dialog-zona-titulo").textContent = zona ? "Editar zona" : "Nova zona";
  popularSelectEspecieZona();

  document.getElementById("zona-nome").value = zona ? zona.nome : "";
  document.getElementById("zona-especie").value = zona
    ? zona.especie
    : Object.keys(CONFIG_APP.indicesPorEspecie)[0];
  atualizarSelectIndiceZona();
  if (zona) document.getElementById("zona-indice").value = zona.indice;
  document.getElementById("zona-ativa").checked = zona ? zona.ativa : true;
  esconderErroDialog("zona-form-erro");

  document.getElementById("dialog-zona").showModal();
}

async function salvarZona(evento) {
  evento.preventDefault();
  const payload = {
    nome: document.getElementById("zona-nome").value.trim(),
    especie: document.getElementById("zona-especie").value,
    indice: document.getElementById("zona-indice").value,
    ativa: document.getElementById("zona-ativa").checked,
  };
  const url = zonaEmEdicaoId ? "/api/zonas/" + zonaEmEdicaoId : "/api/zonas";
  const metodo = zonaEmEdicaoId ? "PUT" : "POST";

  try {
    const resposta = await fetch(url, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrarErroDialog("zona-form-erro", dados.erro || "Não foi possível salvar a zona.");
      return;
    }
    zonaCadastroSelecionadaId = dados.id;
    if (dados.ativa) estado.zonaId = dados.id;
    document.getElementById("dialog-zona").close();
    await carregarZonas();
  } catch (erro) {
    mostrarErroDialog("zona-form-erro", "Falha de comunicação com o servidor.");
  }
}

async function excluirZona(zona) {
  const confirmado = confirm(
    'Excluir a zona "' + zona.nome + '"? Os equipamentos cadastrados nela também ' +
    "serão removidos. O histórico já gravado é mantido."
  );
  if (!confirmado) return;
  try {
    await fetch("/api/zonas/" + zona.id, { method: "DELETE" });
    if (zonaCadastroSelecionadaId === zona.id) zonaCadastroSelecionadaId = null;
    if (estado.zonaId === zona.id) estado.zonaId = null;
    await carregarZonas();
  } catch (erro) {
    console.error("Falha ao excluir zona:", erro);
  }
}

// --- Dialog de equipamento ---------------------------------------------------
function popularSelectCampoMedido() {
  const select = document.getElementById("equip-campo-medido");
  select.textContent = "";
  Object.entries(CONFIG_APP.campoMetadados).forEach(([campo, meta]) => {
    const option = document.createElement("option");
    option.value = campo;
    option.textContent = meta.label + " (" + campo + ")";
    select.appendChild(option);
  });
}

function popularSelectTipoRegistrador(tipo) {
  const select = document.getElementById("equip-tipo-registrador");
  const valorAtual = select.value;
  select.textContent = "";
  const opcoes =
    tipo === "sensor"
      ? [["holding", "Holding register"], ["input", "Input register"]]
      : [["holding", "Holding register"], ["coil", "Coil"]];
  opcoes.forEach(([valor, texto]) => {
    const option = document.createElement("option");
    option.value = valor;
    option.textContent = texto;
    select.appendChild(option);
  });
  if (opcoes.some(([v]) => v === valorAtual)) select.value = valorAtual;
}

function atualizarCamposDialogEquipamento() {
  const tipo = document.getElementById("equip-tipo").value;
  const modoConexao = document.getElementById("equip-modo-conexao").value;
  const ehSensor = tipo === "sensor";

  document.getElementById("wrap-equip-campo-medido").classList.toggle("oculto", !ehSensor);
  document.getElementById("wrap-equip-tipo-dado").classList.toggle("oculto", !ehSensor);
  document.getElementById("wrap-equip-fator-escala").classList.toggle("oculto", !ehSensor);

  document.getElementById("wrap-equip-host").classList.toggle("oculto", modoConexao !== "tcp");
  document.getElementById("wrap-equip-porta").classList.toggle("oculto", modoConexao !== "tcp");
  document
    .getElementById("wrap-equip-porta-serial")
    .classList.toggle("oculto", modoConexao !== "rtu");
  document.getElementById("wrap-equip-baud-rate").classList.toggle("oculto", modoConexao !== "rtu");

  popularSelectTipoRegistrador(tipo);
}

function abrirDialogEquipamento(zonaId, equipamento = null, tipoSugerido = "sensor") {
  equipamentoEmEdicao = { zonaId, equipamentoId: equipamento ? equipamento.id : null };
  document.getElementById("dialog-equipamento-titulo").textContent = equipamento
    ? "Editar equipamento"
    : "Novo equipamento";
  popularSelectCampoMedido();

  document.getElementById("equip-tipo").value = equipamento ? equipamento.tipo : tipoSugerido;
  document.getElementById("equip-nome").value = equipamento ? equipamento.nome : "";
  document.getElementById("equip-modo-conexao").value = equipamento
    ? equipamento.modo_conexao
    : "tcp";
  atualizarCamposDialogEquipamento();

  document.getElementById("equip-host").value = equipamento?.host || "";
  document.getElementById("equip-porta").value = equipamento?.porta || 502;
  document.getElementById("equip-porta-serial").value = equipamento?.porta_serial || "";
  document.getElementById("equip-baud-rate").value = equipamento?.baud_rate || 9600;
  document.getElementById("equip-unidade-id").value = equipamento?.unidade_id || 1;
  document.getElementById("equip-endereco-registrador").value =
    equipamento?.endereco_registrador ?? 0;
  document.getElementById("equip-tipo-dado").value = equipamento?.tipo_dado || "int16";
  document.getElementById("equip-fator-escala").value = equipamento?.fator_escala ?? 1;
  if (equipamento?.tipo_registrador) {
    document.getElementById("equip-tipo-registrador").value = equipamento.tipo_registrador;
  }
  if (equipamento?.campo_medido) {
    document.getElementById("equip-campo-medido").value = equipamento.campo_medido;
  }

  esconderErroDialog("equipamento-form-erro");
  const resultadoTeste = document.getElementById("equipamento-teste-resultado");
  resultadoTeste.textContent = "";
  resultadoTeste.classList.add("oculto");

  document.getElementById("dialog-equipamento").showModal();
}

function coletarPayloadEquipamento() {
  const tipo = document.getElementById("equip-tipo").value;
  const modoConexao = document.getElementById("equip-modo-conexao").value;
  return {
    tipo,
    nome: document.getElementById("equip-nome").value.trim(),
    modo_conexao: modoConexao,
    host: modoConexao === "tcp" ? document.getElementById("equip-host").value.trim() : null,
    porta: modoConexao === "tcp" ? Number(document.getElementById("equip-porta").value) : null,
    porta_serial:
      modoConexao === "rtu" ? document.getElementById("equip-porta-serial").value.trim() : null,
    baud_rate:
      modoConexao === "rtu" ? Number(document.getElementById("equip-baud-rate").value) : null,
    unidade_id: Number(document.getElementById("equip-unidade-id").value),
    tipo_registrador: document.getElementById("equip-tipo-registrador").value,
    endereco_registrador: Number(document.getElementById("equip-endereco-registrador").value),
    tipo_dado: document.getElementById("equip-tipo-dado").value,
    fator_escala: Number(document.getElementById("equip-fator-escala").value),
    campo_medido: tipo === "sensor" ? document.getElementById("equip-campo-medido").value : null,
  };
}

async function salvarEquipamento(evento) {
  evento.preventDefault();
  const { zonaId, equipamentoId } = equipamentoEmEdicao;
  const payload = coletarPayloadEquipamento();
  const url = equipamentoId
    ? "/api/zonas/" + zonaId + "/equipamentos/" + equipamentoId
    : "/api/zonas/" + zonaId + "/equipamentos";
  const metodo = equipamentoId ? "PUT" : "POST";

  try {
    const resposta = await fetch(url, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const dados = await resposta.json();
    if (!resposta.ok) {
      mostrarErroDialog("equipamento-form-erro", dados.erro || "Não foi possível salvar o equipamento.");
      return;
    }
    document.getElementById("dialog-equipamento").close();
    await carregarZonas();
  } catch (erro) {
    mostrarErroDialog("equipamento-form-erro", "Falha de comunicação com o servidor.");
  }
}

async function excluirEquipamento(zonaId, equipamento) {
  if (!confirm('Excluir o equipamento "' + equipamento.nome + '"?')) return;
  try {
    await fetch("/api/zonas/" + zonaId + "/equipamentos/" + equipamento.id, { method: "DELETE" });
    await carregarZonas();
  } catch (erro) {
    console.error("Falha ao excluir equipamento:", erro);
  }
}

async function testarConexaoEquipamentoAtual() {
  const { zonaId, equipamentoId } = equipamentoEmEdicao;
  const resultado = document.getElementById("equipamento-teste-resultado");
  if (!equipamentoId) {
    resultado.textContent = "Salve o equipamento primeiro para poder testar a conexão.";
    resultado.classList.remove("oculto");
    return;
  }
  resultado.textContent = "Testando conexão...";
  resultado.classList.remove("oculto");
  try {
    const resposta = await fetch(
      "/api/zonas/" + zonaId + "/equipamentos/" + equipamentoId + "/testar-conexao",
      { method: "POST" }
    );
    const dados = await resposta.json();
    resultado.textContent = dados.conectado
      ? "Conexão bem-sucedida."
      : dados.aviso || "Não foi possível conectar a este equipamento.";
    if (dados.aviso) {
      const banner = document.getElementById("zonas-aviso-pymodbus");
      banner.textContent = dados.aviso;
      banner.classList.remove("oculto");
    }
  } catch (erro) {
    resultado.textContent = "Falha de comunicação com o servidor.";
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
  atualizarEquipamento(null, null);
  atualizarSensorRemoto();
  await carregarZonas();

  document.getElementById("btn-calcular").addEventListener("click", calcular);
  document.getElementById("btn-limpar").addEventListener("click", limparHistorico);
  document.getElementById("zona-principal")?.addEventListener("change", (evento) => {
    selecionarZonaPrincipal(evento.target.value);
  });
  document.getElementById("zona-cadastro")?.addEventListener("change", (evento) => {
    selecionarZonaCadastro(evento.target.value);
  });
  document.getElementById("filtro-zona-cadastro")?.addEventListener("change", (evento) => {
    selecionarFiltroZonaCadastro(evento.target.value);
  });

  document.getElementById("cfg-coletar").addEventListener("change", (e) => {
    atualizarSensorRemoto();
  });
  document.getElementById("cfg-emails").addEventListener("change", (e) => {
    document.getElementById("wrap-email-destino").classList.toggle("oculto", !e.target.checked);
  });
  document.getElementById("cfg-auto").addEventListener("change", (e) => {
    if (e.target.checked) {
      document.getElementById("cfg-coletar").checked = true;
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
    renderCamposEntrada();
    atualizarCamposCalculados();
  });
  document.getElementById("cfg-umidade-relativa").addEventListener("change", () => {
    renderCamposEntrada();
    atualizarCamposCalculados();
  });
  document.getElementById("cfg-altitude").addEventListener("input", atualizarCamposCalculados);
  document.getElementById("cfg-smtp-host")?.addEventListener("input", refletirStatusSmtp);
  document.getElementById("cfg-smtp-senha")?.addEventListener("input", refletirStatusSmtp);
  document.querySelectorAll("#aba-configuracoes input, #aba-configuracoes select").forEach((controle) => {
    controle.addEventListener("change", agendarSalvarConfiguracoes);
    if (["number", "email"].includes(controle.type)) {
      controle.addEventListener("input", agendarSalvarConfiguracoes);
    }
  });
  if (document.getElementById("cfg-auto").checked) {
    alternarModoAutomatico(true);
  }

  document.getElementById("btn-nova-zona").addEventListener("click", () => abrirDialogZona());
  document.getElementById("btn-cancelar-zona").addEventListener("click", () => {
    document.getElementById("dialog-zona").close();
  });
  document.getElementById("form-zona").addEventListener("submit", salvarZona);
  document.getElementById("zona-especie").addEventListener("change", atualizarSelectIndiceZona);

  document.getElementById("btn-cancelar-equipamento").addEventListener("click", () => {
    document.getElementById("dialog-equipamento").close();
  });
  document.getElementById("form-equipamento").addEventListener("submit", salvarEquipamento);
  document
    .getElementById("equip-tipo")
    .addEventListener("change", atualizarCamposDialogEquipamento);
  document
    .getElementById("equip-modo-conexao")
    .addEventListener("change", atualizarCamposDialogEquipamento);
  document
    .getElementById("btn-testar-conexao-equipamento")
    .addEventListener("click", testarConexaoEquipamentoAtual);

  document.getElementById("cfg-zonas-simulado").addEventListener("change", agendarSalvarConfiguracoes);
});
