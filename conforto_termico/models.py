# -*- coding: utf-8 -*-
"""
models.py
=========
Classes de domínio inspiradas literalmente no Diagrama de Classes da
dissertação (Figura 14, seção 3.3.3): Temperatura, Resfriamento e Email.

No documento original, o diagrama descreve:
    Temperatura     -Temperatura: double        +VerificarTemperatura(): void
                                                  +CalcularICT(): void
    Resfriamento    -TipoDeResfriador: int       +Ativar(): void
                                                  +Desativar(): void
    Email           -Destino: char               +Enviar(): void
                    -Conteudo: char               +InformarEnvio(): void

As três classes abaixo implementam esses mesmos métodos, adaptados para
Python/Flask.
"""

from __future__ import annotations

import datetime
import os
import smtplib
from email.mime.text import MIMEText

from . import thermal_indices as ti


class Temperatura:
    """Corresponde à classe 'Temperatura' da Figura 14: recebe leituras
    (manuais ou de sensores simulados) e calcula o Índice de Conforto
    Térmico (ICT) apropriado para a espécie selecionada."""

    def __init__(self, especie: str, indice: str):
        if especie not in ti.ESPECIES_VALIDAS:
            raise ti.EntradaInvalidaError(f"Espécie inválida: '{especie}'.")
        if not ti.indice_disponivel(especie, indice):
            raise ti.EntradaInvalidaError(
                f"O índice {indice} não está disponível para {ti.NOME_ESPECIE.get(especie, especie)}."
            )
        self.especie = especie
        self.indice = indice
        self.temperatura: float | None = None  # último valor calculado (ICT)
        self.entradas: dict = {}  # últimas entradas validadas (para persistir o histórico)

    def verificar_temperatura(self, entradas: dict) -> dict:
        """Valida os dados recebidos (digitados ou de sensores remotos)."""
        return ti.validar_entradas(self.indice, entradas)

    def calcular_ict(self, entradas: dict) -> tuple[float, str]:
        """Calcula o Índice de Conforto Térmico e devolve (valor, status)."""
        entradas_validas = self.verificar_temperatura(entradas)
        valor = round(ti.CALCULADORAS[self.indice](**entradas_validas), 2)
        status = ti.classificar_status(valor, self.especie, self.indice)
        self.temperatura = valor
        self.entradas = entradas_validas
        return valor, status


class Resfriamento:
    """Corresponde à classe 'Resfriamento' da Figura 14: representa o estado
    dos equipamentos remotos (ventiladores e nebulizadores) descritos na
    seção 4.3 da dissertação."""

    # tipo_de_resfriador: 0=nenhum, 1=ventilador, 2=nebulizador, 3=ambos
    def __init__(self):
        self.tipo_de_resfriador: int = 0
        self.ativo: bool = False
        self.intensidade: str | None = None

    def ativar(self, intensidade: str) -> None:
        self.ativo = True
        self.intensidade = intensidade
        self.tipo_de_resfriador = 3  # a dissertação liga ventilador + nebulizador juntos

    def desativar(self) -> None:
        self.ativo = False
        self.intensidade = None
        self.tipo_de_resfriador = 0

    def estado(self) -> dict:
        return {
            "ativo": self.ativo,
            "intensidade": self.intensidade,
            "ventilador": self.ativo,
            "nebulizador": self.ativo,
        }


class Email:
    """Corresponde à classe 'Email' da Figura 14: monta e (opcionalmente)
    envia a notificação, no mesmo formato mostrado nas Figuras 20/22/25/28
    da dissertação.

    Sem variáveis de ambiente de SMTP configuradas, opera em modo simulado:
    o conteúdo é montado normalmente para exibição na tela, mas nenhum
    e-mail real é disparado."""

    def __init__(self, destino: str, conteudo: str):
        self.destino = destino
        self.conteudo = conteudo
        self._enviado = False

    def enviar(self) -> bool:
        host = os.environ.get("SMTP_HOST")
        if not host:
            self._enviado = False
            return False
        porta = int(os.environ.get("SMTP_PORT", "587"))
        usuario = os.environ.get("SMTP_USER")
        senha = os.environ.get("SMTP_PASS")
        try:
            msg = MIMEText(self.conteudo, _charset="utf-8")
            msg["Subject"] = "Alerta - Sistema de Controle dos Índices de Conforto Térmico"
            msg["From"] = usuario
            msg["To"] = self.destino
            with smtplib.SMTP(host, porta, timeout=10) as servidor:
                servidor.starttls()
                servidor.login(usuario, senha)
                servidor.sendmail(usuario, [self.destino], msg.as_string())
            self._enviado = True
        except Exception:
            self._enviado = False
        return self._enviado

    def informar_envio(self) -> bool:
        return self._enviado

    @staticmethod
    def montar_conteudo(indice: str, valor: float, status: str) -> str:
        """Monta o texto do e-mail no mesmo layout das Figuras 20/22/25/28."""
        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return (
            f"Status: {status}\n"
            f"Data: {agora}\n"
            f"Valor do {indice}: {valor}\n"
            f"Mensagem: {ti.MENSAGENS_STATUS[status]}\n"
            + "*" * 75
            + "\n"
            "Você está recebendo esse e-mail por estar cadastrado na lista de "
            "usuários do Sistema de Controle dos Índices de Conforto Térmico. "
            "Em caso de dúvida contate o administrador do sistema.\nObrigado."
        )
