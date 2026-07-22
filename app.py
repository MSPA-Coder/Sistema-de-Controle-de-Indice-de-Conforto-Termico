# -*- coding: utf-8 -*-
"""Lancador para executar a aplicacao com `python app.py`."""

from app.web import (
    app,
    executar_servidor_local,
)


if __name__ == "__main__":
    executar_servidor_local()
