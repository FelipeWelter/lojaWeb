# Mapeamento Funcional — Projeto lojaWeb

> Objetivo: criar uma ponte direta entre UI (botões, formulários, tabelas e modais) e a lógica backend/frontend responsável por cada ação.

## Módulo: Vendas (Carrinho / PDV)

| Elemento de Interface | Localização (Arquivo) | Função Principal | Lógica Funcional |
|---|---|---|---|
| Botão **"Finalizar venda"** (`#finalize-sale-btn`) no formulário `#sale-form` | `templates/sales.html` + `app.py` | `vendas()` | No frontend, o submit bloqueia duplo clique e exibe "Processando...". No backend, valida cliente, linhas de item/produto/serviço, calcula subtotal/desconto/total, movimenta estoque e cria cobrança quando fluxo for a prazo. |
| Botão **"+ Adicionar item/serviço"** (`#add-line`) | `templates/sales.html` | `bindLine(line)` + handler de `addLineBtn` | Clona a primeira linha do carrinho, reseta campos, reaplica bindings de eventos e recalcula totais para manter consistência de preço/custo/descrição por linha. |
| Campos **Desconto, Valor recebido e Troco** | `templates/sales.html` | `recalcTotal()` | Soma itens em centavos (evita erro de ponto flutuante), aplica desconto, calcula total final e troco, atualizando indicadores visuais (positivo/negativo/neutro). |
| Checkbox **"Marque se for a prazo"** + parcelas | `templates/sales.html` | `togglePaymentFlowFields()` + `rebuildInstallmentDueDates()` | Abre/fecha bloco de crédito, limpa campos quando desativado e gera dinamicamente datas de vencimento por parcela para envio no POST da venda. |
| Botão **"Cancelar venda"** (histórico) | `templates/sales.html` + `app.py` | `cancelar_venda(sale_id)` | Marca venda como cancelada e estorna estoque item a item (incluindo reativação de computador quando aplicável), preservando trilha histórica. |
| Botão **"Baixar parcela"** (financeiro da venda) | `templates/sales.html` + `app.py` | `pagar_parcela_cobranca(charge_id, installment_number)` | Registra baixa parcial/total da parcela, atualiza status agregado da cobrança e sincroniza estado do serviço relacionado quando necessário. |

---

## Módulo: Cadastro de Clientes (CRM)

| Elemento de Interface | Localização (Arquivo) | Função Principal | Lógica Funcional |
|---|---|---|---|
| Formulário **"Novo cliente / Editar cliente"** | `templates/clients.html` + `app.py` | `clientes()` + `_persist_client_from_form(form_data)` | Valida nome obrigatório, impede CPF e nome duplicados, aplica DTO/validação e decide entre criação ou atualização do registro. |
| Botão **"Mesclar históricos"** | `templates/clients.html` + `app.py` | `mesclar_clientes()` | Transfere todas as vendas do cliente origem para o cliente destino e remove o cadastro antigo, mantendo histórico comercial consolidado. |
| Botão **"Remover cliente"** | `templates/clients.html` + `app.py` | `remover_cliente(client_id)` | Bloqueia remoção quando existir venda ativa; quando permitido, realiza inativação lógica do cliente. |
| Campo de busca **"Pesquisar por nome, CPF..."** | `templates/clients.html` | Handler `input` de `#client-search` | Filtra linhas da tabela em tempo real por dataset indexado; colapsa automaticamente históricos de clientes ocultados pelo filtro. |
| Botões de expansão de histórico (`.accordion-toggle`) | `templates/clients.html` | Handler de clique do acordeão | Alterna abertura/fechamento da linha de histórico do cliente e sincroniza `aria-expanded` para acessibilidade. |

---

## Módulo: Cobranças e Pagamento

| Elemento de Interface | Localização (Arquivo) | Função Principal | Lógica Funcional |
|---|---|---|---|
| Formulário **"Registrar cobrança"** | `templates/charges.html` + `app.py` | `cobrancas()` (POST) | Valida origem (venda/serviço), data e valores, calcula total líquido com desconto, cria cobrança (simples ou parcelada), normaliza status e persiste parcelas. |
| Selects **Venda/Serviço + Total/Desconto/Valor final** | `templates/charges.html` | `syncChargeAmountFromSource()` | Obtém total da origem selecionada, aplica desconto, preenche total de referência e valor final da cobrança automaticamente. |
| Checkbox **"Pagamento parcelado"** + preview de parcela | `templates/charges.html` | `updateInstallmentPreview()` | Habilita/desabilita quantidade de parcelas e calcula valor estimado de cada parcela em tempo real. |
| Botão **"Confirmar pagamento"** / **"Marcar faturas pagas"** | `templates/charges.html` + `app.py` | `confirmar_cobranca(charge_id)` | Liquida cobrança integralmente (ou parcelas), atualiza status, grava timestamp de confirmação e dispara sincronizações de serviço/venda. |
| Formulário **"Salvar"** (edição da cobrança) | `templates/charges.html` + `app.py` | `editar_cobranca(charge_id)` | Atualiza metadados financeiros (referência, vencimento, valor, pagamento parcial, forma/status), mantendo consistência das parcelas. |
| Botões **"Cancelar cobrança"** e **"Excluir cobrança"** | `templates/charges.html` + `app.py` | `cancelar_cobranca(charge_id)` / `excluir_cobranca(charge_id)` | Permite cancelar semanticamente (status) ou excluir definitivamente o lançamento financeiro. |

