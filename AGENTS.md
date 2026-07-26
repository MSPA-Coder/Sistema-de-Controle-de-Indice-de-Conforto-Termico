# Base compartilhada de engenharia

<!-- SHARED-ENGINEERING-BASE:BEGIN version="1.0" -->

## Governança deste bloco-base

Este bloco estabelece as orientações compartilhadas e permanentes do mantenedor
para seus projetos Python e Flask.

Ele é controlado pelo mantenedor e não deve ser alterado, resumido, removido,
deslocado, enfraquecido ou substituído automaticamente durante implementação,
correção, refatoração, atualização de documentação ou manutenção ordinária.

Uma alteração neste bloco somente é autorizada quando o mantenedor solicitar
explicitamente, na conversa atual, uma mudança na **base compartilhada de
engenharia**. Um pedido genérico para melhorar, atualizar, organizar ou corrigir
o projeto não autoriza modificar este bloco.

Se uma tarefa entrar em conflito com estas orientações:

1. não reescreva a orientação conflitante;
2. explique objetivamente o conflito;
3. proponha a menor exceção necessária;
4. aguarde autorização explícita quando a exceção alterar segurança,
   integridade, persistência, produção ou confiabilidade;
5. registre a exceção na seção específica do projeto.

Arquivos `AGENTS.md` em subdiretórios podem acrescentar comandos e regras
locais, mas não devem enfraquecer esta base. Não crie nem altere
`AGENTS.override.md` sem autorização explícita do mantenedor.

Mudanças aprovadas nesta base devem:

- incrementar sua versão;
- registrar uma justificativa curta;
- ser propagadas deliberadamente aos projetos que usam a mesma base;
- preservar os marcadores de início e fim;
- atualizar a verificação automática de integridade, quando existente.

A flexibilidade técnica prevista neste documento não autoriza o próprio agente a
apagar ou reescrever as orientações. Soluções alternativas devem ser
implementadas como decisões justificadas ou desvios aprovados, mantendo a base
legível e estável.

## Intenção e liberdade técnica

Os projetos usam Python e Flask, com PostgreSQL como único banco operacional e
Docker para empacotamento e implantação.

PostgreSQL também é o banco utilizado em todos os testes que exercem
persistência. Testes unitários de cálculos, validações e regras puras não usam
banco de dados. SQLite somente é permitido quando for o objeto explícito da
funcionalidade testada, como a leitura de uma base legada; não é usado para
simular PostgreSQL.

Essas escolhas são a base atual, não uma proibição de evolução. Bibliotecas,
ferramentas, padrões ou componentes adicionais podem ser adotados quando
trouxerem benefício concreto de segurança, confiabilidade, desempenho,
simplicidade ou manutenção.

Toda divergência relevante deve registrar:

- problema concreto que pretende resolver;
- benefício esperado;
- impacto de compatibilidade;
- riscos e alternativas consideradas;
- estratégia de migração ou rollback;
- testes e validações aplicáveis.

Não transforme uma implementação existente em restrição permanente sem razão de
domínio, segurança, operação ou manutenção.

## Arquitetura proporcional

Use uma fábrica de aplicação e organize funcionalidades em módulos ou
blueprints. O fluxo de referência é:

```text
HTTP -> validação e normalização -> caso de uso -> persistência
```

Esse fluxo orienta responsabilidades, mas não obriga a existência de uma pasta
ou classe para cada camada.

- Rotas tratam HTTP, autenticação, autorização, entrada e resposta.
- Casos de uso ou serviços coordenam regras de negócio e limites transacionais.
- Persistência concentra acesso ao banco e consultas reutilizáveis.
- Templates apresentam dados; não concentram regras de negócio.
- Regras importantes devem ser testáveis sem uma requisição HTTP.
- Prefira composição a herança e funções simples para lógica sem estado.
- Use classes quando houver estado coerente, invariantes, ciclo de vida ou
  polimorfismo real.
- Não crie interfaces, repositories ou camadas vazias para satisfazer um
  desenho teórico.

Application Factory, Service Layer, Unit of Work, Repository, Adapter, Strategy,
Policy e Value Object são padrões disponíveis, não uma lista obrigatória. Adote
um padrão quando ele reduzir uma complexidade concreta ou proteger um contrato
importante.

## Persistência e integridade

PostgreSQL é a fonte de verdade do ambiente operacional e dos testes de
persistência.

- Represente dados estruturados e relacionamentos estáveis com colunas, tabelas
  e relações explícitas.
- Use `JSONB` para dados semiestruturados, atributos variáveis ou documentos
  externos cuja estrutura possa evoluir. Não o use apenas para evitar modelagem
  relacional.
