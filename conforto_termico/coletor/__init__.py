# -*- coding: utf-8 -*-
"""
coletor
=======
Tudo que fala Modbus, calcula o indice e grava no banco: leitura de
sensores, malha de controle (ventilador/nebulizador), e a configuracao
que rege esse ciclo. Pensado para rodar no SITE, na mesma rede/serial dos
equipamentos -- ver `agents.md`, secao de arquitetura, para o raciocinio
completo por tras dessa separacao.

So importe deste pacote quem realmente precisa da malha de controle
(`app_factory.criar_app` com `papel_app` None ou "coletor"). Um processo
de dashboard nunca deve importar nada daqui.
"""
