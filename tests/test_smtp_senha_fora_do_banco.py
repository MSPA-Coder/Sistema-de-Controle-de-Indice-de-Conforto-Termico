"""A senha SMTP não mora mais no banco (CT-03).

Até 01/09/2026, `smtpSenha` persistia em texto claro na tabela
`configuracoes`. A API já não a devolvia (`_configuracoes_publicas`
mascarava), mas o dump que o BackupRestore gera e cataloga todo dia replicava
o valor sem passar por tela nenhuma. Agora a senha nunca chega ao banco: vem
exclusivamente de `SMTP_PASS` (variável direta ou segredo do Compose via
`SMTP_PASS_FILE`), resolvida por `models._resolver_senha_smtp`.

Estes testes não tocam PostgreSQL: `_sanitizar_configuracoes` e
`smtp_config_atual` são funções puras, e a resolução de segredo só lê
variável de ambiente/arquivo local.
"""

from __future__ import annotations

from app import models, notificacoes
from app.database.configuracoes import CONFIGURACOES_PADRAO, _sanitizar_configuracoes
from app.ict.administracao import _configuracoes_publicas
from app.models import Email, _resolver_senha_smtp, senha_smtp_configurada


def test_configuracoes_padrao_nao_tem_chave_de_senha():
    assert "smtpSenha" not in CONFIGURACOES_PADRAO


def test_sanitizar_configuracoes_descarta_senha_recebida():
    """Um cliente antigo que ainda envie `smtpSenha` é ignorado, não recusado."""
    resultado = _sanitizar_configuracoes({"smtpSenha": "segredo-antigo", "smtpHost": "smtp.exemplo.com"})

    assert "smtpSenha" not in resultado
    assert resultado["smtpHost"] == "smtp.exemplo.com"


def test_sanitizar_configuracoes_descarta_senha_da_base_anterior():
    """Uma linha de `smtpSenha` remanescente no banco (antes da migração que a
    apaga) também não sobrevive à sanitização -- ela nunca volta a ser
    persistida, mesmo que ainda exista na leitura bruta da tabela."""
    resultado = _sanitizar_configuracoes({}, base={"smtpSenha": "segredo-antigo"})

    assert "smtpSenha" not in resultado


def test_smtp_config_atual_nao_tem_chave_de_senha():
    config = {"smtpHost": "smtp.exemplo.com", "smtpPorta": 587, "smtpUsuario": "alertas"}

    resultado = notificacoes.smtp_config_atual(config)

    assert "senha" not in resultado
    assert resultado["host"] == "smtp.exemplo.com"


def test_resolver_senha_smtp_le_variavel_de_ambiente(monkeypatch):
    monkeypatch.delenv("SMTP_PASS_FILE", raising=False)
    monkeypatch.setenv("SMTP_PASS", "senha-de-teste")

    assert _resolver_senha_smtp() == "senha-de-teste"
    assert senha_smtp_configurada() is True


def test_resolver_senha_smtp_ausente_e_none(monkeypatch):
    monkeypatch.delenv("SMTP_PASS_FILE", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    assert _resolver_senha_smtp() is None
    assert senha_smtp_configurada() is False


def test_resolver_senha_smtp_le_segredo_de_arquivo(monkeypatch, tmp_path):
    """`SMTP_PASS_FILE` (segredo do Compose) tem precedência sobre a variável direta.

    `caminho_esperado` (ver `sharedauth.secrets.ler_arquivo_de_segredo`) fecha
    `SMTP_PASS_FILE` num alvo único -- por isso o teste aponta
    `models.DIRETORIO_SECRETS_COMPOSE` para `tmp_path`, mesmo padrão já usado
    em `tests/test_auth_required.py` para `auth.DIRETORIO_SECRETS_COMPOSE`.
    """
    monkeypatch.setattr(models, "DIRETORIO_SECRETS_COMPOSE", tmp_path)
    arquivo = tmp_path / "smtp_password"
    arquivo.write_text("senha-do-arquivo", encoding="utf-8")
    monkeypatch.setenv("SMTP_PASS_FILE", str(arquivo))
    monkeypatch.setenv("SMTP_PASS", "senha-que-nao-deveria-ganhar")

    assert _resolver_senha_smtp() == "senha-do-arquivo"


def test_email_enviar_usa_a_senha_resolvida_quando_smtp_config_nao_traz(monkeypatch):
    """`Email.enviar` recebe host/porta/usuario de `smtp_config`, mas a senha
    vem do resolvedor -- exatamente o que `smtp_config_atual` (sem "senha")
    força a acontecer em produção."""
    monkeypatch.delenv("SMTP_PASS_FILE", raising=False)
    monkeypatch.setenv("SMTP_PASS", "senha-do-servidor")

    capturado = {}

    class _SMTPFalso:
        def __init__(self, host, porta, timeout):
            capturado["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self):
            pass

        def login(self, usuario, senha):
            capturado["usuario"] = usuario
            capturado["senha"] = senha

        def sendmail(self, remetente, destinatarios, mensagem):
            pass

    monkeypatch.setattr("smtplib.SMTP", _SMTPFalso)

    email = Email("destino@exemplo.com", "conteudo")
    enviado = email.enviar({"host": "smtp.exemplo.com", "usuario": "alertas@exemplo.com"})

    assert enviado is True
    assert capturado["senha"] == "senha-do-servidor"


def test_configuracoes_publicas_reflete_segredo_nao_o_banco(monkeypatch):
    monkeypatch.delenv("SMTP_PASS_FILE", raising=False)
    monkeypatch.setenv("SMTP_PASS", "senha-do-servidor")

    # `config` simula o que vem do banco: mesmo que carregue uma chave de
    # senha remanescente (linha antiga, ainda não apagada pela migração), a
    # tela nunca deve refletir ISSO -- só se o segredo do servidor resolve.
    publico = _configuracoes_publicas({"smtpHost": "smtp.exemplo.com", "smtpSenha": "resto-antigo"})

    assert publico["smtpSenha"] == ""
    assert publico["smtpSenhaConfigurada"] is True


def test_configuracoes_publicas_sem_segredo_reporta_nao_configurada(monkeypatch):
    monkeypatch.delenv("SMTP_PASS_FILE", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    publico = _configuracoes_publicas({"smtpHost": ""})

    assert publico["smtpSenhaConfigurada"] is False
