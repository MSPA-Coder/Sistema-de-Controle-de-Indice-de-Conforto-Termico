// =============================================================================
// Front-end do sistema de conforto termico
// =============================================================================

const TOKEN_CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";
const FETCH_NATIVO = window.fetch.bind(window);
const METODOS_HTTP_SEGUROS = new Set(["GET", "HEAD", "OPTIONS"]);

// Todas as mutações da interface usam fetch relativo ao mesmo host. Centralizar
// o cabeçalho aqui evita depender de cada tela lembrar da proteção CSRF.
window.fetch = function fetchComCsrf(entrada, opcoes = {}) {
  const metodo = String(
    opcoes.method || (entrada instanceof Request ? entrada.method : "GET")
  ).toUpperCase();
  if (TOKEN_CSRF && !METODOS_HTTP_SEGUROS.has(metodo)) {
    const headers = new Headers(
      entrada instanceof Request ? entrada.headers : undefined
    );
    new Headers(opcoes.headers || {}).forEach((valor, chave) => {
      headers.set(chave, valor);
    });
    headers.set("X-CSRF-Token", TOKEN_CSRF);
    opcoes = { ...opcoes, headers };
  }
  return FETCH_NATIVO(entrada, opcoes);
};

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
const ROTULO_TIPO_VALOR_HISTORICO = { minimo: "Mínimo", medio: "Médio", maximo: "Máximo" };
const CORES_CAMPOS_ENTRADA = ["#4F8A93", "#D9A441", "#8FBF9F", "#C1443C", "#9E7BB5", "#6FA8DC"];
const HISTORICO_LINHAS_POR_PAGINA = 20;
const HISTORICO_JANELA_LEITURAS = 30;
const ORDEM_CAMPOS_INTERFACE = ["tbs", "tbu", "tgn", "tpo", "ur", "v"];

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

let graficoEntradas = null;
let graficosHistoricoPorIndice = new Map();
let graficoHistoricoEntradas = null;
let assinaturaGraficosHistorico = "";
let graficosIndicePrincipalPorZona = new Map();
let assinaturasIndicePrincipalPorZona = new Map();
let ultimosResultados = null;
let ultimosHistoricosGrafico = {};
let historicoLeiturasJanela = [];
let historicoLeiturasBase = [];
let historicoLeiturasAtuais = [];
let historicoPaginaAtual = 1;
let historicoTotalLeituras = 0;
let historicoDeslocamento = 0;
let filtroHistoricoIndice = "";
let filtroHistoricoStatus = "";
let filtroHistoricoZona = "";
let filtroHistoricoValorReferencia = null;
let filtroHistoricoValorTipo = "";
let filtroHistoricoValoresEncontrados = [];
let filtroHistoricoDataInicio = null;
let filtroHistoricoDataFim = null;
let historicoMinimosFiltro = { indices: {}, entradas: {} };
let historicoMaximosFiltro = { indices: {}, entradas: {} };
let historicoLeituraSelecionadaId = null;
let historicoCarregamentoId = 0;
let salvamentoConfigTimeoutId = null;
let historicoScrollTimeoutId = null;

// Grafico de tendencia por resolucao (aba Historico): a mesma zona pode ser
// vista em 3 granularidades -- leitura bruta (1-5 min), agregado de 15 min
// e resumo horario. "bruto" usa a mesma rota GET /api/zonas/<id>/historico
// ja existente; as outras duas consomem as rotas novas de agregacao.
const RESOLUCOES_TENDENCIA = [
  { valor: "bruto", texto: "Tempo real (leitura bruta)" },
  { valor: "15min", texto: "Agregado de 15 em 15 min" },
  { valor: "hora", texto: "Resumo por hora" },
];
let resolucaoTendencia = "bruto";
let graficoTendenciaResolucao = null;
let tendenciaResolucaoCarregamentoId = 0;
let paineisExecutivosCache = [];
let smtpSenhaJaConfigurada = false;
let audioCtx = null;
let ultimoStatusPorZona = new Map();
let ultimasEntradasPorZona = new Map();

function indicesDaEspecie() {
  return estado.indice ? [estado.indice] : [];
}

function camposDaEspecie() {
  const campos = camposDoIndiceAtual();
  return ordenarCamposInterface(campos);
}

function ordenarCamposInterface(campos) {
  return [...campos].sort((a, b) => {
    const ordemA = ORDEM_CAMPOS_INTERFACE.includes(a) ? ORDEM_CAMPOS_INTERFACE.indexOf(a) : 999;
    const ordemB = ORDEM_CAMPOS_INTERFACE.includes(b) ? ORDEM_CAMPOS_INTERFACE.indexOf(b) : 999;
    return ordemA - ordemB || a.localeCompare(b);
  });
}

function adicionarCampoSeAusente(campos, campo) {
  if (!campos.includes(campo)) campos.push(campo);
}

function camposObrigatoriosIndiceAtual() {
  return [...(CONFIG_APP.camposPorIndice[estado.indice] || [])];
}

function camposDerivadosIndiceAtual() {
  const camposObrigatorios = camposObrigatoriosIndiceAtual();
  const derivados = [];
  const indiceTemBulbos = camposObrigatorios.includes("tbs") && camposObrigatorios.includes("tbu");

  if (indiceTemBulbos) {
    adicionarCampoSeAusente(derivados, "ur");
    adicionarCampoSeAusente(derivados, "tpo");
  }

  return ordenarCamposInterface(derivados.filter((campo) => !camposObrigatorios.includes(campo)));
}

function camposEntradaIndiceAtual() {
  return [...camposObrigatoriosIndiceAtual(), ...camposDerivadosIndiceAtual()];
}