- Proteja invariantes também no banco, quando aplicável, com `NOT NULL`,
  `UNIQUE`, `CHECK`, foreign keys e constraints apropriadas.
- Crie índices a partir das consultas e volumes esperados; não indexe
  mecanicamente todas as colunas.
- Índices GIN ou de expressão para `JSONB` devem corresponder a consultas reais
  e ter benefício verificável.
- Toda alteração persistente de schema usa uma nova revisão Alembic.
- Migrações autogeradas são candidatas e precisam de revisão manual.
- Não reescreva uma migração que possa ter sido aplicada em outro banco.
- Alterações destrutivas ou transformações de dados reais exigem backup
  validado, plano de migração e autorização explícita.
- Não mantenha adaptadores, condicionais ou tipos especiais apenas para
  compatibilidade com SQLite, salvo quando o produto possuir funcionalidade
  explícita de importação ou leitura desse formato.

## Transações, concorrência e efeitos externos

O caso de uso que inicia uma operação de escrita é responsável por seu limite
transacional. Camadas inferiores não fazem `commit` por conta própria.

- Uma operação composta deve concluir integralmente ou sofrer rollback integral.
- Validações que protegem integridade concorrente não devem existir apenas no
  código; use constraints, locks ou níveis de isolamento quando necessários.
- `Read Committed` é o padrão normal do PostgreSQL.
- Locks, controle otimista, `Repeatable Read` ou `Serializable` devem responder
  a uma condição de corrida identificada e possuir testes no PostgreSQL.
- Quando houver falha de serialização, o caso de uso deve poder repetir a
  transação completa com segurança.
- Não mantenha transações abertas durante chamadas externas lentas sem
  necessidade.
- Banco de dados, e-mail, APIs e dispositivos externos não formam uma única
  transação atômica.
- Quando a consistência com um sistema externo for crítica, considere
  idempotência, retentativas controladas, registro de estado ou padrão Outbox.
- Retentativas automáticas só são seguras para operações idempotentes ou
  protegidas contra duplicidade.

## Testes e qualidade

Use o teste mais rápido que ofereça confiança suficiente, sem substituir o banco
de produção por outro dialeto.

- Testes unitários de cálculos, normalização, validações e regras de domínio não
  usam banco.
- Dependências externas são substituídas por fakes ou adapters controlados
  quando o objetivo não for validar a própria integração.
- Testes de models, repositories, serviços com persistência e rotas que gravam
  dados usam PostgreSQL descartável.
- Migrações, constraints, transações, rollback, concorrência, locks, isolamento,
  `JSONB`, índices e consultas específicas são validados em PostgreSQL.
- A suíte nunca acessa o banco operacional.
- O schema de teste é criado com `alembic upgrade head`.
- `create_all()` somente pode ser usado quando o teste deliberadamente não
  avaliar migrações e isso não reduzir a confiança no schema.
- Cada teste deve ser isolado por rollback transacional, savepoint, schema ou
  banco próprio.
- Testes paralelos não compartilham estado mutável.
- Fixtures criam somente os dados necessários e não dependem da ordem de
  execução.
- Relógio, aleatoriedade, rede e serviços externos são controlados quando
  puderem tornar o teste não determinístico.
- Testes HTTP protegem autenticação, autorização, validação e contratos
  observáveis.
- Testes em navegador ficam reservados às jornadas críticas.
- Correções devem incluir um teste que demonstre a falha quando isso for viável.
- Teste comportamento e invariantes, não detalhes internos acidentais.
- Cobertura é uma rede de segurança, não um objetivo isolado.
- SQLite só aparece em testes de funcionalidades que realmente leem, importam ou
  transformam arquivos SQLite.

Para projetos novos, prefira pytest, Ruff, análise de tipos gradual com mypy ou
ferramenta equivalente, auditoria de dependências e CI. Suítes existentes em
`unittest` podem permanecer quando forem confiáveis; não as reescreva apenas
para uniformizar ferramentas.

## Estratégia de validação progressiva

A validação deve equilibrar retorno rápido durante o desenvolvimento e confiança
integral antes da conclusão.

Não execute automaticamente a suíte completa depois de cada pequena alteração.

### Ciclo de desenvolvimento

Durante a implementação:

1. identifique o comportamento, o risco e os consumidores afetados;
2. execute primeiro o menor teste que reproduza ou proteja esse comportamento;
3. depois de corrigido, execute os testes do módulo ou caso de uso relacionado;
4. quando houver persistência, execute os testes PostgreSQL correspondentes;
5. amplie a seleção quando a mudança afetar contratos compartilhados, segurança,
   arquitetura ou múltiplos consumidores.

Durante esse ciclo:

