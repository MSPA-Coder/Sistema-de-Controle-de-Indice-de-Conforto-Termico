# ADR 004: Ferramentas de Qualidade de Código

## Status

Aceito

## Contexto

Para manter a qualidade do código do Sistema de Controle de Conforto Térmico Animal, é necessário estabelecer padrões consistentes e automatizar verificações.

## Decisão

Adotar o seguinte stack de ferramentas de qualidade:

### 1. Ruff (Linter e Formatter)
- Substitui: flake8, black, isort, pyupgrade
- Vantagens: Extremamente rápido (escrito em Rust), configuração unificada
- Configuração: `ruff.toml`
- Regras habilitadas:
  - E, F, W: Erros e warnings padrão
  - I: Ordenação de imports
  - N: Naming conventions
  - UP: Upgrade para sintaxe Python moderna
  - B: Bugbear (bugs comuns)
  - C4: Compreensões otimizadas
  - SIM: Simplificações de código

### 2. Mypy (Type Checker)
- Abordagem: Gradual typing
- Configuração: `mypy.ini`
- Módulos com strict mode inicial: auth, cache, services, thermal_indices
- Expansão gradual para outros módulos

### 3. Pre-commit Hooks
- Execução automática antes de commits
- Hooks configurados:
  - Ruff check + format
  - Mypy type checking
  - Trailing whitespace
  - End of file fixer
  - YAML/JSON validation
  - Detect private keys
  - Check merge conflicts

## Configuração Técnica

```toml
# ruff.toml
target-version = "py313"
line-length = 100
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]
```

```ini
# mypy.ini
[mypy]
python_version = 3.13
strict = False
ignore_missing_imports = True
check_untyped_defs = True
```

## Consequências Positivas

- Código consistente automaticamente
- Bugs detectados antes da execução
- Documentação implícita via type hints
- Review de código mais focado em lógica
- Onboarding mais rápido de novos desenvolvedores

## Consequências Negativas

- Curva de aprendizado inicial
- Time adicional no CI para type checking
- Necessidade de adicionar type hints gradualmente

## Alternativas Consideradas

1. **Pyright**: Mais rápido que mypy, mas menos maduro
2. **Pylance**: Excelente para VS Code, mas menos CLI-focused
3. **Flake8 + Black + Isort**: Stack tradicional, mais lento e complexo

## Implementação

- Instalação: `pip install ruff mypy pre-commit`
- Setup local: `pre-commit install`
- CI integration: GitHub Actions workflow

## Referências

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Mypy Documentation](https://mypy.readthedocs.io/)
- [Pre-commit Documentation](https://pre-commit.com/)