function campoCalculado(campo) {
  return camposDerivadosIndiceAtual().includes(campo);
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

// ---------------------------------------------------------------------------
// Campos de entrada dinamicos
// ---------------------------------------------------------------------------
function renderCamposEntrada() {
  const container = document.getElementById("campos-entrada");
  if (!container) return;
  container.innerHTML = "";
  if (!zonaPrincipalSelecionada()) return;
  const campos = camposEntradaIndiceAtual();
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

function renderCamposEntradaDashboard(entradas, zona = zonaPrincipalSelecionada()) {
  const container = document.getElementById("campos-entrada-dashboard");
  if (!container) return;
  container.textContent = "";

  if (!zona) {
    container.textContent = "Nenhuma zona ativa selecionada.";
    return;
  }

  const dados = entradas || {};
  const camposEsperados = CONFIG_APP.camposPorIndice[zona.indice] || [];
  const campos = ordenarCamposInterface(
    [...new Set([...camposEsperados, ...Object.keys(dados)])]
  );
  campos.forEach((campo) => {
    const meta = CONFIG_APP.campoMetadados[campo] || {
      label: campo,
      unidade: "",
    };
    const wrap = document.createElement("div");
    wrap.className = "campo-entrada";

    const label = document.createElement("span");
    label.className = "campo-entrada-rotulo";
    label.textContent = meta.label + (meta.unidade ? " (" + meta.unidade + ")" : "");
    label.style.color = corCampoEntrada(campo);

    const valor = document.createElement("output");
    valor.className = "campo-entrada-valor";
    valor.textContent =
      dados[campo] === undefined || dados[campo] === null
        ? "--"
        : String(dados[campo]).replace(".", ",");

    wrap.append(label, valor);
    container.appendChild(wrap);
  });
}

function camposDoIndiceAtual() {
  return camposEntradaIndiceAtual();
}

function atualizarCamposEntrada() {
  const camposAtivos = camposEntradaIndiceAtual();
  camposEntradaIndiceAtual().forEach((campo) => {
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
    campoCalculado("ur") &&
    !(preservarValoresExistentes && urInput.value !== "")
  ) {
    urInput.value = podeCalcular ? calcularUmidadeRelativa(tbs, tbu, altitude).toFixed(1) : "";
  }

  if (
    tpoInput &&
    campoCalculado("tpo") &&
    !(preservarValoresExistentes && tpoInput.value !== "")
  ) {
    tpoInput.value = podeCalcular ? calcularPontoOrvalho(tbs, tbu, altitude).toFixed(1) : "";
  }
}

function coletarEntradas(incluirDesabilitados = false) {
  const campos = camposEntradaIndiceAtual();
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

function coletarConfig() {
  return {
    coletarDados: document.getElementById("cfg-coletar").checked,
    habilitarSons: document.getElementById("cfg-sons").checked,
    enviarEmails: document.getElementById("cfg-emails").checked,
    habilitarEquipamentos: document.getElementById("cfg-equipamentos").checked,
    emailDestino: document.getElementById("email-destino").value,
    statusMinimoEmail: document.getElementById("cfg-status-minimo-email")?.value || "conforto",
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
    // coletor.rotas._configuracoes_publicas), entao so enviamos algo aqui quando o
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
  definirValorConfiguracao("cfg-status-minimo-email", config.statusMinimoEmail);
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
  const usarSensores = document.getElementById("cfg-coletar").checked;

  let dados;
  try {
    let resposta;
    resposta = await fetch("/api/zonas/" + zona.id + "/calcular", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        usarSensores
          ? {}
          : { entradas: coletarEntradas(!!opcoes.incluirCamposDesabilitados) }
      ),
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
      atualizarErroLinhaZonaPrincipal(zona, corpo.erro || "Não foi possível calcular. Confira os dados informados.");
      mostrarErro(corpo.erro || "Não foi possível calcular. Confira os dados informados.");
      return;
    }
    dados = corpo;
  } catch (erro) {
    // Esta captura e exclusivamente para falhas de rede (fetch nao completou,
    // ou a resposta nao era JSON valido) - nunca para erros ocorridos depois,
    // ao atualizar a tela.
    console.error("Erro de comunicacao ao calcular zonas:", erro);
    mostrarErro(
      erro && erro.message && erro.message.includes("Flask")
        ? erro.message
        : "Falha de comunicação com o ICT. Verifique os contêineres com docker compose ps."
    );
    return;
  }

  // A requisicao foi concluida com sucesso. Qualquer erro a partir daqui e de
  // atualizacao da tela (ex.: graficos), nao de comunicacao - tratado a parte
  // dentro de atualizarResultado(), para nunca ser confundido com o caso acima.
  atualizarResultado(dados);
}

async function carregarHistorico(opcoes = {}) {
  const zona = zonaPrincipalSelecionada();
  const zonasPrincipal = zonasOrdenadasPrincipal();
  if (!zonasPrincipal.length) {
    ultimosHistoricosGrafico = {};
    destruirGraficosZonasPrincipal();
    if (graficoEntradas) {
      graficoEntradas.destroy();
      graficoEntradas = null;
    }
    if (!opcoes.somenteTempoReal) {
      await carregarHistoricoPersistido({ manterJanelaFinal: true });
    }
    return;
  }
  try {
    const historicos = new Map();
    await Promise.all(
      zonasPrincipal.map(async (zonaItem) => {
        const resposta = await fetch("/api/zonas/" + zonaItem.id + "/historico");
        if (!resposta.ok) return;
        const historico = await resposta.json();
        historicos.set(zonaItem.id, historico);
        atualizarLinhaComHistoricoZonaPrincipal(zonaItem, historico);
        atualizarGraficoIndiceZonaPrincipal(zonaItem, historico);
      })
    );

    if (zona) {
      const historicoSelecionado = historicos.get(zona.id) || [];
      ultimosHistoricosGrafico = { [zona.indice]: historicoSelecionado };
      atualizarGraficoEntradas(ultimosHistoricosGrafico);
    } else {
      ultimosHistoricosGrafico = {};
    }
    if (!opcoes.somenteTempoReal) {
      await carregarHistoricoPersistido({ manterJanelaFinal: true });
    }
  } catch (erro) {
    /* nao critico */
  }
}

async function limparHistorico() {
  const confirmado = window.confirm(
    "Limpar histórico?\n\n" +
    "Esta ação apaga todas as leituras salvas no banco e limpa os gráficos/tabelas do histórico nesta sessão. " +
    "Zonas, equipamentos e configurações serão preservados. A ação não pode ser desfeita; faça um backup antes se precisar guardar os dados."
  );
  if (!confirmado) return;

  try {
    const resposta = await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const corpo = await resposta.json().catch(() => ({}));
    if (!resposta.ok || !corpo.ok) {
      mostrarErro(corpo.erro || "Não foi possível limpar o histórico.");
      return;
    }
    resetarPainelResultado();
    await carregarHistorico();
    atualizarStatusBanco("Histórico limpo. Zonas, equipamentos e configurações foram preservados.");
  } catch (erro) {
    console.error("Erro ao limpar historico:", erro);
    mostrarErro("Falha de comunicação ao limpar o histórico.");
  }
}

function atualizarStatusBanco(mensagem) {
  const status = document.getElementById("banco-status");
  if (!status) return;
  status.textContent = mensagem;
  status.classList.remove("oculto");
}

async function fazerBackupBanco() {
  const botao = document.getElementById("btn-backup-banco");
  if (botao) botao.disabled = true;
  try {
    const resposta = await fetch("/api/backup-banco", { method: "POST" });
    const corpo = await resposta.json().catch(() => ({}));
    if (!resposta.ok || !corpo.ok) {
      atualizarStatusBanco(corpo.erro || "Não foi possível criar o backup do banco.");
      return;
    }
    atualizarStatusBanco("Backup criado no diretório do banco: " + corpo.backup.arquivo);
  } catch (erro) {
    console.error("Erro ao criar backup do banco:", erro);
    atualizarStatusBanco("Falha de comunicação ao criar o backup do banco.");
  } finally {
    if (botao) botao.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Atualizacao da interface
// ---------------------------------------------------------------------------

// NOTA DE SEGURANCA: `resultado.mensagem` e o texto de aviso sao recebidos
// da resposta JSON do servidor. Mesmo sendo valores controlados pelo backend,
// esta funcao monta os elementos via DOM real com `textContent`, sem
// interpretar conteudo como HTML.
function definirMensagemOrientacao(mensagem, aviso, container) {
  if (!container) return;
  container.textContent = "";
  container.appendChild(document.createTextNode(mensagem));

  if (aviso) {
    container.appendChild(document.createElement("br"));
    const em = document.createElement("em");
    em.textContent = aviso;
    container.appendChild(em);
  }
}

function resetarLinhaZonaPrincipal(zona) {
  const linha = linhaZonaPrincipal(zona.id);
  if (!linha) return;

  const readoutValor = elementoLinhaZonaPrincipal(zona.id, "readout-valor");
  if (readoutValor) {
    readoutValor.textContent = "--,--";
    readoutValor.className = "readout-valor";
  }
  const readoutIndice = elementoLinhaZonaPrincipal(zona.id, "readout-indice");
  if (readoutIndice) readoutIndice.textContent = zona.indice;

  const faixa = elementoLinhaZonaPrincipal(zona.id, "faixa-status");
  const faixaTexto = elementoLinhaZonaPrincipal(zona.id, "faixa-status-texto");
  if (faixa) faixa.className = "faixa-status faixa-status--vazio";
  if (faixaTexto) faixaTexto.textContent = zona.ativa ? "AGUARDANDO CALCULO" : "ZONA INATIVA";

  const mensagem = elementoLinhaZonaPrincipal(zona.id, "mensagem-orientacao");
  if (mensagem) {
    mensagem.textContent = zona.ativa
      ? "Aguardando leitura desta zona."
      : "Zona inativa. O historico permanece disponivel, mas ela nao entra no monitoramento automatico.";
  }

  atualizarEquipamento(null, null, zona);
  atualizarSensorRemotoZona(zona);
}

function resetarPainelResultado() {
  ultimosResultados = null;
  zonasOrdenadasPrincipal().forEach((zona) => resetarLinhaZonaPrincipal(zona));
  atualizarEmail(null);
  renderCamposEntradaDashboard(null);
  esconderErro();
}

function atualizarErroLinhaZonaPrincipal(zona, mensagemErro) {
  if (!zona) return;
  const faixa = elementoLinhaZonaPrincipal(zona.id, "faixa-status");
  const faixaTexto = elementoLinhaZonaPrincipal(zona.id, "faixa-status-texto");
  if (faixa) faixa.className = "faixa-status faixa-status--vazio";
  if (faixaTexto) faixaTexto.textContent = "SEM LEITURA";
  const mensagem = elementoLinhaZonaPrincipal(zona.id, "mensagem-orientacao");
  if (mensagem) mensagem.textContent = mensagemErro || "Não foi possível calcular esta zona.";
  atualizarEquipamento(null, null, zona);
}

function atualizarLinhaComHistoricoZonaPrincipal(zona, historico) {
  if (!zona || !Array.isArray(historico) || !historico.length) return;
  const ultima = historico[historico.length - 1];
  ultimoStatusPorZona.set(zona.id, ultima.status);
  ultimasEntradasPorZona.set(zona.id, ultima.entradas || {});
  const classe = classeStatus(ultima.status);

  const readoutValor = elementoLinhaZonaPrincipal(zona.id, "readout-valor");
  if (readoutValor) {
    readoutValor.textContent = Number(ultima.valor).toFixed(2).replace(".", ",");
    readoutValor.className = "readout-valor cor-" + classe;
  }
  const readoutIndice = elementoLinhaZonaPrincipal(zona.id, "readout-indice");
  if (readoutIndice) readoutIndice.textContent = ultima.indice || zona.indice;

  const faixa = elementoLinhaZonaPrincipal(zona.id, "faixa-status");
  const faixaTexto = elementoLinhaZonaPrincipal(zona.id, "faixa-status-texto");
  if (faixa) faixa.className = "faixa-status faixa-" + classe;
  if (faixaTexto) faixaTexto.textContent = String(ultima.status || "").toUpperCase();

  const mensagem = elementoLinhaZonaPrincipal(zona.id, "mensagem-orientacao");
  if (mensagem) mensagem.textContent = "Ultima leitura registrada as " + formatarHora(ultima.criado_em) + ".";
  atualizarEquipamentoDoEstadoOperacional(zona, ultima.status);
  if (zona.id === estado.zonaId) {
    renderCamposEntradaDashboard(ultima.entradas, zona);
    const modo = estadoOperacionalCache?.zonas?.find(
      (item) => item.zona_id === Number(zona.id)
    )?.modo;
    if (modo === "automatico") {
      preencherEntradasDoResultado({ entradas: ultima.entradas || {} });
    }
    const zonaEstado = estadoOperacionalCache?.zonas?.find(
      (item) => item.zona_id === Number(zona.id)
    );
    renderizarEquipamentosOperacao(zona, zonaEstado);
  }
}

function atualizarResultado(dados) {
  const zona = zonaPorId(dados.zona_id) || zonaPrincipalSelecionada();
  if (!zona) return;
  const zonaSelecionada = zona.id === estado.zonaId;
  if (zonaSelecionada) {
    estado.especie = dados.especie || zona.especie || estado.especie;
    estado.indice = dados.indice || zona.indice || estado.indice;
    preencherEntradasDoResultado(dados);
    renderCamposEntradaDashboard(dados.entradas, zona);
    ultimosResultados = { [estado.indice]: dados };
  }
  const selecionado = dados;
  ultimoStatusPorZona.set(zona.id, selecionado.status);
  const classe = classeStatus(selecionado.status);

  // 1) Elementos essenciais primeiro - nunca dependem de bibliotecas externas,
  //    entao sempre devem atualizar mesmo se algo mais adiante falhar.
  const readoutValor = elementoLinhaZonaPrincipal(zona.id, "readout-valor");
  if (readoutValor) {
    readoutValor.textContent = selecionado.valor.toFixed(2).replace(".", ",");
    readoutValor.className = "readout-valor cor-" + classe;
  }
  const readoutIndice = elementoLinhaZonaPrincipal(zona.id, "readout-indice");
  if (readoutIndice) readoutIndice.textContent = selecionado.indice || zona.indice;

  const faixa = elementoLinhaZonaPrincipal(zona.id, "faixa-status");
  if (faixa) faixa.className = "faixa-status faixa-" + classe;
  const faixaTexto = elementoLinhaZonaPrincipal(zona.id, "faixa-status-texto");
  if (faixaTexto) faixaTexto.textContent = selecionado.status.toUpperCase();

  definirMensagemOrientacao(
    selecionado.mensagem,
    dados.aviso,
    elementoLinhaZonaPrincipal(zona.id, "mensagem-orientacao")
  );

  atualizarEquipamento(dados.equipamento, selecionado.status, zona);
  if (zonaSelecionada) atualizarEmail(dados.email);

  // 2) Graficos e tabela: isolados em try/catch proprios. Se a biblioteca de
  //    graficos nao carregar por qualquer motivo, o restante do painel acima
  //    ja esta atualizado e continua funcionando normalmente.
  try {
    const historicoZona = selecionado.historico_grafico || [];
    atualizarGraficoIndiceZonaPrincipal(zona, historicoZona);
    if (zonaSelecionada) {
      ultimosHistoricosGrafico = { [zona.indice]: historicoZona };
      atualizarGraficoEntradas(ultimosHistoricosGrafico);
    }
  } catch (erro) {
    console.error("Erro ao desenhar os graficos:", erro);
    mostrarErro(
      "O valor foi calculado normalmente (" + selecionado.valor.toFixed(2).replace(".", ",") +
      ", " + selecionado.status + "), mas os gráficos não puderam ser desenhados. " +
      "Detalhes no console do navegador (F12 → Console)."
    );
  }

  carregarHistoricoPersistido({ manterJanelaFinal: true });

  if (zonaSelecionada && dados.tocarSom && selecionado.status !== "Conforto") {
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
  const container = typeof containerId === "string" ? document.getElementById(containerId) : containerId;
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

function atualizarEquipamento(equip, status, zona = zonaPrincipalSelecionada()) {
  const ventiladorLigado = !!(equip && equip.ventilador);
  const nebulizadorLigado = !!(equip && equip.nebulizador);
  const intensidade = (equip && equip.intensidade) || null;
  const totalVentiladores = equipamentosDaZona(zona, "ventilador").length * ICONES_POR_EQUIPAMENTO_ATUADOR;
  const totalNebulizadores = equipamentosDaZona(zona, "nebulizador").length * ICONES_POR_EQUIPAMENTO_ATUADOR;

  renderizarIconesEquipamento(
    elementoLinhaZonaPrincipal(zona?.id, "icones-ventilador"),
    ICONE_VENTILADOR,
    "Ventilador",
    ventiladorLigado,
    intensidade,
    status,
    totalVentiladores,
    ventiladorLigado ? totalVentiladores : 0
  );
  renderizarIconesEquipamento(
    elementoLinhaZonaPrincipal(zona?.id, "icones-nebulizador"),
    ICONE_NEBULIZADOR,
    "Nebulizador",
    nebulizadorLigado,
    intensidade,
    status,
    totalNebulizadores,
    nebulizadorLigado ? totalNebulizadores : 0
  );

  const intensidadeValor = elementoLinhaZonaPrincipal(zona?.id, "intensidade-valor");
  if (intensidadeValor) {
    intensidadeValor.textContent = intensidade ? rotuloIntensidade(intensidade) : "desligado";
  }
}

function atualizarEquipamentoDoEstadoOperacional(zona, status = null) {
  if (!zona || !estadoOperacionalCache) return;
  const estadoZona = (estadoOperacionalCache.zonas || []).find(
    (item) => item.zona_id === Number(zona.id)
  );
  if (!estadoZona) return;
  atualizarEquipamento(
    {
      ventilador: estadoZona.confirmado?.ventilador === true,
      nebulizador: estadoZona.confirmado?.nebulizador === true,
      intensidade: estadoZona.intensidade,
    },
    status || ultimoStatusPorZona.get(zona.id) || null,
    zona
  );
}

function atualizarSensorRemotoZona(zona) {
  const checkboxColeta = document.getElementById("cfg-coletar");
  const sensorLigado = !!(checkboxColeta && checkboxColeta.checked && zona && zona.ativa);

  renderizarIconesEquipamento(
    elementoLinhaZonaPrincipal(zona?.id, "icones-sensor"),
    ICONE_SENSOR,
    "Sensor",
    sensorLigado,
    null,
    null,
    equipamentosDaZona(zona, "sensor").length * ICONES_POR_SENSOR,
    sensorLigado ? equipamentosDaZona(zona, "sensor").length * ICONES_POR_SENSOR : 0
  );
}

function atualizarSensorRemoto() {
  zonasOrdenadasPrincipal().forEach((zona) => atualizarSensorRemotoZona(zona));
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

function formatarDataHoraCurta(isoString) {
  const data = new Date(isoString);
  return data.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) +
    " " +
    data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function formatarDataCurta(isoString) {
  return new Date(isoString).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
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
      x: {
        ticks: { display: false, color: "#A79C8C", font: { size: 10 } },
        grid: { color: "rgba(255,255,255,0.05)" },
      },
      y: {
        beginAtZero: false,
        ticks: { color: "#A79C8C", font: { size: 10 }, precision: 0 },
        grid: { color: "rgba(255,255,255,0.05)" },
      },
    },
  };
  if (comEixoSecundario) {
    opcoes.scales.y1 = {
      position: "right",
      beginAtZero: false,
      ticks: { color: "#A79C8C", font: { size: 10 }, precision: 0 },
      grid: { display: false },
    };
  }
  return opcoes;
}

function limitesEscalaDinamica(valores) {
  const validos = valores
    .map((valor) => Number(valor))
    .filter((valor) => Number.isFinite(valor));
  if (!validos.length) return null;

  const minimo = Math.min(...validos);
  const maximo = Math.max(...validos);
  const intervalo = maximo - minimo;
  const margem = intervalo > 0
    ? intervalo * 0.12
    : Math.max(Math.abs(maximo) * 0.03, 1);

  return {
    min: minimo - margem,
    max: maximo + margem,
  };
}

function extremosEscalaHistorico(minimos, maximos) {
  let minimo = Infinity;
  let maximo = -Infinity;
  minimos.forEach((valor) => {
    const numerico = Number(valor);
    if (!Number.isFinite(numerico)) return;
    minimo = Math.min(minimo, numerico);
  });
  maximos.forEach((valor) => {
    const numerico = Number(valor);
    if (!Number.isFinite(numerico)) return;
    maximo = Math.max(maximo, numerico);
  });
  if (!Number.isFinite(minimo) || !Number.isFinite(maximo)) return null;
  const min = Math.floor(minimo - Math.abs(minimo) * 0.05);
  let max = Math.ceil(maximo + Math.abs(maximo) * 0.05);
  if (max <= min) max = min + 1;
  return { min, max };
}

function aplicarExtremosEscalaHistorico(opcoes, eixo, minimos, maximos) {
  const extremos = extremosEscalaHistorico(minimos, maximos);
  if (!extremos || !opcoes.scales[eixo]) return;
  Object.assign(opcoes.scales[eixo], extremos);
}

function aplicarEscalaDinamica(opcoes, eixo, valores) {
  const limites = limitesEscalaDinamica(valores);
  if (!limites || !opcoes.scales[eixo]) return;
  Object.assign(opcoes.scales[eixo], limites);
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

function resumoZonaPrincipal(zona) {
  if (!zona) return "";
  const especie = CONFIG_APP.nomeEspecie[zona.especie] || zona.especie;
  return zona.nome + " \u00b7 " + especie + " \u00b7 " + zona.indice;
}

function tituloGraficoZonaPrincipal(zona) {
  return resumoZonaPrincipal(zona);
}

function atualizarGraficoIndiceZonaPrincipal(zona, historico) {
  if (!zona || typeof Chart === "undefined") return;
  const canvas = elementoLinhaZonaPrincipal(zona.id, "grafico-indice");
  if (!canvas) return;

  const titulo = elementoLinhaZonaPrincipal(zona.id, "grafico-titulo");
  if (titulo) titulo.textContent = tituloGraficoZonaPrincipal(zona);

  const leituras = Array.isArray(historico) ? historico : [];
  const assinatura = JSON.stringify({ indice: zona.indice, leituras });
  if (
    assinaturasIndicePrincipalPorZona.get(zona.id) === assinatura &&
    graficosIndicePrincipalPorZona.has(zona.id)
  ) {
    return;
  }
  assinaturasIndicePrincipalPorZona.set(zona.id, assinatura);

  const graficoAtual = graficosIndicePrincipalPorZona.get(zona.id);
  const dataset = graficoAtual?.data.datasets[0] || {};
  Object.assign(dataset, {
    label: zona.indice,
    data: leituras.map((h) => h.valor),
    backgroundColor: leituras.map((h) => corStatus(h.status)),
    borderRadius: 3,
    maxBarThickness: 26,
  });

  const opcoes = opcoesGrafico(false);
  opcoes.plugins.legend.display = false;
  aplicarEscalaDinamica(opcoes, "y", dataset.data);

  const grafico = criarOuAtualizarGrafico(graficoAtual, canvas.id, {
    type: "bar",
    data: {
      labels: leituras.map((h) => formatarHora(h.criado_em)),
      datasets: [dataset],
    },
    options: opcoes,
  });
  graficosIndicePrincipalPorZona.set(zona.id, grafico);
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
  aplicarEscalaDinamica(
    opcoes,
    "y",
    datasets
      .filter((dataset) => (dataset.yAxisID || "y") === "y")
      .flatMap((dataset) => dataset.data)
  );
  aplicarEscalaDinamica(
    opcoes,
    "y1",
    datasets
      .filter((dataset) => dataset.yAxisID === "y1")
      .flatMap((dataset) => dataset.data)
  );

  graficoEntradas = criarOuAtualizarGrafico(graficoEntradas, "grafico-entradas", {
    type: "line",
    data: {
      labels: chaves.map((chave) => formatarHora(chave)),
      datasets,
    },
    options: opcoes,
  });
}

function historicosPorIndiceDasLeituras(leituras) {
  return (leituras || []).reduce((agrupado, leitura) => {
    const indice = leitura.indice || estado.indice;
    if (!agrupado[indice]) agrupado[indice] = [];
    agrupado[indice].push(leitura);
    return agrupado;
  }, {});
}

function camposDasLeituras(leituras) {
  return ordenarCamposInterface([
    ...new Set((leituras || []).flatMap((leitura) => Object.keys(leitura.entradas || {}))),
  ]);
}

function historicoTemMaisDeUmDia(leituras) {
  return new Set((leituras || []).map((leitura) => String(leitura.criado_em || "").slice(0, 10))).size > 1;
}

function rotulosHistorico(leituras) {
  const usarData = historicoTemMaisDeUmDia(leituras);
  return (leituras || []).map((leitura) =>
    usarData ? formatarDataHoraCurta(leitura.criado_em) : formatarHora(leitura.criado_em)
  );
}

function textoLegendaPeriodo(leituras) {
  if (!leituras || !leituras.length) return "Sem leituras no período selecionado.";
  const inicio = leituras[0].criado_em;
  const fim = leituras[leituras.length - 1].criado_em;
  const dias = [...new Set(leituras.map((leitura) => formatarDataCurta(leitura.criado_em)))];
  const periodo = dias.length === 1
    ? dias[0]
    : formatarDataCurta(inicio) + " a " + formatarDataCurta(fim);
  return "Período exibido: " + periodo + ". Clique em uma barra ou ponto para cruzar a leitura nos gráficos.";
}

function removerLegendaGraficoHistorico(containerId) {
  const container = document.getElementById(containerId);
  const legenda = container?.querySelector(".grafico-legenda");
  if (legenda) legenda.remove();
}

function opcoesGraficoHistorico(comEixoSecundario, aoClicar) {
  const opcoes = opcoesGrafico(comEixoSecundario);
  opcoes.plugins.legend.display = true;
  opcoes.onClick = (evento, elementos, grafico) => {
    if (!elementos.length) return;
    aoClicar(elementos[0], grafico);
  };
  return opcoes;
}

function selecionarLeituraHistorico(leituraId) {
  if (!leituraId || historicoLeituraSelecionadaId === leituraId) return;
  historicoLeituraSelecionadaId = leituraId;
  assinaturaGraficosHistorico = "";
  atualizarGraficosHistorico(historicoLeiturasJanela);
}

function atualizarGraficoHistoricoEntradas(leituras) {
  const canvas = document.getElementById("grafico-historico-entradas");
  if (!canvas || typeof Chart === "undefined") return;
  removerLegendaGraficoHistorico("historico-grafico-entradas");

  const campos = camposDasLeituras(leituras);
  const temEixoSecundario = campos.some((campo) => campo === "v" || campo === "ur");
  const datasetsAtuais = new Map(
    graficoHistoricoEntradas
      ? graficoHistoricoEntradas.data.datasets.map((dataset) => [dataset.campo, dataset])
      : []
  );
  const datasets = campos.map((campo) => {
    const meta = CONFIG_APP.campoMetadados[campo] || { label: campo };
    const cor = corCampoEntrada(campo);
    const dataset = datasetsAtuais.get(campo) || {};
    Object.assign(dataset, {
      campo,
      label: meta.label,
      data: leituras.map((leitura) => leitura.entradas?.[campo] ?? null),
      borderColor: cor,
      backgroundColor: cor + "33",
      tension: 0.35,
      cubicInterpolationMode: "monotone",
      pointRadius: leituras.map((leitura) => leitura.id === historicoLeituraSelecionadaId ? 5 : 2),
      pointHoverRadius: 4,
      pointBorderWidth: leituras.map((leitura) => leitura.id === historicoLeituraSelecionadaId ? 2 : 1),
      pointBorderColor: leituras.map((leitura) =>
        leitura.id === historicoLeituraSelecionadaId ? "#F2ECE1" : cor
      ),
      fill: campo !== "v" && campo !== "ur",
      yAxisID: campo === "v" || campo === "ur" ? "y1" : "y",
    });
    return dataset;
  });

  const opcoes = opcoesGraficoHistorico(temEixoSecundario, (elemento) => {
    selecionarLeituraHistorico(leituras[elemento.index]?.id);
  });
  opcoes.plugins.legend.display = false;
  aplicarExtremosEscalaHistorico(
    opcoes,
    "y",
    datasets
      .filter((dataset) => (dataset.yAxisID || "y") === "y")
      .map((dataset) => historicoMinimosFiltro.entradas[dataset.campo]),
    datasets
      .filter((dataset) => (dataset.yAxisID || "y") === "y")
      .map((dataset) => historicoMaximosFiltro.entradas[dataset.campo])
  );
  aplicarExtremosEscalaHistorico(
    opcoes,
    "y1",
    datasets
      .filter((dataset) => dataset.yAxisID === "y1")
      .map((dataset) => historicoMinimosFiltro.entradas[dataset.campo]),
    datasets
      .filter((dataset) => dataset.yAxisID === "y1")
      .map((dataset) => historicoMaximosFiltro.entradas[dataset.campo])
  );

  graficoHistoricoEntradas = criarOuAtualizarGrafico(
    graficoHistoricoEntradas,
    "grafico-historico-entradas",
    {
      type: "line",
      data: {
        labels: rotulosHistorico(leituras),
        datasets,
      },
      options: opcoes,
    }
  );
}

function idGraficoHistoricoIndice(indice) {
  return "grafico-historico-indice-" + indice.toLowerCase();
}

function garantirBlocosGraficosHistorico(indices) {
  const container = document.getElementById("graficos-historico-indices");
  if (!container) return;

  const idsAtivos = new Set(indices.map(idGraficoHistoricoIndice));
  [...container.querySelectorAll(".grafico-bloco-indice")].forEach((bloco) => {
    if (!idsAtivos.has(bloco.dataset.canvasId)) bloco.remove();
  });

  indices.forEach((indice) => {
    const canvasId = idGraficoHistoricoIndice(indice);
    let bloco = container.querySelector(`[data-canvas-id="${canvasId}"]`);
    if (!bloco) {
      bloco = document.createElement("div");
      bloco.className = "grafico-bloco grafico-bloco-indice";
      bloco.dataset.canvasId = canvasId;

      const titulo = document.createElement("p");
      titulo.className = "grafico-titulo";
      titulo.textContent = "Valor do " + indice + " no histórico";

      const legenda = document.createElement("p");
      legenda.className = "grafico-legenda";

      const wrap = document.createElement("div");
      wrap.className = "grafico-canvas-wrap";

      const canvas = document.createElement("canvas");
      canvas.id = canvasId;

      wrap.appendChild(canvas);
      bloco.append(titulo, legenda, wrap);
    }
    container.appendChild(bloco);
  });
}

function leituraTendenciaBruta(item) {
  return { rotulo: formatarDataHoraCurta(item.criado_em), valor: item.valor, cor: corStatus(item.status) };
}

function leituraTendenciaAgregada15min(item) {
  return {
    rotulo: formatarDataHoraCurta(item.janela_inicio),
    valor: item.valor_medio,
    minimo: item.valor_minimo,
    maximo: item.valor_maximo,
  };
}

function leituraTendenciaHoraria(item) {
  return {
    rotulo: formatarDataHoraCurta(item.hora_inicio),
    valor: item.valor_medio,
    minimo: item.valor_minimo,
    maximo: item.valor_maximo,
    cor: corStatus(item.status_da_media),
  };
}

async function buscarPontosTendencia(zonaId) {
  if (resolucaoTendencia === "15min") {
    const resposta = await fetch(`/api/zonas/${zonaId}/agregados-15min?limite=96`);
    if (!resposta.ok) throw new Error("Falha ao carregar agregados de 15 min.");
    const dados = await resposta.json();
    return {
      pontos: dados.map(leituraTendenciaAgregada15min),
      legenda: `Média, mínimo e máximo a cada 15 min — últimas ${dados.length} janelas (até 24h).`,
    };
  }
  if (resolucaoTendencia === "hora") {
    const resposta = await fetch(`/api/zonas/${zonaId}/resumo-horario?limite=168`);
    if (!resposta.ok) throw new Error("Falha ao carregar o resumo horário.");
    const dados = await resposta.json();
    return {
      pontos: dados.map(leituraTendenciaHoraria),
      legenda: `Média horária (status calculado a partir da média) — últimas ${dados.length} horas (até 7 dias).`,
    };
  }
  const resposta = await fetch(`/api/zonas/${zonaId}/historico?limite=200`);
  if (!resposta.ok) throw new Error("Falha ao carregar a leitura em tempo real.");
  const dados = await resposta.json();
  return {
    pontos: dados.map(leituraTendenciaBruta),
    legenda: `Leitura bruta, uma a cada ciclo do coletor — últimas ${dados.length} leituras.`,
  };
}

async function atualizarGraficoTendenciaResolucao() {
  if (typeof Chart === "undefined") return;
  const canvas = document.getElementById("grafico-tendencia-resolucao");
  const legendaEl = document.getElementById("tendencia-resolucao-legenda");
  if (!canvas) return;

  if (!filtroHistoricoZona) {
    if (graficoTendenciaResolucao) {
      graficoTendenciaResolucao.destroy();
      graficoTendenciaResolucao = null;
    }
    if (legendaEl) legendaEl.textContent = "Selecione uma zona no filtro acima para ver a tendência.";
    return;
  }

  const carregamentoId = ++tendenciaResolucaoCarregamentoId;
  let pontos = [];
  let legenda = "";
  try {
    ({ pontos, legenda } = await buscarPontosTendencia(filtroHistoricoZona));
  } catch (erro) {
    if (carregamentoId !== tendenciaResolucaoCarregamentoId) return;
    console.error("Nao foi possivel carregar a tendencia da zona:", erro);
    if (legendaEl) legendaEl.textContent = "Não foi possível carregar os dados desta resolução agora.";
    return;
  }
  if (carregamentoId !== tendenciaResolucaoCarregamentoId) return;

  if (legendaEl) {
    legendaEl.textContent = pontos.length
      ? legenda
      : "Sem dados consolidados nesta resolução ainda (aguarde o coletor rodar mais alguns ciclos).";
  }

  const temFaixa = resolucaoTendencia !== "bruto";
  const corLinha = "#4F8A93";
  const datasets = [];
  if (temFaixa) {
    datasets.push({
      label: "Máximo",
      data: pontos.map((ponto) => ponto.maximo),
      borderWidth: 0,
      pointRadius: 0,
      backgroundColor: "rgba(79, 138, 147, 0.18)",
      fill: "+1",
      tension: 0.25,
      order: 2,
    });
    datasets.push({
      label: "Mínimo",
      data: pontos.map((ponto) => ponto.minimo),
      borderWidth: 0,
      pointRadius: 0,
      backgroundColor: "rgba(79, 138, 147, 0.18)",
      fill: false,
      tension: 0.25,
      order: 2,
    });
  }
  datasets.push({
    label: "Média",
    data: pontos.map((ponto) => ponto.valor),
    borderColor: corLinha,
    backgroundColor: pontos.map((ponto) => ponto.cor || corLinha),
    borderWidth: 2,
    pointRadius: temFaixa ? 2 : 1.5,
    pointHoverRadius: 5,
    tension: 0.25,
    fill: false,
    order: 1,
  });

  const opcoes = opcoesGrafico(false);
  opcoes.plugins.legend.display = false;
  opcoes.scales.x.ticks.display = pontos.length <= 40;
  aplicarEscalaDinamica(
    opcoes,
    "y",
    pontos.flatMap((ponto) => [ponto.valor, ponto.minimo, ponto.maximo])
  );

  graficoTendenciaResolucao = criarOuAtualizarGrafico(graficoTendenciaResolucao, "grafico-tendencia-resolucao", {
    type: "line",
    data: { labels: pontos.map((ponto) => ponto.rotulo), datasets },
    options: opcoes,
  });
}

function atualizarGraficosHistorico(leituras) {
  if (typeof Chart === "undefined") return;
  const assinatura = JSON.stringify({
    leituras,
    total: historicoTotalLeituras,
    deslocamento: historicoDeslocamento,
    selecionada: historicoLeituraSelecionadaId,
  });
  if (assinatura === assinaturaGraficosHistorico) return;
  assinaturaGraficosHistorico = assinatura;

  atualizarGraficoHistoricoEntradas(leituras);

  const historicosPorIndice = historicosPorIndiceDasLeituras(leituras);
  const indices = Object.keys(historicosPorIndice).sort();
  garantirBlocosGraficosHistorico(indices);

  const indicesAtivos = new Set(indices);
  graficosHistoricoPorIndice.forEach((grafico, indice) => {
    if (!indicesAtivos.has(indice)) {
      grafico.destroy();
      graficosHistoricoPorIndice.delete(indice);
    }
  });

  indices.forEach((indice) => {
    const historico = historicosPorIndice[indice] || [];
    const canvasId = idGraficoHistoricoIndice(indice);
    const bloco = document.querySelector(`[data-canvas-id="${canvasId}"]`);
    const legenda = bloco?.querySelector(".grafico-legenda");
    if (legenda) legenda.textContent = textoLegendaPeriodo(historico);
    const dataset = graficosHistoricoPorIndice.get(indice)?.data.datasets[0] || {};
    Object.assign(dataset, {
      label: indice,
      data: historico.map((h) => h.valor),
      backgroundColor: historico.map((h) => corStatus(h.status)),
      borderColor: historico.map((h) => h.id === historicoLeituraSelecionadaId ? "#F2ECE1" : corStatus(h.status)),
      borderWidth: historico.map((h) => h.id === historicoLeituraSelecionadaId ? 2 : 0),
      borderRadius: 3,
      maxBarThickness: 26,
      leituraIds: historico.map((h) => h.id),
    });

    const opcoes = opcoesGraficoHistorico(false, (elemento, grafico) => {
      const ids = grafico.data.datasets[elemento.datasetIndex]?.leituraIds || [];
      selecionarLeituraHistorico(ids[elemento.index]);
    });
    opcoes.plugins.legend.display = false;
    aplicarExtremosEscalaHistorico(
      opcoes,
      "y",
      [historicoMinimosFiltro.indices[indice]],
      [historicoMaximosFiltro.indices[indice]]
    );

    const grafico = criarOuAtualizarGrafico(graficosHistoricoPorIndice.get(indice), canvasId, {
      type: "bar",
      data: {
        labels: rotulosHistorico(historico),
        datasets: [dataset],
      },
      options: opcoes,
    });
    graficosHistoricoPorIndice.set(indice, grafico);
  });
}

function leiturasTabela(historicos) {
  const leituras = Array.isArray(historicos)
    ? historicos.map((leitura) => ({ ...leitura, indice: leitura.indice || estado.indice }))
    : Object.entries(normalizarHistoricosPorIndice(historicos))
      .flatMap(([indice, itens]) => itens.map((leitura) => ({ ...leitura, indice: leitura.indice || indice })));
  return leituras
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

function garantirZonaHistoricoSelecionada() {
  if (!zonasCache.length) {
    filtroHistoricoZona = "";
    return false;
  }
  if (filtroHistoricoZona && zonasCache.some((zona) => String(zona.id) === filtroHistoricoZona)) {
    return true;
  }
  const zonaDashboard = zonaPrincipalSelecionada();
  filtroHistoricoZona = String(zonaDashboard?.id || zonasCache[0].id);
  return true;
}

function renderizarFiltrosHistorico() {
  if (filtroHistoricoStatus && !STATUS_HISTORICO.includes(filtroHistoricoStatus)) {
    filtroHistoricoStatus = "";
  }
  garantirZonaHistoricoSelecionada();

  preencherSelectHistorico(
    document.getElementById("filtro-historico-status"),
    STATUS_HISTORICO,
    filtroHistoricoStatus
  );

  const selectZona = document.getElementById("filtro-historico-zona");
  if (selectZona) {
    selectZona.innerHTML = "";
    zonasCache.forEach((zona) => {
      const option = document.createElement("option");
      option.value = String(zona.id);
      option.textContent = zona.nome;
      selectZona.appendChild(option);
    });
    if (!zonasCache.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Nenhuma zona cadastrada";
      selectZona.appendChild(option);
    }
    selectZona.disabled = !zonasCache.length;
    selectZona.value = filtroHistoricoZona;
  }

  const selectValor = document.getElementById("filtro-historico-valor");
  if (selectValor) {
    selectValor.textContent = "";
    const optionTodos = document.createElement("option");
    optionTodos.value = "";
    optionTodos.textContent = "Todos";
    selectValor.appendChild(optionTodos);

    if (Number.isFinite(filtroHistoricoValorReferencia)) {
      const optionReferencia = document.createElement("option");
      optionReferencia.value = String(filtroHistoricoValorReferencia);
      const tipo = filtroHistoricoValorTipo
        ? (ROTULO_TIPO_VALOR_HISTORICO[filtroHistoricoValorTipo] || "Valor") + ": "
        : "Próximo de ";
      const encontrados = filtroHistoricoValoresEncontrados.length
        ? " → " + filtroHistoricoValoresEncontrados.map(formatarValorFiltroHistorico).join(" / ")
        : "";
      optionReferencia.textContent =
        tipo + formatarValorFiltroHistorico(filtroHistoricoValorReferencia) + encontrados;
      selectValor.appendChild(optionReferencia);
      selectValor.value = optionReferencia.value;
    } else {
      selectValor.value = "";
    }
  }
}

function formatarValorFiltroHistorico(valor) {
  return Number(valor).toFixed(2).replace(".", ",");
}

function criarFiltroPeriodoHistorico(prefixo, rotulo) {
  const grupo = document.createElement("div");
  grupo.className = "campo-config historico-filtro-periodo";
  const id = `filtro-historico-${prefixo}`;
  const titulo = document.createElement("label");
  titulo.htmlFor = id;
  titulo.textContent = rotulo;
  const input = document.createElement("input");
  input.type = "date";
  input.id = id;
  grupo.append(titulo, input);
  return grupo;
}

function lerLimitePeriodoHistorico(prefixo) {
  const data = document.getElementById(`filtro-historico-${prefixo}`)?.value || "";
  return { data: data || null, erro: "" };
}

function definirStatusPeriodoHistorico(mensagem) {
  const status = document.getElementById("historico-filtro-periodo-status");
  if (!status) return;
  status.textContent = mensagem || "";
  status.classList.toggle("oculto", !mensagem);
}

function aplicarFiltrosHistorico(resetarPagina) {
  historicoLeiturasAtuais = historicoLeiturasBase.filter((leitura) => {
    const statusOk = !filtroHistoricoStatus || leitura.status === filtroHistoricoStatus;
    const zonaOk = !filtroHistoricoZona || String(leitura.zona_id || "") === filtroHistoricoZona;
    return statusOk && zonaOk;
  });

  if (resetarPagina) historicoPaginaAtual = 1;
  renderizarPaginaHistorico();
}

function atualizarFiltroHistorico() {
  filtroHistoricoIndice = "";
  filtroHistoricoStatus = document.getElementById("filtro-historico-status")?.value || "";
  filtroHistoricoZona = document.getElementById("filtro-historico-zona")?.value || "";
  const valorSelecionado = document.getElementById("filtro-historico-valor")?.value || "";
  filtroHistoricoValorReferencia = valorSelecionado === "" ? null : Number(valorSelecionado);
  if (!Number.isFinite(filtroHistoricoValorReferencia)) filtroHistoricoValorReferencia = null;
  if (filtroHistoricoValorReferencia === null) filtroHistoricoValorTipo = "";
  filtroHistoricoValoresEncontrados = [];
  const inicio = lerLimitePeriodoHistorico("de");
  const fim = lerLimitePeriodoHistorico("ate");
  if (inicio.erro || fim.erro) {
    definirStatusPeriodoHistorico(inicio.erro || fim.erro);
    return;
  }
  if (inicio.data && fim.data && inicio.data > fim.data) {
    definirStatusPeriodoHistorico("A data inicial não pode ser posterior à data final.");
    return;
  }
  filtroHistoricoDataInicio = inicio.data;
  filtroHistoricoDataFim = fim.data;
  definirStatusPeriodoHistorico("");
  carregarHistoricoPersistido({ resetarJanela: true });
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

  if (!historicoLeiturasAtuais.length) {
    tabela.classList.add("oculto");
    vazio.textContent = historicoLeiturasBase.length
      ? "Nenhuma leitura encontrada para os filtros selecionados."
      : "Nenhuma leitura registrada ainda no banco para os filtros selecionados.";
    vazio.classList.remove("oculto");
    if (paginacao) paginacao.classList.remove("oculto");
    atualizarControleHistoricoScroll();
    return;
  }
  tabela.classList.remove("oculto");
  vazio.classList.add("oculto");
  if (paginacao) paginacao.classList.remove("oculto");
  if (paginaInfo) paginaInfo.textContent = "";
  if (btnAnterior) btnAnterior.disabled = true;
  if (btnProximo) btnProximo.disabled = true;

  const leituras = historicoLeiturasAtuais;

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
  atualizarControleHistoricoScroll();
}

function atualizarControleHistoricoScroll() {
  const scroll = document.getElementById("historico-scroll");
  const info = document.getElementById("historico-pagina-info");
  const btnAnterior = document.getElementById("btn-historico-anterior");
  const btnProximo = document.getElementById("btn-historico-proximo");
  const maximo = Math.max(0, historicoTotalLeituras - HISTORICO_JANELA_LEITURAS);
  const temLeituras = historicoTotalLeituras > 0;

  if (scroll) {
    scroll.min = "0";
    scroll.max = String(maximo);
    scroll.step = "1";
    scroll.value = String(Math.min(historicoDeslocamento, maximo));
    scroll.disabled = !temLeituras || maximo === 0;
  }
  if (btnAnterior) btnAnterior.disabled = !temLeituras || historicoDeslocamento <= 0;
  if (btnProximo) btnProximo.disabled = !temLeituras || historicoDeslocamento >= maximo;
  if (info) {
    if (!temLeituras) {
      info.textContent = "Sem leituras";
    } else {
      const inicio = historicoDeslocamento + 1;
      const fim = Math.min(historicoDeslocamento + historicoLeiturasBase.length, historicoTotalLeituras);
      info.textContent = `Leituras ${inicio}-${fim} de ${historicoTotalLeituras}`;
    }
  }
}

async function carregarHistoricoPersistido(opcoes = {}) {
  const carregamentoId = ++historicoCarregamentoId;
  if (!garantirZonaHistoricoSelecionada()) {
    historicoTotalLeituras = 0;
    historicoDeslocamento = 0;
    historicoLeiturasJanela = [];
    historicoLeiturasBase = [];
    historicoLeiturasAtuais = [];
    historicoMinimosFiltro = { indices: {}, entradas: {} };
    historicoMaximosFiltro = { indices: {}, entradas: {} };
    renderizarFiltrosHistorico();
    renderizarPaginaHistorico();
    atualizarGraficosHistorico([]);
    atualizarGraficoTendenciaResolucao();
    atualizarControleHistoricoScroll();
    return;
  }
  const maximoAtual = Math.max(0, historicoTotalLeituras - HISTORICO_JANELA_LEITURAS);
  const estavaNoFim = historicoDeslocamento >= maximoAtual;
  const params = new URLSearchParams();
  params.set("limite", String(HISTORICO_JANELA_LEITURAS));
  if (filtroHistoricoZona) params.set("zona_id", filtroHistoricoZona);
  if (filtroHistoricoIndice) params.set("indice", filtroHistoricoIndice);
  if (filtroHistoricoStatus) params.set("status", filtroHistoricoStatus);
  if (Number.isFinite(filtroHistoricoValorReferencia)) {
    params.set("valor_referencia", String(filtroHistoricoValorReferencia));
  }
  if (filtroHistoricoDataInicio) params.set("data_inicio", filtroHistoricoDataInicio);
  if (filtroHistoricoDataFim) params.set("data_fim", filtroHistoricoDataFim);

  if (Number.isFinite(opcoes.deslocamento)) {
    params.set("deslocamento", String(Math.max(0, opcoes.deslocamento)));
  } else if (!opcoes.resetarJanela && !(opcoes.manterJanelaFinal && estavaNoFim)) {
    params.set("deslocamento", String(Math.max(0, historicoDeslocamento)));
  }

  try {
    const resposta = await fetch("/api/historico-leituras?" + params.toString());
    if (!resposta.ok) return;
    const dados = await resposta.json();
    if (carregamentoId !== historicoCarregamentoId) return;
    historicoTotalLeituras = Number(dados.total) || 0;
    historicoDeslocamento = Number(dados.deslocamento) || 0;
    filtroHistoricoValoresEncontrados = Array.isArray(dados.valores_encontrados)
      ? dados.valores_encontrados.map(Number).filter(Number.isFinite)
      : [];
    historicoMinimosFiltro = {
      indices: dados.minimos?.indices || {},
      entradas: dados.minimos?.entradas || {},
    };
    historicoMaximosFiltro = {
      indices: dados.maximos?.indices || {},
      entradas: dados.maximos?.entradas || {},
    };
    historicoLeiturasJanela = Array.isArray(dados.leituras) ? dados.leituras : [];
    if (
      historicoLeituraSelecionadaId &&
      !historicoLeiturasJanela.some((leitura) => leitura.id === historicoLeituraSelecionadaId)
    ) {
      historicoLeituraSelecionadaId = null;
    }
    historicoLeiturasBase = leiturasTabela(historicoLeiturasJanela);
    renderizarFiltrosHistorico();
    aplicarFiltrosHistorico(false);
    atualizarGraficosHistorico(historicoLeiturasJanela);
    atualizarGraficoTendenciaResolucao();
    atualizarControleHistoricoScroll();
  } catch (erro) {
    if (carregamentoId === historicoCarregamentoId) {
      console.error("Nao foi possivel carregar o historico persistido:", erro);
    }
  }
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
  const maximo = Math.max(0, historicoTotalLeituras - HISTORICO_JANELA_LEITURAS);
  const proximo = Math.max(
    0,
    Math.min(maximo, historicoDeslocamento + delta * HISTORICO_JANELA_LEITURAS)
  );
  carregarHistoricoPersistido({ deslocamento: proximo });
}

function rolarHistorico(evento) {
  const deslocamento = Number(evento.target.value);
  if (historicoScrollTimeoutId) clearTimeout(historicoScrollTimeoutId);
  historicoScrollTimeoutId = setTimeout(() => {
    carregarHistoricoPersistido({ deslocamento });
  }, 120);
}

function prepararAbaHistorico() {
  const slot = document.getElementById("historico-tabela-slot");
  const painelTabela = document.querySelector(".tabela-painel");
  if (slot && painelTabela && painelTabela.parentElement !== slot) {
    slot.appendChild(painelTabela);
  }

  const corpo = document.getElementById("historico-corpo");
  if (corpo) corpo.classList.remove("oculto");
  const botaoToggle = document.getElementById("btn-toggle-historico");
  if (botaoToggle) botaoToggle.remove();

  const filtros = document.querySelector("#historico-acoes .historico-filtros");
  const slotFiltros = document.getElementById("historico-filtros-slot");
  if (filtros && slotFiltros && filtros.parentElement !== slotFiltros) {
    slotFiltros.appendChild(filtros);
  }
  if (filtros && !document.getElementById("filtro-historico-zona")) {
    const label = document.createElement("label");
    label.className = "historico-filtro";
    label.setAttribute("for", "filtro-historico-zona");
    const span = document.createElement("span");
    span.textContent = "Zona";
    const select = document.createElement("select");
    select.id = "filtro-historico-zona";
    label.append(span, select);
    filtros.prepend(label);
  }
  if (filtros && !document.getElementById("filtro-historico-valor")) {
    const label = document.createElement("label");
    label.className = "historico-filtro";
    label.setAttribute("for", "filtro-historico-valor");
    const span = document.createElement("span");
    span.textContent = "Valor do índice";
    const select = document.createElement("select");
    select.id = "filtro-historico-valor";
    label.append(span, select);
    filtros.appendChild(label);
  }
  if (filtros && !document.getElementById("filtro-historico-de")) {
    filtros.appendChild(criarFiltroPeriodoHistorico("de", "De"));
    filtros.appendChild(criarFiltroPeriodoHistorico("ate", "Até"));
    const statusPeriodo = document.createElement("p");
    statusPeriodo.id = "historico-filtro-periodo-status";
    statusPeriodo.className = "historico-periodo-status mensagem-erro oculto";
    filtros.appendChild(statusPeriodo);
  }

  const slotResolucao = document.getElementById("historico-resolucao-slot");
  if (slotResolucao && !document.getElementById("filtro-historico-resolucao")) {
    const label = document.createElement("label");
    label.className = "historico-filtro";
    label.setAttribute("for", "filtro-historico-resolucao");
    const span = document.createElement("span");
    span.textContent = "Resolução";
    const select = document.createElement("select");
    select.id = "filtro-historico-resolucao";
    RESOLUCOES_TENDENCIA.forEach((opcao) => {
      const item = document.createElement("option");
      item.value = opcao.valor;
      item.textContent = opcao.texto;
      select.appendChild(item);
    });
    select.value = resolucaoTendencia;
    label.append(span, select);
    slotResolucao.appendChild(label);
  }

  const paginacao = document.getElementById("historico-paginacao");
  const controleCabecalho = document.getElementById("historico-controle-cabecalho");
  if (controleCabecalho && paginacao && paginacao.parentElement !== controleCabecalho) {
    controleCabecalho.appendChild(paginacao);
  }
  if (paginacao && !document.getElementById("historico-scroll")) {
    const scroll = document.createElement("input");
    scroll.type = "range";
    scroll.id = "historico-scroll";
    scroll.className = "historico-scroll";
    scroll.min = "0";
    scroll.max = "0";
    scroll.value = "0";
    const info = document.getElementById("historico-pagina-info");
    paginacao.insertBefore(scroll, info || null);
  }
  const btnAnterior = document.getElementById("btn-historico-anterior");
  const btnProximo = document.getElementById("btn-historico-proximo");
  if (btnAnterior) btnAnterior.textContent = "Retroceder";
  if (btnProximo) btnProximo.textContent = "Avançar";
  if (paginacao && btnAnterior && btnProximo && btnAnterior.nextElementSibling !== btnProximo) {
    paginacao.insertBefore(btnAnterior, btnProximo);
  }
}

function inicializarHistorico() {
  prepararAbaHistorico();
  renderizarFiltrosHistorico();
  document.getElementById("btn-toggle-historico")?.addEventListener("click", alternarHistorico);
  document.getElementById("btn-historico-anterior")?.addEventListener("click", () => paginaHistorico(-1));
  document.getElementById("btn-historico-proximo")?.addEventListener("click", () => paginaHistorico(1));
  document.getElementById("historico-scroll")?.addEventListener("input", rolarHistorico);
  document.getElementById("filtro-historico-status")?.addEventListener("change", atualizarFiltroHistorico);
  document.getElementById("filtro-historico-zona")?.addEventListener("change", atualizarFiltroHistorico);
  document.getElementById("filtro-historico-valor")?.addEventListener("change", atualizarFiltroHistorico);
  document.getElementById("filtro-historico-de")?.addEventListener("change", atualizarFiltroHistorico);
  document.getElementById("filtro-historico-ate")?.addEventListener("change", atualizarFiltroHistorico);
  document.getElementById("filtro-historico-resolucao")?.addEventListener("change", (evento) => {
    resolucaoTendencia = evento.target.value;
    atualizarGraficoTendenciaResolucao();
  });
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
function ativarAba(aba) {
  const botoes = document.querySelectorAll("[data-aba]");
  const conteudos = document.querySelectorAll("[data-aba-conteudo]");

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
      graficosIndicePrincipalPorZona.forEach((grafico) => grafico.resize());
      if (graficoEntradas) graficoEntradas.resize();
    }, 0);
  }

  // Dashboard e Operacao dependem do polling de 3s (`atualizarMonitoramento`)
  // para dado ao vivo; dispara na hora ao entrar na aba em vez de esperar o
  // proximo tick, senao a tela mostraria ate 3s de estado desatualizado
  // (ou "aguardando heartbeat") logo ao trocar de aba.
  if (aba === "principal" || aba === "operacao") {
    atualizarMonitoramento();
  }

  if (aba === "analises") {
    carregarAnalises();
  }

  if (aba === "historico") {
    carregarHistoricoPersistido({ manterJanelaFinal: true });
    setTimeout(() => {
      graficosHistoricoPorIndice.forEach((grafico) => grafico.resize());
      if (graficoHistoricoEntradas) graficoHistoricoEntradas.resize();
    }, 0);
  }

  if (aba === "zonas") {
    carregarZonas();
  }

  if (aba === "dados-entrada") {
    carregarDadosEntrada();
  }
}

function inicializarAbas() {
  document.querySelectorAll("[data-aba]").forEach((botao) => {
    botao.addEventListener("click", () => ativarAba(botao.dataset.aba));
  });
}

// Abre a aba Historico com zona e, quando informado, status ja selecionados
// nos filtros -- usada pelos relatorios da aba Analises.
function abrirHistoricoComZona(
  zonaId,
  status = "",
  valorReferencia = null,
  valorTipo = "",
  indice = ""
) {
  filtroHistoricoZona = String(zonaId);
  filtroHistoricoIndice = indice;
  filtroHistoricoStatus = STATUS_HISTORICO.includes(status) ? status : "";
  const valorNumerico = Number(valorReferencia);
  filtroHistoricoValorReferencia = valorReferencia !== null && Number.isFinite(valorNumerico)
    ? valorNumerico
    : null;
  filtroHistoricoValorTipo = filtroHistoricoValorReferencia === null ? "" : valorTipo;
  filtroHistoricoValoresEncontrados = [];
  ativarAba("historico");
}

function moverControlesParaConfiguracoes() {
  const configuracoesApp = document.getElementById("configuracoes-app");
  const configuracoesEmail = document.getElementById("configuracoes-email");
  const configuracoesSensores = document.getElementById("configuracoes-sensores");
  const configuracoesCalculos = document.getElementById("configuracoes-calculos");
  const configuracoesHistorico = document.getElementById("configuracoes-historico");

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

  moverCheck("cfg-emails", configuracoesEmail);
  if (configuracoesEmail && email) configuracoesEmail.appendChild(email);

  moverCampo("cfg-intervalo-leitura", configuracoesSensores);

  moverCampo("cfg-ponto-orvalho", configuracoesCalculos);
  moverCampo("cfg-umidade-relativa", configuracoesCalculos);
  moverCampo("cfg-altitude", configuracoesCalculos);
  moverCampo("cfg-limite-umidade-nebulizador", configuracoesCalculos);

  if (configuracoesHistorico && limparHistorico) configuracoesHistorico.appendChild(limparHistorico);
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

function zonaPorId(zonaId) {
  return zonasCache.find((zona) => zona.id === Number(zonaId)) || null;
}

function zonasAtivas() {
  return zonasCache.filter((zona) => zona.ativa);
}

function zonaPrincipalSelecionada() {
  return zonasCache.find((zona) => zona.id === estado.zonaId && zona.ativa) || null;
}

function zonasOrdenadasPrincipal() {
  const selecionadaId = Number(estado.zonaId);
  return zonasAtivas().sort((a, b) => {
    if (a.id === selecionadaId) return -1;
    if (b.id === selecionadaId) return 1;
    return a.id - b.id;
  });
}

function equipamentosDaZona(zona, tipo) {
  if (!zona) return [];
  return (zona.equipamentos || []).filter((equipamento) => equipamento.tipo === tipo);
}

function linhaZonaPrincipal(zonaId) {
  return document.querySelector(`.principal-zona-linha[data-zona-id="${Number(zonaId)}"]`);
}

function elementoLinhaZonaPrincipal(zonaId, papel) {
  return linhaZonaPrincipal(zonaId)?.querySelector(`[data-role="${papel}"]`) || null;
}

function destruirGraficosZonasPrincipal() {
  graficosIndicePrincipalPorZona.forEach((grafico) => grafico.destroy());
  graficosIndicePrincipalPorZona.clear();
  assinaturasIndicePrincipalPorZona.clear();
}

function construirLinhaZonaPrincipal(zona) {
  const linha = document.createElement("div");
  linha.className = "principal-zona-linha";
  linha.dataset.zonaId = zona.id;

  const leitura = document.createElement("section");
  leitura.className = "painel leitura-painel";

  const readout = document.createElement("div");
  readout.className = "readout";
  const valor = document.createElement("span");
  valor.className = "readout-valor";
  valor.dataset.role = "readout-valor";
  valor.textContent = "--,--";
  readout.appendChild(valor);
  const etiquetaIndice = document.createElement("span");
  etiquetaIndice.className = "readout-etiqueta";
  etiquetaIndice.dataset.role = "readout-indice";
  etiquetaIndice.textContent = zona.indice;
  readout.appendChild(etiquetaIndice);
  leitura.appendChild(readout);

  const faixa = document.createElement("div");
  faixa.className = "faixa-status faixa-status--vazio";
  faixa.dataset.role = "faixa-status";
  const faixaTexto = document.createElement("span");
  faixaTexto.dataset.role = "faixa-status-texto";
  faixaTexto.textContent = zona.ativa ? "AGUARDANDO CALCULO" : "ZONA INATIVA";
  faixa.appendChild(faixaTexto);
  leitura.appendChild(faixa);

  const mensagem = document.createElement("p");
  mensagem.className = "mensagem-orientacao";
  mensagem.dataset.role = "mensagem-orientacao";
  mensagem.textContent = zona.ativa
    ? "Aguardando leitura desta zona."
    : "Zona inativa. O historico permanece disponivel, mas ela nao entra no monitoramento automatico.";
  leitura.appendChild(mensagem);
  linha.appendChild(leitura);

  const painelGrafico = document.createElement("section");
  painelGrafico.className = "graficos-painel";
  const graficos = document.createElement("div");
  graficos.className = "graficos-indices";
  const bloco = document.createElement("div");
  bloco.className = "grafico-bloco grafico-bloco-indice";
  const tituloGrafico = document.createElement("p");
  tituloGrafico.className = "grafico-titulo";
  tituloGrafico.dataset.role = "grafico-titulo";
  tituloGrafico.textContent = tituloGraficoZonaPrincipal(zona);
  const wrap = document.createElement("div");
  wrap.className = "grafico-canvas-wrap";
  const canvas = document.createElement("canvas");
  canvas.id = "grafico-zona-principal-" + zona.id;
  canvas.dataset.role = "grafico-indice";
  wrap.appendChild(canvas);
  bloco.append(tituloGrafico, wrap);
  graficos.appendChild(bloco);
  painelGrafico.appendChild(graficos);
  linha.appendChild(painelGrafico);

  const equipamentos = document.createElement("section");
  equipamentos.className = "painel equipamentos-painel";
  const tituloEquipamentos = document.createElement("h2");
  tituloEquipamentos.className = "painel-titulo";
  tituloEquipamentos.textContent = "Equipamentos remotos";
  equipamentos.appendChild(tituloEquipamentos);
  const intensidade = document.createElement("div");
  intensidade.className = "intensidade-info";
  const intensidadeEtiqueta = document.createElement("span");
  intensidadeEtiqueta.className = "intensidade-etiqueta";
  intensidadeEtiqueta.textContent = "Intensidade";
  const intensidadeValor = document.createElement("span");
  intensidadeValor.dataset.role = "intensidade-valor";
  intensidadeValor.textContent = "desligado";
  intensidade.append(intensidadeEtiqueta, intensidadeValor);
  equipamentos.appendChild(intensidade);

  const gradeEquipamentos = document.createElement("div");
  gradeEquipamentos.className = "equipamentos";
  [
    ["Ventilador", "icones-ventilador"],
    ["Nebulizador", "icones-nebulizador"],
    ["Sensor", "icones-sensor"],
  ].forEach(([rotulo, papel]) => {
    const grupo = document.createElement("div");
    grupo.className = "lampada-grupo";
    const legenda = document.createElement("span");
    legenda.className = "lampada-legenda";
    legenda.textContent = rotulo;
    const icones = document.createElement("div");
    icones.className = "icones-equipamento";
    icones.dataset.role = papel;
    icones.setAttribute("role", "img");
    icones.setAttribute("aria-label", rotulo + " desligado");
    grupo.append(legenda, icones);
    gradeEquipamentos.appendChild(grupo);
  });
  equipamentos.appendChild(gradeEquipamentos);
  linha.appendChild(equipamentos);

  return linha;
}

function renderizarLinhasZonasPrincipal() {
  const container = document.getElementById("linhas-zonas-principal");
  if (!container) return;
  destruirGraficosZonasPrincipal();
  container.textContent = "";

  zonasOrdenadasPrincipal().forEach((zona) => {
    container.appendChild(construirLinhaZonaPrincipal(zona));
    resetarLinhaZonaPrincipal(zona);
  });
}

function atualizarResumoZonaPrincipal(zona) {
  const resumo = document.getElementById("zona-principal-resumo");
  if (!resumo) return;
  if (!zona) {
    resumo.textContent = "Nenhuma zona ativa selecionada.";
    return;
  }
  resumo.textContent = resumoZonaPrincipal(zona);
}

function renderizarSelectZonaPrincipal() {
  const selects = [
    document.getElementById("zona-principal"),
    document.getElementById("zona-dashboard"),
    document.getElementById("zona-executivo"),
  ].filter(Boolean);
  if (!selects.length) return;

  const ativas = zonasAtivas();
  const zonaAtualAindaValida = ativas.some((zona) => zona.id === estado.zonaId);
  if (!zonaAtualAindaValida) {
    estado.zonaId = ativas.length ? ativas[0].id : null;
  }

  selects.forEach((select) => { select.textContent = ""; });
  if (!ativas.length) {
    selects.forEach((select) => {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Nenhuma zona ativa cadastrada";
      select.appendChild(option);
      select.disabled = true;
    });
    const botaoCalcular = document.getElementById("btn-calcular");
    if (botaoCalcular) botaoCalcular.disabled = true;
    atualizarResumoZonaPrincipal(null);
    renderCamposEntrada();
    renderizarLinhasZonasPrincipal();
    renderizarPainelExecutivo();
    return;
  }

  selects.forEach((select) => {
    select.disabled = false;
    ativas.forEach((zona) => {
      const option = document.createElement("option");
      option.value = String(zona.id);
      option.textContent = zona.nome + " (" + zona.indice + ")";
      select.appendChild(option);
    });
    select.value = String(estado.zonaId);
  });
  const botaoCalcular = document.getElementById("btn-calcular");
  if (botaoCalcular) botaoCalcular.disabled = false;

  const zona = zonaPrincipalSelecionada();
  if (zona) {
    estado.especie = zona.especie;
    estado.indice = zona.indice;
  }
  atualizarResumoZonaPrincipal(zona);
  renderCamposEntrada();
  renderizarLinhasZonasPrincipal();
  resetarPainelResultado();
  renderizarPainelExecutivo();
}

async function selecionarZonaPrincipal(zonaId) {
  const id = Number(zonaId);
  estado.zonaId = Number.isFinite(id) ? id : null;
  const zona = zonaPrincipalSelecionada();
  if (zona) {
    estado.especie = zona.especie;
    estado.indice = zona.indice;
  }
  ["zona-principal", "zona-dashboard", "zona-executivo"].forEach((selectId) => {
    const select = document.getElementById(selectId);
    if (select) select.value = zona ? String(zona.id) : "";
  });
  historicoPaginaAtual = 1;
  atualizarResumoZonaPrincipal(zona);
  renderCamposEntrada();
  renderizarLinhasZonasPrincipal();
  resetarPainelResultado();
  renderizarPainelExecutivo();
  await carregarHistorico();
  await carregarEstadoOperacional();
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

async function carregarAnalises() {
  try {
    const [respostaEstatisticas, respostaPainel] = await Promise.all([
      fetch("/api/analises"),
      fetch("/api/analises/painel-executivo"),
    ]);
    if (respostaEstatisticas.ok) {
      const estatisticas = await respostaEstatisticas.json();
      renderizarAnalisePercentuais(estatisticas);
      renderizarAnaliseIndices(estatisticas);
    }
    if (respostaPainel.ok) {
      renderizarPainelExecutivo(await respostaPainel.json());
    }
  } catch (erro) {
    console.error("Não foi possível carregar as análises:", erro);
  }
}

function formatarMinutosDuracao(minutos) {
  if (minutos === null || minutos === undefined) return "—";
  const totalMinutos = Math.max(0, Math.round(minutos));
  const horas = Math.floor(totalMinutos / 60);
  const resto = totalMinutos % 60;
  return horas > 0 ? horas + "h" + String(resto).padStart(2, "0") + "min" : resto + " min";
}

const ROTULO_TENDENCIA_EXECUTIVO = { subindo: "Subindo", estavel: "Estável", descendo: "Descendo" };
// Subir = pior (mais estresse termico), descer = melhor -- mesma logica de
// cor do restante da interface (verde = conforto, vermelho = perigo).
const CLASSE_TENDENCIA_EXECUTIVO = { subindo: "cor-perigo", estavel: "", descendo: "cor-conforto" };

function linhaTendenciaExecutivo(rotuloJanela, tendencia) {
  const linha = document.createElement("span");
  const rotulo = document.createElement("strong");
  rotulo.textContent = rotuloJanela + ": ";
  linha.appendChild(rotulo);
  const valor = document.createElement("span");
  valor.textContent = tendencia ? ROTULO_TENDENCIA_EXECUTIVO[tendencia] : "sem dados";
  if (tendencia && CLASSE_TENDENCIA_EXECUTIVO[tendencia]) {
    valor.className = CLASSE_TENDENCIA_EXECUTIVO[tendencia];
  }
  linha.appendChild(valor);
  return linha;
}

function construirMetricaExecutivo(rotulo, montarValor) {
  const caixa = document.createElement("div");
  caixa.className = "executivo-metrica";
  const rotuloEl = document.createElement("p");
  rotuloEl.className = "executivo-metrica-rotulo";
  rotuloEl.textContent = rotulo;
  caixa.appendChild(rotuloEl);
  const valorEl = document.createElement("p");
  valorEl.className = "executivo-metrica-valor";
  montarValor(valorEl);
  caixa.appendChild(valorEl);
  return caixa;
}

// Monta o card de uma zona no "Painel executivo por zona" (aba Analises) a
// partir do resultado de GET /api/analises/painel-executivo. Assim como o
// resto do app.js, tudo aqui e construido via DOM real (createElement +
// textContent), nunca via innerHTML com dado vindo do servidor.
function construirCartaoExecutivoZona(zona) {
  const cartao = document.createElement("section");
  cartao.className = "executivo-cartao";
  cartao.dataset.zonaId = zona.zona_id;

  const cabecalho = document.createElement("div");
  cabecalho.className = "executivo-cabecalho";

  const tituloGrupo = document.createElement("div");
  tituloGrupo.className = "executivo-titulo-grupo";

  const nome = document.createElement("h3");
  nome.className = "executivo-nome";
  nome.textContent = zona.nome;
  tituloGrupo.appendChild(nome);

  const badgeEspecie = document.createElement("span");
  badgeEspecie.className = "zona-badge";
  const nomesEspecie = (window.CONFIG_APP && CONFIG_APP.nomeEspecie) || {};
  badgeEspecie.textContent = nomesEspecie[zona.especie] || zona.especie;
  tituloGrupo.appendChild(badgeEspecie);

  const badgeStatus = document.createElement("span");
  if (zona.status_atual) {
    badgeStatus.className = "faixa-status executivo-status-badge faixa-" + classeStatus(zona.status_atual);
    badgeStatus.textContent = zona.status_atual.toUpperCase();
  } else {
    badgeStatus.className = "faixa-status executivo-status-badge faixa-status--vazio";
    badgeStatus.textContent = "SEM LEITURA";
  }
  tituloGrupo.appendChild(badgeStatus);
  cabecalho.appendChild(tituloGrupo);

  const indiceValor = document.createElement("div");
  indiceValor.className = "executivo-indice-valor";
  indiceValor.textContent =
    zona.indice + (zona.valor_atual !== null ? ": " + String(zona.valor_atual).replace(".", ",") : "");
  cabecalho.appendChild(indiceValor);

  cartao.appendChild(cabecalho);

  const metricas = document.createElement("div");
  metricas.className = "executivo-metricas";
  const tendencias = zona.tendencias || {};

  metricas.appendChild(
    construirMetricaExecutivo("Tendência", (valorEl) => {
      valorEl.appendChild(linhaTendenciaExecutivo("15 min", tendencias["15min"]));
      valorEl.appendChild(document.createElement("br"));
      valorEl.appendChild(linhaTendenciaExecutivo("30 min", tendencias["30min"]));
      valorEl.appendChild(document.createElement("br"));
      valorEl.appendChild(linhaTendenciaExecutivo("60 min", tendencias["60min"]));
    })
  );

  metricas.appendChild(
    construirMetricaExecutivo("Conforto nas últimas 24h", (valorEl) => {
      valorEl.textContent =
        zona.percentual_conforto_24h === null
          ? "Sem leituras no período"
          : String(zona.percentual_conforto_24h).replace(".", ",") + "%";
    })
  );

  metricas.appendChild(
    construirMetricaExecutivo("Tempo contínuo no status atual", (valorEl) => {
      valorEl.textContent = formatarMinutosDuracao(zona.tempo_continuo_status_minutos);
    })
  );

  metricas.appendChild(
    construirMetricaExecutivo("Maior nível atingido hoje", (valorEl) => {
      if (!zona.nivel_maximo_dia) {
        valorEl.textContent = "Sem leituras hoje";
        return;
      }
      valorEl.textContent = zona.nivel_maximo_dia;
      valorEl.classList.add("cor-" + classeStatus(zona.nivel_maximo_dia));
    })
  );

  metricas.appendChild(
    construirMetricaExecutivo("Minutos em perigo / emergência hoje", (valorEl) => {
      const linhaPerigo = document.createElement("span");
      linhaPerigo.textContent = "Perigo: " + formatarMinutosDuracao(zona.minutos_perigo_dia);
      const linhaEmergencia = document.createElement("span");
      linhaEmergencia.textContent = "Emergência: " + formatarMinutosDuracao(zona.minutos_emergencia_dia);
      valorEl.append(linhaPerigo, document.createElement("br"), linhaEmergencia);
    })
  );

  metricas.appendChild(
    construirMetricaExecutivo("Horário previsto do pico", (valorEl) => {
      const pico = zona.pico_previsto || {};
      if (!pico.horario) {
        valorEl.textContent = "Dados insuficientes (mín. 2 dias anteriores)";
        return;
      }
      valorEl.append(pico.horario);
      const nota = document.createElement("span");
      nota.className = "executivo-metrica-nota";
      nota.textContent =
        (pico.ja_ocorreu ? "já ocorreu hoje · " : "estimativa · ") +
        "com base em " +
        pico.dias_amostrados +
        " dia(s) anteriores";
      valorEl.appendChild(nota);
    })
  );

  metricas.appendChild(
    construirMetricaExecutivo("Sensores indisponíveis", (valorEl) => {
      if (zona.sensores_indisponiveis === null) {
        valorEl.textContent = "Sem leitura para verificar";
      } else if (zona.sensores_indisponiveis.length === 0) {
        valorEl.textContent = "Nenhum";
      } else {
        valorEl.textContent = zona.sensores_indisponiveis.join(", ");
        valorEl.classList.add("cor-perigo");
      }
    })
  );

  metricas.appendChild(
    construirMetricaExecutivo("Equipamentos ligados", (valorEl) => {
      const equipamentos = zona.equipamentos_ligados || {
        ventiladores_ligados: 0,
        ventiladores_total: 0,
        nebulizadores_ligados: 0,
        nebulizadores_total: 0,
      };
      const linhaVentilador = document.createElement("span");
      linhaVentilador.textContent =
        "Ventiladores: " + equipamentos.ventiladores_ligados + " de " + equipamentos.ventiladores_total;
      const linhaNebulizador = document.createElement("span");
      linhaNebulizador.textContent =
        "Nebulizadores: " + equipamentos.nebulizadores_ligados + " de " + equipamentos.nebulizadores_total;
      valorEl.append(linhaVentilador, document.createElement("br"), linhaNebulizador);
    })
  );

  cartao.appendChild(metricas);

  const recomendacao = document.createElement("p");
  recomendacao.className = "executivo-recomendacao";
  recomendacao.textContent = zona.recomendacao || "";
  cartao.appendChild(recomendacao);

  const rodape = document.createElement("div");
  rodape.className = "executivo-rodape";
  const btnHistorico = document.createElement("button");
  btnHistorico.type = "button";
  btnHistorico.className = "botao botao--fantasma botao--compacto";
  btnHistorico.textContent = "Ver histórico";
  btnHistorico.addEventListener("click", () => abrirHistoricoComZona(zona.zona_id));
  rodape.appendChild(btnHistorico);
  cartao.appendChild(rodape);

  return cartao;
}

function renderizarPainelExecutivo(paineis = paineisExecutivosCache) {
  const lista = document.getElementById("executivo-lista");
  const vazio = document.getElementById("executivo-vazio");
  if (!lista || !vazio) return;

  paineisExecutivosCache = Array.isArray(paineis) ? paineis : [];
  const zonaSelecionadaId = Number(estado.zonaId);
  const painelSelecionado = Number.isFinite(zonaSelecionadaId)
    ? paineisExecutivosCache.find((zona) => Number(zona.zona_id) === zonaSelecionadaId)
    : paineisExecutivosCache[0];

  lista.textContent = "";
  vazio.classList.toggle("oculto", !!painelSelecionado);
  if (painelSelecionado) lista.appendChild(construirCartaoExecutivoZona(painelSelecionado));
}

// Uma linha de relatorio inteira funciona como link para o historico da
// zona correspondente -- tanto por clique quanto por teclado (Enter/Espaço).
function linhaAnaliseClicavel(zona) {
  const linha = document.createElement("tr");
  linha.tabIndex = 0;
  linha.setAttribute("role", "button");
  linha.setAttribute("aria-label", "Ver histórico da zona " + zona.nome);
  const abrir = (evento) => {
    const colunaStatus = evento?.target?.closest?.("td[data-status]");
    const colunaValor = evento?.target?.closest?.("td[data-valor-referencia]");
    abrirHistoricoComZona(
      zona.zona_id,
      colunaStatus?.dataset.status || "",
      colunaValor?.dataset.valorReferencia ?? null,
      colunaValor?.dataset.valorTipo || "",
      colunaValor ? zona.indice : ""
    );
  };
  linha.addEventListener("click", abrir);
  linha.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" || evento.key === " ") {
      evento.preventDefault();
      abrir();
    }
  });
  return linha;
}

function renderizarAnalisePercentuais(estatisticas) {
  const corpo = document.querySelector("#tabela-analise-percentuais tbody");
  const vazio = document.getElementById("analise-percentuais-vazio");
  if (!corpo || !vazio) return;

  corpo.textContent = "";
  vazio.classList.toggle("oculto", estatisticas.length > 0);

  estatisticas.forEach((zona) => {
    const linha = linhaAnaliseClicavel(zona);

    const tdNome = document.createElement("td");
    tdNome.textContent = zona.nome;
    linha.appendChild(tdNome);

    STATUS_HISTORICO.forEach((status) => {
      const td = document.createElement("td");
      td.dataset.status = status;
      td.title = "Ver histórico de " + zona.nome + " com status " + status;
      if (zona.percentuais) {
        td.textContent = zona.percentuais[status].toFixed(1).replace(".", ",") + "%";
        td.className = "status-" + classeStatus(status);
      } else {
        td.textContent = "—";
      }
      linha.appendChild(td);
    });

    corpo.appendChild(linha);
  });
}

function renderizarAnaliseIndices(estatisticas) {
  const corpo = document.querySelector("#tabela-analise-indices tbody");
  const vazio = document.getElementById("analise-indices-vazio");
  if (!corpo || !vazio) return;

  corpo.textContent = "";
  vazio.classList.toggle("oculto", estatisticas.length > 0);

  const formatarIndice = (valor) => (valor === null ? "—" : valor.toFixed(2).replace(".", ","));

  const configurarFiltroValor = (celula, zona, tipo, valor) => {
    if (valor === null) return;
    celula.dataset.valorReferencia = String(valor);
    celula.dataset.valorTipo = tipo;
    const rotuloTipo = ROTULO_TIPO_VALOR_HISTORICO[tipo] || "Valor";
    celula.title =
      "Ver histórico de " +
      zona.nome +
      " próximo do índice " +
      rotuloTipo.toLowerCase() +
      " " +
      formatarIndice(valor);
  };

  estatisticas.forEach((zona) => {
    const linha = linhaAnaliseClicavel(zona);

    const tdNome = document.createElement("td");
    tdNome.textContent = zona.nome;
    const tdIndice = document.createElement("td");
    tdIndice.textContent = zona.indice;
    const tdMinimo = document.createElement("td");
    tdMinimo.textContent = formatarIndice(zona.minimo);
    configurarFiltroValor(tdMinimo, zona, "minimo", zona.minimo);
    const tdMedia = document.createElement("td");
    tdMedia.textContent = formatarIndice(zona.media);
    configurarFiltroValor(tdMedia, zona, "medio", zona.media);
    const tdMaximo = document.createElement("td");
    tdMaximo.textContent = formatarIndice(zona.maximo);
    configurarFiltroValor(tdMaximo, zona, "maximo", zona.maximo);

    linha.append(tdNome, tdIndice, tdMinimo, tdMedia, tdMaximo);
    corpo.appendChild(linha);
  });
}

let estadoOperacionalCache = null;
let atualizandoControleOperacao = false;
let monitoramentoEmExecucao = false;

function rotuloEstadoAtuador(valor) {
  if (valor === null || valor === undefined) return "sem confirmação";
  return valor ? "ligado" : "desligado";
}

function falhaDoEquipamentoOperacao(equipamento, falhas) {
  const nome = String(equipamento?.nome || "");
  return (falhas || []).find((falha) => {
    const texto = String(falha);
    return texto === nome || texto.startsWith(nome + " (");
  }) || null;
}

function descricaoConexaoOperacao(equipamento) {
  if (equipamento.modo_conexao === "rtu") {
    return "RTU · " + (equipamento.porta_serial || "porta não informada") +
      " · unidade " + equipamento.unidade_id;
  }
  return "TCP · " + (equipamento.host || "host não informado") +
    (equipamento.porta ? ":" + equipamento.porta : "") +
    " · unidade " + equipamento.unidade_id;
}

function adicionarDadoEquipamentoOperacao(container, rotulo, valor) {
  const linha = document.createElement("div");
  linha.className = "operacao-equipamento-dado";
  const etiqueta = document.createElement("span");
  etiqueta.textContent = rotulo;
  const conteudo = document.createElement("strong");
  conteudo.textContent = valor;
  linha.append(etiqueta, conteudo);
  container.appendChild(linha);
}

function construirCartaoEquipamentoOperacao(equipamento, zona, zonaEstado, entradas) {
  const cartao = document.createElement("article");
  cartao.className = "operacao-equipamento-card operacao-equipamento-card--" + equipamento.tipo;
  cartao.dataset.equipamentoId = String(equipamento.id);

  const falha = falhaDoEquipamentoOperacao(equipamento, zonaEstado?.falhas);
  if (falha) cartao.classList.add("operacao-equipamento-card--falha");

  const cabecalho = document.createElement("div");
  cabecalho.className = "operacao-equipamento-cabecalho";
  const nome = document.createElement("strong");
  nome.textContent = equipamento.nome;
  const status = document.createElement("span");
  status.className = "operacao-equipamento-status";

  if (equipamento.tipo === "sensor") {
    const campo = equipamento.campo_medido;
    const valor = campo ? entradas[campo] : null;
    const possuiValor = valor !== undefined && valor !== null && valor !== "";
    status.textContent = falha ? "Falha" : possuiValor ? "Com leitura" : "Sem leitura";
    status.classList.add(falha ? "status--falha" : possuiValor ? "status--ok" : "status--neutro");
  } else {
    const confirmado = zonaEstado?.confirmado?.[equipamento.tipo];
    status.textContent = falha ? "Falha" : rotuloEstadoAtuador(confirmado);
    status.classList.add(falha ? "status--falha" : confirmado === true ? "status--ativo" : "status--neutro");
  }
  cabecalho.append(nome, status);
  cartao.appendChild(cabecalho);

  if (equipamento.tipo === "sensor") {
    const campo = equipamento.campo_medido;
    const meta = CONFIG_APP.campoMetadados[campo] || { label: campo || "Não definido", unidade: "" };
    const valor = campo ? entradas[campo] : null;
    const sensoresDoCampo = equipamentosDaZona(zona, "sensor").filter(
      (sensor) => sensor.campo_medido === campo
    ).length;
    const valorFormatado = valor === undefined || valor === null || valor === ""
      ? "--"
      : String(valor).replace(".", ",") + (meta.unidade ? " " + meta.unidade : "");
    adicionarDadoEquipamentoOperacao(cartao, "Campo", meta.label);
    adicionarDadoEquipamentoOperacao(
      cartao,
      sensoresDoCampo > 1 ? "Média do campo no ciclo" : "Valor processado no ciclo",
      valorFormatado
    );
  } else {
    adicionarDadoEquipamentoOperacao(
      cartao,
      "Comando desejado",
      rotuloEstadoAtuador(zonaEstado?.desejado?.[equipamento.tipo])
    );
    adicionarDadoEquipamentoOperacao(
      cartao,
      "Estado confirmado",
      rotuloEstadoAtuador(zonaEstado?.confirmado?.[equipamento.tipo])
    );
  }

  adicionarDadoEquipamentoOperacao(cartao, "Conexão", descricaoConexaoOperacao(equipamento));
  adicionarDadoEquipamentoOperacao(
    cartao,
    "Registrador",
    String(equipamento.tipo_registrador || "--") + " · endereço " + equipamento.endereco_registrador
  );
  if (falha) adicionarDadoEquipamentoOperacao(cartao, "Diagnóstico", falha);
  return cartao;
}

function renderizarEquipamentosOperacao(zona, zonaEstado) {
  const container = document.getElementById("operacao-equipamentos");
  if (!container) return;
  container.textContent = "";

  if (!zona) {
    container.textContent = "Nenhuma zona ativa selecionada.";
    return;
  }

  const entradas = ultimasEntradasPorZona.get(zona.id) || {};
  const tipos = [
    ["sensor", "Sensores"],
    ["ventilador", "Ventiladores"],
    ["nebulizador", "Nebulizadores"],
  ];
  tipos.forEach(([tipo, titulo]) => {
    const equipamentos = equipamentosDaZona(zona, tipo);
    const grupo = document.createElement("section");
    grupo.className = "operacao-equipamento-grupo";
    const cabecalho = document.createElement("div");
    cabecalho.className = "operacao-equipamento-grupo-cabecalho";
    const nome = document.createElement("h4");
    nome.textContent = titulo;
    const quantidade = document.createElement("span");
    quantidade.textContent = String(equipamentos.length);
    cabecalho.append(nome, quantidade);
    grupo.appendChild(cabecalho);

    const grade = document.createElement("div");
    grade.className = "operacao-equipamento-grade";
    if (!equipamentos.length) {
      const vazio = document.createElement("p");
      vazio.className = "operacao-equipamento-vazio";
      vazio.textContent = "Nenhum equipamento deste tipo cadastrado.";
      grade.appendChild(vazio);
    } else {
      equipamentos.forEach((equipamento) => {
        grade.appendChild(construirCartaoEquipamentoOperacao(equipamento, zona, zonaEstado, entradas));
      });
    }
    grupo.appendChild(grade);
    container.appendChild(grupo);
  });
}

function renderizarEventosOperacao(eventos) {
  const container = document.getElementById("operacao-eventos");
  if (!container) return;
  container.textContent = "";
  if (!Array.isArray(eventos) || !eventos.length) {
    container.textContent = "Nenhum evento operacional registrado para esta zona.";
    return;
  }
  eventos.forEach((evento) => {
    const linha = document.createElement("div");
    linha.className = "operacao-evento";
    const momento = document.createElement("time");
    momento.textContent = formatarHora(evento.criado_em);
    const texto = document.createElement("span");
    texto.textContent = evento.acao.replaceAll("_", " ");
    linha.append(momento, texto);
    container.appendChild(linha);
  });
}

function renderizarEstadoOperacional(payload) {
  estadoOperacionalCache = payload;
  const coletor = payload?.coletor || {};
  const textoColetor = coletor.online
    ? "Coletor online · heartbeat " + formatarHora(coletor.heartbeat_em)
    : "Coletor " + String(coletor.status || "offline").replaceAll("_", " ");
  ["dashboard-coletor-status", "operacao-coletor-status"].forEach((id) => {
    const elemento = document.getElementById(id);
    if (elemento) {
      elemento.textContent = textoColetor;
      elemento.classList.toggle("coletor-status--online", !!coletor.online);
      elemento.classList.toggle("coletor-status--offline", !coletor.online);
    }
  });

  const global = payload?.configuracao_global || {};
  const travaGlobal = document.getElementById("cfg-equipamentos");
  if (travaGlobal) travaGlobal.checked = !!global.habilitarEquipamentos;

  (payload?.zonas || []).forEach((estadoZona) => {
    const zona = zonaPorId(estadoZona.zona_id);
    if (zona) atualizarEquipamentoDoEstadoOperacional(zona);
  });

  const zonaEstado = (payload?.zonas || []).find(
    (item) => item.zona_id === Number(estado.zonaId)
  );
  renderizarEquipamentosOperacao(zonaPrincipalSelecionada(), zonaEstado);
  const modo = document.getElementById("operacao-modo");
  const travaZona = document.getElementById("operacao-acionamento-zona");
  if (!zonaEstado) {
    if (modo) modo.disabled = true;
    if (travaZona) travaZona.disabled = true;
    return;
  }

  if (modo) {
    modo.disabled = false;
    modo.value = zonaEstado.modo;
  }
  if (travaZona) {
    travaZona.disabled = false;
    travaZona.checked = !!zonaEstado.acionamento_habilitado;
  }
  if (zonaEstado.modo === "automatico") {
    const entradasAutomaticas = ultimasEntradasPorZona.get(zonaEstado.zona_id);
    if (entradasAutomaticas) {
      preencherEntradasDoResultado({ entradas: entradasAutomaticas });
    }
  }

  const estadoEl = document.getElementById("operacao-estado-atuadores");
  if (estadoEl) {
    const falhas = zonaEstado.falhas?.length
      ? " · Falhas: " + zonaEstado.falhas.join(", ")
      : "";
    estadoEl.textContent =
      "Desejado — ventilador: " + rotuloEstadoAtuador(zonaEstado.desejado?.ventilador) +
      ", nebulizador: " + rotuloEstadoAtuador(zonaEstado.desejado?.nebulizador) +
      " | Confirmado — ventilador: " + rotuloEstadoAtuador(zonaEstado.confirmado?.ventilador) +
      ", nebulizador: " + rotuloEstadoAtuador(zonaEstado.confirmado?.nebulizador) +
      " · Qualidade: " + zonaEstado.qualidade + falhas;
  }

  const manual = zonaEstado.modo === "manual";
  const botaoCalcular = document.getElementById("btn-calcular");
  if (botaoCalcular) botaoCalcular.disabled = !manual;
  document.querySelectorAll("[data-comando-tipo]").forEach((botao) => {
    botao.disabled =
      !manual || !global.habilitarEquipamentos || !zonaEstado.acionamento_habilitado;
  });
}

async function carregarEstadoOperacional() {
  try {
    const resposta = await fetch("/api/operacao/status");
    if (!resposta.ok) return;
    renderizarEstadoOperacional(await resposta.json());
    const zonaId = Number(estado.zonaId);
    if (Number.isFinite(zonaId)) {
      const eventosResposta = await fetch(
        "/api/operacao/eventos?limite=12&zona_id=" + zonaId
      );
      if (eventosResposta.ok) renderizarEventosOperacao(await eventosResposta.json());
    }
  } catch (erro) {
    console.error("Não foi possível consultar o estado operacional:", erro);
  }
}

// ---------------------------------------------------------------------------
// Monitoramento em tempo real (polling de 3s): so as abas Dashboard e
// Operacao mostram dado ao vivo (status do coletor, eventos, cartoes de
// zona) -- nas outras abas, rodar esse polling e trabalho de servidor
// desperdicado, multiplicado por sessao aberta (cada zona cadastrada vira
// uma chamada `/api/zonas/<id>/historico` a cada 3s, em paralelo com
// `/api/operacao/status` e `/api/operacao/eventos` -- ver
// `atualizarMonitoramento`). `abaAtivaAtual()` le a classe `.ativo` que
// `ativarAba()` ja mantem no botao da aba corrente -- nenhum estado novo
// para manter sincronizado.
const ABAS_COM_MONITORAMENTO_AO_VIVO = new Set(["principal", "operacao"]);

function abaAtivaAtual() {
  return document.querySelector("[data-aba].ativo")?.dataset.aba || "principal";
}

function monitoramentoAoVivoNecessario() {
  // `document.hidden`: a aba do NAVEGADOR esta em segundo plano (usuario
  // trocou de aba/app) -- ninguem esta olhando, independente de qual aba
  // do sistema estava selecionada.
  return !document.hidden && ABAS_COM_MONITORAMENTO_AO_VIVO.has(abaAtivaAtual());
}

async function atualizarMonitoramento() {
  if (monitoramentoEmExecucao) return;
  if (!monitoramentoAoVivoNecessario()) return;
  monitoramentoEmExecucao = true;
  try {
    await Promise.all([
      carregarEstadoOperacional(),
      carregarHistorico({ somenteTempoReal: true }),
    ]);
  } finally {
    monitoramentoEmExecucao = false;
  }
}

async function alterarControleOperacao() {
  if (atualizandoControleOperacao) return;
  const zona = zonaPrincipalSelecionada();
  if (!zona) return;
  atualizandoControleOperacao = true;
  try {
    const resposta = await fetch("/api/zonas/" + zona.id + "/controle", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        modo: document.getElementById("operacao-modo").value,
        acionamento_habilitado: document.getElementById("operacao-acionamento-zona").checked,
      }),
    });
    const corpo = await resposta.json().catch(() => ({}));
    if (!resposta.ok) mostrarErro(corpo.erro || "Não foi possível alterar o modo operacional.");
  } catch (erro) {
    mostrarErro("Falha de comunicação ao alterar o modo operacional.");
  } finally {
    atualizandoControleOperacao = false;
    await carregarEstadoOperacional();
  }
}

async function comandarAtuadorOperacao(botao) {
  const zona = zonaPrincipalSelecionada();
  if (!zona) return;
  const tipo = botao.dataset.comandoTipo;
  const ligar = botao.dataset.comandoLigar === "true";
  if (ligar && !window.confirm("Confirmar acionamento físico de " + tipo + " na zona " + zona.nome + "?")) {
    return;
  }
  botao.disabled = true;
  try {
    const resposta = await fetch("/api/zonas/" + zona.id + "/comando", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tipo, ligar }),
    });
    const corpo = await resposta.json().catch(() => ({}));
    if (!resposta.ok) mostrarErro(corpo.erro || "Não foi possível executar o comando.");
  } catch (erro) {
    mostrarErro("Falha de comunicação ao executar o comando.");
  } finally {
    await carregarEstadoOperacional();
  }
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
    await carregarEstadoOperacional();
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
// Gerador independente de dados de entrada
// ---------------------------------------------------------------------------
let referenciasDadosEntrada = {
  cidades_por_especie: {},
  peso_medio_estimado_kg: {},
  lotacao: { categorias: [], modelos: {} },
};

function definirStatusDadosEntrada(id, mensagem, erro = false) {
  const elemento = document.getElementById(id);
  if (!elemento) return;
  elemento.textContent = mensagem || "";
  elemento.classList.toggle("oculto", !mensagem);
  elemento.classList.toggle("mensagem-erro", !!erro);
}

async function respostaJsonDadosEntrada(url, opcoes = {}) {
  const resposta = await fetch(url, opcoes);
  let dados = {};
  try {
    dados = await resposta.json();
  } catch (_erro) {
    dados = {};
  }
  if (!resposta.ok) throw new Error(dados.erro || "A operação não pôde ser concluída.");
  return dados;
}

function campoConfigDadosEntrada(config, nome, rotulo, opcoes = {}) {
  const grupo = document.createElement("div");
  grupo.className = "campo-config" + (opcoes.classe ? " " + opcoes.classe : "");
  const label = document.createElement("label");
  const id = `dados-zona-${config.zona_id}-${nome}`;
  label.htmlFor = id;
  label.textContent = rotulo;
  grupo.appendChild(label);
  const input = document.createElement("input");
  input.id = id;
  input.name = nome;
  input.dataset.zonaId = config.zona_id;
  input.className = "dados-entrada-zona-campo";
  input.type = opcoes.tipo || "number";
  if (opcoes.step) input.step = opcoes.step;
  if (opcoes.min !== undefined) input.min = opcoes.min;
  if (opcoes.max !== undefined) input.max = opcoes.max;
  if (opcoes.somenteLeitura) input.readOnly = true;
  input.placeholder = opcoes.placeholder || "";
  const valor = config[nome];
  input.value = valor === null || valor === undefined ? "" : valor;
  grupo.appendChild(input);
  return grupo;
}

function campoDensidadeDadosEntrada(config) {
  const grupo = document.createElement("div");
  grupo.className = "campo-config";
  const label = document.createElement("label");
  const id = `dados-zona-${config.zona_id}-densidade_categoria`;
  label.htmlFor = id;
  label.textContent = "Nível de lotação";
  grupo.appendChild(label);
  const select = document.createElement("select");
  select.id = id;
  select.name = "densidade_categoria";
  select.dataset.zonaId = config.zona_id;
  (referenciasDadosEntrada.lotacao?.categorias || []).forEach((categoria) => {
    const option = document.createElement("option");
    option.value = categoria.valor;
    option.textContent = categoria.rotulo;
    option.selected = categoria.valor === (config.densidade_categoria || "media");
    select.appendChild(option);
  });
  grupo.appendChild(select);
  return grupo;
}

function calcularDensidadeReferenciaDadosEntrada(especie, peso) {
  const modelo = referenciasDadosEntrada.lotacao?.modelos?.[especie];
  if (!modelo || !(peso > 0)) return null;
  if (modelo.tipo === "massa_viva") {
    return Number(modelo.referencia_kg_m2) / peso;
  }
  if (modelo.tipo === "area_por_animal") {
    return 1 / Number(modelo.referencia_m2_animal);
  }
  const faixa = (modelo.faixas || []).find(
    (item) => item.peso_max_kg === null || peso <= Number(item.peso_max_kg)
  );
  return faixa ? 1 / Number(faixa.referencia_m2_animal) : null;
}

function atualizarLotacaoDadosEntrada(cartao) {
  const numero = (nome) => Number(cartao.querySelector(`[name="${nome}"]`)?.value);
  const peso = numero("peso_medio_kg");
  const area = numero("area_util_m2");
  const categoriaValor = cartao.querySelector('[name="densidade_categoria"]')?.value;
  const categoria = (referenciasDadosEntrada.lotacao?.categorias || []).find(
    (item) => item.valor === categoriaValor
  );
  const densidadeReferencia = calcularDensidadeReferenciaDadosEntrada(
    cartao.dataset.especie, peso
  );
  const campoDensidade = cartao.querySelector('[name="densidade_animais_m2"]');
  const campoQuantidade = cartao.querySelector('[name="quantidade_animais"]');
  if (!(area > 0) || !(densidadeReferencia > 0) || !categoria) {
    if (campoDensidade) campoDensidade.value = "";
    if (campoQuantidade) campoQuantidade.value = "";
    return;
  }
  const densidadeAlvo = densidadeReferencia * Number(categoria.fator);
  const quantidade = Math.floor(area * densidadeAlvo + 1e-9);
  const densidadeReal = quantidade > 0 ? quantidade / area : 0;
  if (campoDensidade) campoDensidade.value = Number(densidadeReal.toFixed(6));
  if (campoQuantidade) campoQuantidade.value = quantidade;
  const modelo = referenciasDadosEntrada.lotacao?.modelos?.[cartao.dataset.especie];
  if (campoDensidade && modelo?.fonte) campoDensidade.title = modelo.fonte;
}

function campoCidadeDadosEntrada(config) {
  const grupo = document.createElement("div");
  grupo.className = "campo-config campo-config--cidade";
  const label = document.createElement("label");
  const id = `dados-zona-${config.zona_id}-cidade_codigo_ibge`;
  label.htmlFor = id;
  label.textContent = "Cidade de referência (PPM 2024/IBGE)";
  grupo.appendChild(label);
  const select = document.createElement("select");
  select.id = id;
  select.name = "cidade_codigo_ibge";
  select.dataset.zonaId = config.zona_id;
  const inicial = document.createElement("option");
  inicial.value = "";
  inicial.textContent = "Selecione uma cidade";
  select.appendChild(inicial);
  const cidades = referenciasDadosEntrada.cidades_por_especie[config.especie] || [];
  cidades.forEach((cidade, indice) => {
    const option = document.createElement("option");
    option.value = cidade.codigo_ibge;
    option.textContent = `${indice + 1}º · ${cidade.nome}/${cidade.uf} · ${Number(cidade.efetivo_2024).toLocaleString("pt-BR")} animais`;
    option.selected = cidade.codigo_ibge === config.cidade_codigo_ibge;
    select.appendChild(option);
  });
  select.addEventListener("change", () => {
    const cidade = cidades.find((item) => item.codigo_ibge === select.value);
    if (!cidade) return;
    const cartao = select.closest(".dados-entrada-zona");
    const preencher = (nome, valor) => {
      const campo = cartao?.querySelector(`[name="${nome}"]`);
      if (campo) campo.value = valor;
    };
    preencher("latitude", cidade.latitude);
    preencher("longitude", cidade.longitude);
    preencher("altitude_m", cidade.altitude_m);
    preencher("fuso_horario", cidade.fuso_horario);
  });
  grupo.appendChild(select);
  return grupo;
}

function renderizarConfiguracoesDadosEntrada(configuracoes) {
  const container = document.getElementById("dados-entrada-zonas");
  const vazio = document.getElementById("dados-entrada-zonas-vazio");
  if (!container || !vazio) return;
  container.textContent = "";
  vazio.classList.toggle("oculto", configuracoes.length > 0);
  configuracoes.forEach((config) => {
    const cartao = document.createElement("article");
    cartao.className = "dados-entrada-zona " +
      (config.configurada ? "dados-entrada-zona--configurada" : "dados-entrada-zona--pendente");
    cartao.dataset.zonaId = config.zona_id;
    cartao.dataset.especie = config.especie;

    const cabecalho = document.createElement("div");
    cabecalho.className = "dados-entrada-zona-cabecalho";
    const titulo = document.createElement("h4");
    titulo.textContent = `${config.zona_nome} · ${CONFIG_APP.nomeEspecie[config.especie] || config.especie}`;
    cabecalho.appendChild(titulo);
    const status = document.createElement("span");
    status.className = "dados-entrada-zona-status";
    status.textContent = config.configurada ? "configurada" : "dados pendentes";
    cabecalho.appendChild(status);
    cartao.appendChild(cabecalho);

    const grade = document.createElement("div");
    grade.className = "campos-config";
    grade.appendChild(campoCidadeDadosEntrada(config));
    grade.appendChild(campoConfigDadosEntrada(config, "latitude", "Latitude", { step: "0.000001", min: -90, max: 90, placeholder: "-23.550520" }));
    grade.appendChild(campoConfigDadosEntrada(config, "longitude", "Longitude", { step: "0.000001", min: -180, max: 180, placeholder: "-46.633308" }));
    grade.appendChild(campoConfigDadosEntrada(config, "altitude_m", "Altitude (m)", { step: "0.1", min: -500, max: 9000, placeholder: "Informe a altitude" }));
    grade.appendChild(campoConfigDadosEntrada(config, "fuso_horario", "Fuso horário IANA", { tipo: "text", classe: "campo-config--fuso", placeholder: "America/Sao_Paulo" }));
    grade.appendChild(campoConfigDadosEntrada(config, "peso_medio_kg", "Peso médio (kg)", { step: "0.01", min: 0.01, max: 2000 }));
    grade.appendChild(campoConfigDadosEntrada(config, "area_util_m2", "Área útil da zona (m²)", { step: "0.1", min: 0.1, max: 10000000, placeholder: "Informe a área disponível" }));
    grade.appendChild(campoDensidadeDadosEntrada(config));
    grade.appendChild(campoConfigDadosEntrada(config, "densidade_animais_m2", "Densidade calculada (animais/m²)", { step: "0.000001", somenteLeitura: true }));
    grade.appendChild(campoConfigDadosEntrada(config, "quantidade_animais", "Quantidade estimada de animais", { step: "1", somenteLeitura: true }));
    grade.appendChild(campoConfigDadosEntrada(config, "producao_leite_kg_dia", "Leite por animal (kg/dia)", { step: "0.1", min: 0, max: 150 }));
    grade.appendChild(campoConfigDadosEntrada(config, "ordenhas_dia", "Ordenhas por dia", { step: "1", min: 0, max: 4 }));
    const peso = grade.querySelector('[name="peso_medio_kg"]');
    const pesoEstimado = referenciasDadosEntrada.peso_medio_estimado_kg[config.especie];
    if (peso && !peso.value && pesoEstimado) peso.value = pesoEstimado;
    const pesoLabel = peso?.closest(".campo-config")?.querySelector("label");
    if (pesoLabel) pesoLabel.textContent = "Peso médio estimado (kg)";
    if (config.especie !== "bovinos") {
      grade.querySelector('[name="producao_leite_kg_dia"]')?.closest(".campo-config")?.remove();
      grade.querySelector('[name="ordenhas_dia"]')?.closest(".campo-config")?.remove();
    }
    ["peso_medio_kg", "area_util_m2", "densidade_categoria"].forEach((nome) => {
      grade.querySelector(`[name="${nome}"]`)?.addEventListener(
        "input", () => atualizarLotacaoDadosEntrada(cartao)
      );
      grade.querySelector(`[name="${nome}"]`)?.addEventListener(
        "change", () => atualizarLotacaoDadosEntrada(cartao)
      );
    });
    cartao.appendChild(grade);
    container.appendChild(cartao);
    atualizarLotacaoDadosEntrada(cartao);
  });
}

function coletarConfiguracoesDadosEntrada() {
  return [...document.querySelectorAll(".dados-entrada-zona")].map((cartao) => {
    const valor = (nome) => cartao.querySelector(`[name="${nome}"]`)?.value.trim() || "";
    return {
      zona_id: Number(cartao.dataset.zonaId),
      cidade_codigo_ibge: valor("cidade_codigo_ibge"),
      latitude: valor("latitude"),
      longitude: valor("longitude"),
      altitude_m: valor("altitude_m"),
      fuso_horario: valor("fuso_horario"),
      peso_medio_kg: valor("peso_medio_kg"),
      area_util_m2: valor("area_util_m2"),
      densidade_categoria: valor("densidade_categoria"),
      producao_leite_kg_dia: valor("producao_leite_kg_dia") || "0",
      ordenhas_dia: valor("ordenhas_dia") || "0",
    };
  });
}

async function carregarConfiguracoesDadosEntrada() {
  try {
    const [configuracoes, referencias] = await Promise.all([
      respostaJsonDadosEntrada("/api/dados-entrada/configuracoes"),
      respostaJsonDadosEntrada("/api/dados-entrada/referencias"),
    ]);
    referenciasDadosEntrada = referencias;
    renderizarConfiguracoesDadosEntrada(configuracoes);
  } catch (erro) {
    definirStatusDadosEntrada("dados-entrada-status", erro.message, true);
  }
}

async function salvarConfiguracoesDadosEntrada(mostrarStatus = true) {
  const configuracoes = await respostaJsonDadosEntrada("/api/dados-entrada/configuracoes", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zonas: coletarConfiguracoesDadosEntrada() }),
  });
  renderizarConfiguracoesDadosEntrada(configuracoes);
  if (mostrarStatus) definirStatusDadosEntrada("dados-entrada-status", "Parâmetros das zonas salvos.");
  return configuracoes;
}