- use saída compacta, como `-q`, `-x` e `--tb=short`;
- interrompa na primeira falha quando isso acelerar o diagnóstico;
- use `--last-failed` apenas para corrigir falhas já conhecidas;
- não calcule cobertura repetidamente;
- não execute E2E, auditoria completa ou build de produção após cada edição;
- não repita uma validação cujo código e dependências relevantes não mudaram;
- mantenha registro dos comandos já executados durante a tarefa.

### Validação completa de encerramento

Quando a implementação estiver estável, execute uma única validação completa com
todos os controles aplicáveis ao projeto.

A validação final deve executar sem filtros parciais como caminhos específicos,
`-k`, `--last-failed` ou exclusões de testes lentos, salvo quando a própria
configuração oficial da suíte separar etapas complementares que também serão
executadas.

Conforme o projeto e o risco, a validação final inclui:

1. suíte unitária completa;
2. testes de integração com PostgreSQL;
3. testes de migração;
4. testes HTTP e E2E aplicáveis;
5. lint;
6. análise de tipos;
7. cobertura;
8. auditoria de dependências;
9. construção da imagem de produção;
10. smoke test da pilha Docker.

Qualquer alteração posterior em código, testes, migrations, dependências ou
configuração invalida a validação completa anterior. Nesse caso:

1. execute primeiro o teste que falhou ou foi afetado;
2. execute os testes relacionados;
3. quando o código voltar a ficar estável, repita a validação completa uma única
   vez.

Mudanças exclusivamente documentais não exigem a suíte completa, salvo quando a
documentação for validada ou consumida por testes, empacotamento ou automação.

### Otimização segura

- Reutilize um PostgreSQL descartável durante a mesma tarefa quando isso não
  comprometer isolamento.
- Aplique migrações novamente durante a iteração somente quando models ou
  revisions mudarem.
- Use rollback, savepoints, bancos ou schemas separados para manter testes
  independentes.
- Considere execução paralela somente depois que o isolamento entre workers
  estiver garantido.
- Meça periodicamente os testes mais lentos e corrija gargalos reais.
- Preserve uma execução completa em ambiente limpo na CI, mesmo quando a
  validação local já tiver sido concluída.
- Resultados bem-sucedidos devem ser apresentados de forma resumida; detalhes
  completos são necessários principalmente para falhas.

Ao concluir uma tarefa, informe:

- testes direcionados executados;
- validação final executada;
- resultado;
- controles omitidos e respectivos motivos.

## Segurança e interface

- Valide e normalize toda entrada nas fronteiras.
- A autorização é aplicada no servidor; menus e botões são apenas apresentação.
- Escritas originadas no navegador usam proteção CSRF.
- Preserve escape de HTML, CSP, cookies seguros, hosts confiáveis, limites de
  requisição e validação defensiva de uploads.
- Segredos nunca ficam no código, imagem, logs, mensagens de erro ou valores
  padrão de produção.
- Logs não expõem senhas, tokens, conteúdo financeiro ou dados pessoais
  desnecessários.
- APIs e respostas JSON possuem contratos coerentes; mudanças coordenam backend,
  consumidores, testes e documentação.
- HTML deve ser semântico e acessível.
- CSS e JavaScript permanecem em assets próprios quando a política de segurança
  impedir código inline.

## Produção e Docker

O artefato de produção é uma imagem construída e reproduzível.

- Use servidor WSGI apropriado; nunca o servidor de desenvolvimento do Flask.
- A imagem de produção contém somente código e dependências de runtime.
- Execute com usuário não-root e menor privilégio possível.
- Não monte o código-fonte do host no contêiner de produção.
- Dados persistentes ficam em volumes ou serviços próprios.
- Segredos são concedidos somente aos serviços que precisam deles,
  preferencialmente como arquivos.
- Preserve health checks, limites de logs, timeouts e desligamento gracioso.
- A aplicação só inicia depois que o banco estiver saudável e as migrações
  tiverem sido aplicadas por uma etapa controlada.
- Bind mounts, debugger e dependências de desenvolvimento pertencem ao Compose
  de desenvolvimento ou Dev Container.
- Use builds multi-stage quando eles reduzirem de forma útil o tamanho, as
  dependências ou a superfície de ataque.
- A infraestrutura de testes usa credenciais, volumes e bancos descartáveis
  separados da implantação operacional.

## Desempenho, confiabilidade e manutenção

- Meça antes de otimizar.
- Investigue paginação, N+1, plano de consulta e índices antes de adicionar
  cache.
- Cache exige política explícita de invalidação.
- Integrações externas usam Adapter e possuem timeout.
- Retentativas e circuit breaker são adicionados conforme o risco real.
- Falhas esperadas ficam observáveis e produzem mensagens seguras.
- Dependências devem ter faixas ou locks reproduzíveis e atualização deliberada.
- Prefira bibliotecas maduras quando elas reduzirem risco.
- Prefira a biblioteca padrão quando ela resolver o problema com clareza.
- Atualize código, testes, migrações e documentação como uma única mudança
  coerente.
