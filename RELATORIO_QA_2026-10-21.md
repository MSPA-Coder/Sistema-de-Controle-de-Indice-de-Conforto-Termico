# Relatório de testes — ConfortoTermico (21/10/2026)

Escopo: pilha Docker local reconstruída a partir do `main` (d49cf25), dados locais, API
(HTTP real, com sessão, CSRF e perfis), banco (SQL direto) e tela (navegador interno).
Nada foi tocado no VPS. O banco local voltou ao estado inicial (43.200 leituras, 5 zonas,
usuários `mspa` e `Admin`, execução 8); a trilha de auditoria mantém as linhas geradas
pelos testes. Backup anterior aos testes: `backup_antes_qa.dump` (scratchpad da sessão).

## Resultado resumido

| Área | Resultado |
|---|---|
| Suíte `quality` (ruff + pytest) | 586 passaram, 1 ignorado |
| Cálculos ITU/ITUV/IGNU, limites, psicrometria | sem defeito (exemplos da dissertação, fronteiras, 20 mil amostras) |
| Filtros do histórico (zona, índice, status, datas, valor) | corretos contra SQL, na API e na tela |
| Autorização por perfil (6 perfis x 33 rotas) | 226/226 corretas, mais troca obrigatória de senha, CSRF, trava de admin |
| Persistência (CRUD, cascata, auditoria) | funciona; defeitos listados abaixo |
| Contêineres | não-root, FS somente leitura, `cap_drop ALL`, coletor sem porta, API interna exige token |

## Situação após as correções (mesmo dia)

Verificação completa na máquina (`quality`): 685 testes passaram, 1 ignorado (antes 586;
são 99 novos/ajustados, em `tests/test_correcoes_qa_2026_10_21.py` e
`tests/test_correcoes_qa_postgres.py`). Pilha reconstruída e conferida na tela (375, 768
e desktop). Nada foi enviado ao VPS.

| # | Situação | Como ficou |
|---|---|---|
| 1 | Corrigido | Leituras que listam várias zonas filtram pela ACL (`zonas_permitidas`); `?zona_id=` não liberado dá 403; cópia para o histórico exige todas as zonas da execução |
| 2 | Corrigido | Corpo JSON que não é objeto responde 400 em toda escrita (não abre mais o disjuntor) |
| 3 | Corrigido | Stull limitado ao bulbo seco até 0,3 °C de excesso; acima disso o dado continua recusado; a tela mostra a causa do erro |
| 4 | Corrigido | Autor vem de `g.usuario`; entram login (ok/falha), logout, senha, conta, zonas da conta, geração, cópia, exclusão e apagar histórico. 6 linhas antigas recuperadas no banco local; 86 não têm conta de origem |
| 5 | Corrigido | Migração `20261021_01_sessoes_revogadas`; logout revoga o `sid`. Sessões anteriores não têm `sid` e valem até vencer |
| 6 | Corrigido | Conta inexistente gasta o mesmo hash |
| 7 | Corrigido | CSV prefixa `'` em texto que começa com `= + - @ tab CR` |
| 8 | Corrigido | Datas nos extremos do calendário viram "sem limite" |
| 9 | Corrigido | Nome só texto, sem controle e sem corte; `ativa` só booleano |
| 10 | Corrigido | `host` IP ou nome de host; 29 equipamentos locais de 5 octetos (`192.168.11.2.1`) viraram `192.168.11.21` |
| 11 | Corrigido | Tetos explícitos nas rotas (200 / 2.000 / 5.000 / 500) |
| 12 | Mantido, documentado | É janela ancorada no fim, e a tela usa o `deslocamento` devolvido; teste fixa o contrato |
| 13 | Corrigido | `Cache-Control: no-store` em páginas e `/api/*`; HSTS quando a requisição é HTTPS |
| 14 | Corrigido | Zona inexistente: 404 para administrador, 403 para as demais contas (não revela ids) |
| 15 | Corrigido | Rotas de leitura do histórico/análises com limite próprio de 120/min e 3.000/h |
| 16 | Corrigido | `scripts/recalcular_ignu.py` (simula por padrão, idempotente); aplicado: 8.640 leituras e 8.640 medições, 1.744 Conforto→Alerta, 1 Conforto→Emergência, 3 Alerta→Emergência; backup antes |
| 17 | Corrigido | Análises mostra "DADO DESATUALIZADO" com a idade da leitura |
| 18 | Corrigido | Eventos, Histórico e Auditoria com data completa no fuso e formato da conta; entradas no formato regional |
| 19 | Corrigido | Sem rolagem horizontal em 375 e 768 px nas 9 abas |
| 20 | Resolvido | VPS estava em d49cf25 (já com a validação de números); deploy de 2dc7479 feito em 22/10/2026, saúde ok, sem IGNU legado no VPS |
| U1 | Corrigido | Botão **Zonas** na tela de usuários e coluna com a contagem |
| U2 | Corrigido | Erro do servidor com campo: mensagem real, `aria-invalid`, foco e Host obrigatório em TCP |
| U3 | Corrigido | Salvar mostra "Configurações salvas"; valor fora da faixa não é corrigido em silêncio nem gravado |
| U4 | Corrigido | Trilhas do grid com `minmax(0, 1fr)` |
| U5 | Corrigido | `aria-label` nos gráficos, rótulos nos campos numéricos, `h1`, abas por setas com `tabindex` e `aria-labelledby`, contraste ≥ 4,5:1 |
| U6 | Corrigido | Placeholder regional, sem citar README, último acesso formatado, mínimo de senha e "mostrar senha", eixo vazio oculto |
| U7 | Corrigido | Ver 17 e 18 |
| U8 | Corrigido | Botão e campo ocultos de "Limpar histórico" removidos (a rota `/api/reset` fica, com seus testes) |

