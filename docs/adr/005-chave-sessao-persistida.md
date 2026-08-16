# ADR 005: Chave de sessão persistida no volume de instância

## Status

Aceito como desvio local da política geral de segredo obrigatório em ambiente,
registrado em 2026-08-15.

## Contexto

A aplicação precisa de chave estável para assinar sessões. O Compose não fornece
uma chave de sessão como Docker secret dedicado. Exigir uma variável de ambiente
imediatamente alteraria a instalação existente e arriscaria invalidar sessões
durante uma troca sem coordenação.

## Decisão

Quando a configuração explícita não está disponível, a aplicação gera a chave
uma vez e a persiste no volume `app_instance`. O volume é persistente e não faz
parte da imagem. Segredos de banco e do canal interno continuam em `.secrets/`
e não são substituídos por esse mecanismo.

## Consequências

- Reinícios normais preservam sessões porque reutilizam a chave persistida.
- Remover ou recriar `app_instance` invalida sessões existentes; esse impacto
  deve ser considerado antes de operações destrutivas em volumes.
- O fallback não é modelo para novos segredos. Uma evolução para secret dedicado
  requer migração coordenada, compatibilidade temporária e procedimento de
  rollback documentado.
