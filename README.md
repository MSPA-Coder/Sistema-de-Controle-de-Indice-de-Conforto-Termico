# Sistema de Controle dos Índices de Conforto Térmico

Aplicação web em Python e Flask para monitorar conforto térmico na produção animal. O sistema calcula índices térmicos, acompanha zonas com sensores e atuadores, mantém histórico local e oferece visões de operação e análise com acesso controlado por perfil.

As fórmulas, faixas de classificação e espécies atendidas têm como referência a dissertação *Programa Computacional para o Cálculo de Índices de Conforto Térmico na Produção Industrial de Animais para Carne e Leite* (Mariano Sergio Pacheco de Angelo, UNIP, 2013). A implementação atual está centralizada em `app/thermal_indices.py`.

## Principais recursos

- Cálculo e classificação dos índices ITU, ITUV e IGNU.
- Monitoramento por zona com sensores, ventiladores e nebulizadores independentes.
- Modos de operação desligado, manual, automático e manutenção.
- Simulação de sensores e atuadores para uso sem hardware Modbus.
- Histórico em SQLite, com séries em tempo real, agregados de 15 minutos e resumos horários.
- Painéis de acompanhamento, análises por zona e filtros de histórico.
- Geração de dados de entrada a partir do clima histórico disponibilizado pelo Open-Meteo.
- Alertas por e-mail, com pré-visualização quando não há SMTP configurado.
- Login obrigatório, perfis de acesso e administração de usuários.
- Execução combinada ou separada nos papéis de coletor e dashboard.

## Índices implementados

| Índice | Fórmula | Espécies |
|---|---|---|
| ITU | `0.72 * (tbs + tbu) + 40.6` | frangos, bovinos e suínos |
| ITUV | `(0.85 * tbs + 0.15 * tbu) * v ** -0.058` | frangos |
| IGNU | `0.6 * tgn + 0.36 * tpo + 41.5` | frangos, bovinos e suínos |

Cada resultado é classificado como **Conforto**, **Alerta**, **Perigo** ou **Emergência**. Os limites por espécie e índice ficam em `app/thermal_indices.py`.

## Requisitos

- Python 3.10 ou superior.
- Dependências de `requirements.txt`.
- `pymodbus` somente para comunicação com hardware Modbus real.
- Acesso à internet somente para baixar dados climáticos ainda não presentes no cache.

## Instalação

No PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Para usar equipamentos Modbus reais:

```powershell
python -m pip install "pymodbus>=3.8,<4.0"
```

## Primeiro acesso

Crie o primeiro administrador antes de iniciar o uso:

```powershell
python scripts/criar_usuario_admin.py
```

O script solicita nome, login e senha. Depois do primeiro acesso, administradores podem gerenciar as demais contas pela interface.

## Execução

### Aplicação completa

Esta é a opção indicada para execução local em uma única máquina:

```powershell
python app.py
```

Acesse `http://127.0.0.1:5000`.

No Windows, `scripts/conforto_termico_menu.bat` oferece um menu para iniciar a aplicação localmente, disponibilizá-la na rede, alterar a porta da sessão ou encerrar o processo iniciado pelo projeto.

### Coletor e dashboard separados

Use esta opção quando houver necessidade operacional de separar a comunicação com o hardware da camada de consulta:

```powershell
python run_coletor.py
```

```powershell
python run_dashboard.py
```

Por padrão, o coletor usa a porta `5000` e o dashboard usa a porta `5001`. Na mesma máquina, ambos acessam `instance/historico.db`.

O coletor lê sensores, executa a malha de controle, aciona equipamentos e grava dados. O dashboard expõe somente consultas e análises, sem carregar o cliente Modbus.

Não compartilhe o arquivo SQLite por NFS, SMB ou pasta de rede entre máquinas. Para uma implantação distribuída, use um banco cliente-servidor ou uma integração explícita entre o coletor e o dashboard.

## Configuração do servidor

Os valores padrão ficam em `config/servidor.json`. Variáveis de ambiente, quando definidas, têm precedência:

| Variável | Padrão | Finalidade |
|---|---:|---|
| `CONFORTO_DEBUG` | `0` | Ativa o modo de depuração do Flask. Use somente em desenvolvimento local. |
| `CONFORTO_HOST` | `127.0.0.1` | Interface de rede usada pelo servidor. |
| `CONFORTO_PORT` | conforme o papel | Porta TCP. |
| `CONFORTO_THREADED` | `1` | Habilita atendimento concorrente no servidor local. |
| `CONFORTO_MAX_CONTENT_LENGTH` | `1000000` | Limite do corpo das requisições, em bytes. |
| `CONFORTO_SECRET_KEY` | arquivo local gerado | Define a chave usada para assinar a sessão. |

