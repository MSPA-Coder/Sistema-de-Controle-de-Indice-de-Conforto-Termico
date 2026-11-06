/* Traduções de interface fornecidas pelo servidor; não traduz dados do usuário. */
(function () {
  'use strict';
  const elemento = document.getElementById('i18n-js');
  const catalogo = elemento ? JSON.parse(elemento.textContent) : {};

  window.t = function (texto, valores) {
    if (typeof texto !== 'string') return texto == null ? '' : String(texto);
    const traducao = Object.prototype.hasOwnProperty.call(catalogo, texto) ? catalogo[texto] : texto;
    return traducao.replace(/%\((\w+)\)s/g, function (original, nome) {
      return valores && Object.prototype.hasOwnProperty.call(valores, nome) ? String(valores[nome]) : original;
    });
  };

  // Algumas APIs mantêm mensagens em português por contrato e incluem nelas
  // nomes e números. Só padrões completos e conhecidos são traduzidos; o
  // conteúdo variável é preservado e mensagens desconhecidas passam intactas.
  window.traduzirErro = function (texto) {
    if (typeof texto !== 'string' || !Object.keys(catalogo).length) return texto;
    const traduzido = window.t(texto);
    if (traduzido !== texto) return traduzido;
    const padroes = [
      [/^Informe um valor numérico para ([a-z_]+)\.$/, 'Informe um valor numérico para %(campo)s.', ['campo']],
      [/^([a-z_]+) deve estar entre (-?[\d.]+) e (-?[\d.]+)\.$/, '%(campo)s deve estar entre %(minimo)s e %(maximo)s.', ['campo', 'minimo', 'maximo']],
      [/^Selecione uma das cidades de referência da zona '(.+)'\.$/, "Selecione uma das cidades de referência da zona '%(zona)s'.", ['zona']],
      [/^Selecione uma categoria de densidade para a zona '(.+)'\.$/, "Selecione uma categoria de densidade para a zona '%(zona)s'.", ['zona']],
      [/^A área útil da zona '(.+)' é insuficiente para um animal com o peso e a densidade selecionados\.$/, "A área útil da zona '%(zona)s' é insuficiente para um animal com o peso e a densidade selecionados.", ['zona']],
      [/^A lotação calculada da zona '(.+)' excede 1\.000\.000 de animais\.$/, "A lotação calculada da zona '%(zona)s' excede 1.000.000 de animais.", ['zona']],
      [/^Fuso horário inválido: (.+)\. Use um nome IANA, como America\/Sao_Paulo\.$/, 'Fuso horário inválido: %(fuso)s. Use um nome IANA, como America/Sao_Paulo.', ['fuso']],
      [/^Produção de leite e ordenhas só se aplicam à zona bovina '(.+)'\.$/, "Produção de leite e ordenhas só se aplicam à zona bovina '%(zona)s'.", ['zona']],
      [/^Informe ao menos uma ordenha diária para a zona '(.+)'\.$/, "Informe ao menos uma ordenha diária para a zona '%(zona)s'.", ['zona']],
      [/^Zona (\d+) não encontrada\.$/, 'Zona %(id)s não encontrada.', ['id']],
      [/^Execução (\d+) não encontrada\.$/, 'Execução %(id)s não encontrada.', ['id']],
    ];
    for (const [padrao, fonte, nomes] of padroes) {
      const partes = texto.match(padrao);
      if (!partes) continue;
      const valores = Object.fromEntries(nomes.map((nome, indice) => [nome, partes[indice + 1]]));
      return window.t(fonte, valores);
    }
    return texto;
  };

  // O servidor entrega a recomendação como texto completo, sem alterar o
  // contrato da API. Traduzimos apenas a sequência canônica conhecida. Se o
  // servidor devolver uma frase nova ou inesperada, mantemos o texto inteiro
  // original em vez de misturar ou inventar uma orientação.
  window.traduzirRecomendacao = function (texto) {
    if (!texto || !Object.keys(catalogo).length) return texto || '';
    const frases = [
      'Ainda não há leitura registrada para esta zona.',
      'A última leitura desta zona é antiga: o status térmico mostrado não é atual. Confira o coletor e os sensores.',
      'As condições de temperatura são adequadas.',
      'São necessárias medidas para a diminuição da temperatura.',
      'As condições de temperatura exigem atenção imediata. Caso seja possível, ligue ventiladores ou nebulizadores.',
      'Condições extremas. Abaixe a temperatura imediatamente. Ligue ventiladores e nebulizadores e considere a retirada dos animais.',
      'O índice ainda está subindo nos últimos 15 minutos: reforce o resfriamento.',
      'Tendência de subida nos últimos 15 minutos; monitore de perto.',
      'O índice já vem caindo nos últimos 15 minutos.',
    ];
    let restante = texto;
    const traduzidas = [];
    while (restante) {
      const frase = frases.find((item) => restante === item || restante.startsWith(item + ' '));
      if (frase) {
        traduzidas.push(window.t(frase));
        restante = restante.slice(frase.length).trimStart();
        continue;
      }
      const sensores = restante.match(/^(\d+) (sensor|sensores) sem leitura recente -- confira a conexão Modbus antes de confiar no índice mostrado\.$/);
      if (!sensores) return texto;
      const fonte = sensores[2] === 'sensor'
        ? '%(total)s sensor sem leitura recente -- confira a conexão Modbus antes de confiar no índice mostrado.'
        : '%(total)s sensores sem leitura recente -- confira a conexão Modbus antes de confiar no índice mostrado.';
      traduzidas.push(window.t(fonte, { total: sensores[1] }));
      restante = '';
    }
    return traduzidas.join(' ');
  };
}());
