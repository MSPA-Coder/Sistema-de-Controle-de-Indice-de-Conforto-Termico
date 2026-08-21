# ADR 007: Chave de sessão como segredo do Compose, obrigatória em produção

## Status

Aceito em 2026-08-21. **Substitui a ADR 005**, que passa a Substituída.

## Contexto

A ADR 005 aceitou, como desvio consciente da política de segredo obrigatório,
que a aplicação gerasse a chave de sessão e a persistisse no volume
`app_instance` quando nenhuma configuração explícita existisse. O motivo era
concreto e específico:

> O Compose não fornece uma chave de sessão como Docker secret dedicado.

Esse motivo deixou de valer: os outros três aplicativos do mantenedor
(MegaSena, ControleRendaVariavel, ControleBancario) já leem a chave deles de
segredo montado, e nada impedia este de fazer o mesmo além de ninguém ter
criado o segredo.

A própria ADR 005 previu esta ADR e definiu o que ela teria de trazer:

> Uma evolução para secret dedicado requer migração coordenada, compatibilidade
> temporária e procedimento de rollback documentado.

O que a geração silenciosa custava, e que não estava escrito em lugar nenhum:
ela transforma um erro de configuração — ninguém nunca definiu a chave — num
sistema que sobe normalmente e parece saudável. O estrago só aparece no dia em
que o volume se perde, e a forma que ele toma (todo mundo deslogado de uma vez,
sem mensagem) não aponta para a causa. Foi levantado na Fase 3 de
`_manutencao/PLANO_SINAL_E_DEFEITOS.md` como a única divergência de segredo
entre os quatro projetos.

## Decisão

A chave de sessão passa a ser lida, nesta ordem:

1. `CONFORTO_SECRET_KEY_FILE` → segredo do Compose em `/run/secrets/secret_key`
   (o caminho é validado; a variável não é um seletor arbitrário de arquivo);
2. `CONFORTO_SECRET_KEY` no ambiente;
3. **somente** com `CONFORTO_DEVELOPMENT=1` ou `CONFORTO_TESTING=1`, geração
   persistida em `instance/secret_key.txt`, como antes.

Fora de desenvolvimento e teste, a ausência das duas primeiras é `RuntimeError`
na criação da app: o contêiner não sobe.

A distinção de ambiente reaproveita as variáveis que o projeto já usa para isso
(`app_factory` valida `CONFORTO_DEBUG` contra `CONFORTO_DEVELOPMENT`; o
`conftest` liga `CONFORTO_TESTING`), em vez de inventar um terceiro sinal de
"isto não é produção" — que é como se acaba com três definições discordantes.

Só o serviço `ict` monta o segredo. O `coletor` não tem sessão de usuário.

## Migração, compatibilidade e rollback

**Migração sem deslogar ninguém**, que é o ponto que a ADR 005 exigia
coordenar. O arquivo `.secrets/secret_key.txt` da instalação existente foi
semeado com a chave que já estava em `app_instance`, copiada dentro do próprio
servidor. Como o valor não muda, nenhuma sessão aberta é invalidada — a troca
é de *onde a chave vem*, não de *qual chave é*.

**Compatibilidade temporária.** `CONFORTO_SECRET_KEY` no ambiente continua
aceita e tem precedência sobre a geração. Instalações que já a usavam não
precisam mudar nada.

**Rollback.** Reverter o commit devolve a geração silenciosa; a chave em
`instance/secret_key.txt` continua lá e volta a ser usada, então o rollback
também não desloga ninguém. Se o arquivo de segredo estiver ausente ou vazio
depois de implantar, o sintoma é explícito — o contêiner não sobe e a mensagem
diz o que fazer — e o `deploy.sh` reverte sozinho para o commit anterior.

## Consequências

- Um erro de configuração passa a aparecer na hora, no lugar certo, em vez de
  virar um incidente meses depois sem pista da causa.
- Rodar `scripts/configurar_segredos.py --force` numa instalação existente
  agora invalida todas as sessões: o arquivo passou a fazer parte da lista, e
  regenerá-lo troca a chave. O script não sobrescreve sem `--force`; o aviso
  está ao lado da entrada.
- Perder o volume `app_instance` deixa de invalidar sessões, porque a chave não
  mora mais lá.
- A ADR 005 fica como registro histórico. Não apagar: ela explica por que o
  desvio existiu e por quanto tempo.
