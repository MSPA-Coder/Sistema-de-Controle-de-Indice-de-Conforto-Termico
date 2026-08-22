export function criarEntradaCalculo({
  obterConfiguracao,
  obterEstado,
  obterZonaPrincipal,
  camposEntradaIndiceAtual,
  campoCalculado,
  ordenarCamposInterface,
  corCampoEntrada,
  esconderErro,
  mostrarErro,
  atualizarErroLinhaZonaPrincipal,
  atualizarResultado,
  resetarPainelResultado,
  recarregarHistorico,
  recarregarSensores,
  documento = document,
  requisitar = fetch,
  // `window.sharedauth.confirmar` devolve Promise<boolean> -- ao contrario do
  // `window.confirm` sincrono que isto substituiu. Ver ATENCAO em
  // `limparHistorico`, unico chamador: precisa de `await`.
  confirmar = (opcoes) => window.sharedauth.confirmar(opcoes),
  avisar = (opcoes) => window.sharedauth.avisar(opcoes),
}) {
  const CONFIG_APP = obterConfiguracao();
  const estado = obterEstado();
  const document = documento;
  const fetch = requisitar;
  let salvamentoConfigTimeoutId = null;
  let smtpSenhaJaConfigurada = false;

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
    if (!obterZonaPrincipal()) return;
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

  function renderCamposEntradaDashboard(entradas, zona = obterZonaPrincipal()) {
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
    const zona = obterZonaPrincipal();
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
  async function limparHistorico() {
    // Modal decide; o campo de texto com "APAGAR" continua existindo e
    // validado no servidor (`app_factory.confirmacao_de_exclusao_valida`) --
    // o modal não substitui a digitação, só evita chegar nela sem querer.
    const confirmacao = document.getElementById("confirmacao-limpar-historico").value;
    const confirmado = await confirmar({
      mensagem:
        "Esta ação apaga todas as leituras salvas no banco e limpa os gráficos/tabelas do histórico " +
        "nesta sessão.\n\nZonas, equipamentos e configurações serão preservados. A ação não pode ser " +
        "desfeita; faça um backup antes se precisar guardar os dados.",
      titulo: "Limpar histórico",
      severidade: "error",
    });
    if (!confirmado) return;

    try {
      const resposta = await fetch("/api/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmacao }),
      });
      const corpo = await resposta.json().catch(() => ({}));
      if (!resposta.ok || !corpo.ok) {
        avisar({ mensagem: corpo.erro || "Não foi possível limpar o histórico.", severidade: "error" });
        return;
      }
      resetarPainelResultado();
      await recarregarHistorico();
      avisar({
        mensagem: "Histórico limpo. Zonas, equipamentos e configurações foram preservados.",
        severidade: "success",
      });
    } catch (erro) {
      console.error("Erro ao limpar historico:", erro);
      avisar({ mensagem: "Falha de comunicação ao limpar o histórico.", severidade: "error" });
    }
  }

  async function fazerBackupBanco() {
    const botao = document.getElementById("btn-backup-banco");
    if (botao) botao.disabled = true;
    try {
      const resposta = await fetch("/api/backup-banco", { method: "POST" });
      const corpo = await resposta.json().catch(() => ({}));
      if (!resposta.ok || !corpo.ok) {
        avisar({ mensagem: corpo.erro || "Não foi possível criar o backup do banco.", severidade: "error" });
        return;
      }
      avisar({
        mensagem: "Backup criado no diretório do banco: " + corpo.backup.arquivo,
        severidade: "success",
      });
    } catch (erro) {
      console.error("Erro ao criar backup do banco:", erro);
      avisar({ mensagem: "Falha de comunicação ao criar o backup do banco.", severidade: "error" });
    } finally {
      if (botao) botao.disabled = false;
    }
  }

  async function consolidarHistorico() {
    const botao = document.getElementById("btn-consolidar-historico");
    if (botao) botao.disabled = true;
    try {
      const resposta = await fetch("/api/consolidar-historico", { method: "POST" });
      const corpo = await resposta.json().catch(() => ({}));
      if (!resposta.ok || !corpo.ok) {
        avisar({ mensagem: corpo.erro || "Não foi possível consolidar o histórico.", severidade: "error" });
        return;
      }
      const total = Array.isArray(corpo.resultados) ? corpo.resultados.length : 0;
      avisar({ mensagem: `Consolidação concluída para ${total} zona(s).`, severidade: "success" });
    } catch (erro) {
      console.error("Erro ao consolidar histórico:", erro);
      avisar({ mensagem: "Falha de comunicação ao consolidar o histórico.", severidade: "error" });
    } finally {
      if (botao) botao.disabled = false;
    }
  }
  function inicializar() {
    document.getElementById("btn-calcular").addEventListener("click", calcular);
    document.getElementById("btn-limpar").addEventListener("click", limparHistorico);
    document.getElementById("btn-backup-banco")?.addEventListener("click", fazerBackupBanco);
    document.getElementById("btn-consolidar-historico")?.addEventListener("click", consolidarHistorico);
    document.getElementById("cfg-coletar").addEventListener("change", () => {
      recarregarSensores();
      agendarSalvarConfiguracoes();
    });
    document.getElementById("cfg-emails").addEventListener("change", (evento) => {
      document.getElementById("wrap-email-destino").classList.toggle("oculto", !evento.target.checked);
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
  }

  function inicializarPersistencia() {
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
    document.getElementById("cfg-zonas-simulado").addEventListener("change", agendarSalvarConfiguracoes);
  }

  return {
    calcular,
    carregarConfiguracoes: carregarConfiguracoesPersistidas,
    fazerBackupBanco,
    inicializar,
    inicializarPersistencia,
    limparHistorico,
    preencherEntradasDoResultado,
    renderCamposEntrada,
    renderCamposEntradaDashboard,
    salvarConfiguracoes: salvarConfiguracoesPersistidas,
  };
}
