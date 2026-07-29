"""Repositórios para acesso a dados - Pattern Repository.

Módulos especializados para operações CRUD, separando lógica de banco
de dados da lógica de negócio.
"""

from app.repositories.configuracao_repository import ConfiguracaoRepository
from app.repositories.leitura_repository import LeituraRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.repositories.zona_repository import ZonaRepository

__all__ = [
    "ZonaRepository",
    "LeituraRepository",
    "UsuarioRepository",
    "ConfiguracaoRepository",
]
