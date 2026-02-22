# Refatoração Profissional — lojaWeb

## 1) Estrutura de pastas sugerida (alvo Spring Boot + Thymeleaf)

```txt
src/main/java/com/lojaweb/
  config/
    WebConfig.java
  controller/
    generic/GenericCrudController.java
    ProductController.java
    CategoryController.java
    BrandController.java
    ClientController.java
  dto/
    product/ProductRequestDTO.java
    product/ProductResponseDTO.java
    client/ClientRequestDTO.java
    client/ClientResponseDTO.java
    category/CategoryDTO.java
    brand/BrandDTO.java
  entity/
    BaseEntity.java          # id, createdAt, updatedAt, ativo
    Product.java
    Category.java
    Brand.java
    Client.java
  exception/
    GlobalExceptionHandler.java
    BusinessException.java
    ResourceNotFoundException.java
  mapper/
    ProductMapper.java
    ClientMapper.java
  repository/
    BaseRepository.java
    ProductRepository.java
    CategoryRepository.java
    BrandRepository.java
    ClientRepository.java
  service/
    generic/GenericCrudService.java
    generic/GenericCrudServiceImpl.java
    ProductService.java
    CategoryService.java
    BrandService.java
    ClientService.java

src/main/resources/templates/
  layout/fragments.html
  dashboard/inventory-management.html
  product/_product-table.html
  product/_product-form-modal.html
  shared/_toasts.html
```

## 2) Exemplo de `GenericService`

```java
public interface GenericCrudService<REQ, RES, ID> {
    RES create(@Valid REQ request);
    RES update(ID id, @Valid REQ request);
    RES findById(ID id);
    Page<RES> findAll(Pageable pageable);
    void softDelete(ID id);
}

@Transactional
public abstract class GenericCrudServiceImpl<E extends BaseEntity, REQ, RES>
        implements GenericCrudService<REQ, RES, Long> {

    protected abstract JpaRepository<E, Long> repository();
    protected abstract E toEntity(REQ request);
    protected abstract void merge(E entity, REQ request);
    protected abstract RES toResponse(E entity);

    @Override
    public RES create(@Valid REQ request) {
        E entity = toEntity(request);
        entity.setAtivo(true);
        return toResponse(repository().save(entity));
    }

    @Override
    public RES update(Long id, @Valid REQ request) {
        E entity = repository().findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("Registro não encontrado"));
        merge(entity, request);
        return toResponse(repository().save(entity));
    }

    @Override
    @Transactional(readOnly = true)
    public RES findById(Long id) {
        E entity = repository().findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("Registro não encontrado"));
        return toResponse(entity);
    }

    @Override
    public void softDelete(Long id) {
        E entity = repository().findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("Registro não encontrado"));
        entity.setAtivo(false);
        repository().save(entity);
    }
}
```

## 3) Como deve ficar o novo `fragments.html`

```html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org">
<body>
  <aside th:fragment="sidebar(active)">
    <nav>
      <a th:href="@{/dashboard}" th:classappend="${active == 'dashboard'} ? 'active'">Dashboard</a>
      <a th:href="@{/inventario}" th:classappend="${active == 'inventario'} ? 'active'">Gestão de Inventário</a>
      <a th:href="@{/clientes}" th:classappend="${active == 'clientes'} ? 'active'">Clientes</a>
    </nav>
  </aside>

  <header th:fragment="navbar(user)">
    <h1>Painel de Gestão</h1>
    <span th:text="${user}">Usuário</span>
  </header>

  <div th:fragment="toasts(messages)">
    <div class="toast-container" th:if="${messages != null}">
      <div class="toast" th:each="m : ${messages}" th:text="${m}"></div>
    </div>
  </div>

  <th:block th:fragment="scripts">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/js/inventory-filters.js"></script>
  </th:block>
</body>
</html>
```

## 4) Guia de migração: abas redundantes → Dashboard Única

1. **Mapear telas atuais**: identificar páginas “Lista” e “Cadastro” de Produto/Categoria/Marca/Cliente.
2. **Criar rota única de gestão** (`/inventario`) retornando tabela + botões de ação.
3. **Mover formulários para modais**:
   - Modal “Novo” compartilhado por tipo.
   - Modal “Editar” carregado sob demanda por ID.
4. **Substituir submits com redirect** por:
   - resposta AJAX `200/400`;
   - toast de sucesso/erro sem navegar.
5. **Aplicar filtros dinâmicos** por nome, categoria e status (`ativo`).
6. **Soft delete obrigatório**:
   - remoção vira `ativo = false`;
   - listagens usam `where ativo = true` por padrão.
7. **Bean Validation**:
   - `@NotBlank`, `@Size`, `@PositiveOrZero` em DTOs;
   - exibir erros no modal (sem reload).
8. **GlobalExceptionHandler**:
   - `ResourceNotFoundException` → 404 toast;
   - `MethodArgumentNotValidException` → 400 com erros de campo;
   - `BusinessException` → 422.

---

## Implementação aplicada neste repositório (Flask)

- Introduzido `GenericCrudService` + DTOs (`ProductDTO`, `ClientDTO`) em `crud.py`.
- Criada tela única de inventário (`/gestao-inventario`) com filtros e modais.
- Novo layout por fragmentos (`templates/fragments.html`) e toasts não bloqueantes.
- Soft delete com coluna `active` em `Product` e `Client`.
- Handlers globais de exceção para erros de domínio e falhas inesperadas.
