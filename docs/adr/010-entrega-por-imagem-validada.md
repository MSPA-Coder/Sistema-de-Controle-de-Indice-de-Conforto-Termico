# Entregar o artefato efetivamente validado

Decisão: 18/10/2026.

O rebuild no servidor resolvia novamente base/sistema e não reproduzia a imagem
exercitada pela CI. Locks de dependências não tornam dois builds idênticos.

Construir uma candidata de runtime e outra PostgreSQL, nativas ARM64, e passar
os mesmos IDs por qualidade, browser, segurança e contratos operacionais.
Transferi-las por artefato entre jobs, verificar revisão/run/plataforma e só
publicar depois dos gates. Deploy resolve tags de run em digest antes de tocar
serviços. A imagem de ferramentas não é publicada.

Alternativas recusadas: rebuild no VPS, latest como identidade, publicar
AMD64 para ARM64 ou manifesto com variante não executada. Desenvolvimento
AMD64 local permanece independente. Custo aceito: transferência de dois TARs
entre jobs e dependência de acesso ao registry; falha nele recusa sem substituir
serviços. Snapshots anteriores devem existir antes do fast-forward.

Schema/dados não fazem parte do rollback automático. Contratos de sessão,
CSRF, papéis, backup, vigia e autocura permanecem. Não se introduz framework,
novo serviço operacional ou migração de banco.
