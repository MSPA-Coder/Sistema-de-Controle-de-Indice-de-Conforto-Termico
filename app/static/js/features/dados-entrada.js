// Gerador independente de dados de entrada.
//
// A feature recebe seus pontos de contato com o restante da interface para não
// depender de estado global do entrypoint. As escritas continuam usando o
// fetch configurado pelo módulo central de API, inclusive com CSRF.
export function criarDadosEntrada({
  obterConfiguracao,
  recarregarHistorico,
  documento = document,
  requisitar = (...argumentos) => fetch(...argumentos),
  // `window.sharedauth.confirmar` devolve Promise<boolean> -- ao contrario do
  // `window.confirm` sincrono que isto substituiu. Os tres chamadores
  // (`copiarExecucaoParaHistorico`, `apagarHistoricoDireto`,
  // `apagarDadosGerados`) precisam de `await`.
  confirmar = (opcoes) => window.sharedauth.confirmar(opcoes),
  avisar = (opcoes) => window.sharedauth.avisar(opcoes),
  // `solicitar` continua sincrono de proposito: e o campo de "digite APAGAR"
  // que o modal NAO substitui (ver `apagarDadosGerados`), so a decisao vira
  // modal.
  solicitar = window.prompt.bind(window),
}) {
  let referencias = {
    cidades_por_especie: {},
    peso_medio_estimado_kg: {},
    lotacao: { categorias: [], modelos: {} },
  };

  function definirStatus(id, mensagem, erro = false) {
    const elemento = documento.getElementById(id);
    if (!elemento) return;
    elemento.textContent = mensagem || "";
    elemento.classList.toggle("oculto", !mensagem);
    elemento.classList.toggle("mensagem-erro", !!erro);
  }

  async function respostaJson(url, opcoes = {}) {
    const resposta = await requisitar(url, opcoes);
    let dados = {};
    try {
      dados = await resposta.json();
    } catch (_erro) {
      dados = {};
    }
    if (!resposta.ok) throw new Error(dados.erro || "A operação não pôde ser concluída.");
    return dados;
  }

  function campoConfig(config, nome, rotulo, opcoes = {}) {
    const grupo = documento.createElement("div");
    grupo.className = "campo-config" + (opcoes.classe ? " " + opcoes.classe : "");
    const label = documento.createElement("label");
    const id = "dados-zona-" + config.zona_id + "-" + nome;
    label.htmlFor = id;
    label.textContent = rotulo;
    grupo.appendChild(label);
    const input = documento.createElement("input");
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

  function campoDensidade(config) {
    const grupo = documento.createElement("div");
    grupo.className = "campo-config";
    const label = documento.createElement("label");
    const id = "dados-zona-" + config.zona_id + "-densidade_categoria";
    label.htmlFor = id;
    label.textContent = "Nível de lotação";
    grupo.appendChild(label);
    const select = documento.createElement("select");
    select.id = id;
    select.name = "densidade_categoria";
    select.dataset.zonaId = config.zona_id;
    (referencias.lotacao?.categorias || []).forEach((categoria) => {
      const option = documento.createElement("option");
      option.value = categoria.valor;
      option.textContent = categoria.rotulo;
      option.selected = categoria.valor === (config.densidade_categoria || "media");
      select.appendChild(option);
    });
    grupo.appendChild(select);
    return grupo;
  }

  function calcularDensidadeReferencia(especie, peso) {
    const modelo = referencias.lotacao?.modelos?.[especie];
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

  function atualizarLotacao(cartao) {
    const numero = (nome) => Number(cartao.querySelector('[name="' + nome + '"]')?.value);
    const peso = numero("peso_medio_kg");
    const area = numero("area_util_m2");
    const categoriaValor = cartao.querySelector('[name="densidade_categoria"]')?.value;
    const categoria = (referencias.lotacao?.categorias || []).find(
      (item) => item.valor === categoriaValor
    );
    const densidadeReferencia = calcularDensidadeReferencia(cartao.dataset.especie, peso);
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
    const modelo = referencias.lotacao?.modelos?.[cartao.dataset.especie];
    if (campoDensidade && modelo?.fonte) campoDensidade.title = modelo.fonte;
  }

  function campoCidade(config) {
    const grupo = documento.createElement("div");
    grupo.className = "campo-config campo-config--cidade";
    const label = documento.createElement("label");
    const id = "dados-zona-" + config.zona_id + "-cidade_codigo_ibge";
    label.htmlFor = id;
    label.textContent = "Cidade de referência (PPM 2024/IBGE)";
    grupo.appendChild(label);
    const select = documento.createElement("select");
    select.id = id;
    select.name = "cidade_codigo_ibge";
    select.dataset.zonaId = config.zona_id;
    const inicial = documento.createElement("option");
    inicial.value = "";
    inicial.textContent = "Selecione uma cidade";
    select.appendChild(inicial);
    const cidades = referencias.cidades_por_especie[config.especie] || [];
    cidades.forEach((cidade, indice) => {
      const option = documento.createElement("option");
      option.value = cidade.codigo_ibge;
      option.textContent =
        indice + 1 + "º · " + cidade.nome + "/" + cidade.uf + " · " +
        Number(cidade.efetivo_2024).toLocaleString("pt-BR") + " animais";
      option.selected = cidade.codigo_ibge === config.cidade_codigo_ibge;
      select.appendChild(option);
    });
    select.addEventListener("change", () => {
      const cidade = cidades.find((item) => item.codigo_ibge === select.value);
      if (!cidade) return;
      const cartao = select.closest(".dados-entrada-zona");
      const preencher = (nome, valor) => {
        const campo = cartao?.querySelector('[name="' + nome + '"]');
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

  function renderizarConfiguracoes(configuracoes) {
    const container = documento.getElementById("dados-entrada-zonas");
    const vazio = documento.getElementById("dados-entrada-zonas-vazio");
    if (!container || !vazio) return;
    container.textContent = "";
    vazio.classList.toggle("oculto", configuracoes.length > 0);
    configuracoes.forEach((config) => {
      const cartao = documento.createElement("article");
      cartao.className =
        "dados-entrada-zona " +
        (config.configurada
          ? "dados-entrada-zona--configurada"
          : "dados-entrada-zona--pendente");
      cartao.dataset.zonaId = config.zona_id;
      cartao.dataset.especie = config.especie;

      const cabecalho = documento.createElement("div");
      cabecalho.className = "dados-entrada-zona-cabecalho";
      const titulo = documento.createElement("h4");
      const configuracao = obterConfiguracao();
      titulo.textContent =
        config.zona_nome +
        " · " +
        (configuracao.nomeEspecie[config.especie] || config.especie);
      cabecalho.appendChild(titulo);
      const status = documento.createElement("span");
      status.className = "dados-entrada-zona-status";
      status.textContent = config.configurada ? "configurada" : "dados pendentes";
      cabecalho.appendChild(status);
      cartao.appendChild(cabecalho);

      const grade = documento.createElement("div");
      grade.className = "campos-config";
      grade.appendChild(campoCidade(config));
      grade.appendChild(
        campoConfig(config, "latitude", "Latitude", {
          step: "0.000001",
          min: -90,
          max: 90,
          placeholder: "-23.550520",
        })
      );
      grade.appendChild(
        campoConfig(config, "longitude", "Longitude", {
          step: "0.000001",
          min: -180,
          max: 180,
          placeholder: "-46.633308",
        })
      );
      grade.appendChild(
        campoConfig(config, "altitude_m", "Altitude (m)", {
          step: "0.1",
          min: -500,
          max: 9000,
          placeholder: "Informe a altitude",
        })
      );
      grade.appendChild(
        campoConfig(config, "fuso_horario", "Fuso horário IANA", {
          tipo: "text",
          classe: "campo-config--fuso",
          placeholder: "America/Sao_Paulo",
        })
      );
      grade.appendChild(
        campoConfig(config, "peso_medio_kg", "Peso médio (kg)", {
          step: "0.01",
          min: 0.01,
          max: 2000,
        })
      );
      grade.appendChild(
        campoConfig(config, "area_util_m2", "Área útil da zona (m²)", {
          step: "0.1",
          min: 0.1,
          max: 10000000,
          placeholder: "Informe a área disponível",
        })
      );
      grade.appendChild(campoDensidade(config));
      grade.appendChild(
        campoConfig(config, "densidade_animais_m2", "Densidade calculada (animais/m²)", {
          step: "0.000001",
          somenteLeitura: true,
        })
      );
      grade.appendChild(
        campoConfig(config, "quantidade_animais", "Quantidade estimada de animais", {
          step: "1",
          somenteLeitura: true,
        })
      );
      grade.appendChild(
        campoConfig(config, "producao_leite_kg_dia", "Leite por animal (kg/dia)", {
          step: "0.1",
          min: 0,
          max: 150,
        })
      );
      grade.appendChild(
        campoConfig(config, "ordenhas_dia", "Ordenhas por dia", {
          step: "1",
          min: 0,
          max: 4,
        })
      );
      const peso = grade.querySelector('[name="peso_medio_kg"]');
      const pesoEstimado = referencias.peso_medio_estimado_kg[config.especie];
      if (peso && !peso.value && pesoEstimado) peso.value = pesoEstimado;
      const pesoLabel = peso?.closest(".campo-config")?.querySelector("label");
      if (pesoLabel) pesoLabel.textContent = "Peso médio estimado (kg)";
      if (config.especie !== "bovinos") {
        grade.querySelector('[name="producao_leite_kg_dia"]')?.closest(".campo-config")?.remove();
        grade.querySelector('[name="ordenhas_dia"]')?.closest(".campo-config")?.remove();
      }
      ["peso_medio_kg", "area_util_m2", "densidade_categoria"].forEach((nome) => {
        grade
          .querySelector('[name="' + nome + '"]')
          ?.addEventListener("input", () => atualizarLotacao(cartao));
        grade
          .querySelector('[name="' + nome + '"]')
          ?.addEventListener("change", () => atualizarLotacao(cartao));
      });
      cartao.appendChild(grade);
      container.appendChild(cartao);
      atualizarLotacao(cartao);
    });
  }

  function coletarConfiguracoes() {
    return [...documento.querySelectorAll(".dados-entrada-zona")].map((cartao) => {
      const valor = (nome) => cartao.querySelector('[name="' + nome + '"]')?.value.trim() || "";
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

  async function carregarConfiguracoes() {
    try {
      const [configuracoes, novasReferencias] = await Promise.all([
        respostaJson("/api/dados-entrada/configuracoes"),
        respostaJson("/api/dados-entrada/referencias"),
      ]);
      referencias = novasReferencias;
      renderizarConfiguracoes(configuracoes);
    } catch (erro) {
      definirStatus("dados-entrada-status", erro.message, true);
    }
  }

  async function salvarConfiguracoes(mostrarStatus = true) {
    const configuracoes = await respostaJson("/api/dados-entrada/configuracoes", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ zonas: coletarConfiguracoes() }),
    });
    renderizarConfiguracoes(configuracoes);
    // `mostrarStatus=false` quando chamado de dentro de `gerar()`: a
    // geracao ja tem a propria mensagem de resultado, um toast a mais aqui
    // seria ruido duplicado para a mesma acao do usuario.
    if (mostrarStatus) avisar({ mensagem: "Parâmetros das zonas salvos.", severidade: "success" });
    return configuracoes;
  }

  function renderizarExecucoes(payload) {
    const tbody = documento.querySelector("#tabela-dados-entrada-execucoes tbody");
    const vazio = documento.getElementById("dados-entrada-execucoes-vazio");
    const resumo = documento.getElementById("dados-entrada-resumo-banco");
    if (!tbody || !vazio || !resumo) return;
    const execucoes = payload.execucoes || [];
    tbody.textContent = "";
    vazio.classList.toggle("oculto", execucoes.length > 0);
    const totalGerado = execucoes.reduce(
      (soma, item) => soma + Number(item.total_medicoes || 0),
      0
    );
    const totalCopiado = execucoes.reduce(
      (soma, item) => soma + Number(item.medicoes_copiadas || 0),
      0
    );
    resumo.textContent =
      totalGerado.toLocaleString("pt-BR") +
      " medições geradas em " +
      (payload.destino || "PostgreSQL (schema dados_entrada)") +
      "; " +
      totalCopiado.toLocaleString("pt-BR") +
      " já copiadas para o histórico.";
    execucoes.forEach((execucao) => {
      const tr = documento.createElement("tr");
      const valores = [
        execucao.id,
        execucao.data_inicio + " a " + execucao.data_fim,
        execucao.intervalo_minutos + " min",
        execucao.total_zonas,
        execucao.total_medicoes,
        execucao.medicoes_copiadas || 0,
        execucao.status,
      ];
      valores.forEach((valor) => {
        const td = documento.createElement("td");
        td.textContent = valor;
        tr.appendChild(td);
      });
      const acoes = documento.createElement("td");
      if (execucao.status === "concluida") {
        const link = documento.createElement("a");
        link.className = "botao botao--fantasma botao--compacto";
        link.href = "/api/dados-entrada/exportar.csv?execucao_id=" + execucao.id;
        link.textContent = "CSV";
        acoes.appendChild(link);
        if (Number(execucao.medicoes_copiadas || 0) < Number(execucao.total_medicoes || 0)) {
          const copiar = documento.createElement("button");
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
    // "warning", nao "error": nao apaga nem sobrescreve nada (a leitura
    // gerada continua existindo), so nao ha como desfazer so a copia -- ela
    // sai junto se o historico for apagado depois (ver rodape 6 do
    // INVENTARIO_OPERACOES_DESTRUTIVAS, secao 7.3).
    const confirmado = await confirmar({
      mensagem: "Copiar as medições da geração " + execucaoId + " para o histórico?",
      titulo: "Copiar para o histórico",
      severidade: "warning",
    });
    if (!confirmado) return;
    botao.disabled = true;
    try {
      const resultado = await respostaJson("/api/dados-entrada/copiar-para-historico", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ execucao_id: execucaoId }),
      });
      avisar({
        mensagem: resultado.novas_copiadas + " novas medições copiadas para o histórico.",
        severidade: "success",
      });
      await carregarExecucoes();
      await recarregarHistorico({ manterJanelaFinal: false });
    } catch (erro) {
      avisar({ mensagem: erro.message, severidade: "error" });
      botao.disabled = false;
    }
  }

  async function carregarExecucoes() {
    try {
      const payload = await respostaJson("/api/dados-entrada/execucoes");
      renderizarExecucoes(payload);
    } catch (erro) {
      definirStatus("dados-entrada-status", erro.message, true);
    }
  }

  async function carregar() {
    const dataFinal = documento.getElementById("dados-entrada-data-final");
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
    await Promise.all([carregarConfiguracoes(), carregarExecucoes()]);
  }

  async function gerar(evento) {
    evento.preventDefault();
    const botao = documento.getElementById("btn-gerar-dados-entrada");
    botao.disabled = true;
    definirStatus(
      "dados-entrada-status",
      "Validando as zonas e baixando o clima histórico. Aguarde..."
    );
    try {
      await salvarConfiguracoes(false);
      const payload = {
        dias: Number(documento.getElementById("dados-entrada-dias").value),
        intervalo_minutos: Number(documento.getElementById("dados-entrada-intervalo").value),
        data_final: documento.getElementById("dados-entrada-data-final").value || null,
        semente: Number(documento.getElementById("dados-entrada-semente").value),
      };
      const resultado = await respostaJson("/api/dados-entrada/gerar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      // O "Validando... Aguarde" fica no banner enquanto a geração roda --
      // um toast não serve para progresso, só para o resultado final. Limpa
      // o banner e mostra o resultado como toast.
      definirStatus("dados-entrada-status", "");
      avisar({
        mensagem:
          "Geração " +
          resultado.execucao_id +
          " concluída: " +
          resultado.total_medicoes +
          " medições em " +
          resultado.total_zonas +
          " zonas.",
        severidade: "success",
      });
      await carregarExecucoes();
    } catch (erro) {
      definirStatus("dados-entrada-status", "");
      avisar({ mensagem: erro.message, severidade: "error" });
    } finally {
      botao.disabled = false;
    }
  }

  async function apagarHistoricoDireto() {
    // Uma das duas rotas com trava dupla: modal decide, campo "APAGAR"
    // continua sendo validado no servidor (ver `apagar_historico` em
    // `dados_entrada_rotas.py`). O modal não substitui a digitação.
    const confirmacao = documento.getElementById("dados-entrada-confirmacao-historico").value;
    const confirmado = await confirmar({
      mensagem: "Apagar definitivamente todas as medições do histórico?",
      titulo: "Apagar histórico",
      severidade: "error",
    });
    if (!confirmado) return;
    try {
      const resultado = await respostaJson("/api/dados-entrada/apagar-historico", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmacao }),
      });
      avisar({
        mensagem: resultado.medicoes_apagadas + " medições apagadas do histórico.",
        severidade: "success",
      });
      await recarregarHistorico({ manterJanelaFinal: false });
    } catch (erro) {
      avisar({ mensagem: erro.message, severidade: "error" });
    }
  }

  async function apagarDadosGerados() {
    // A terceira rota com "APAGAR" validado no servidor (ver `excluir_medicoes`
    // em `dados_entrada_rotas.py`) -- aqui o campo de texto forte é um
    // `prompt()` nativo em vez de um `<input>` na página, mas a regra é a
    // mesma: o modal decide, o texto digitado continua sendo a confirmação
    // forte que o servidor valida.
    const confirmado = await confirmar({
      mensagem: "Apagar todas as séries geradas? As medições já copiadas para o histórico serão preservadas.",
      titulo: "Apagar dados gerados",
      severidade: "error",
    });
    if (!confirmado) return;
    const confirmacao = solicitar("Digite APAGAR para confirmar:", "");
    if (confirmacao === null) return;
    try {
      const resultado = await respostaJson("/api/dados-entrada/medicoes", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmacao }),
      });
      avisar({
        mensagem: resultado.medicoes_apagadas + " medições geradas foram apagadas.",
        severidade: "success",
      });
      await carregarExecucoes();
    } catch (erro) {
      avisar({ mensagem: erro.message, severidade: "error" });
    }
  }

  function inicializar() {
    documento.getElementById("form-dados-entrada-gerar")?.addEventListener("submit", gerar);
    documento
      .getElementById("btn-salvar-config-dados-entrada")
      ?.addEventListener("click", async () => {
        try {
          await salvarConfiguracoes(true);
        } catch (erro) {
          avisar({ mensagem: erro.message, severidade: "error" });
        }
      });
    documento
      .getElementById("btn-apagar-historico-direto")
      ?.addEventListener("click", apagarHistoricoDireto);
    documento
      .getElementById("btn-apagar-dados-gerados")
      ?.addEventListener("click", apagarDadosGerados);
  }

  return { carregar, inicializar };
}
