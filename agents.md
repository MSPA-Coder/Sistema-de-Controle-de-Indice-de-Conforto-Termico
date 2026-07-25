# Diretrizes para agentes de código

## Objetivo do repositório

Este projeto é uma aplicação Flask para cálculo e monitoramento de índices de conforto térmico na produção animal. Ele combina regras científicas de domínio, persistência PostgreSQL no ambiente Docker (com SQLite para testes e migração), autenticação por perfil, simulação e integração opcional com equipamentos Modbus.

Antes de alterar uma área, identifique o contrato atual no código e nos testes relacionados. O `README.md` descreve instalação, operação e arquitetura em alto nível.

## Comandos de verificação

Suíte completa:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Alternativa com o ambiente Python já ativo:

```powershell
python -m unittest discover -v
```

Durante o desenvolvimento, execute primeiro os testes diretamente relacionados à mudança. Use a suíte completa antes de concluir alterações amplas ou transversais.

## Organização do código

- `app/thermal_indices.py`: fórmulas, limites, espécies, índices e validações de domínio.
- `app/app_factory.py`: configuração do servidor, composição da aplicação e tratamento global de erros.
- `app/coletor/`: malha contínua e API interna autenticada para ações Modbus.
- `app/ict/`: consultas, análises, administração e proxy das ações operacionais.
- `app/rotas_comuns.py`: rotas de leitura compartilhadas.
- `app/services.py`: estratégias de geração e resfriamento usadas pelo simulador.
- `app/zona_service.py`: leitura, cálculo e controle de zonas Modbus.
- `app/modbus_client.py`: único adaptador para `pymodbus`.
- `app/database.py`: persistência operacional.
- `app/dados_entrada_db.py`: persistência separada dos dados de entrada.
- `app/auth.py`: autenticação, sessão e autorização por perfil.
- `app/static/js/app.js`: comportamento da interface.

Respeite essas fronteiras quando elas mantiverem a responsabilidade clara. Uma refatoração pode alterá-las se reduzir complexidade real e atualizar, no mesmo trabalho, consumidores, testes e documentação.

## Contratos essenciais

### Domínio térmico

- Fórmulas, limites e combinações de espécie/índice devem ter uma única fonte de verdade.
- Mudanças científicas precisam de justificativa explícita e exemplos numéricos verificáveis.
- Entradas ausentes ou inválidas não devem produzir um índice aparentemente válido.

### Controle e Modbus

- Uma zona calcula a média das leituras válidas que medem o mesmo campo.
- A falha de um sensor é tolerada somente quando ainda existem dados suficientes para o índice.
- Ciclos automáticos da mesma zona não podem se sobrepor.
- Estados, travas e histerese de uma zona não podem interferir em outra.
- Reduções de intensidade devem respeitar a histerese definida pelo domínio.
- Configuração física inválida deve ser rejeitada; não substitua endereço, unidade ou registrador por um valor silencioso.
- Falhas de comunicação devem gerar estado de falha observável, sem derrubar o servidor.
- Código fora de `app/modbus_client.py` não deve depender diretamente de `pymodbus`.

### Persistência

- Valide e normalize dados na fronteira antes de persistir ou acionar equipamentos.
- Configurações desconhecidas ou inválidas não devem se propagar para o controle.
- A exclusão de uma zona preserva suas leituras históricas, salvo mudança explícita do modelo de dados.
- Alterações de esquema devem funcionar tanto em uma instalação nova quanto em um banco existente suportado.

### Segurança

- Autorização é aplicada no servidor; visibilidade de botões não é controle de acesso.
- Respostas de `/api/*` não devem expor exceções, caminhos, SQL ou segredos.
- Senhas de usuários são armazenadas apenas como hash.
- A senha SMTP é somente escrita na API e nunca deve aparecer em respostas ou logs.
- O último administrador ativo não pode ser removido ou desativado.
- O modo de depuração permanece desabilitado por padrão.

### Papéis da aplicação

