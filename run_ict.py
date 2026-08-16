"""Lançador da Interface de Conforto Térmico (ICT)."""

from app.app_factory import AppConfig, criar_app_ict, executar_ict

config = AppConfig.from_env("ict")
app = criar_app_ict(config)


if __name__ == "__main__":
    executar_ict(app, config)