---

## Módulo: Estoque e Produtos

| Elemento de Interface | Localização (Arquivo) | Função Principal | Lógica Funcional |
|---|---|---|---|
| Formulário **"Cadastrar no estoque"** (produto/peça) | `templates/products.html` + `app.py` | `produtos()` | Diferencia cadastro de peça x computador montado, valida classe da peça, processa foto e persiste atributos técnicos e comerciais. |
| Botão **"Salvar alterações"** de produto | `templates/products.html` + `app.py` | `editar_produto(product_id)` | Atualiza preço/custo/metadados técnicos, incluindo registro de auditoria quando há alteração de preço. |
| Botão **"Inativar"** | `templates/inventory_management.html` + `app.py` | `remover_produto(product_id)` | Realiza soft delete (item inativo), mantendo histórico para consultas e relatórios. |
| Botão **"Ativar"** | `templates/inventory_management.html` + `app.py` | `ativar_produto(product_id)` | Reativa item previamente inativado para retorno ao fluxo de venda/estoque. |
| Botão **"Excluir"** | `templates/inventory_management.html` + `app.py` | `excluir_produto(product_id)` | Remove o item permanentemente da base quando a operação exige limpeza definitiva. |

---

## Padrão de Documentação Inline (JSDoc/PHPDoc)

> Abaixo estão modelos recomendados para padronizar comentários de funções críticas mapeadas acima.

### Exemplo JSDoc (frontend JS)

```js
/**
 * Recalcula subtotal, desconto, total e troco do checkout.
 *
 * @returns {void} Não retorna valor; atualiza o DOM com os valores formatados.
 */
function recalcTotal() {
  // ...
}

/**
 * Sincroniza uma linha de venda entre tipo (produto/serviço), preço, custo e descrição.
 *
 * @param {HTMLElement} line Linha de item da venda que receberá os event listeners.
 * @returns {void} Não retorna valor; altera estado de campos e aciona recálculo.
 */
function bindLine(line) {
  // ...
}

/**
 * Alterna a exibição dos campos de pagamento a prazo e reconfigura valores padrão.
 *
 * @returns {void} Não retorna valor; ajusta visibilidade e limpa campos de crédito.
 */
function togglePaymentFlowFields() {
  // ...
}
```

### Exemplo PHPDoc (backend PHP — referência de padrão)

```php
/**
 * Confirma o pagamento de uma cobrança e atualiza seu status final.
 *
 * @param int $chargeId Identificador único da cobrança.
 * @param float $amountPaid Valor pago na operação atual.
 * @return array{success: bool, message: string} Resultado da confirmação para a camada de apresentação.
 */
function confirmarCobranca(int $chargeId, float $amountPaid): array
{
    // ...
}

/**
 * Mescla o histórico comercial de um cliente origem em um cliente destino.
 *
 * @param int $sourceClientId ID do cliente que será descontinuado.
 * @param int $targetClientId ID do cliente que receberá o histórico.
 * @return bool Retorna true quando a operação é concluída sem erro.
 */
function mergeClients(int $sourceClientId, int $targetClientId): bool
{
    // ...
}
```

### Exemplo equivalente para este projeto (Python Docstring)

```python
def mesclar_clientes():
    """Mescla dois clientes transferindo o histórico de vendas para o cliente destino.

    Returns:
        Response: Redirecionamento para a tela de clientes com flash de sucesso/erro.
    """
```

---

## Bloco final — preparo para exportação em PDF

### Estrutura recomendada para PDF
1. **Capa:** "Mapeamento Funcional — lojaWeb" + data da versão.
2. **Sumário por módulo:** Vendas, Clientes, Cobranças, Estoque.
3. **Tabelas de mapeamento funcional:** (conteúdo deste documento).
4. **Anexo técnico:** padrões JSDoc/PHPDoc/docstring.

### Sugestão prática de exportação
- Converter este Markdown para PDF mantendo tabelas e blocos de código.
- Opções comuns:
  - VS Code: `Markdown: Open Preview to the Side` → `Print` → `Save as PDF`.
  - Pandoc: `pandoc docs/MAPEAMENTO_FUNCIONAL.md -o docs/MAPEAMENTO_FUNCIONAL.pdf`.

> Estado: **conteúdo já estruturado e pronto para exportação em PDF**.
