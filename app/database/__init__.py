"""Fachada dos agregados de persistência.

Os consumidores continuam usando :mod:`app.database`; cada agregado tem seu
módulo dentro deste pacote (``comum``, ``zonas``, ``leituras``,
``equipamentos``, ``configuracoes``, ``usuarios``, ``operacao``,
``auditoria``). Quem precisa de um agregado específico -- para monkeypatch
num teste, por exemplo -- importa o submódulo direto; o resto usa esta
fachada.

`app/nucleo/db_backend.py` fica de fora de propósito: é a camada de engine e URL,
usada também por `dados_entrada.db`, pelas migrações e pelos scripts, não
um agregado de persistência.
"""

from __future__ import annotations

import os

from .auditoria import listar_eventos_auditoria as listar_eventos_auditoria
from .auditoria import registrar_evento_auditoria as registrar_evento_auditoria
from .comum import PERFIS_VALIDOS as PERFIS_VALIDOS
from .comum import coagir_booleano as coagir_booleano
from .comum import conexao
from .configuracoes import CONFIGURACOES_PADRAO as CONFIGURACOES_PADRAO
from .configuracoes import limpar_cache_configuracoes as limpar_cache_configuracoes
from .configuracoes import obter_configuracoes as obter_configuracoes
from .configuracoes import salvar_configuracoes as salvar_configuracoes
from .equipamentos import CAMPOS_MEDIVEIS as CAMPOS_MEDIVEIS
from .equipamentos import MODOS_CONEXAO as MODOS_CONEXAO
from .equipamentos import TIPOS_DADO as TIPOS_DADO
from .equipamentos import TIPOS_EQUIPAMENTO as TIPOS_EQUIPAMENTO
from .equipamentos import atualizar_equipamento as atualizar_equipamento
from .equipamentos import criar_equipamento as criar_equipamento
from .equipamentos import excluir_equipamento as excluir_equipamento
from .equipamentos import obter_equipamento as obter_equipamento
from .equipamentos import (
    registrar_falha_operacional_zona as registrar_falha_operacional_zona,
)
from .equipamentos import salvar_comando_manual_atuador as salvar_comando_manual_atuador
from .equipamentos import salvar_estado_equipamentos as salvar_estado_equipamentos
from .leituras import INTERVALO_MINIMO_LEITURAS as INTERVALO_MINIMO_LEITURAS
from .leituras import _formatar_janela as _formatar_janela
from .leituras import _intervalo_minimo_leituras as _intervalo_minimo_leituras
from .leituras import agregar_janela_15min as agregar_janela_15min
from .leituras import consolidar_resumo_horario as consolidar_resumo_horario
from .leituras import contar_leituras as contar_leituras
from .leituras import horas_pendentes as horas_pendentes
from .leituras import janelas_15min_pendentes as janelas_15min_pendentes
from .leituras import limpar_historico as limpar_historico
from .leituras import obter_agregados_15min as obter_agregados_15min
from .leituras import obter_historico_leituras as obter_historico_leituras
from .leituras import obter_historico_por_zona as obter_historico_por_zona
from .leituras import obter_historicos_recentes_zonas as obter_historicos_recentes_zonas
from .leituras import obter_leituras_recentes_zona as obter_leituras_recentes_zona
from .leituras import obter_resumos_horarios as obter_resumos_horarios
from .leituras import salvar_leitura as salvar_leitura
from .leituras import salvar_leitura_recente_zona as salvar_leitura_recente_zona
from .operacao import listar_eventos_operacao as listar_eventos_operacao
from .operacao import obter_status_coletor as obter_status_coletor
from .operacao import registrar_evento_operacao as registrar_evento_operacao
from .operacao import salvar_status_coletor as salvar_status_coletor
from .usuarios import UltimoAdministradorError as UltimoAdministradorError
from .usuarios import UsuarioInvalidoError as UsuarioInvalidoError
from .usuarios import UsuarioNaoEncontradoError as UsuarioNaoEncontradoError
from .usuarios import atualizar_usuario as atualizar_usuario
from .usuarios import (
    contar_usuarios_ativos_por_perfil as contar_usuarios_ativos_por_perfil,
)
from .usuarios import criar_usuario as criar_usuario
from .usuarios import excluir_usuario as excluir_usuario
from .usuarios import listar_usuarios as listar_usuarios
from .usuarios import obter_hash_de_senha as obter_hash_de_senha
from .usuarios import obter_usuario as obter_usuario
from .usuarios import obter_usuario_por_login as obter_usuario_por_login
from .usuarios import redefinir_senha_usuario as redefinir_senha_usuario
from .usuarios import registrar_login_usuario as registrar_login_usuario
from .usuarios import trocar_senha_propria as trocar_senha_propria
from .zonas import EPSILON_TENDENCIA as EPSILON_TENDENCIA
from .zonas import LIMITE_LEITURAS_PAINEL_EXECUTIVO as LIMITE_LEITURAS_PAINEL_EXECUTIVO
from .zonas import MODO_OPERACAO_PADRAO as MODO_OPERACAO_PADRAO
from .zonas import MODOS_OPERACAO as MODOS_OPERACAO
from .zonas import ZonaInvalidaError as ZonaInvalidaError
from .zonas import ZonaNaoEncontradaError as ZonaNaoEncontradaError
from .zonas import _recomendacao_operacional as _recomendacao_operacional
from .zonas import _resumir_painel_zona as _resumir_painel_zona
from .zonas import _validar_inteiro as _validar_inteiro
from .zonas import _validar_numero as _validar_numero
from .zonas import _validar_zona as _validar_zona
from .zonas import atualizar_zona as atualizar_zona
from .zonas import criar_zona as criar_zona
from .zonas import excluir_zona as excluir_zona
from .zonas import listar_zonas as listar_zonas
from .zonas import obter_controle_zona as obter_controle_zona
from .zonas import obter_estado_operacional_zonas as obter_estado_operacional_zonas
from .zonas import obter_estatisticas_zonas as obter_estatisticas_zonas
from .zonas import obter_painel_zonas as obter_painel_zonas
from .zonas import obter_zona as obter_zona
from .zonas import salvar_controle_zona as salvar_controle_zona

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(PROJECT_ROOT, "instance")
_conexao = conexao


def iniciar_banco() -> None:
    """A inicialização de schema é exclusiva das revisões Alembic."""
