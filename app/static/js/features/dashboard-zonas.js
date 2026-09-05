export function criarDashboardZonas({
  obterConfiguracao,
  obterEstado,
  obterEntradaCalculo,
  obterHistorico,
  obterOperacao,
  obterAnalises,
  obterCadastroZonas,
  esconderErro,
  mostrarErro,
  tocarSom,
  classeStatus,
  corStatus,
  rotuloStatus,
  corCampoEntrada,
  formatarHora,
  formatarDataHoraCurta,
  camposDaEspecie,
  normalizarChaveTexto,
  rotuloIntensidade,
  iconeVentilador,
  iconeNebulizador,
  iconeSensor,
  iconesPorEquipamentoAtuador,
  iconesPorSensor,
  graficos,
  documento = document,
  requisitar = fetch,
  obterChart = () => window.Chart,
}) {
  const CONFIG_APP = obterConfiguracao();
  const estado = obterEstado();
  const document = documento;
  const fetch = requisitar;
  const Chart = obterChart();
  const {
    opcoesGrafico,
    aplicarEscalaDinamica,
    chavesCronologicas,
    criarOuAtualizarGrafico,
  } = graficos;
  let graficoEntradas = null;
  let graficosIndicePrincipalPorZona = new Map();
  let assinaturasIndicePrincipalPorZona = new Map();
  let ultimosResultados = null;
  let ultimosHistoricosGrafico = {};
  let ultimoStatusPorZona = new Map();
  let ultimasEntradasPorZona = new Map();
  let ultimaLeituraPorZona = new Map();
  let atualidadePorZona = new Map();
  let zonasCache = [];

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
        await obterHistorico().carregar({ manterJanelaFinal: true });
      }
      return;
    }
    try {
      const resposta = await fetch("/api/zonas/historicos-recentes?limite=30");
      if (!resposta.ok) throw new Error("Falha ao carregar os históricos recentes das zonas.");
      const historicos = await resposta.json();
      zonasPrincipal.forEach((zonaItem) => {
        const historico = historicos[String(zonaItem.id)] || [];
        atualizarLinhaComHistoricoZonaPrincipal(zonaItem, historico);
        atualizarGraficoIndiceZonaPrincipal(zonaItem, historico);
      });

      if (zona) {
        const historicoSelecionado = historicos[String(zona.id)] || [];
        ultimosHistoricosGrafico = { [zona.indice]: historicoSelecionado };
        atualizarGraficoEntradas(ultimosHistoricosGrafico);
      } else {
        ultimosHistoricosGrafico = {};
      }
      if (!opcoes.somenteTempoReal) {
        await obterHistorico().carregar({ manterJanelaFinal: true });
      }
    } catch (erro) {
      /* nao critico */
    }
  }
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
    obterEntradaCalculo().renderCamposEntradaDashboard(null);
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
    ultimaLeituraPorZona.set(zona.id, ultima);
    ultimoStatusPorZona.set(zona.id, ultima.status);
    ultimasEntradasPorZona.set(zona.id, ultima.entradas || {});
    const atualidade = atualidadePorZona.get(zona.id);
    const desatualizada = atualidade?.leitura_atual === false;
    const classe = classeStatus(ultima.status);

    const readoutValor = elementoLinhaZonaPrincipal(zona.id, "readout-valor");
    if (readoutValor) {
      readoutValor.textContent = Number(ultima.valor).toFixed(2).replace(".", ",");
      readoutValor.className = desatualizada ? "readout-valor" : "readout-valor cor-" + classe;
    }
    const readoutIndice = elementoLinhaZonaPrincipal(zona.id, "readout-indice");
    if (readoutIndice) readoutIndice.textContent = ultima.indice || zona.indice;

    const faixa = elementoLinhaZonaPrincipal(zona.id, "faixa-status");
    const faixaTexto = elementoLinhaZonaPrincipal(zona.id, "faixa-status-texto");
    if (faixa) faixa.className = desatualizada
      ? "faixa-status faixa-status--vazio"
      : "faixa-status faixa-" + classe;
    if (faixaTexto) faixaTexto.textContent = desatualizada
      ? "DADO DESATUALIZADO"
      : rotuloStatus(ultima.status).toUpperCase();

    const mensagem = elementoLinhaZonaPrincipal(zona.id, "mensagem-orientacao");
    if (mensagem) mensagem.textContent = desatualizada
      ? "Última leitura em " + formatarDataHoraCurta(ultima.criado_em) + ". O status térmico não é atual."
      : "Última leitura registrada às " + formatarHora(ultima.criado_em) + ".";
    if (desatualizada) {
      atualizarEquipamento(null, null, zona);
    } else {
      obterOperacao().atualizarEquipamentoDaZona(zona, ultima.status);
    }
    if (zona.id === estado.zonaId) {
      obterEntradaCalculo().renderCamposEntradaDashboard(ultima.entradas, zona);
      const zonaEstado = obterOperacao().obterEstadoDaZona(zona.id);
      const modo = zonaEstado?.modo;
      if (modo === "automatico") {
        obterEntradaCalculo().preencherEntradasDoResultado({ entradas: ultima.entradas || {} });
      }
      obterOperacao().renderizarEquipamentos(zona, zonaEstado);
    }
  }

  function atualizarResultado(dados) {
    const zona = zonaPorId(dados.zona_id) || zonaPrincipalSelecionada();
    if (!zona) return;
    const zonaSelecionada = zona.id === estado.zonaId;
    if (zonaSelecionada) {
      estado.especie = dados.especie || zona.especie || estado.especie;
      estado.indice = dados.indice || zona.indice || estado.indice;
      obterEntradaCalculo().preencherEntradasDoResultado(dados);
      obterEntradaCalculo().renderCamposEntradaDashboard(dados.entradas, zona);
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
    if (faixaTexto) faixaTexto.textContent = rotuloStatus(selecionado.status).toUpperCase();

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
        ", " + rotuloStatus(selecionado.status) + "), mas os gráficos não puderam ser desenhados. " +
        "Detalhes no console do navegador (F12 → Console)."
      );
    }

    obterHistorico().carregar({ manterJanelaFinal: true });

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
    const totalVentiladores = equipamentosDaZona(zona, "ventilador").length * iconesPorEquipamentoAtuador;
    const totalNebulizadores = equipamentosDaZona(zona, "nebulizador").length * iconesPorEquipamentoAtuador;

    renderizarIconesEquipamento(
      elementoLinhaZonaPrincipal(zona?.id, "icones-ventilador"),
      iconeVentilador,
      "Ventilador",
      ventiladorLigado,
      intensidade,
      status,
      totalVentiladores,
      ventiladorLigado ? totalVentiladores : 0
    );
    renderizarIconesEquipamento(
      elementoLinhaZonaPrincipal(zona?.id, "icones-nebulizador"),
      iconeNebulizador,
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

  function atualizarSensorRemotoZona(zona) {
    const checkboxColeta = document.getElementById("cfg-coletar");
    const sensorLigado = !!(checkboxColeta && checkboxColeta.checked && zona && zona.ativa);

    renderizarIconesEquipamento(
      elementoLinhaZonaPrincipal(zona?.id, "icones-sensor"),
      iconeSensor,
      "Sensor",
      sensorLigado,
      null,
      null,
      equipamentosDaZona(zona, "sensor").length * iconesPorSensor,
      sensorLigado ? equipamentosDaZona(zona, "sensor").length * iconesPorSensor : 0
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
      obterEntradaCalculo().renderCamposEntrada();
      renderizarLinhasZonasPrincipal();
      obterAnalises().renderizar();
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
    obterEntradaCalculo().renderCamposEntrada();
    renderizarLinhasZonasPrincipal();
    resetarPainelResultado();
    obterAnalises().renderizar();
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
    obterHistorico().resetarPaginacao();
    obterEntradaCalculo().renderCamposEntrada();
    renderizarLinhasZonasPrincipal();
    resetarPainelResultado();
    obterAnalises().renderizar();
    await carregarHistorico();
    await obterOperacao().carregar();
  }

  async function carregarZonas() {
    try {
      const resposta = await fetch("/api/zonas");
      if (!resposta.ok) {
        throw new Error(`A API devolveu ${resposta.status} ao carregar as zonas.`);
      }
      zonasCache = await resposta.json();
      renderizarSelectZonaPrincipal();
      obterCadastroZonas().atualizar();
      await carregarHistorico();
      await obterOperacao().carregar();
    } catch (erro) {
      console.error("Não foi possível carregar as zonas:", erro);
      mostrarErro("Não foi possível carregar as zonas monitoradas. Consulte o console do navegador para detalhes.");
    }
  }
  function redimensionarGraficos() {
    graficosIndicePrincipalPorZona.forEach((grafico) => grafico.resize());
    if (graficoEntradas) graficoEntradas.resize();
  }

  function obterUltimasEntradas(zonaId) {
    return ultimasEntradasPorZona.get(zonaId) || {};
  }

  function obterUltimoStatus(zonaId) {
    return ultimoStatusPorZona.get(zonaId);
  }

  function atualizarAtualidadeZonas(zonas) {
    atualidadePorZona = new Map((zonas || []).map((item) => [item.zona_id, item]));
    zonasCache.forEach((zona) => {
      const ultima = ultimaLeituraPorZona.get(zona.id);
      if (ultima) atualizarLinhaComHistoricoZonaPrincipal(zona, [ultima]);
    });
  }

  return {
    atualizarEquipamento,
    atualizarAtualidadeZonas,
    atualizarErroLinhaZonaPrincipal,
    atualizarResultado,
    atualizarSensorRemoto,
    carregarHistorico,
    carregarZonas,
    equipamentosDaZona,
    obterUltimasEntradas,
    obterUltimoStatus,
    obterZonas: () => zonasCache,
    redimensionarGraficos,
    resetarPainelResultado,
    selecionarZonaPrincipal,
    zonaPorId,
    zonaPrincipalSelecionada,
  };
}