Descoberto no caminho: três mensagens com texto corrompido (`numÃ©rico`, `invÃ¡lido`,
`climÃ¡tica`) em `dados_entrada/db.py` e `gerador_dados.py`, corrigidas.

## Defeitos (por severidade)

### Médios
1. **ACL de zona não vale nas leituras agregadas.** Conta sem nenhuma zona concedida
   (gestor, operador, analista) recebe dados de todas as zonas em `/api/zonas`,
   `/api/zonas/historicos-recentes`, `/api/historico-leituras` (inclusive `?zona_id=1`),
   `/api/analises*`, `/api/operacao/status|eventos` e `/api/dados-entrada/exportar.csv`
   (44 MB). Só rotas com `zona_id` no caminho são barradas. O README promete que a ausência
   do vínculo bloqueia a rota.
2. **Corpo JSON que não é objeto derruba o controle.** `[1]`, `"x"`, `123` ou `true` em
   qualquer rota de escrita dão 500 (`request.get_json(...) or {}` seguido de `.get`). Nas
   rotas que encaminham ao coletor, o 500 conta como falha transitória e abre o circuito:
   após poucas requisições, calcular/controle/comando devolvem 502 "coletor indisponível"
   por pelo menos 30 s, para todos os usuários.
3. **Gerador de dados aborta com umidade ~100 %.** `calcular_bulbo_umido` (Stull) passa do
   bulbo seco por 0,01–0,19 °C quando tbs >= 20 °C e UR >= 99,5 %; o código lança erro e a
   execução inteira falha ("bulbo úmido acima do bulbo seco"). Reproduzido em 19–20/09 e
   12–13/10/2026. A tela mostra só "Não foi possível gerar os dados". Sugestão: limitar
   tbu a tbs.
4. **Auditoria sem autor e com lacunas.** `ator_login`/`ator_perfil` gravam sempre
   `unknown` (só `ator_id` é real); a aba Auditoria mostra "unknown (unknown)". Não geram
   evento: criar/editar/excluir usuário, redefinir senha, conceder/revogar zona, gerar dados,
   copiar para histórico, excluir medições, apagar histórico (em `dados_entrada`). Logins vão
   só para o log do contêiner.
5. **Logout não revoga a sessão.** Cookie guardado antes do logout continua com 200 depois
   (sessão assinada no cliente, sem revogação no servidor).

### Baixos
6. Login: conta existente leva ~85 ms e inexistente ~13 ms (hash só roda para conta real);
   permite enumerar logins.
