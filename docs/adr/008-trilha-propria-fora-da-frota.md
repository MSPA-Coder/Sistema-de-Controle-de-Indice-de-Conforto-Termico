# Trilha própria: arquitetura livre, contrato operacional preservado

Decidido em 07/09/2026, durante o levantamento em profundidade dos oito
repositórios (`_manutencao/docs/historico/LEVANTAMENTO_2026-09.md`, achado L13). Registrado
aqui em 08/09/2026.

## O que mudou

Este projeto **deixou de ser referência de padronização** e saiu do roteiro de
fases que rege os outros. Ele é o mestrado do mantenedor: o assunto, o ritmo e
as necessidades são de pesquisa, não de produto.

A frota passa a ser **MegaSena, ControleBancario e ControleRendaVariavel** —
três aplicativos que compartilham base, evoluem juntos e servem de referência
uns aos outros. O ConfortoTermico não está mais nesse conjunto.

## O que fica livre

**A arquitetura.** Estrutura de módulos, divisão de processos, formato de
configuração, escolhas de biblioteca. A divergência que antes era um débito a
ser resolvido passa a ser uma consequência esperada de um projeto com outro
propósito.

Concretamente, a liberdade de arquitetura não autoriza atualizações sem teste.
As dependências PyPI ficam fixadas em `constraints.txt` e a referência Git do
SharedAuth em `pyproject.toml` (não há `uv.lock` neste projeto); a tag móvel da imagem
base, as atualizações do Debian e as ferramentas de segurança são buscadas pela
CI semanal, que testa e varre a imagem. O Dependabot mantém tags e Actions em
atualização. A escolha de biblioteca, a estrutura dos módulos e o fluxo de
pesquisa continuam livres.

## O que continua obrigatório

**O contrato operacional, inteiro.** A separação é de código, não de operação:

- continua no VPS, atrás do mesmo nginx, com o mesmo `deploy.sh`;
- continua coberto pelo `vigia.sh`, pelo `autocura.sh` e pelo alerta do
  Telegram;
- continua no ciclo do `backup-db.sh`, que segue cobrindo **quatro** bancos;
- continua consumindo o `SharedAuth` para sessão, CSRF, limite de login,
  cabeçalhos e CSP — e continua recebendo as correções feitas lá;
- continua com CI, CodeQL, varredura de imagem e as mesmas proteções de
  repositório.

Uma mudança que quebre qualquer um desses pontos não é "arquitetura livre": é
quebrar a operação compartilhada, e precisa ser tratada como tal.

## Por que decidir isso explicitamente

Enquanto a divergência era implícita, ela aparecia como pendência: cada
levantamento a reencontrava, cada comparação entre repositórios a apontava, e
alguém sempre acabava propondo unificar. O custo que desaparece com esta
decisão é o de *padrão e interface* — deixar de perseguir uma uniformidade que
não serve a este projeto. O custo que **permanece** é o de contrato
operacional, e ele permanece de propósito.

Ver também `AGENTS.md` (primeira seção) e a §7 do
`LEVANTAMENTO_2026-09.md`, que reúne o que este projeto herda do levantamento e
continua valendo.
