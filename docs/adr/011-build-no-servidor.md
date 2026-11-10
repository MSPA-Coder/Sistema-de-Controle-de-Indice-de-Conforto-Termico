# Build no servidor a partir do `main`

Estado: vigente.

Decisão: 20/10/2026. Substitui o ADR 010.

A entrega por imagem validada na CI (ADR 010) fazia o deploy depender do
registry e de uma fila de jobs, e o mantenedor passou a esperar por ela em
toda mudança. Decidido: a verificação que vale é a completa na máquina, antes
do commit; o commit vai direto ao `main`; o `~/deploy.sh` monta a imagem no
próprio VPS a partir do código do `main`, sem consultar a CI, confere
`/health` e volta sozinho para código e imagem anteriores se falhar.

Custo aceito: a imagem que sobe não é, byte a byte, a que foi testada na
máquina (AMD64 local, ARM64 no servidor; a base só muda com `--refresh`). O
lock de dependências, o `/health` e o rollback automático cobrem a diferença.

Revisitar se um defeito chegar à produção por diferença entre a imagem
testada e a servida.
