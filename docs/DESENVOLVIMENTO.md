# Desenvolvimento e validação

## Ambiente reproduzível

Use Docker Compose para aplicação, PostgreSQL, migrações e ferramentas. Não
instale Python, dependências ou test runners no host para trabalhar no projeto.

Prepare a instalação local:

```powershell
Copy-Item .env.docker.example .env.docker
docker run --rm -v "${PWD}:/workspace" -w /workspace python:3.14-slim `
  python scripts/configurar_segredos.py
docker compose --env-file .env.docker config --quiet
```

Os segredos ficam em `.secrets/` e não devem ser impressos ou versionados. Em
uma instalação existente, não execute o gerador com `--force` sem planejar a
rotação: a chave de sessão muda e invalida sessões.

O script gera a senha do PostgreSQL, o token interno e a chave de sessão. O
build também exige `.secrets/github_token.txt` para ler o repositório privado
SharedAuth. Forneça uma credencial restrita a leitura pelo mecanismo aprovado
de autenticação do GitHub; não a coloque no ambiente, histórico do shell ou
documentação.

Se o host Windows intercepta HTTPS com uma autoridade local, gere o arquivo de
CA usado no build:

```powershell
.\scripts\exportar_ca_local.ps1
```

O Compose exige que `.certs/local-root-ca.crt` exista. Quando não houver CA
local a incorporar, crie um arquivo vazio nesse caminho; ele é uma entrada do
build e nunca faz parte da imagem final.

## Pilha operacional

```powershell
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

O último comando verifica operações básicas no PostgreSQL da pilha. Para
acompanhar os processos:

```powershell
docker compose --env-file .env.docker logs -f ict coletor
```

## Qualidade

```powershell
docker compose --env-file .env.docker --profile quality run --rm quality
```

O estágio `quality` instala as dependências de desenvolvimento e executa
`ruff check . && pytest`. Não documente uma contagem fixa de testes: a suíte
muda com o código.

A CI também valida a configuração Compose, executa `pip-audit`, varre a imagem
servida com Trivy e confere contratos de segurança do runtime. Esses controles
não substituem o exercício do fluxo alterado nem a verificação da pilha.

## Triagem de alertas externos

O repositório não possui workflow nem configuração local de CodeQL. A CI cobre
Ruff, pytest, `pip-audit`, Trivy e contratos de runtime; portanto, qualquer
alerta CodeQL citado por uma ferramenta externa deve ser associado a um arquivo
e revisão concretos antes de virar mudança ou supressão. Sem essa evidência, o
item permanece documentado para triagem, sem alterar dependências ou adicionar
exceções.

Também não há `rpcbind`, `portmap`, NFS ou serviço equivalente no `compose.yaml`.
Ruído desse tipo pertence ao host/VPS, não a esta composição. Não adicionar,
remover ou desabilitar pacotes/serviços sem inventário do ambiente e checagem de
dependências; a decisão atual é não modificar a aplicação.

## Validação proporcional

- documentação: `git diff --check`, links locais e busca por afirmações
  obsoletas;
- autenticação, autorização, sessão, CSRF e contratos cobertos: `quality` e
  exercício manual do fluxo afetado;
- persistência, dependências ou contêineres: `quality`, rebuild da pilha e
  `scripts.verificar_postgres`;
- schema: nova revisão Alembic, `upgrade` e `downgrade` coerentes, bootstrap em
  PostgreSQL vazio e backup conferido antes de tocar dados existentes;
- integração externa: teste controlado de falha, timeout e indisponibilidade.

Registre verificações não executadas e o motivo. O projeto valida software; não
descreva testes automatizados como validação experimental dos índices.