function renderizarExecucoesDadosEntrada(payload) {
  const tbody = document.querySelector("#tabela-dados-entrada-execucoes tbody");
  const vazio = document.getElementById("dados-entrada-execucoes-vazio");
  const resumo = document.getElementById("dados-entrada-resumo-banco");
  if (!tbody || !vazio || !resumo) return;
  const execucoes = payload.execucoes || [];
  tbody.textContent = "";
  vazio.classList.toggle("oculto", execucoes.length > 0);
  const totalGerado = execucoes.reduce((soma, item) => soma + Number(item.total_medicoes || 0), 0);
  const totalCopiado = execucoes.reduce((soma, item) => soma + Number(item.medicoes_copiadas || 0), 0);
  resumo.textContent = `${totalGerado.toLocaleString("pt-BR")} medições geradas em ${payload.destino || "PostgreSQL (schema dados_entrada)"}; ${totalCopiado.toLocaleString("pt-BR")} já copiadas para o histórico.`;
  execucoes.forEach((execucao) => {
    const tr = document.createElement("tr");
    const valores = [
      execucao.id,
      `${execucao.data_inicio} a ${execucao.data_fim}`,
      `${execucao.intervalo_minutos} min`,
      execucao.total_zonas,
      execucao.total_medicoes,
      execucao.medicoes_copiadas || 0,
      execucao.status,
    ];
    valores.forEach((valor) => {
      const td = document.createElement("td");
      td.textContent = valor;
      tr.appendChild(td);
    });
    const acoes = document.createElement("td");
    if (execucao.status === "concluida") {
      const link = document.createElement("a");
      link.className = "botao botao--fantasma botao--compacto";
      link.href = `/api/dados-entrada/exportar.csv?execucao_id=${execucao.id}`;
      link.textContent = "CSV";
      acoes.appendChild(link);
      if (Number(execucao.medicoes_copiadas || 0) < Number(execucao.total_medicoes || 0)) {
        const copiar = document.createElement("button");
        copiar.type = "button";
        copiar.className = "botao botao--primario botao--compacto";
        copiar.textContent = "Copiar para histórico";
        copiar.addEventListener("click", () => copiarExecucaoParaHistorico(execucao.id, copiar));
        acoes.appendChild(copiar);
      }
    } else if (execucao.erro) {
      acoes.title = execucao.erro;
      acoes.textContent = "Ver erro";
    }
    tr.appendChild(acoes);
    tbody.appendChild(tr);
  });
}

