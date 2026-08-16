# ADR 001: Separação entre ICT e coletor

## Status
Aceito.

## Contexto
O sistema comunica com dispositivos Modbus enquanto atende operadores por HTTP.
A malha de aquisição e controle requer ciclos contínuos; a interface pública
requer autenticação, autorização e respostas HTTP independentes desses ciclos.

## Decisão
O Docker Compose executa dois serviços de aplicação:

- **ICT (Interface de Controle Térmico):** única interface HTTP pública; autentica, autoriza, serve a interface e persiste cadastros e configurações.
- **Coletor:** serviço privado; executa o cliente Modbus, mantém a malha de controle e expõe somente `/health` e `/api/interno/*`.

Os serviços comunicam por API HTTP interna autenticada. O ICT não importa
módulos, cliente Modbus nem estado do coletor diretamente.

## Consequências

- Falhas de sensor ou atuador ficam isoladas da interface pública e permanecem observáveis pelo coletor.
- O coletor não tem porta publicada no host; o ICT concentra a autorização e encaminha os comandos operacionais.
- Os serviços compartilham o PostgreSQL, mas têm responsabilidades distintas sobre os dados operacionais.
- A operação exige health checks, logs e segredo para a autenticação interna, além de manter os dois processos disponíveis.

## Referências
- `AGENTS.md` — contratos de arquitetura e segurança.
- `app/app_factory.py` — fábricas de aplicação separadas.