Exemplo:

```powershell
$env:CONFORTO_HOST = "0.0.0.0"
$env:CONFORTO_PORT = "5000"
python app.py
```

Ao expor o serviço fora da máquina local, mantenha `CONFORTO_DEBUG=0`, restrinja a rede de acesso e use um servidor WSGI e HTTPS adequados ao ambiente. O servidor embutido do Flask é voltado ao desenvolvimento e a operações locais controladas.

## Perfis de acesso

Todo acesso exige autenticação. As permissões são verificadas nas rotas; ocultar uma aba é apenas parte da apresentação da interface.

| Perfil | Áreas disponíveis |
|---|---|
| Operador | Dashboard e Operação |
| Técnico | Dashboard, Operação, Histórico, Cadastro, Sistema e Dados de entrada |
| Veterinário | Dashboard, Análises, Histórico e Configurações |
| Analista | Dashboard, Análises, Histórico e Dados de entrada |
| Gestor | Dashboard, Análises e Histórico |
| Administrador | Todas as áreas e gerenciamento de usuários |

A exclusão de dados de entrada é restrita a técnicos e administradores. O sistema também impede que o último administrador ativo seja removido ou desativado.

As sessões duram até 12 horas e usam cookies `HttpOnly` e `SameSite=Lax`. A aplicação não implementa token CSRF; encerre a sessão em dispositivos compartilhados e não exponha a instalação diretamente à internet.

## Organização da interface

- **Monitoramento:** Dashboard, Análises e Histórico.
- **Operação:** modos das zonas, ciclos manuais e comandos de equipamentos.
- **Administração:** Cadastro, Configurações e Sistema.
- **Dados:** geração, consulta, exportação e cópia de dados de entrada.

A disponibilidade de cada área depende do perfil do usuário e, quando os processos são separados, do papel da aplicação.

## Zonas e Modbus

Uma zona representa uma área de produção com espécie, índice, sensores e atuadores próprios. Cada zona pode ter de zero a vários sensores, ventiladores e nebulizadores.

Os equipamentos podem usar Modbus TCP ou RTU. A configuração inclui os parâmetros de conexão, unidade, registrador e, para sensores, campo medido, tipo de dado e fator de escala.

Em cada ciclo de uma zona, o sistema:

1. lê os sensores ativos;
2. agrupa as leituras pelo campo medido;
3. calcula a média quando há mais de um sensor para o mesmo campo;
4. desconsidera sensores sem resposta e registra as falhas;
5. deriva umidade relativa e ponto de orvalho quando possível;
6. calcula e classifica o índice;
7. atualiza o estado de resfriamento da zona;
8. envia comandos aos atuadores habilitados;
9. persiste a leitura e o estado dos equipamentos.

As zonas mantêm estados de controle independentes. A falha de um sensor não bloqueia o ciclo se os campos obrigatórios continuarem disponíveis.

### Modo simulado

`modoSimuladoZonas` vem habilitado em uma instalação nova. Nesse modo, não há comunicação com rede ou porta serial: leituras são geradas pelo simulador e comandos de atuadores retornam sucesso simulado.

Antes de desabilitar a simulação:

- instale `pymodbus`;
- confira endereços, unidades, registradores e fatores de escala;
- teste a conexão de cada equipamento;
- valide as travas global e da zona;
- execute o primeiro acionamento com supervisão local.

Falhas de comunicação Modbus são convertidas em estado de leitura ou escrita malsucedida e registradas pelo fluxo de controle, sem encerrar o servidor.

## E-mail

Configure destinatário, status mínimo e servidor SMTP pela interface. Também é possível fornecer valores SMTP pelo ambiente:

```powershell
$env:SMTP_HOST = "smtp.exemplo.com"
$env:SMTP_PORT = "587"
$env:SMTP_USER = "usuario@exemplo.com"
$env:SMTP_PASS = "senha-ou-app-password"
```

Os valores persistidos têm prioridade quando não estão vazios. Sem host SMTP, o sistema prepara a mensagem, mas não realiza o envio.

A senha SMTP nunca é devolvida pela API. A interface informa apenas se existe uma senha configurada.

