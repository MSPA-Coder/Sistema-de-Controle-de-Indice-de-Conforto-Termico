# Segurança aplicada

O ICT é a única interface pública. O coletor não publica porta no host e
recusa toda rota, exceto `/health`, sem o token interno correspondente.

## Capacidades internas

Há duas capacidades distintas:

- `leitura`: teste de conexão do equipamento;
- `controle`: cálculo, alteração de controle e comando de atuador.

O cabeçalho continua sendo `X-Interno-Token`, para preservar o contrato HTTP,
mas o valor é derivado com um rótulo de capacidade. Um bearer de leitura não é
aceito em uma rota de controle. A configuração de produção deve fornecer
`CONFORTO_INTERNO_TOKEN_LEITURA_FILE` e
`CONFORTO_INTERNO_TOKEN_CONTROLE_FILE`; a ausência de qualquer um falha
fechado quando a rota é usada. O provisionador cria raízes físicas
independentes em `internal_read_token.txt` e `internal_control_token.txt`, e o
Compose monta cada uma somente nos processos que precisam dela.

## Perfis e zonas

`app/seguranca/auth.py` nega endpoints não mapeados por padrão e aplica áreas
no servidor. Toda rota com `zona_id` também consulta a ACL persistida em
`historico.usuario_zonas` antes de encaminhar a chamada. A migração faz
backfill das contas não administradoras existentes; administradores continuam
globais por perfil. Novos vínculos são concedidos ou revogados por
administrador em `/usuarios/api/<usuario_id>/zonas/<zona_id>`. A ausência de
vínculo nega o acesso, inclusive antes do encaminhamento ao coletor.

## Análises

As consultas de análise têm limite local por identidade/endereço de 30/minuto e
300/hora e cache de 15 segundos por processo. O cache reduz varreduras
repetidas, sem alterar a resposta pública nem armazenar segredos.

## Build e operação

`Dockerfile` fixa a digest da base e versões de pacotes do sistema. O
`constraints.txt` fixa as dependências Python; `SharedAuth` é fixado por commit.
O PostgreSQL do Compose também usa digest. Atualizações devem alterar essas
referências deliberadamente e passar pela qualidade no Docker.
