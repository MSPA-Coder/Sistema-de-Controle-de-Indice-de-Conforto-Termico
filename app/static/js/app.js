// =============================================================================
// Front-end do sistema de conforto termico
// =============================================================================

import { configurarFetchComCsrf } from "./core/api.js";
import { carregarConfiguracaoInterface, CONFIG_APP } from "./core/interface-config.js";
import { criarAnalises } from "./features/analises.js";
import { criarCadastroZonas } from "./features/cadastro-zonas.js";
import { criarDashboardZonas } from "./features/dashboard-zonas.js";
import { criarDadosEntrada } from "./features/dados-entrada.js";
import { criarEntradaCalculo } from "./features/entrada-calculo.js";
import { criarHistorico } from "./features/historico.js";
import { criarOperacao } from "./features/operacao.js";

configurarFetchComCsrf();

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

let audioCtx = null;
let analises;
let cadastroZonas;
let dashboardZonas;
let dadosEntrada;
let entradaCalculo;
let historico;
let operacao;

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

function camposDoIndiceAtual() {
  return camposEntradaIndiceAtual();
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
    setTimeout(() => dashboardZonas.redimensionarGraficos(), 0);
  }

  // Dashboard e Operacao dependem do polling de 3s (`atualizarMonitoramento`)
  // para dado ao vivo; dispara na hora ao entrar na aba em vez de esperar o
  // proximo tick, senao a tela mostraria ate 3s de estado desatualizado
  // (ou "aguardando heartbeat") logo ao trocar de aba.
  if (aba === "principal" || aba === "operacao") {
    operacao.atualizarMonitoramento();
  }

  if (aba === "analises") {
    analises.carregar();
  }

  if (aba === "historico") {
    historico.carregar({ manterJanelaFinal: true });
    setTimeout(() => historico.redimensionarGraficos(), 0);
  }

  if (aba === "zonas") {
    dashboardZonas.carregarZonas();
  }

  if (aba === "dados-entrada") {
    dadosEntrada.carregar();
  }
}

