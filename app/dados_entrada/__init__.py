"""Entrada manual de dados: cidades de referência, persistência e rotas.

Mesma forma de :mod:`app.ict` e :mod:`app.coletor` -- um pacote por área, com
os módulos nomeados pelo papel que exercem dentro dela. Não reexporta nada de
propósito: quem precisa de uma parte importa o submódulo, e assim o custo de
importar as rotas (que puxam Flask) não recai sobre quem só quer a tabela de
cidades.
"""
