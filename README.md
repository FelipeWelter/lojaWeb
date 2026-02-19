# LojaWeb (MVP)

Aplicação web em Python para gestão de loja de informática (desktop e mobile), com foco em:

- Controle de **estoque** de peças e computadores.
- Registro de **clientes**.
- Registro de **vendas** com baixa automática de estoque.
- Gestão de **cobranças** e confirmação de pagamento.
- Campo para referência de boleto/cobrança no **Mercado Pago**.

## Tecnologias

- Python + Flask
- HTML (Jinja2) + CSS responsivo
- SQLite

## Como executar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Acesse em `http://localhost:5000`.

## Fluxo sugerido para Mercado Pago

1. Gere os boletos/cobranças na sua conta Mercado Pago.
2. Cadastre no sistema a referência retornada em **Cobranças**.
3. Quando o pagamento entrar, use o botão **Confirmar pagamento**.

## Deploy em contêiner (Hostinger)

- Use uma imagem Python 3.11+
- Exponha a porta `5000`
- Defina comando de inicialização para `python app.py` (ou use Gunicorn em produção)
