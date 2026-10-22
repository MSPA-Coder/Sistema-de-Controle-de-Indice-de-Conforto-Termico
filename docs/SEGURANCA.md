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
administrador em `/usuarios/<usuario_id>/zonas` (tela) ou
`/usuarios/api/<usuario_id>/zonas/<zona_id>` (JSON). A ausência de vínculo
nega o acesso, inclusive antes do encaminhamento ao coletor.

As consultas que não têm `zona_id` no caminho (`/api/zonas`,
`/api/zonas/historicos-recentes`, `/api/historico-leituras`, `/api/analises*`,
`/api/operacao/status|eventos` e `/api/dados-entrada/*`) filtram o resultado
pelas zonas da conta (`app/seguranca/zonas.py::zonas_permitidas`); pedir uma
zona não liberada por parâmetro (`?zona_id=`) responde 403, e copiar para o
histórico uma execução com zonas que a conta não enxerga também. Zona
inexistente responde 404 só para quem já vê todas as zonas (administrador);
para as demais contas continua 403, que não revela quais ids existem.

## Sessão, auditoria e respostas

- **Logout encerra a sessão no servidor.** O cookie é assinado e sem estado; o
  login grava nele um `sid`, o logout registra o `sid` em
  `historico.sessoes_revogadas` (até a sessão vencer sozinha) e a requisição
  seguinte com esse cookie é tratada como deslogada. Sessões de antes dessa
  mudança não têm `sid` e valem até vencer. Sair de um aparelho não derruba os
  outros da mesma conta; trocar a senha continua derrubando todos.
- **Login em tempo constante.** Conta inexistente também gasta uma verificação
  de hash, para o tempo de resposta não revelar quais logins existem.
- **Trilha de auditoria com autor.** O ator vem de `g.usuario`. Além do
  cadastro, entram login (sucesso e falha), logout, troca e redefinição de
  senha, criação/edição/exclusão de conta, zonas liberadas, geração de dados,
  cópia para o histórico, exclusão de medições e apagar histórico.
- **Corpo JSON precisa ser um objeto.** `[1]`, `"x"`, `123` ou `true` em
  qualquer escrita respondem 400 (antes eram 500 e, nas rotas que encaminham ao
  coletor, abriam o disjuntor para todos).
- **Cabeçalhos.** `Cache-Control: no-store` em páginas autenticadas e em
  `/api/*`; `Strict-Transport-Security` quando a requisição chega por HTTPS.
- **CSV de dados de entrada** prefixa com `'` o texto que começa com `=`, `+`,
  `-`, `@`, tab ou retorno (injeção de fórmula no Excel/LibreOffice).
- **Cadastro valida o que recebe.** Nome só texto, sem caractere de controle e
  sem corte silencioso; `ativa` só booleano; `host` Modbus TCP só IP ou nome de
  host. A resposta 400 traz `erro` e `campo`.

## Análises

As consultas de análise têm limite local por identidade/endereço de 30/minuto e
300/hora e cache de 15 segundos por processo. O cache reduz varreduras
repetidas, sem alterar a resposta pública nem armazenar segredos.

## Build e operação

`constraints.txt` fixa as dependências Python; `SharedAuth` é fixado por commit.
O `Dockerfile` busca a tag móvel de Python 3.15, atualiza os pacotes Debian e
as ferramentas de build a cada reconstrução. O Compose busca sempre
`postgres:17-alpine`. A CI semanal reconstrói essas imagens, roda a qualidade,
audita dependências Python e varre CVEs corrigíveis na imagem. O Dependabot
propõe atualizações de dependências, tags e Actions; elas só entram depois dos
checks passarem. A série principal do PostgreSQL continua em 17 para proteger
o formato dos volumes existentes.
