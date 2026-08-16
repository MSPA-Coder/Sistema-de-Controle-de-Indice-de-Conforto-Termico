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

  CONFIG_APP = configuracao;
}