## Dados de entrada

A área **Dados de entrada** gera séries para zonas ativas a partir de dados climáticos históricos do Open-Meteo, complementados por cálculos psicrométricos e simulação de atividade e carga térmica animal.

Os resultados ficam em `instance/dados_entrada.db`, separado do histórico operacional. Uma execução pode ser exportada em CSV ou copiada uma única vez para `instance/historico.db`.

Consultas climáticas são armazenadas em cache. Uma geração que precise de um período ainda não armazenado depende de acesso à internet e da disponibilidade do serviço externo.

## Persistência e arquivos locais

Arquivos de execução ficam em `instance/`, que não deve ser versionada:

- `historico.db`: usuários, configurações, zonas, equipamentos, leituras, estados e agregações;
- `dados_entrada.db`: parâmetros, cache climático e séries geradas;
- `secret_key.txt`: chave de sessão gerada automaticamente quando `CONFORTO_SECRET_KEY` não foi definida.

Excluir uma zona remove seus equipamentos, mas preserva as leituras históricas sem vínculo com a zona.

Faça backup periódico de `instance/` com a aplicação parada ou use a função de backup disponível na área Sistema.

Para criar uma distribuição do código sem bancos, ambiente virtual, caches e metadados locais:

```powershell
python scripts/gerar_zip_limpo.py
```

## Dados de demonstração

Para cadastrar cinco zonas de exemplo:

```powershell
python scripts/seed_zonas.py
```

O script não adiciona zonas quando já existem registros. Use `--forcar` apenas quando quiser inserir outro conjunto:

```powershell
python scripts/seed_zonas.py --forcar
```

## Estrutura do projeto

```text
.
├── app.py                     # aplicação completa
├── run_coletor.py             # processo com aquisição e controle
├── run_dashboard.py           # processo de consulta e análise
├── config/servidor.json       # configuração versionada do servidor
├── app/
│   ├── app_factory.py         # composição da aplicação por papel
│   ├── auth.py                # autenticação e autorização
│   ├── thermal_indices.py     # fórmulas, limites e validações
│   ├── services.py            # estratégias do simulador de sensores
│   ├── zona_service.py        # cálculo e controle por zona
│   ├── modbus_client.py       # integração com pymodbus
│   ├── database.py            # persistência operacional
│   ├── agregacao.py           # agregados de 15 minutos e horários
│   ├── dados_entrada_*.py     # geração e persistência de dados de entrada
│   ├── coletor/               # rotas e estado do coletor
│   ├── dashboard/             # rotas de análise
│   ├── templates/             # interface HTML
│   └── static/                # CSS, JavaScript e Chart.js
├── scripts/                   # utilitários de administração e demonstração
├── tests/                     # testes automatizados
├── docs/                      # material de referência
└── instance/                  # dados locais não versionados
```

## Arquitetura

`app_factory.criar_app(papel_app)` compõe a aplicação a partir de Blueprints:

- `papel_app=None`: aplicação completa;
- `papel_app="coletor"`: aquisição, configuração, controle e escrita;
- `papel_app="dashboard"`: consultas e análises.

As rotas compartilhadas de leitura ficam em `app/rotas_comuns.py`. Os cálculos operacionais são sempre associados a uma zona e coordenados por `app/zona_service.py`. Em desenvolvimento, `app/modbus_simulador.py` reutiliza as estratégias de geração e resfriamento de `app/services.py` para simular sensores sem hardware Modbus.

A API é interna à interface web e não possui versionamento público. Ao alterar um contrato JSON, atualize no mesmo trabalho o backend, o JavaScript consumidor, os testes e esta documentação.

## Testes

Execute a suíte completa:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Ou, com o Python já ativo no ambiente:

```powershell
python -m unittest discover -v
```

Os testes de Modbus usam simulações e não exigem hardware ou conectividade. Mudanças locais podem ser verificadas primeiro com o módulo de teste relacionado; antes de integrar uma alteração ampla, execute a suíte completa.

## Manutenção

As diretrizes permanentes para alterações no código estão em `agents.md`. Em resumo:

- mantenha fórmulas e limites centralizados;
- trate segurança de atuadores e segredos como contratos;
- prefira testes de comportamento a testes de detalhes internos;
- altere ou remova testes quando o requisito correspondente mudar intencionalmente;
- documente o estado atual do produto, sem registrar etapas intermediárias de desenvolvimento.
