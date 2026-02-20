from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///loja.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-change-me'
app.config['UPLOAD_FOLDER'] = 'static/uploads/products'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

db = SQLAlchemy(app)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, default='Peça')
    stock = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    photo_url = db.Column(db.String(255), nullable=True)
    component_class = db.Column(db.String(50), nullable=True)


class ProductComposition(db.Model):
    __tablename__ = 'composicao_produto'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    id_computador = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    id_peca = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantidade_utilizada = db.Column(db.Integer, nullable=False, default=1)
    id_montagem = db.Column(db.Integer, db.ForeignKey('montagem_computador.id'), nullable=False)

    computador = db.relationship('Product', foreign_keys=[id_computador])
    peca = db.relationship('Product', foreign_keys=[id_peca])


class ComputerAssembly(db.Model):
    __tablename__ = 'montagem_computador'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    id_computador = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    nome_referencia = db.Column(db.String(120), nullable=True)
    preco_original = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    custo_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    preco_sugerido = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    computador = db.relationship('Product')
    composicao = db.relationship('ProductComposition', backref='montagem', cascade='all, delete-orphan')


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), nullable=True, unique=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_name = db.Column(db.String(120), nullable=False, default='Venda sem nome')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    canceled = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    client = db.relationship('Client')
    product = db.relationship('Product')


class Charge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    mercado_pago_reference = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pendente')
    payment_method = db.Column(db.String(30), nullable=False, default='pix')
    payment_confirmed_at = db.Column(db.DateTime, nullable=True)

    sale = db.relationship('Sale')




def _save_product_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None

    original_name = secure_filename(file_storage.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise ValueError('Formato de imagem inválido. Use JPG, PNG ou WEBP.')

    upload_dir = Path(app.root_path) / app.config['UPLOAD_FOLDER']
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid4().hex
    original_relative = f"uploads/products/{file_id}{extension}"
    original_path = Path(app.root_path) / 'static' / original_relative

    file_storage.save(original_path)

    return f"/static/{original_relative}", None


def _remove_product_photo_files(photo_url: str | None):
    if not photo_url or not photo_url.startswith('/static/uploads/products/'):
        return

    relative = photo_url.removeprefix('/static/')
    original_path = Path(app.root_path) / 'static' / relative
    if original_path.exists():
        original_path.unlink()


COMPONENT_SLOTS = [
    ('gabinete', 'Gabinete', False),
    ('placa_mae', 'Placa-mãe', False),
    ('processador', 'Processador', False),
    ('memoria_ram', 'Memória RAM', True),
    ('armazenamento', 'Armazenamento', True),
    ('fonte', 'Fonte', False),
]

PAYMENT_METHODS = [
    ('credito', 'Crédito'),
    ('pix', 'Pix'),
    ('boleto', 'Boleto'),
    ('parcelado', 'Parcelado'),
]

PAYMENT_METHOD_LABELS = dict(PAYMENT_METHODS)


@app.route('/')
def dashboard():
    product_count = Product.query.count()
    total_stock = db.session.query(db.func.coalesce(db.func.sum(Product.stock), 0)).scalar()
    sales_count = Sale.query.count()
    pending_charges = Charge.query.filter(Charge.status != 'confirmado').count()
    total_sales_amount = db.session.query(db.func.coalesce(db.func.sum(Sale.total), 0)).filter(Sale.canceled.is_(False)).scalar()
    total_profit = db.session.query(
        db.func.coalesce(db.func.sum(Sale.total - (Product.cost_price * Sale.quantity)), 0)
    ).join(Product, Product.id == Sale.product_id).filter(Sale.canceled.is_(False)).scalar()
    payment_method_summary = (
        db.session.query(
            Charge.payment_method,
            db.func.count(Charge.id),
            db.func.coalesce(db.func.sum(Sale.total), 0),
        )
        .join(Sale, Sale.id == Charge.sale_id)
        .filter(Sale.canceled.is_(False))
        .group_by(Charge.payment_method)
        .all()
    )
    latest_sales = Sale.query.order_by(Sale.created_at.desc()).limit(5).all()

    return render_template(
        'dashboard.html',
        product_count=product_count,
        total_stock=total_stock,
        sales_count=sales_count,
        pending_charges=pending_charges,
        total_sales_amount=total_sales_amount,
        total_profit=total_profit,
        payment_method_summary=payment_method_summary,
        payment_method_labels=PAYMENT_METHOD_LABELS,
        latest_sales=latest_sales,
    )


@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    if request.method == 'POST':
        category = request.form['category']
        component_class = request.form.get('component_class') or None
        if category != 'Peça':
            component_class = None
        elif not component_class:
            flash('Informe a classe da peça para cadastro no estoque.', 'danger')
            return redirect(url_for('produtos'))

        photo_url = None
        photo_file = request.files.get('photo_file')
        if photo_file and photo_file.filename:
            try:
                photo_url, _ = _save_product_photo(photo_file)
            except ValueError as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('produtos'))

        product = Product(
            name=request.form['name'],
            category=category,
            stock=int(request.form['stock']),
            price=Decimal(request.form['price']),
            cost_price=Decimal(request.form.get('cost_price') or '0'),
            photo_url=photo_url,
            component_class=component_class,
        )
        db.session.add(product)
        db.session.commit()
        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('produtos'))

    products = Product.query.order_by(Product.category, Product.component_class, Product.name).all()
    return render_template('products.html', products=products)


