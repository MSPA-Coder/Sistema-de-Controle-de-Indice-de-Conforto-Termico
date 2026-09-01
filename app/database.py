"""Fachada compatível para os agregados de persistência.

Os consumidores continuam usando :mod:`app.database`; os módulos
``database_*`` concentram a implementação de cada agregado.
"""

from __future__ import annotations

import os

from .database_auditoria import listar_eventos_auditoria as listar_eventos_auditoria
from .database_auditoria import registrar_evento_auditoria as registrar_evento_auditoria
from .database_comum import PERFIS_VALIDOS as PERFIS_VALIDOS
from .database_comum import coagir_booleano as coagir_booleano
from .database_comum import conexao
from .database_configuracoes import CONFIGURACOES_PADRAO as CONFIGURACOES_PADRAO
from .database_configuracoes import limpar_cache_configuracoes as limpar_cache_configuracoes
from .database_configuracoes import obter_configuracoes as obter_configuracoes
from .database_configuracoes import salvar_configuracoes as salvar_configuracoes
from .database_equipamentos import CAMPOS_MEDIVEIS as CAMPOS_MEDIVEIS
from .database_equipamentos import MODOS_CONEXAO as MODOS_CONEXAO
from .database_equipamentos import TIPOS_DADO as TIPOS_DADO
from .database_equipamentos import TIPOS_EQUIPAMENTO as TIPOS_EQUIPAMENTO
from .database_equipamentos import atualizar_equipamento as atualizar_equipamento
from .database_equipamentos import criar_equipamento as criar_equipamento
from .database_equipamentos import excluir_equipamento as excluir_equipamento
from .database_equipamentos import obter_equipamento as obter_equipamento
from .database_equipamentos import (
    registrar_falha_operacional_zona as registrar_falha_operacional_zona,
)
from .database_equipamentos import salvar_comando_manual_atuador as salvar_comando_manual_atuador
from .database_equipamentos import salvar_estado_equipamentos as salvar_estado_equipamentos
from .database_leituras import INTERVALO_MINIMO_LEITURAS as INTERVALO_MINIMO_LEITURAS
from .database_leituras import _formatar_janela as _formatar_janela
from .database_leituras import _intervalo_minimo_leituras as _intervalo_minimo_leituras
from .database_leituras import agregar_janela_15min as agregar_janela_15min
from .database_leituras import consolidar_resumo_horario as consolidar_resumo_horario
from .database_leituras import contar_leituras as contar_leituras
from .database_leituras import horas_pendentes as horas_pendentes
from .database_leituras import janelas_15min_pendentes as janelas_15min_pendentes
from .database_leituras import limpar_historico as limpar_historico
from .database_leituras import obter_agregados_15min as obter_agregados_15min
from .database_leituras import obter_historico_leituras as obter_historico_leituras
from .database_leituras import obter_historico_por_zona as obter_historico_por_zona
from .database_leituras import obter_historicos_recentes_zonas as obter_historicos_recentes_zonas
from .database_leituras import obter_leituras_recentes_zona as obter_leituras_recentes_zona
from .database_leituras import obter_resumos_horarios as obter_resumos_horarios
from .database_leituras import salvar_leitura as salvar_leitura
from .database_leituras import salvar_leitura_recente_zona as salvar_leitura_recente_zona
from .database_operacao import listar_eventos_operacao as listar_eventos_operacao
from .database_operacao import obter_status_coletor as obter_status_coletor
from .database_operacao import registrar_evento_operacao as registrar_evento_operacao
from .database_operacao import salvar_status_coletor as salvar_status_coletor
from .database_usuarios import UltimoAdministradorError as UltimoAdministradorError
from .database_usuarios import UsuarioInvalidoError as UsuarioInvalidoError
from .database_usuarios import UsuarioNaoEncontradoError as UsuarioNaoEncontradoError
from .database_usuarios import atualizar_usuario as atualizar_usuario
from .database_usuarios import (
    contar_usuarios_ativos_por_perfil as contar_usuarios_ativos_por_perfil,
)
from .database_usuarios import criar_usuario as criar_usuario
from .database_usuarios import excluir_usuario as excluir_usuario
from .database_usuarios import listar_usuarios as listar_usuarios
from .database_usuarios import obter_hash_de_senha as obter_hash_de_senha
from .database_usuarios import obter_usuario as obter_usuario
from .database_usuarios import obter_usuario_por_login as obter_usuario_por_login
from .database_usuarios import redefinir_senha_usuario as redefinir_senha_usuario
from .database_usuarios import registrar_login_usuario as registrar_login_usuario
from .database_usuarios import trocar_senha_propria as trocar_senha_propria
from .database_zonas import EPSILON_TENDENCIA as EPSILON_TENDENCIA
from .database_zonas import LIMITE_LEITURAS_PAINEL_EXECUTIVO as LIMITE_LEITURAS_PAINEL_EXECUTIVO
from .database_zonas import MODO_OPERACAO_PADRAO as MODO_OPERACAO_PADRAO
from .database_zonas import MODOS_OPERACAO as MODOS_OPERACAO
from .database_zonas import ZonaInvalidaError as ZonaInvalidaError
from .database_zonas import ZonaNaoEncontradaError as ZonaNaoEncontradaError
from .database_zonas import _recomendacao_operacional as _recomendacao_operacional
from .database_zonas import _resumir_painel_zona as _resumir_painel_zona
from .database_zonas import _validar_inteiro as _validar_inteiro
from .database_zonas import _validar_numero as _validar_numero
from .database_zonas import _validar_zona as _validar_zona
from .database_zonas import atualizar_zona as atualizar_zona
from .database_zonas import criar_zona as criar_zona
from .database_zonas import excluir_zona as excluir_zona
from .database_zonas import listar_zonas as listar_zonas
from .database_zonas import obter_controle_zona as obter_controle_zona
from .database_zonas import obter_estado_operacional_zonas as obter_estado_operacional_zonas
from .database_zonas import obter_estatisticas_zonas as obter_estatisticas_zonas
from .database_zonas import obter_painel_zonas as obter_painel_zonas
from .database_zonas import obter_zona as obter_zona
from .database_zonas import salvar_controle_zona as salvar_controle_zona

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(PROJECT_ROOT, "instance")
_conexao = conexao


def iniciar_banco() -> None:
    """A inicialização de schema é exclusiva das revisões Alembic."""
