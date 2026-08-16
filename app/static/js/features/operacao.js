export function criarOperacao({
  obterConfiguracao,
  obterEstado,
  obterZonaPrincipal,
  obterZonaPorId,
  obterEquipamentosDaZona,
  obterUltimasEntradas,
  obterUltimoStatus,
  atualizarEquipamento,
  preencherEntradasDoResultado,
  formatarHora,
  mostrarErro,
  carregarHistoricoTempoReal,
  salvarConfiguracoes,
  documento = document,
  requisitar = fetch,
  confirmar = window.confirm.bind(window),
  agendarPolling = window.setInterval.bind(window),
}) {
  const CONFIG_APP = obterConfiguracao();
  const estado = obterEstado();
  const document = documento;
  const fetch = requisitar;
  let estadoOperacionalCache = null;
  let atualizandoControleOperacao = false;
  let monitoramentoEmExecucao = false;

  function obterEstadoDaZona(zonaId) {
    return (estadoOperacionalCache?.zonas || []).find((item) => item.zona_id === Number(zonaId));
  }

  function atualizarEquipamentoDaZona(zona, status = null) {
    if (!zona || !estadoOperacionalCache) return;
    const estadoZona = obterEstadoDaZona(zona.id);
    if (!estadoZona) return;
    atualizarEquipamento(
      {
        ventilador: estadoZona.confirmado?.ventilador === true,
        nebulizador: estadoZona.confirmado?.nebulizador === true,
        intensidade: estadoZona.intensidade,
      },
      status || obterUltimoStatus(zona.id) || null,
      zona
    );
  }

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
      const sensoresDoCampo = obterEquipamentosDaZona(zona, "sensor").filter(
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

    const entradas = obterUltimasEntradas(zona.id) || {};
    const tipos = [
      ["sensor", "Sensores"],
      ["ventilador", "Ventiladores"],
      ["nebulizador", "Nebulizadores"],
    ];
    tipos.forEach(([tipo, titulo]) => {
      const equipamentos = obterEquipamentosDaZona(zona, tipo);
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
      const zona = obterZonaPorId(estadoZona.zona_id);
      if (zona) atualizarEquipamentoDaZona(zona);
    });

    const zonaEstado = (payload?.zonas || []).find(
      (item) => item.zona_id === Number(estado.zonaId)
    );
    renderizarEquipamentosOperacao(obterZonaPrincipal(), zonaEstado);
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
    const entradasAutomaticas = obterUltimasEntradas(zonaEstado.zona_id);
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
        carregarHistoricoTempoReal(),
      ]);
    } finally {
      monitoramentoEmExecucao = false;
    }
  }

  async function alterarControleOperacao() {
    if (atualizandoControleOperacao) return;
    const zona = obterZonaPrincipal();
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
    const zona = obterZonaPrincipal();
    if (!zona) return;
    const tipo = botao.dataset.comandoTipo;
    const ligar = botao.dataset.comandoLigar === "true";
    if (ligar && !confirmar("Confirmar acionamento físico de " + tipo + " na zona " + zona.nome + "?")) {
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
  function inicializarConfiguracao() {
    document.getElementById("cfg-equipamentos").addEventListener("change", async () => {
      await salvarConfiguracoes();
      await carregarEstadoOperacional();
    });
  }

  function inicializar() {
    document.getElementById("operacao-modo")?.addEventListener("change", alterarControleOperacao);
    document
      .getElementById("operacao-acionamento-zona")
      ?.addEventListener("change", alterarControleOperacao);
    document.querySelectorAll("[data-comando-tipo]").forEach((botao) => {
      botao.addEventListener("click", () => comandarAtuadorOperacao(botao));
    });
    agendarPolling(atualizarMonitoramento, 3000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) atualizarMonitoramento();
    });
  }

  return {
    atualizarEquipamentoDaZona,
    atualizarMonitoramento,
    carregar: carregarEstadoOperacional,
    inicializar,
    inicializarConfiguracao,
    obterEstadoDaZona,
    renderizarEquipamentos: renderizarEquipamentosOperacao,
  };
}