7. CSV de dados de entrada exporta `zona_nome` sem neutralizar `=`/`+`/`-`/`@` (injeção de
   fórmula no Excel).
8. `data_fim=9999-12-31` em `/api/historico-leituras` e `/resumo-horario` dá 500
   (estouro de data ao somar 1 dia).
9. Nome de zona com caractere NUL dá 500; nome `null` vira o texto "None"; `ativa:"talvez"`
   vira `true` sem erro.
10. `host` de equipamento só precisa ser não vazio: aceita `http://evil/`, `999.999.999.999`,
    espaços, 5.000 caracteres. O seed local já tem `192.168.11.3.1` (5 octetos). Como o
    coletor usa esse host em "testar conexão", vale validar IP/hostname (não testado).
11. `limite` sem teto em `agregados-15min`, `resumo-horario`, `auditoria` (`eventos` e
    `historico-leituras` limitam a 200).
12. Paginação: `deslocamento` além do fim é recuado para `total - limite`; paginar de 200 em
    200 repete linhas na última página (2.600 linhas lidas para 2.510 reais).
13. Páginas HTML autenticadas sem `Cache-Control` (inclui a tela que mostra a senha
    temporária); sem HSTS (relevante só atrás de TLS).
14. Zona inexistente em rota administrativa responde 403, não 404 (o handler 404 é
    inalcançável para quem passa pela checagem central).
15. Rate limit de 20/min e 100/h por rota e por IP: `/api/historico-leituras` estourou as
    100/h durante o teste e a tela do histórico recebeu 429. Rotas de polling são isentas.

### Dados e interface
16. **IGNU legado no banco local:** as 8.640 leituras da zona 4 usam a fórmula antiga (0,6·Tgn),
    anterior ao ADR 009. Análises mostra 99,97 % Conforto; com a fórmula atual o valor sobe
    ~0,4·Tgn. O ADR já pede para regerar a série; nada na base marca qual fórmula gerou cada
    linha.
17. Análises exibe "CONFORTO" e "As condições de temperatura são adequadas" para leitura
    de 15/08 (o Dashboard marca "dado desatualizado", Análises não).
18. Eventos de operação mostram só HH:MM:SS (eventos de agosto parecem de hoje); Auditoria
    mostra UTC cru com microssegundos; "Entradas" do histórico usam ponto e 4 casas, fora do
    formato regional.
19. Mobile (375 px): rolagem horizontal (página com 685 px) no painel de status do Dashboard.
20. A imagem em execução era de 18/10, anterior ao commit de 20/10 ("validação de números").
    Nela `fator_escala` NaN/Infinity e porta 502.5 eram aceitos; no `main` atual estão
    corrigidos. Conferir o VPS com `~/deploy.sh --status`.

## Usabilidade (navegador interno, perfil administrador)

Método: navegação real por todas as abas, formulários, diálogos, teclado, auditoria de
acessibilidade por script (rótulos, contraste, alvos de toque), 3 larguras (desktop, 768, 375 px).

### Problemas
U1. **Conta não administradora não consegue ser usada de verdade.** A tela de usuários não
    tem como conceder zonas (só existem as rotas `/usuarios/api/<id>/zonas/...`, sem
    nenhum chamador em template ou JS). Sem concessão, todo operador/técnico/gestor recebe
    403 em qualquer ação por zona, embora as abas apareçam e a lista de zonas venha cheia.
U2. **Erros de formulário genéricos.** Equipamento com host vazio mostra só "Os dados do
    equipamento são inválidos."; a zona mostra "Os dados da zona são inválidos." O servidor
    sabe o campo e o motivo, mas a mensagem é descartada. O foco vai para o primeiro campo e
    nenhum campo é marcado; "Host/IP" nem aparece como obrigatório no modo TCP.
U3. **Configurações do Sistema gravam sozinhas e corrigem em silêncio.** Não há botão Salvar
    nem aviso de "salvo". Digitar 0 em "Intervalo entre leituras" (mínimo 1) gravou 1 no
    servidor sem mensagem.
