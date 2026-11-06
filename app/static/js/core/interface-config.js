export let CONFIG_APP;

export async function carregarConfiguracaoInterface() {
  const resposta = await fetch("/api/configuracao-interface");
  if (!resposta.ok) {
    throw new Error("A configuracao da interface nao esta disponivel.");
  }

  const configuracao = await resposta.json();
  if (
    !configuracao ||
    typeof configuracao !== "object" ||
    !configuracao.indicesPorEspecie ||
    !configuracao.camposPorIndice ||
    !configuracao.campoMetadados
  ) {
    throw new Error("A configuracao da interface esta incompleta.");
  }

  // Apenas rótulos de apresentação. As chaves, fórmulas e valores da API
  // continuam canônicos e não dependem do idioma da conta.
  for (const campo of Object.values(configuracao.campoMetadados)) {
    if (typeof campo.label === "string") campo.label = window.t(campo.label);
  }
  for (const tabela of [configuracao.nomeEspecie, configuracao.nomeIndice]) {
    if (tabela) for (const chave of Object.keys(tabela)) tabela[chave] = window.t(tabela[chave]);
  }
  CONFIG_APP = configuracao;
}
