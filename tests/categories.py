"""Classificação verificável da suíte por risco e finalidade.

As regras usam o módulo do teste para que a seleção de controles na CI não
dependa de detalhes internos nem de uma ordem de execução.
"""

from __future__ import annotations

from pathlib import Path

_CATEGORIES_BY_MODULE = {
    "test_auth": {"security", "critical"},
    "test_criar_usuario_admin": {"security", "critical"},
    "test_configurar_segredos": {"security"},
    "test_app": {"contract", "critical"},
    "test_administracao": {"contract", "security"},
    "test_verificar_postgres": {"migration", "persistence", "critical"},
    "test_db_backend": {"migration", "persistence", "critical"},
    "test_database": {"persistence", "critical"},
    "test_models": {"persistence"},
    "test_thermal_indices": {"business_rule", "critical"},
    "test_zona_service": {"business_rule", "critical"},
    "test_controle": {"business_rule", "critical"},
    "test_services": {"business_rule"},
    "test_dados_entrada": {"business_rule", "persistence"},
    "test_agregacao": {"business_rule", "persistence"},
    "test_notificacoes": {"business_rule"},
    "test_cache": {"business_rule"},
    "test_modbus_client": {"business_rule"},
    "test_modbus_simulador": {"business_rule"},
    "test_app_factory": {"architecture"},
    "test_categories": {"architecture"},
    "test_env_config": {"architecture", "security"},
}


def categories_for_test_id(test_id: str) -> set[str]:
    """Retorna as categorias atribuídas ao identificador do unittest."""
    module = test_id.split(".")[-3]
    return _CATEGORIES_BY_MODULE.get(module, set())


def unclassified_test_modules() -> set[str]:
    test_dir = Path(__file__).parent
    discovered = {path.stem for path in test_dir.glob("test_*.py")}
    return discovered - set(_CATEGORIES_BY_MODULE)
