// Cadastro, seleção e configuração de zonas e equipamentos.
//
// O cache operacional de zonas continua na composição da interface. Esta
// feature guarda somente o estado transitório dos filtros e diálogos.
export function criarCadastroZonas({
  obterZonas,
  obterConfiguracao,
  obterZonaPrincipalId,
  definirZonaPrincipal,
  recarregarZonas,
  documento = document,
  requisitar = (...argumentos) => fetch(...argumentos),
  // Assinatura de `window.sharedauth.confirmar`: recebe as mesmas opcoes
  // (mensagem/titulo/severidade) e devolve Promise<boolean> -- diferente do
  // `window.confirm` que isto substituiu, que era sincrono. Ver ATENCAO em
  // `excluirZona`/`excluirEquipamento`: todo chamador precisa de `await`.
  confirmar = (opcoes) => window.sharedauth.confirmar(opcoes),
  avisar = (opcoes) => window.sharedauth.avisar(opcoes),
}) {
  const CONFIG_APP = obterConfiguracao();
  const document = documento;
  const fetch = requisitar;
  let zonaEmEdicaoId = null;
  let equipamentoEmEdicao = null;
  let zonaCadastroSelecionadaId = null;
  let filtroZonaCadastro = "todas";

  const ROTULOS_TIPO_EQUIPAMENTO = {
    sensor: "Sensores",
    ventilador: "Ventiladores",
    nebulizador: "Nebulizadores",
  };
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
      option.textContent = obterZonas().length ? "Nenhuma zona neste filtro" : "Nenhuma zona cadastrada";
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
    if (filtroZonaCadastro === "ativas") return obterZonas().filter((zona) => zona.ativa);
    if (filtroZonaCadastro === "inativas") return obterZonas().filter((zona) => !zona.ativa);
    return [...obterZonas()];
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

  function renderizarZonas() {
    const lista = document.getElementById("zonas-lista");
    const vazio = document.getElementById("zonas-vazio");

    lista.textContent = "";
    const zona = zonaCadastroSelecionada();
    vazio.classList.toggle("oculto", !!zona);
    vazio.textContent = obterZonas().length
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
    document.getElementById("zona-ciclos-expiracao-leitura").value = String(
      zona?.ciclos_expiracao_leitura || 3
    );
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
      ciclos_expiracao_leitura: Number(document.getElementById("zona-ciclos-expiracao-leitura").value),
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
      if (dados.ativa) definirZonaPrincipal(dados.id);
      document.getElementById("dialog-zona").close();
      await recarregarZonas();
    } catch (erro) {
      mostrarErroDialog("zona-form-erro", "Falha de comunicação com o servidor.");
    }
  }

  async function excluirZona(zona) {
    // A exclusao remove em cascata equipamentos, controle operacional e
    // agregados da zona. Leituras brutas permanecem no banco com a referencia
    // da zona anulada; por isso a confirmacao descreve ambos os efeitos.
    const confirmado = await confirmar({
      mensagem:
        'Excluir a zona "' + zona.nome + '"? Saem junto os equipamentos cadastrados, ' +
        "o modo e as travas de operação, e o histórico consolidado desta zona " +
        "(tendências de 15 min e por hora). As leituras brutas já gravadas continuam " +
        "no banco, mas perdem o vínculo com a zona.",
      titulo: "Excluir zona",
      severidade: "error",
    });
    if (!confirmado) return;
    try {
      const resposta = await fetch("/api/zonas/" + zona.id, { method: "DELETE" });
      if (!resposta.ok) {
        avisar({ mensagem: "Não foi possível excluir a zona.", severidade: "error" });
        return;
      }
      if (zonaCadastroSelecionadaId === zona.id) zonaCadastroSelecionadaId = null;
      if (obterZonaPrincipalId() === zona.id) definirZonaPrincipal(null);
      await recarregarZonas();
    } catch (erro) {
      console.error("Falha ao excluir zona:", erro);
      avisar({ mensagem: "Falha de comunicação ao excluir a zona.", severidade: "error" });
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
      await recarregarZonas();
    } catch (erro) {
      mostrarErroDialog("equipamento-form-erro", "Falha de comunicação com o servidor.");
    }
  }

  async function excluirEquipamento(zonaId, equipamento) {
    const confirmado = await confirmar({
      mensagem: 'Excluir o equipamento "' + equipamento.nome + '"? Esta ação não pode ser desfeita.',
      titulo: "Excluir equipamento",
      severidade: "error",
    });
    if (!confirmado) return;
    try {
      const resposta = await fetch(
        "/api/zonas/" + zonaId + "/equipamentos/" + equipamento.id,
        { method: "DELETE" }
      );
      if (!resposta.ok) {
        avisar({ mensagem: "Não foi possível excluir o equipamento.", severidade: "error" });
        return;
      }
      await recarregarZonas();
    } catch (erro) {
      console.error("Falha ao excluir equipamento:", erro);
      avisar({ mensagem: "Falha de comunicação ao excluir o equipamento.", severidade: "error" });
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

  function inicializar() {
    document.getElementById("zona-cadastro")?.addEventListener("change", (evento) => {
      selecionarZonaCadastro(evento.target.value);
    });
    document.getElementById("filtro-zona-cadastro")?.addEventListener("change", (evento) => {
      selecionarFiltroZonaCadastro(evento.target.value);
    });
    document.getElementById("btn-nova-zona")?.addEventListener("click", () => abrirDialogZona());
    document.getElementById("btn-cancelar-zona")?.addEventListener("click", () => {
      document.getElementById("dialog-zona").close();
    });
    document.getElementById("form-zona")?.addEventListener("submit", salvarZona);
    document.getElementById("zona-especie")?.addEventListener("change", atualizarSelectIndiceZona);
    document.getElementById("btn-cancelar-equipamento")?.addEventListener("click", () => {
      document.getElementById("dialog-equipamento").close();
    });
    document.getElementById("form-equipamento")?.addEventListener("submit", salvarEquipamento);
    document.getElementById("equip-tipo")?.addEventListener("change", atualizarCamposDialogEquipamento);
    document
      .getElementById("equip-modo-conexao")
      ?.addEventListener("change", atualizarCamposDialogEquipamento);
    document
      .getElementById("btn-testar-conexao-equipamento")
      ?.addEventListener("click", testarConexaoEquipamentoAtual);
  }

  function atualizar() {
    renderizarSelectZonaCadastro();
    renderizarZonas();
  }

  return { atualizar, inicializar };
}