@app.route('/produtos/<int:product_id>/atualizar_foto', methods=['POST'])
def atualizar_foto_produto(product_id: int):
    product = Product.query.get_or_404(product_id)
    photo_file = request.files.get('photo_file')

    if not photo_file or not photo_file.filename:
        flash('Selecione uma imagem para atualizar a foto do produto.', 'danger')
        return redirect(url_for('produtos'))

    old_photo_url = product.photo_url
    try:
        photo_url, _ = _save_product_photo(photo_file)
        product.photo_url = photo_url
        db.session.commit()
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('produtos'))

    _remove_product_photo_files(old_photo_url)
    flash('Foto do produto atualizada com sucesso!', 'success')
    return redirect(url_for('produtos'))


@app.route('/produtos/<int:product_id>/editar', methods=['POST'])
def editar_produto(product_id: int):
    product = Product.query.get_or_404(product_id)

    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Informe o nome do produto.', 'danger')
        return redirect(url_for('produtos'))

    category = request.form.get('category') or product.category
    component_class = request.form.get('component_class') or None

    if category != 'Peça':
        component_class = None
    elif not component_class:
        flash('Informe a classe da peça para produtos da categoria Peça.', 'danger')
        return redirect(url_for('produtos'))

    product.name = name
    product.category = category
    product.stock = int(request.form.get('stock') or 0)
    product.price = Decimal(request.form.get('price') or '0')
    product.cost_price = Decimal(request.form.get('cost_price') or '0')
    product.component_class = component_class

    db.session.commit()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(url_for('produtos'))


@app.route('/produtos/<int:product_id>/remover', methods=['POST'])
def remover_produto(product_id: int):
    product = Product.query.get_or_404(product_id)

    linked_sale = Sale.query.filter_by(product_id=product.id).first()
    linked_composition = ProductComposition.query.filter(
        (ProductComposition.id_peca == product.id) | (ProductComposition.id_computador == product.id)
    ).first()

    if linked_sale or linked_composition:
        flash('Não é possível remover produto com histórico de vendas ou montagem.', 'danger')
        return redirect(url_for('produtos'))

    old_photo_url = product.photo_url
    db.session.delete(product)
    db.session.commit()
    _remove_product_photo_files(old_photo_url)
    flash('Produto removido com sucesso!', 'success')
    return redirect(url_for('produtos'))


