# ADR 006: Implantação em VPS com fluxo de sentido único

## Status

Aceito em 2026-08-19, junto com a primeira publicação em produção.

## Contexto

Até aqui o projeto era operado apenas na máquina de desenvolvimento. Com a
publicação em um VPS, o mesmo código passa a existir em dois lugares, e é
preciso decidir qual deles é a fonte da verdade.

A primeira implantação foi feita copiando arquivos direto para o servidor.
O resultado foi um diretório que não era um clone Git válido: as migrações
Alembic haviam sido aplicadas no banco do servidor sem que os commits
correspondentes existissem no repositório. O banco andou, o Git ficou parado.
Esse é o risco concreto que esta decisão endereça.

## Decisão

O código no VPS é um **espelho somente-leitura do `main`**. O fluxo tem sentido
único: desenvolvimento na máquina local → commit → push ao GitHub → implantação
no VPS.

Três mecanismos sustentam isso, em vez de disciplina:

1. O repositório é privado e o VPS o lê por uma *deploy key* somente-leitura,
   registrada apenas neste repositório. Um push a partir do servidor falha.
2. A implantação passa por `~/deploy.sh conforto`, que **aborta** se encontrar
   alteração não commitada no servidor, avança apenas em *fast-forward* e
   verifica health checks e o endereço público antes de declarar sucesso.
3. Segredos e certificados (`.secrets/`, `.certs/`) permanecem fora do Git e
   apenas no servidor; os dados vivem em volumes Docker, fora da pasta do
   código, para que substituir o diretório do projeto seja uma operação segura.

## Consequências

- Corrigir algo "rapidinho no servidor" deixa de ser um caminho silencioso: o
  próximo deploy recusa e aponta o que está fora do lugar.
- Rollback é `git checkout` de uma revisão validada, com o entendimento de que
  o estado é destacado e a implantação seguinte realinha com o `main`.
- Um reclone do diretório do projeto é seguro quanto a dados, mas exige
  restaurar `.secrets/` e `.certs/` — sem eles o build falha ou o banco fica
  inacessível.
- O ambiente de produção e o local mantêm bases independentes; nada sincroniza
  dados entre eles automaticamente.
- Rotacionar a *deploy key* é feito pelo GitHub, em Settings → Deploy keys, sem
  tocar em credenciais da conta.