async function copiarExecucaoParaHistorico(execucaoId, botao) {
  if (!confirm(`Copiar as medições da geração ${execucaoId} para o histórico?`)) return;
  botao.disabled = true;
  try {
    const resultado = await respostaJsonDadosEntrada("/api/dados-entrada/copiar-para-historico", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ execucao_id: execucaoId }),
    });
    definirStatusDadosEntrada(
      "dados-entrada-arquivo-status",
      `${resultado.novas_copiadas} novas medições copiadas para o histórico.`
    );
    await carregarExecucoesDadosEntrada();
    await carregarHistoricoPersistido({ manterJanelaFinal: false });
  } catch (erro) {
    definirStatusDadosEntrada("dados-entrada-arquivo-status", erro.message, true);
    botao.disabled = false;
  }
}

async function carregarExecucoesDadosEntrada() {
  try {
    const payload = await respostaJsonDadosEntrada("/api/dados-entrada/execucoes");
    renderizarExecucoesDadosEntrada(payload);
  } catch (erro) {
    definirStatusDadosEntrada("dados-entrada-status", erro.message, true);
  }
}

async function carregarDadosEntrada() {
  const dataFinal = document.getElementById("dados-entrada-data-final");
  if (dataFinal) {
    const limite = new Date();
    limite.setHours(12, 0, 0, 0);
    limite.setDate(limite.getDate() - 8);
    const iso = [
      limite.getFullYear(),
      String(limite.getMonth() + 1).padStart(2, "0"),
      String(limite.getDate()).padStart(2, "0"),
    ].join("-");
    dataFinal.max = iso;
    if (!dataFinal.value || dataFinal.value > iso) dataFinal.value = iso;
  }
  await Promise.all([carregarConfiguracoesDadosEntrada(), carregarExecucoesDadosEntrada()]);
}