- Preserve alterações locais não relacionadas.
- Informe toda validação que não pôde ser executada.

<!-- SHARED-ENGINEERING-BASE:END -->

# Orientações específicas do projeto

## Fonte de verdade e escopo

Este repositório é uma aplicação Flask para cálculo e controle de conforto
térmico animal. Antes de alterar uma área, confirme o contrato no código, nas
migrações e nos testes atuais. Documentos históricos explicam contexto, mas não
se sobrepõem ao comportamento executável.

O único ambiente operacional suportado é Docker Compose com PostgreSQL. Não
acrescente compatibilidade de produção com SQLite, execução Windows nativa ou
bancos legados sem um requisito atual verificável.

## Transição da suíte de persistência

A suíte legada ainda contém testes que usam SQLite. Esses testes não comprovam
compatibilidade de persistência, migrações, constraints ou transações no
PostgreSQL e não devem ser ampliados para novos cenários de banco.

Ao alterar persistência, migrações ou código dependente de dialeto:

- migre os testes afetados para PostgreSQL descartável;
- execute `scripts.verificar_postgres`;
- não conclua a mudança apoiando-se apenas nos resultados SQLite;
- não preserve caminhos de compatibilidade SQLite sem consumidor explícito.

Testes puros de fórmulas, validação e controle sem persistência devem ser
mantidos sem banco.

## Verificação específica

Use testes direcionados durante o desenvolvimento e a estratégia progressiva da
base. Quando aplicável, valide:

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker build schema
docker compose --env-file .env.docker up -d
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

Testes Modbus usam fakes ou simulação, nunca hardware real. Mudanças em
persistência, migrações, segurança ou implantação exigem a validação na pilha
real.

## Arquitetura e contratos

- `ict` é a única interface pública. Autentica, autoriza e encaminha comandos
  operacionais pela API interna.
- `coletor` é privado. Possui Modbus, estado da malha e somente `/health` e
  `/api/interno/*`.
- `criar_app_ict()` não importa `app.modbus_client`, `app.zona_service` nem
  estado do coletor.
- A autorização é aplicada no servidor. A interface apenas reflete permissões.
- Falhas de sensor ou atuador ficam observáveis e não derrubam o processo.
- Ciclos e estados de controle são isolados por zona; parâmetros físicos
  inválidos nunca recebem fallbacks silenciosos.
- Fórmulas e limites científicos têm fonte única em `app/thermal_indices.py`.
  Mudanças exigem justificativa e exemplos numéricos testados.
- Persistência passa pelos módulos de banco. Dados são validados na fronteira.
- Toda alteração de esquema usa Alembic, com `upgrade` e `downgrade` coerentes.
  O identificador de revisão tem no máximo 32 caracteres e a migração deve
  funcionar tanto em banco existente quanto em instalação nova.

## Implantação e segurança

- Segredos ficam em `.secrets/` e são montados pelo Compose; nunca inclua
  valores padrão, segredos em imagens, logs ou respostas.
- Os contêineres da aplicação executam sem root, com filesystem somente leitura,
  capabilities removidas e diretórios temporários explícitos.
- Não monte o código do host em serviços operacionais. A imagem construída é o
  artefato executado por `ict`, `coletor` e tarefas administrativas.
- Preserve health checks, limites de logs e desligamento gracioso.
- Respostas `/api/*` não expõem exceções, SQL, caminhos nem credenciais.
- Senhas de usuários ficam somente como hash; senha SMTP é write-only.
- O último administrador ativo não pode ser removido ou desativado.
- Requisições mutáveis do navegador usam proteção CSRF.

## Prática de mudança

Prefira testes de comportamento e risco real a testes de detalhes internos.
Quando um requisito mudar, atualize ou remova o teste antigo; não preserve código
sem consumidor apenas para mantê-lo verde. Uma quebra intencional é aceitável
quando consumidores, migração, testes e documentação são tratados juntos.

Use UTF-8 sem BOM, português do Brasil para textos de usuário e identificadores
ASCII. Preserve alterações locais não relacionadas.

Atualize o `README.md` quando instalação, configuração, operação, arquitetura,
segurança ou limitações mudarem. Documente somente o estado atual, sem narrar
tentativas, rodadas de migração ou bugs já resolvidos.

## Desvios aprovados da base compartilhada

Não há desvios aprovados. A presença transitória de testes SQLite é uma lacuna
conhecida a ser removida, não uma exceção permanente à base.