function inicializarAbas() {
  document.querySelectorAll("[data-aba]").forEach((botao) => {
    botao.addEventListener("click", () => ativarAba(botao.dataset.aba));
  });
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

  moverCampo("confirmacao-limpar-historico", configuracoesHistorico);
  if (configuracoesHistorico && limparHistorico) configuracoesHistorico.appendChild(limparHistorico);
}

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
  try {
    await carregarConfiguracaoInterface();
  } catch (erro) {
    console.error("Nao foi possivel carregar a configuracao da interface:", erro);
    mostrarErro("Nao foi possivel carregar a configuracao da interface.");
    return;
  }

  dashboardZonas = criarDashboardZonas({
    obterConfiguracao: () => CONFIG_APP,
    obterEstado: () => estado,
    obterEntradaCalculo: () => entradaCalculo,
    obterHistorico: () => historico,
    obterOperacao: () => operacao,
    obterAnalises: () => analises,
    obterCadastroZonas: () => cadastroZonas,
    esconderErro,
    mostrarErro,
    tocarSom,
    classeStatus,
    corStatus,
    corCampoEntrada,
    formatarHora,
    formatarDataHoraCurta,
    camposDaEspecie,
    normalizarChaveTexto,
    rotuloIntensidade,
    iconeVentilador: ICONE_VENTILADOR,
    iconeNebulizador: ICONE_NEBULIZADOR,
    iconeSensor: ICONE_SENSOR,
    iconesPorEquipamentoAtuador: ICONES_POR_EQUIPAMENTO_ATUADOR,
    iconesPorSensor: ICONES_POR_SENSOR,
    graficos: {
      opcoesGrafico,
      aplicarEscalaDinamica,
      chavesCronologicas,
      criarOuAtualizarGrafico,
    },
  });

  historico = criarHistorico({
    obterConfiguracao: () => CONFIG_APP,
    obterEstado: () => estado,
    obterZonas: () => dashboardZonas.obterZonas(),
    obterZonaPrincipal: () => dashboardZonas.zonaPrincipalSelecionada(),
    ativarAba,
    classeStatus,
    corStatus,
    corCampoEntrada,
    formatarHora,
    formatarDataHoraCurta,
    statusHistorico: STATUS_HISTORICO,
    rotuloTipoValorHistorico: ROTULO_TIPO_VALOR_HISTORICO,
    limiteJanela: HISTORICO_JANELA_LEITURAS,
    graficos: {
      opcoesGrafico,
      aplicarExtremosEscalaHistorico,
      aplicarEscalaDinamica,
      criarOuAtualizarGrafico,
    },
    funcoesHistorico: {
      normalizarHistoricosPorIndice,
      historicosPorIndiceDasLeituras,
      camposDasLeituras,
      rotulosHistorico,
      textoLegendaPeriodo,
      removerLegendaGraficoHistorico,
      opcoesGraficoHistorico,
    },
  });

  entradaCalculo = criarEntradaCalculo({
    obterConfiguracao: () => CONFIG_APP,
    obterEstado: () => estado,
    obterZonaPrincipal: () => dashboardZonas.zonaPrincipalSelecionada(),
    camposEntradaIndiceAtual,
    campoCalculado,
    ordenarCamposInterface,
    corCampoEntrada,
    esconderErro,
    mostrarErro,
    atualizarErroLinhaZonaPrincipal: (...argumentos) => dashboardZonas.atualizarErroLinhaZonaPrincipal(...argumentos),
    atualizarResultado: (...argumentos) => dashboardZonas.atualizarResultado(...argumentos),
    resetarPainelResultado: () => dashboardZonas.resetarPainelResultado(),
    recarregarHistorico: (...argumentos) => dashboardZonas.carregarHistorico(...argumentos),
    recarregarSensores: () => dashboardZonas.atualizarSensorRemoto(),
  });

  operacao = criarOperacao({
    obterConfiguracao: () => CONFIG_APP,
    obterEstado: () => estado,
    obterZonaPrincipal: () => dashboardZonas.zonaPrincipalSelecionada(),
    obterZonaPorId: (zonaId) => dashboardZonas.zonaPorId(zonaId),
    obterEquipamentosDaZona: (...argumentos) => dashboardZonas.equipamentosDaZona(...argumentos),
    obterUltimasEntradas: (zonaId) => dashboardZonas.obterUltimasEntradas(zonaId),
    obterUltimoStatus: (zonaId) => dashboardZonas.obterUltimoStatus(zonaId),
    atualizarEquipamento: (...argumentos) => dashboardZonas.atualizarEquipamento(...argumentos),
    atualizarAtualidadeZonas: (...argumentos) => dashboardZonas.atualizarAtualidadeZonas(...argumentos),
    preencherEntradasDoResultado: (...argumentos) => entradaCalculo.preencherEntradasDoResultado(...argumentos),
    formatarHora,
    mostrarErro,
    carregarHistoricoTempoReal: () => dashboardZonas.carregarHistorico({ somenteTempoReal: true }),
    salvarConfiguracoes: (...argumentos) => entradaCalculo.salvarConfiguracoes(...argumentos),
  });

  analises = criarAnalises({
    obterConfiguracao: () => CONFIG_APP,
    obterEstado: () => estado,
    abrirHistoricoComZona: (...argumentos) => historico.abrirComZona(...argumentos),
    classeStatus,
    statusHistorico: STATUS_HISTORICO,
    rotuloTipoValorHistorico: ROTULO_TIPO_VALOR_HISTORICO,
  });

  cadastroZonas = criarCadastroZonas({
    obterZonas: () => dashboardZonas.obterZonas(),
    obterConfiguracao: () => CONFIG_APP,
    obterZonaPrincipalId: () => estado.zonaId,
    definirZonaPrincipal: (zonaId) => {
      estado.zonaId = zonaId;
    },
    recarregarZonas: () => dashboardZonas.carregarZonas(),
  });

  dadosEntrada = criarDadosEntrada({
    obterConfiguracao: () => CONFIG_APP,
    recarregarHistorico: (...opcoes) => historico.carregar(...opcoes),
  });

  moverControlesParaConfiguracoes();
  inicializarAbas();

  historico.inicializar();
  await entradaCalculo.carregarConfiguracoes();
  dashboardZonas.atualizarEquipamento(null, null);
  dashboardZonas.atualizarSensorRemoto();
  await dashboardZonas.carregarZonas();

  document.getElementById("zona-principal")?.addEventListener("change", (evento) => {
    dashboardZonas.selecionarZonaPrincipal(evento.target.value);
  });
  document.getElementById("zona-dashboard")?.addEventListener("change", (evento) => {
    dashboardZonas.selecionarZonaPrincipal(evento.target.value);
  });
  document.getElementById("zona-executivo")?.addEventListener("change", (evento) => {
    dashboardZonas.selecionarZonaPrincipal(evento.target.value);
  });

  entradaCalculo.inicializar();
  operacao.inicializarConfiguracao();
  entradaCalculo.inicializarPersistencia();
  operacao.inicializar();

  cadastroZonas.inicializar();
  dadosEntrada.inicializar();
});
