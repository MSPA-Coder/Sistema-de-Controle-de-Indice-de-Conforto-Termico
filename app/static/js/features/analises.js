// Painéis e tabelas da aba Análises.
//
// A feature retém somente seu cache de painel; seleção, navegação e metadados
// da interface são recebidos pelo ponto de composição.
export function criarAnalises({
  obterConfiguracao,
  obterEstado,
  abrirHistoricoComZona,
  classeStatus,
  rotuloStatus,
  statusHistorico,
  rotuloTipoValorHistorico,
  documento = document,
  requisitar = (...argumentos) => fetch(...argumentos),
}) {
  const CONFIG_APP = obterConfiguracao();
  const estado = obterEstado();
  const document = documento;
  const fetch = requisitar;
  const STATUS_HISTORICO = statusHistorico;
  const ROTULO_TIPO_VALOR_HISTORICO = rotuloTipoValorHistorico;
  let paineisExecutivosCache = [];
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
  const nomesEspecie = CONFIG_APP.nomeEspecie || {};
  badgeEspecie.textContent = nomesEspecie[zona.especie] || zona.especie;
  tituloGrupo.appendChild(badgeEspecie);

  const badgeStatus = document.createElement("span");
  if (zona.status_atual) {
    badgeStatus.className = "faixa-status executivo-status-badge faixa-" + classeStatus(zona.status_atual);
    badgeStatus.textContent = rotuloStatus(zona.status_atual).toUpperCase();
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
      td.title = "Ver histórico de " + zona.nome + " com status " + rotuloStatus(status);
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
  return {
    carregar: carregarAnalises,
    renderizar: renderizarPainelExecutivo,
  };
}