async function gerarDadosEntrada(evento) {
  evento.preventDefault();
  const botao = document.getElementById("btn-gerar-dados-entrada");
  botao.disabled = true;
  definirStatusDadosEntrada("dados-entrada-status", "Validando as zonas e baixando o clima histórico. Aguarde...");
  try {
    await salvarConfiguracoesDadosEntrada(false);
    const payload = {
      dias: Number(document.getElementById("dados-entrada-dias").value),
      intervalo_minutos: Number(document.getElementById("dados-entrada-intervalo").value),
      data_final: document.getElementById("dados-entrada-data-final").value || null,
      semente: Number(document.getElementById("dados-entrada-semente").value),
    };
    const resultado = await respostaJsonDadosEntrada("/api/dados-entrada/gerar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    definirStatusDadosEntrada(
      "dados-entrada-status",
      `Geração ${resultado.execucao_id} concluída: ${resultado.total_medicoes} medições em ${resultado.total_zonas} zonas.`
    );
    await carregarExecucoesDadosEntrada();
  } catch (erro) {
    definirStatusDadosEntrada("dados-entrada-status", erro.message, true);
  } finally {
    botao.disabled = false;
  }
}

async function apagarHistoricoDiretoDadosEntrada() {
  const confirmacao = document.getElementById("dados-entrada-confirmacao-historico").value;
  if (!confirm("Apagar definitivamente todas as medições do histórico?")) return;
  try {
    const resultado = await respostaJsonDadosEntrada("/api/dados-entrada/apagar-historico", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmacao }),
    });
    definirStatusDadosEntrada("dados-entrada-arquivo-status", `${resultado.medicoes_apagadas} medições apagadas do histórico.`);
    await carregarHistoricoPersistido({ manterJanelaFinal: false });
  } catch (erro) {
    definirStatusDadosEntrada("dados-entrada-arquivo-status", erro.message, true);
  }
}

