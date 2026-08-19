export function criarHistorico({
  obterConfiguracao,
  obterEstado,
  obterZonas,
  obterZonaPrincipal,
  ativarAba,
  classeStatus,
  corStatus,
  corCampoEntrada,
  formatarHora,
  formatarDataHoraCurta,
  statusHistorico,
  rotuloTipoValorHistorico,
  limiteJanela,
  graficos,
  funcoesHistorico,
  documento = document,
  requisitar = fetch,
  obterChart = () => window.Chart,
}) {
  const CONFIG_APP = obterConfiguracao();
  const estado = obterEstado();
  const document = documento;
  const fetch = requisitar;
  const Chart = obterChart();
  const STATUS_HISTORICO = statusHistorico;
  const ROTULO_TIPO_VALOR_HISTORICO = rotuloTipoValorHistorico;
  const HISTORICO_JANELA_LEITURAS = limiteJanela;
  const {
    opcoesGrafico,
    aplicarExtremosEscalaHistorico,
    aplicarEscalaDinamica,
    criarOuAtualizarGrafico,
  } = graficos;
  const {
    normalizarHistoricosPorIndice,
    historicosPorIndiceDasLeituras,
    camposDasLeituras,
    rotulosHistorico,
    textoLegendaPeriodo,
    removerLegendaGraficoHistorico,
    opcoesGraficoHistorico,
  } = funcoesHistorico;

  let graficosHistoricoPorIndice = new Map();
  let graficoHistoricoEntradas = null;
  let assinaturaGraficosHistorico = "";
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
  let historicoScrollTimeoutId = null;
  const zonasConsolidadasNestaSessao = new Set();
  const RESOLUCOES_TENDENCIA = [
    { valor: "bruto", texto: "Tempo real (leitura bruta)" },
    { valor: "15min", texto: "Agregado de 15 em 15 min" },
    { valor: "hora", texto: "Resumo por hora" },
  ];
  let resolucaoTendencia = "bruto";
  let graficoTendenciaResolucao = null;
  let tendenciaResolucaoCarregamentoId = 0;

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
    if (!obterZonas().length) {
      filtroHistoricoZona = "";
      return false;
    }
    if (filtroHistoricoZona && obterZonas().some((zona) => String(zona.id) === filtroHistoricoZona)) {
      return true;
    }
    const zonaDashboard = obterZonaPrincipal();
    filtroHistoricoZona = String(zonaDashboard?.id || obterZonas()[0].id);
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
      obterZonas().forEach((zona) => {
        const option = document.createElement("option");
        option.value = String(zona.id);
        option.textContent = zona.nome;
        selectZona.appendChild(option);
      });
      if (!obterZonas().length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Nenhuma zona cadastrada";
        selectZona.appendChild(option);
      }
      selectZona.disabled = !obterZonas().length;
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
      const zonaParaConsolidar = filtroHistoricoZona || obterZonaPrincipal()?.id;
      if (zonaParaConsolidar && !zonasConsolidadasNestaSessao.has(String(zonaParaConsolidar))) {
        const consolidacao = await fetch(`/api/zonas/${zonaParaConsolidar}/consolidar-historico`, {
          method: "POST",
        });
        if (consolidacao.ok) zonasConsolidadasNestaSessao.add(String(zonaParaConsolidar));
      }
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

  function redimensionarGraficos() {
    graficosHistoricoPorIndice.forEach((grafico) => grafico.resize());
    if (graficoHistoricoEntradas) graficoHistoricoEntradas.resize();
  }

  function resetarPaginacao() {
    historicoPaginaAtual = 1;
  }

  return {
    abrirComZona: abrirHistoricoComZona,
    carregar: carregarHistoricoPersistido,
    inicializar: inicializarHistorico,
    redimensionarGraficos,
    resetarPaginacao,
  };
}
