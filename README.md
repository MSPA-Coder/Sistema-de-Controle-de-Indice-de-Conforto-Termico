# ConfortoTermico

Software experimental do projeto de mestrado do mantenedor para calcular,
simular e acompanhar índices de conforto térmico animal. A aplicação organiza
zonas, calcula ITU, ITUV e IGNU, registra séries no PostgreSQL e oferece uma
interface web para consulta e experimentação.

O projeto ainda não está em uso operacional. Ele trabalha em modo simulado e
**não aciona equipamentos físicos**. A existência de adaptadores Modbus no
código não representa implantação, homologação de hardware ou autorização para
controle real.

## Limites da validação

Os testes verificam comportamento do software, inclusive fórmulas e exemplos
numéricos adotados da dissertação de referência. Eles não validam
experimentalmente os índices, os limites por espécie, a qualidade de sensores,
o bem-estar animal nem a eficácia de estratégias de climatização. Resultados e
mensagens são apoio à pesquisa, não recomendação autônoma de manejo.

As hipóteses, fórmulas e limites estão em [Domínio e validação](docs/DOMINIO.md).

## Arquitetura atual

- `ict`: interface HTTP acessada pelo navegador; autentica, autoriza e encaminha
  operações ao coletor;
- `coletor`: serviço privado que executa os ciclos por zona e a simulação;
- `postgres`: PostgreSQL 17, com os schemas `historico` e `dados_entrada`;
- `schema`: job que aplica `alembic upgrade head` antes dos serviços;
- `quality`: estágio opcional para Ruff e pytest.

Flask e Waitress servem os dois processos Python. O SharedAuth fornece sessão,
CSRF, autenticação e controles HTTP comuns. O navegador acessa apenas o ICT; o
coletor não publica porta no host. Veja [Arquitetura](docs/ARQUITETURA.md).

## Executar com Docker

Requisitos: Docker Desktop ou Docker Engine com o plugin Compose. Python,
PostgreSQL e ferramentas de qualidade não precisam ser instalados no host.

```powershell
Copy-Item .env.docker.example .env.docker
docker run --rm -v "${PWD}:/workspace" -w /workspace python:3.14-slim `
  python scripts/configurar_segredos.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

O build da dependência privada SharedAuth também requer
`.secrets/github_token.txt`, com credencial somente de leitura fornecida pelo
mecanismo de autenticação aprovado, e o Compose requer
`.certs/local-root-ca.crt`. Veja o preparo completo no guia de desenvolvimento.

A interface fica em `http://127.0.0.1:5001`. Crie o primeiro administrador:

```powershell
docker compose --env-file .env.docker exec ict python scripts/criar_usuario_admin.py
```

Quem perde a senha é atendido por um administrador em `/usuarios/`: o botão
**Redefinir senha** sorteia uma senha temporária, mostrada uma única vez na
tela de quem redefiniu, para ser entregue fora do sistema. Contas criadas por
essa tela recebem o mesmo tratamento. Enquanto a troca estiver pendente, toda
requisição da pessoa cai em `/minha-senha` — só o logout, o `/health` e os
arquivos estáticos escapam. A troca exige a senha atual e recusa repetir a
senha temporária. `/minha-senha` também está sempre disponível, para qualquer
perfil, sem obrigação. O script acima é a exceção: quem o roda escolheu a
própria senha e não fica com troca pendente.

Duas garantias vieram junto, compartilhadas com os outros apps Flask do
mantenedor: o destino pós-login (`?next=`) é validado por
`sharedauth.access.url_proximo_seguro`, que só aceita caminho interno — sem
isso a tela de login vira um redirecionador aberto; e a sessão carrega uma
marca da senha em vigor (`sharedauth.session`), então **trocar a senha derruba
as sessões abertas em outros lugares**, e não só a atual. Quem troca a própria
senha continua conectado; quem tinha entrado com a senha antiga cai no próximo
acesso.

Para parar sem remover os volumes:

```powershell
docker compose --env-file .env.docker down
```

Não use `down -v` sem decidir descartar os dados persistidos.

## Validar mudanças

```powershell
docker compose --env-file .env.docker --profile quality run --build --rm quality
```

`--build` faz parte do comando: o serviço `quality` não monta o código do
host e `docker compose run` só reconstrói quando a imagem não existe. Sem
ele, a validação roda a versão anterior do código e passa em verde.

O estágio executa `ruff check . && pytest`. Mudanças de persistência,
migrações, dependências ou contêineres também exigem a pilha completa e
`scripts.verificar_postgres`. Veja [Desenvolvimento e validação](docs/DESENVOLVIMENTO.md).

## Logs

Mensagens de log que carregam texto de fora (login digitado, parâmetro de
requisição, exceção de biblioteca) passam por
`sharedauth.logs.sanitizar_log`. Ela é rede, não garantia: redige por
reconhecimento de padrão e não substitui a disciplina de nunca colocar um
segredo na mensagem em primeiro lugar — ver `sharedauth.secrets`, cujas
exceções nunca carregam o valor lido. Um rótulo novo a reconhecer entra em
`sharedauth.logs.CHAVES_SENSIVEIS`, na biblioteca, nunca numa cópia local.

## Dados e backup

O projeto irmão [BackupRestore](https://github.com/MSPA-Coder/BackupRestore)
é o mecanismo preferido de proteção, catálogo, retenção e ensaio de restauração
para as bases local (`conforto_termico`) e do VPS
(`conforto_termico_vps`). Esta aplicação não oferece backup ou restore; use o
fluxo central do BackupRestore. Veja [Operação, dados e recuperação](docs/RUNBOOK.md).

## Documentação viva

- [Arquitetura](docs/ARQUITETURA.md): componentes, fronteiras e responsabilidades;
- [Domínio e validação](docs/DOMINIO.md): fórmulas, hipóteses e limites científicos;
- [Desenvolvimento e validação](docs/DESENVOLVIMENTO.md): fluxo reproduzível em Docker;
- [Runbook](docs/RUNBOOK.md): operação local/VPS, dados, backup e recuperação.

As diretrizes obrigatórias para agentes e contribuidores estão em [AGENTS.md](AGENTS.md).
