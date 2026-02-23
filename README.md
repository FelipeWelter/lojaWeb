# LojaWeb — Plataforma de Gestão para Loja de Informática

LojaWeb é uma aplicação web desenvolvida em **Python + Flask** para operações de varejo técnico, com foco em lojas de informática, assistência e montagem de PCs.

O projeto centraliza o fluxo operacional em um único sistema: **cadastro de clientes, gestão de estoque, vendas, serviços, cobranças e auditoria**.

---

## Visão geral

A aplicação foi desenhada para o contexto de pequenas e médias operações que precisam de controle prático no dia a dia, sem abrir mão de rastreabilidade.

### Principais capacidades

- **Controle de estoque** de peças, periféricos e equipamentos.
- **Cadastro e histórico de clientes** para relacionamento e pós-venda.
- **Registro de vendas** com baixa automática de itens no estoque.
- **Gestão de serviços/manutenções** para atendimento técnico.
- **Montagem de PCs** com gestão de componentes e registros.
- **Cobranças** com referência externa (ex.: Mercado Pago) e confirmação de pagamento.
- **Gestão de usuários e autenticação**.
- **Logs/Auditoria** para rastrear alterações relevantes.
- **Impressões** (recibos, etiquetas e inventário) para apoio à operação.

---

## Stack tecnológica

- **Backend:** Python 3 + Flask
- **Persistência:** SQLite
- **ORM:** Flask-SQLAlchemy
- **E-mail transacional:** Flask-Mail
- **Geração de PDF:** xhtml2pdf
- **Frontend:** HTML + Jinja2 + CSS responsivo

Dependências principais em `requirements.txt`.

---

## Estrutura do projeto

```text
.
├── app.py                # Rotas, regras de negócio e inicialização da aplicação
├── crud.py               # Operações de dados e utilitários de persistência
├── flask_mail.py         # Integração de envio de e-mails
├── templates/            # Páginas e componentes Jinja2
├── static/               # Arquivos estáticos (CSS e impressão)
├── requirements.txt      # Dependências Python
└── docker-compose.yml    # Ambiente opcional via Docker
```

---

## Pré-requisitos

- **Python 3.10+** (recomendado)
- **pip**
- (Opcional) **virtualenv/venv**

---

## Instalação e execução local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

A aplicação ficará disponível em:

- `http://localhost:5000`

---

## Execução com Docker (opcional)

Se preferir executar com containers:

```bash
docker compose up --build
```

> Ajuste variáveis de ambiente e volumes conforme sua necessidade operacional.

---

## Fluxo recomendado para cobranças com Mercado Pago

1. Gere as cobranças no painel do Mercado Pago.
2. Cadastre no LojaWeb a referência retornada pela plataforma.
3. Acompanhe o status no módulo de **Cobranças**.
4. Ao identificar o recebimento, realize a **confirmação de pagamento** no sistema.

---

## Segurança e operação

Para uso em ambiente produtivo, recomenda-se:

- Configurar `SECRET_KEY` forte e gerenciamento seguro de credenciais.
- Restringir acesso ao banco e realizar backups periódicos.
- Utilizar servidor WSGI (ex.: Gunicorn) atrás de proxy reverso.
- Habilitar monitoramento de logs e rotinas de auditoria.

---

## Roadmap sugerido

- API REST para integrações externas.
- Painéis com indicadores avançados de vendas e margem.
- Controle de permissões por perfil (RBAC).
- Testes automatizados de regressão para módulos críticos.

---

## Licença

Defina aqui o modelo de licenciamento adotado pelo projeto (ex.: MIT, Apache-2.0, proprietário).