- O ICT é a única interface pública. Todas as abas e APIs do navegador pertencem a ele; sua visibilidade e autorização dependem somente do perfil autenticado.
- O coletor é um serviço privado, sem páginas nem login. Ele fala Modbus, mantém o estado da malha e expõe somente `/health` e rotas `/api/interno/*` autenticadas por `CONFORTO_INTERNO_TOKEN`.
- Cálculo manual, mudança de modo, comando de atuador e teste de conexão entram no ICT, são autorizados pela sessão e então atravessam por HTTP interno até o coletor.
- `criar_app_ict()` nunca deve importar `app.coletor.estado`, `app.modbus_client` ou `app.zona_service`.
- Parâmetros alteráveis pelas abas ficam no banco. `.env` e `.env.docker` são parâmetros de implantação somente leitura para a aplicação.
- Excluir uma zona não limpa mais, na hora, o estado em memória do coletor referente a ela (histórico do gráfico, histerese) -- isso acontece no próximo ciclo automático (`GerenciadorControleZonas._reconciliar_zonas_removidas`).

Se o desenho dos papéis mudar, trate isso como decisão arquitetural e ajuste rotas, autorização, lançadores e documentação em conjunto.

## Padrões de implementação

- Use Python 3.10+ e siga o estilo já adotado no módulo alterado.
- Prefira funções pequenas e puras para cálculo, classificação e validação.
- Mantenha orquestração com estado em serviços, não em funções de rota.
- Centralize o acesso ao banco nos módulos de persistência e mantenha as diferenças de dialeto no adaptador de backend.
- Reutilize abstrações existentes quando elas representam o mesmo conceito; crie novas abstrações apenas quando houver uma responsabilidade distinta.
- Evite dependências ou frameworks adicionais para resolver comportamento local simples.
- Não misture refatoração ampla com mudança funcional sem necessidade.

## Linguagem e codificação

- Todos os arquivos de texto usam UTF-8 sem BOM.
- Textos apresentados ao usuário usam português do Brasil com acentuação normal.
- Identificadores internos usam ASCII: nomes de arquivos, módulos, funções, variáveis, campos JSON, rotas, ids HTML e classes CSS.
- Uma saída corrompida no terminal não é evidência suficiente de arquivo corrompido; confirme a leitura dos bytes como UTF-8 antes de editar.

## Testes

Escreva testes para comportamento relevante e risco real:

- fórmulas e classificação;
- validação e persistência;
- autorização e proteção de segredos;
- transições do controle automático;
- falhas parciais de sensores e atuadores;
- contratos consumidos pela interface.

Testes de Modbus devem usar fakes ou mocks, nunca hardware ou rede reais. Prefira testes determinísticos a esperas baseadas em tempo.

Não preserve uma implementação somente para satisfazer um teste antigo. Quando um requisito mudar intencionalmente, atualize ou remova os testes obsoletos e acrescente cobertura para o novo comportamento. Evite testes acoplados a nomes privados, ordem incidental de chamadas ou estrutura interna sem relevância para o contrato.

## Compatibilidade

Não existe obrigação de manter indefinidamente todo detalhe histórico.

Considere contrato aquilo que é usado atualmente pela interface, pelos lançadores, pelo banco suportado ou por uma integração declarada. Uma quebra intencional é aceitável quando:

1. o benefício está claro;
2. os consumidores são atualizados no mesmo trabalho;
3. dados existentes recebem migração ou tratamento definido;
4. testes e documentação passam a representar o novo contrato.

Evite camadas de compatibilidade sem consumidor conhecido. Se uma compatibilidade temporária for necessária, documente o motivo e a condição para remoção.

## Documentação

- Descreva o sistema como ele funciona agora.
- Não registre fases, rodadas, conversas, tentativas intermediárias ou bugs já resolvidos.
- Explique decisões apenas quando elas ainda orientarem mudanças futuras.
- Não duplique listas extensas que podem ser obtidas diretamente do código, salvo quando forem necessárias para operar o sistema.
- Atualize `README.md` quando uma mudança afetar instalação, configuração, operação, segurança, arquitetura ou limitações conhecidas.

## Critério de conclusão

Uma alteração está pronta quando:

- o comportamento solicitado foi implementado;
- verificações proporcionais ao risco foram executadas;
- não foram introduzidas dependências acidentais entre os papéis;
- segredos e acionamentos físicos continuam protegidos;
- testes e documentação descrevem o contrato atual;
- alterações locais não relacionadas foram preservadas.