U4. **Celular e tablet.** Em 375 px há rolagem horizontal em 5 de 9 abas (Dashboard 685 px,
    Análises e Histórico 843, Auditoria 983, Dados de entrada 843). Em 768 px: Análises,
    Histórico e Auditoria (843/983). Operação, Cadastro, Configurações e Sistema cabem.
U5. **Acessibilidade.**
    - Os 9 gráficos (`canvas`) não têm `aria-label` nem texto alternativo.
    - Os campos numéricos visíveis (`*-regional`) não têm rótulo; o `<label>` aponta para o
      `<input>` original, que fica oculto. O nome acessível sai do placeholder.
    - Não há `h1` na tela principal (só `h2`).
    - As abas têm `role=tab`, mas a seta do teclado não move o foco, todas têm `tabindex=0`
      e os painéis não têm `aria-labelledby`.
    - Texto de 9,6 px com contraste 3,95:1 (rótulo das entradas) e de 11,7 px com 3,83:1 (status
      do coletor); o mínimo é 4,5:1.
    - O aviso `aria-live` guarda a última mensagem; "Os dados do equipamento são inválidos."
      continuou na região depois do diálogo fechar.
U6. **Textos e formatos.**
    - O placeholder dos campos numéricos usa ponto ("Ex.: 22.5") no formato regional brasileiro.
    - A tela de usuários cita "README.md, seção ..." ao usuário final.
    - "Último login" aparece em ISO cru; a tela de trocar senha não diz o mínimo de 10
      caracteres e não tem "mostrar senha".
    - O gráfico "Valores de entrada" tem um eixo direito de -1 a 1 sem significado.
U7. **Dados antigos parecem atuais (ver itens 17 e 18 acima).** Eventos de operação sem
    data, Análises sem aviso de dado desatualizado, Auditoria em UTC com microssegundos.
U8. **Código morto no Sistema.** O botão "Limpar histórico" e o campo "Digite APAGAR" estão
    ocultos (`oculto`); se o botão voltar sem o campo, o clique leva a "Digite APAGAR para
    confirmar" sem lugar para digitar (testei: nada foi apagado).

### Bom
- Diálogos usam `<dialog>` nativo: foco no primeiro campo, Esc fecha, foco volta ao botão de origem.
- Exclusão de zona avisa o efeito sobre equipamentos, controle, histórico e leituras brutas
  (as leituras ficam no banco com `zona_id` nulo, como o texto diz).
- Dashboard avisa "dado desatualizado" e "aguardando cálculo"; formato brasileiro de números
  e datas na maioria das telas; o histórico filtra e pagina com a faixa "Leituras 116-145 de 145".
- Trocar senha e login têm `autocomplete` correto; o campo de nova senha tem `minlength=10`.
- Nenhum `innerHTML` com dado do servidor; nome de zona com HTML aparece como texto.

## O que passou
- ITU/ITUV/IGNU: exemplos da dissertação (73,72; 17,39), fronteiras de cada faixa/espécie,
  combinação espécie/índice inválida, entradas hostis (nan, inf, vírgula decimal, tbu > tbs).
- Filtros: 13 combinações zona/índice/status, janelas de data no fuso local, paginação sem
  duplicar, parâmetros hostis (SQL, overflow) sem 5xx (exceto o item 8).
- Gerador: determinismo por semente, valor/status == fórmula, UR/tbu/tpo coerentes, CSV
  íntegro, cópia idempotente, exclusão com confirmação "APAGAR".
- Segurança: CSRF (sem token, token inválido, token de outra sessão, text/plain), CSP/XFO/
  nosniff, cookie HttpOnly+Secure+SameSite, `next` seguro, bloqueio de login (429),
  senha/corpo gigante (413), troca de senha derruba outras sessões, redefinição obriga troca,
  usuário desativado perde acesso na hora, perfil alterado vale na sessão aberta, admin não
  se exclui nem se rebaixa, XSS (nome de zona com HTML renderiza como texto).

## Não coberto
Modbus real e e-mail SMTP, "testar conexão", `pip-audit`/varredura da imagem, telas de
Configurações/Sistema (edição), preferências regionais, acessibilidade, carga.
