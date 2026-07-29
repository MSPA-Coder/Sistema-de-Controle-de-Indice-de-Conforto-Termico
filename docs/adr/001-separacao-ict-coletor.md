# ADR 001: Separação ICT e Coletor

## Status
Aceito

## Contexto
O sistema precisa comunicar com dispositivos Modbus para coletar dados térmicos e ao mesmo tempo fornecer uma interface web para operadores. Modbus requer comunicação serial/TCP contínua e de baixa latência, enquanto a interface web serve requisições HTTP intermitentes.

## Decisão
Separar a aplicação em dois serviços distintos:
- **ICT (Interface de Controle Térmico)**: Interface HTTP pública que autentica usuários, serve páginas web e persiste configurações
- **Coletor**: Serviço privado que executa o cliente Modbus e a malha de controle em loop contínuo

Os serviços comunicam via API HTTP interna autenticada. O ICT nunca importa módulos do coletor diretamente.

## Consequências
### Positivas
- Isolamento de falhas: problema no Modbus não derruba a interface web
- Escalabilidade independente
- Segurança: coletor não exposto publicamente
- Manutenção facilitada de cada componente

### Negativas
- Complexidade operacional aumentada (dois processos)
- Latência adicional nas comunicações entre serviços
- Necessidade de autenticação interna entre serviços

## Alternativas Consideradas
1. **Monolito único**: Rejeitado porque bloquearia threads HTTP durante operações Modbus síncronas
2. **Threads separadas no mesmo processo**: Rejeitado porque falha em uma thread poderia corromper estado compartilhado
3. **Filas de mensagens (RabbitMQ/Redis)**: Considerado para futura evolução, mas adiciona complexidade desnecessária inicialmente

## Referências
- AGENTS.md - Documentação de arquitetura
- app/app_factory.py - Implementação das fábricas separadas