@app.route('/montar_pc', methods=['GET', 'POST'])
def montar_pc():
    parts_by_class = {
        slot_key: Product.query.filter_by(category='Peça', component_class=slot_key).order_by(Product.name).all()
        for slot_key, _, _ in COMPONENT_SLOTS
    }

    if request.method == 'POST':
        computer_name = (request.form.get('computer_name') or '').strip()
        if not computer_name:
            flash('Informe o nome do computador montado.', 'danger')
            return redirect(url_for('montar_pc'))

        original_price_new = Decimal(request.form.get('computer_original_price') or '0')

        selected_piece_ids = []
        for slot_key, _, allow_multiple in COMPONENT_SLOTS:
            if allow_multiple:
                ids = request.form.getlist(f'{slot_key}_ids[]')
                qtys = request.form.getlist(f'{slot_key}_qtys[]')
                for piece_id, qty in zip(ids, qtys):
                    if piece_id and qty:
                        selected_piece_ids.extend([int(piece_id)] * int(qty))
            else:
                value = request.form.get(f'slot_{slot_key}')
                if value:
                    selected_piece_ids.append(int(value))

        piece_counter = Counter(selected_piece_ids)

        try:
            with db.session.begin_nested():
                computer = Product.query.filter(
                    db.func.lower(Product.name) == computer_name.lower(),
                    Product.category == 'Computador',
                ).first()

                piece_ids = list(piece_counter.keys())
                pieces = Product.query.filter(Product.id.in_(piece_ids)).all() if piece_ids else []
                pieces_by_id = {piece.id: piece for piece in pieces}

                for piece_id, qty in piece_counter.items():
                    piece = pieces_by_id.get(piece_id)
                    if not piece or piece.category != 'Peça':
                        raise ValueError('Uma das peças selecionadas é inválida.')
                    if piece.stock < qty:
                        raise ValueError(f'Não foi possível finalizar: {piece.name} insuficiente no estoque')

                custo_total = Decimal('0.00')
                for piece_id, qty in piece_counter.items():
                    piece = pieces_by_id[piece_id]
                    piece.stock -= qty
                    custo_total += Decimal(qty) * (piece.cost_price or piece.price)

                preco_sugerido = (custo_total * Decimal('1.20')).quantize(Decimal('0.01'))

                if not computer:
                    computer = Product(
                        name=computer_name,
                        category='Computador',
                        stock=0,
                        price=0,
                    )
                    db.session.add(computer)
                    db.session.flush()

                computer.stock += 1
                preco_base_informado = original_price_new
                if computer.id and preco_base_informado == 0 and Decimal(computer.price) > 0:
                    preco_base_informado = Decimal(computer.price)

                preco_original = preco_base_informado
                preco_final = (preco_original + custo_total).quantize(Decimal('0.01'))
                computer.price = preco_final

                montagem = ComputerAssembly(
                    id_computador=computer.id,
                    nome_referencia=computer_name,
                    preco_original=preco_original,
                    custo_total=custo_total,
                    preco_sugerido=preco_sugerido,
                )
                db.session.add(montagem)
                db.session.flush()

                for piece_id, qty in piece_counter.items():
                    db.session.add(
                        ProductComposition(
                            id_computador=computer.id,
                            id_peca=piece_id,
                            quantidade_utilizada=qty,
                            id_montagem=montagem.id,
                        )
                    )

            db.session.commit()
            flash(
                f'Montagem concluída! Preço base R$ {preco_original:.2f} + '
                f'peças R$ {custo_total:.2f} = preço final R$ {preco_final:.2f} | '
                f'Preço sugerido R$ {preco_sugerido:.2f}.',
                'success',
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')

        return redirect(url_for('montar_pc'))

    latest_assemblies = ComputerAssembly.query.order_by(ComputerAssembly.created_at.desc()).limit(20).all()

    return render_template(
        'assemble_pc.html',
        parts_by_class=parts_by_class,
        component_slots=COMPONENT_SLOTS,
        latest_assemblies=latest_assemblies,
    )


@app.route('/clientes', methods=['GET', 'POST'])
def clientes():
    if request.method == 'POST':
        cpf = (request.form.get('cpf') or '').strip()
        if not cpf:
            flash('Informe o CPF do cliente.', 'danger')
            return redirect(url_for('clientes'))

        existing_client = Client.query.filter_by(cpf=cpf).first()
        if existing_client:
            flash('Este CPF já está cadastrado para outro cliente.', 'danger')
            return redirect(url_for('clientes'))

        client = Client(
            name=request.form['name'],
            cpf=cpf,
            phone=request.form.get('phone'),
            email=request.form.get('email'),
        )
        db.session.add(client)
        db.session.commit()
        flash('Cliente cadastrado com sucesso!', 'success')
        return redirect(url_for('clientes'))

    clients = Client.query.order_by(Client.id.desc()).all()
    return render_template('clients.html', clients=clients)


@app.route('/clientes/<int:client_id>/editar', methods=['GET', 'POST'])
def editar_cliente(client_id: int):
    client = Client.query.get_or_404(client_id)

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        cpf = (request.form.get('cpf') or '').strip()
        if not name:
            flash('Informe o nome do cliente.', 'danger')
            return redirect(url_for('editar_cliente', client_id=client.id))
        if not cpf:
            flash('Informe o CPF do cliente.', 'danger')
            return redirect(url_for('editar_cliente', client_id=client.id))

        duplicate = Client.query.filter(Client.cpf == cpf, Client.id != client.id).first()
        if duplicate:
            flash('Este CPF já está cadastrado para outro cliente.', 'danger')
            return redirect(url_for('editar_cliente', client_id=client.id))

        client.name = name
        client.cpf = cpf
        client.phone = request.form.get('phone')
        client.email = request.form.get('email')
        db.session.commit()
        flash('Cliente atualizado com sucesso!', 'success')
        return redirect(url_for('clientes'))

    return render_template('edit_client.html', client=client)


@app.route('/clientes/<int:client_id>/remover', methods=['POST'])
def remover_cliente(client_id: int):
    client = Client.query.get_or_404(client_id)
    active_sales = Sale.query.filter_by(client_id=client.id, canceled=False).first()
    if active_sales:
        flash('Não é possível remover cliente com vendas ativas.', 'danger')
        return redirect(url_for('clientes'))

    db.session.delete(client)
    db.session.commit()
    flash('Cliente removido com sucesso!', 'success')
    return redirect(url_for('clientes'))


@app.route('/vendas', methods=['GET', 'POST'])
def vendas():
    products = Product.query.order_by(Product.name).all()
    clients = Client.query.order_by(Client.name).all()

    if request.method == 'POST':
        sale_name = (request.form.get('sale_name') or '').strip()
        client_id = int(request.form['client_id'])
        product_id = int(request.form['product_id'])
        quantity = int(request.form['quantity'])

        product = Product.query.get_or_404(product_id)
        if not sale_name:
            flash('Informe um nome para identificar a venda.', 'danger')
            return redirect(url_for('vendas'))
        if quantity <= 0 or quantity > product.stock:
            flash('Quantidade inválida para o estoque disponível.', 'danger')
            return redirect(url_for('vendas'))

        subtotal = (Decimal(quantity) * Decimal(product.price)).quantize(Decimal('0.01'))
        custom_total_raw = request.form.get('custom_total')
        if custom_total_raw:
            total = Decimal(custom_total_raw)
            if total < 0 or total > subtotal:
                flash('Valor final inválido. Use um desconto entre R$ 0,00 e o subtotal.', 'danger')
                return redirect(url_for('vendas'))
        else:
            total = subtotal

        product.stock -= quantity

        sale = Sale(
            sale_name=sale_name,
            client_id=client_id,
            product_id=product_id,
            quantity=quantity,
            subtotal=subtotal,
            total=total,
        )
        db.session.add(sale)
        db.session.commit()
        flash('Venda registrada com sucesso!', 'success')
        return redirect(url_for('vendas'))

    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    return render_template('sales.html', sales=sales, products=products, clients=clients)


@app.route('/vendas/<int:sale_id>/cancelar', methods=['POST'])
def cancelar_venda(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)
    if sale.canceled:
        flash('Esta venda já está cancelada.', 'danger')
        return redirect(url_for('vendas'))

    with db.session.begin_nested():
        sale.product.stock += sale.quantity
        sale.canceled = True
        sale.canceled_at = datetime.utcnow()

    db.session.commit()
    flash('Venda cancelada e itens retornados ao estoque.', 'success')
    return redirect(url_for('vendas'))


@app.route('/vendas/<int:sale_id>/excluir', methods=['POST'])
def excluir_venda(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)
    if not sale.canceled:
        flash('Só é possível excluir vendas canceladas.', 'danger')
        return redirect(request.referrer or url_for('vendas'))

    Charge.query.filter_by(sale_id=sale.id).delete()
    db.session.delete(sale)
    db.session.commit()
    flash('Venda excluída do histórico com sucesso!', 'success')
    return redirect(request.referrer or url_for('vendas'))


@app.route('/cobrancas', methods=['GET', 'POST'])
def cobrancas():
    if request.method == 'POST':
        sale_id = int(request.form['sale_id'])
        charge = Charge(
            sale_id=sale_id,
            mercado_pago_reference=request.form['mercado_pago_reference'],
            status=request.form['status'],
            payment_method=request.form['payment_method'],
            payment_confirmed_at=datetime.utcnow() if request.form['status'] == 'confirmado' else None,
        )
        db.session.add(charge)
        db.session.commit()
        flash('Cobrança registrada com sucesso!', 'success')
        return redirect(url_for('cobrancas'))

    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    charges = Charge.query.order_by(Charge.id.desc()).all()
    return render_template('charges.html', charges=charges, sales=sales, payment_methods=PAYMENT_METHODS)


@app.route('/cobrancas/<int:charge_id>/editar', methods=['POST'])
def editar_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    charge.payment_method = request.form['payment_method']
    charge.status = request.form['status']
    charge.mercado_pago_reference = (request.form.get('mercado_pago_reference') or '').strip()

    if not charge.mercado_pago_reference:
        flash('Informe a referência da cobrança.', 'danger')
        return redirect(url_for('cobrancas'))

    charge.payment_confirmed_at = datetime.utcnow() if charge.status == 'confirmado' else None
    db.session.commit()
    flash('Cobrança atualizada com sucesso!', 'success')
    return redirect(url_for('cobrancas'))


@app.route('/cobrancas/<int:charge_id>/confirmar', methods=['POST'])
def confirmar_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    charge.status = 'confirmado'
    charge.payment_confirmed_at = datetime.utcnow()
    db.session.commit()
    flash('Pagamento confirmado!', 'success')
    return redirect(url_for('cobrancas'))


@app.route('/cobrancas/<int:charge_id>/cancelar', methods=['POST'])
def cancelar_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    if charge.status == 'cancelado':
        flash('Esta cobrança já está cancelada.', 'danger')
        return redirect(url_for('cobrancas'))

    charge.status = 'cancelado'
    charge.payment_confirmed_at = None
    db.session.commit()
    flash('Cobrança cancelada com sucesso!', 'success')
    return redirect(url_for('cobrancas'))


with app.app_context():
    db.create_all()

    columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(product)'))]
    if 'component_class' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN component_class VARCHAR(50)'))
    if 'cost_price' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN cost_price NUMERIC(10,2) NOT NULL DEFAULT 0'))
    db.session.commit()

    montagem_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(montagem_computador)'))]
    if 'nome_referencia' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN nome_referencia VARCHAR(120)'))
    if 'preco_original' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN preco_original NUMERIC(10,2) NOT NULL DEFAULT 0'))
    db.session.execute(
        db.text(
            "UPDATE montagem_computador SET nome_referencia = (SELECT product.name FROM product "
            "WHERE product.id = montagem_computador.id_computador) WHERE nome_referencia IS NULL"
        )
    )
    db.session.execute(db.text('UPDATE montagem_computador SET preco_original = preco_sugerido WHERE preco_original IS NULL'))
    db.session.commit()

    sale_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(sale)'))]
    if 'sale_name' not in sale_columns:
        db.session.execute(db.text("ALTER TABLE sale ADD COLUMN sale_name VARCHAR(120) NOT NULL DEFAULT 'Venda sem nome'"))
    if 'subtotal' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN subtotal NUMERIC(10,2) NOT NULL DEFAULT 0'))
        db.session.execute(db.text('UPDATE sale SET subtotal = total WHERE subtotal = 0'))
    if 'canceled' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN canceled BOOLEAN NOT NULL DEFAULT 0'))
    if 'canceled_at' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN canceled_at DATETIME'))
    db.session.commit()

    client_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(client)'))]
    if 'cpf' not in client_columns:
        db.session.execute(db.text('ALTER TABLE client ADD COLUMN cpf VARCHAR(14)'))
    db.session.execute(db.text('CREATE UNIQUE INDEX IF NOT EXISTS ux_client_cpf ON client (cpf)'))
    db.session.commit()

    charge_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(charge)'))]
    if 'payment_method' not in charge_columns:
        db.session.execute(db.text("ALTER TABLE charge ADD COLUMN payment_method VARCHAR(30) NOT NULL DEFAULT 'pix'"))
    db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
