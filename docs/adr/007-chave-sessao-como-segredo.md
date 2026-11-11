# Chave de sessão

Estado: vigente.

Este caminho é mantido porque mensagens de configuração da aplicação apontam
para ele. O contrato atual é simples: fora de desenvolvimento e testes, o ICT
exige uma chave de sessão explícita em `CONFORTO_SECRET_KEY_FILE` ou
`CONFORTO_SECRET_KEY`. No Compose, somente o ICT monta
`/run/secrets/secret_key`, gerado em `.secrets/secret_key.txt`.

Sem uma chave válida, o ICT falha ao iniciar. O fallback persistido em
`instance/secret_key.txt` existe apenas com `CONFORTO_DEVELOPMENT=1` ou
`CONFORTO_TESTING=1`. Arquivos antigos dessa pasta (o volume `instance` de
uma instalação anterior ao ADR) devem ser apagados: o código deixou de lê-los,
mas o arquivo continua sendo uma chave de assinatura esquecida. Regenerar o
segredo invalida as sessões existentes.

O preparo e as regras de proteção dos segredos estão em
[Desenvolvimento e validação](../DESENVOLVIMENTO.md).