async function apagarDadosGerados() {
  if (!confirm("Apagar todas as séries geradas? As medições já copiadas para o histórico serão preservadas.")) return;
  const confirmacao = prompt("Digite APAGAR para confirmar:", "");
  if (confirmacao === null) return;
  try {
    const resultado = await respostaJsonDadosEntrada("/api/dados-entrada/medicoes", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmacao }),
    });
    definirStatusDadosEntrada("dados-entrada-status", `${resultado.medicoes_apagadas} medições geradas foram apagadas.`);
    await carregarExecucoesDadosEntrada();
  } catch (erro) {
    definirStatusDadosEntrada("dados-entrada-status", erro.message, true);
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
  document.getElementById("btn-backup-banco")?.addEventListener("click", fazerBackupBanco);
  document.getElementById("zona-principal")?.addEventListener("change", (evento) => {
    selecionarZonaPrincipal(evento.target.value);
  });
  document.getElementById("zona-dashboard")?.addEventListener("change", (evento) => {
    selecionarZonaPrincipal(evento.target.value);
  });
  document.getElementById("zona-executivo")?.addEventListener("change", (evento) => {
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
    agendarSalvarConfiguracoes();
  });
  document.getElementById("cfg-equipamentos").addEventListener("change", async () => {
    await salvarConfiguracoesPersistidas();
    await carregarEstadoOperacional();
  });
  document.getElementById("cfg-emails").addEventListener("change", (e) => {
    document.getElementById("wrap-email-destino").classList.toggle("oculto", !e.target.checked);
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
  // Configuracoes de uso e de sistema sao persistidas automaticamente.
  document
    .querySelectorAll(
      "#aba-configuracoes input, #aba-configuracoes select, " +
        "#aba-sistema input, #aba-sistema select"
    )
    .forEach((controle) => {
      controle.addEventListener("change", agendarSalvarConfiguracoes);
      if (["number", "email"].includes(controle.type)) {
        controle.addEventListener("input", agendarSalvarConfiguracoes);
      }
    });
  document.getElementById("operacao-modo")?.addEventListener("change", alterarControleOperacao);
  document
    .getElementById("operacao-acionamento-zona")
    ?.addEventListener("change", alterarControleOperacao);
  document.querySelectorAll("[data-comando-tipo]").forEach((botao) => {
    botao.addEventListener("click", () => comandarAtuadorOperacao(botao));
  });
  window.setInterval(atualizarMonitoramento, 3000);
  // Complementa o `if (document.hidden)` dentro de `atualizarMonitoramento`:
  // ao voltar para a aba do navegador (ex.: usuario alternou de app e
  // voltou), atualiza na hora em vez de esperar ate 3s parado num estado
  // desatualizado. Sem custo quando a aba do SISTEMA ativa nao e
  // Dashboard/Operacao -- `monitoramentoAoVivoNecessario()` ja filtra isso.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) atualizarMonitoramento();
  });

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

  document.getElementById("form-dados-entrada-gerar")?.addEventListener("submit", gerarDadosEntrada);
  document.getElementById("btn-salvar-config-dados-entrada")?.addEventListener("click", async () => {
    try {
      await salvarConfiguracoesDadosEntrada(true);
    } catch (erro) {
      definirStatusDadosEntrada("dados-entrada-status", erro.message, true);
    }
  });
  document.getElementById("btn-apagar-historico-direto")?.addEventListener("click", apagarHistoricoDiretoDadosEntrada);
  document.getElementById("btn-apagar-dados-gerados")?.addEventListener("click", apagarDadosGerados);
});
