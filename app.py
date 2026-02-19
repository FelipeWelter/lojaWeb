from collections import Counter
from datetime import datetime
from decimal import Decimal

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///loja.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-change-me'

db = SQLAlchemy(app)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, default='Peça')
    stock = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    photo_url = db.Column(db.String(255), nullable=True)
    component_class = db.Column(db.String(50), nullable=True)


class ProductComposition(db.Model):
    __tablename__ = 'composicao_produto'

    id = db.Column(db.Integer, primary_key=True)
    id_computador = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    id_peca = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantidade_utilizada = db.Column(db.Integer, nullable=False, default=1)
    id_montagem = db.Column(db.Integer, db.ForeignKey('montagem_computador.id'), nullable=False)

    computador = db.relationship('Product', foreign_keys=[id_computador])
    peca = db.relationship('Product', foreign_keys=[id_peca])


class ComputerAssembly(db.Model):
    __tablename__ = 'montagem_computador'

    id = db.Column(db.Integer, primary_key=True)
    id_computador = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    custo_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    preco_sugerido = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    computador = db.relationship('Product')
    composicao = db.relationship('ProductComposition', backref='montagem', cascade='all, delete-orphan')


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    client = db.relationship('Client')
    product = db.relationship('Product')


class Charge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    mercado_pago_reference = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pendente')
    payment_confirmed_at = db.Column(db.DateTime, nullable=True)

    sale = db.relationship('Sale')


COMPONENT_SLOTS = [
    ('gabinete', 'Gabinete', False),
    ('placa_mae', 'Placa-mãe', False),
    ('processador', 'Processador', False),
    ('memoria_ram', 'Memória RAM', True),
    ('armazenamento', 'Armazenamento', True),
    ('fonte', 'Fonte', False),
]


@app.route('/')
def dashboard():
    product_count = Product.query.count()
    total_stock = db.session.query(db.func.coalesce(db.func.sum(Product.stock), 0)).scalar()
    sales_count = Sale.query.count()
    pending_charges = Charge.query.filter(Charge.status != 'confirmado').count()
    latest_sales = Sale.query.order_by(Sale.created_at.desc()).limit(5).all()

    return render_template(
        'dashboard.html',
        product_count=product_count,
        total_stock=total_stock,
        sales_count=sales_count,
        pending_charges=pending_charges,
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

        product = Product(
            name=request.form['name'],
            category=category,
            stock=int(request.form['stock']),
            price=Decimal(request.form['price']),
            photo_url=request.form.get('photo_url') or None,
            component_class=component_class,
        )
        db.session.add(product)
        db.session.commit()
        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('produtos'))

    products = Product.query.order_by(Product.id.desc()).all()
    return render_template('products.html', products=products)


@app.route('/montar_pc', methods=['GET', 'POST'])
def montar_pc():
    computers = Product.query.filter_by(category='Computador').order_by(Product.name).all()
    parts_by_class = {
        slot_key: Product.query.filter_by(category='Peça', component_class=slot_key).order_by(Product.name).all()
        for slot_key, _, _ in COMPONENT_SLOTS
    }

    if request.method == 'POST':
        computer_id = int(request.form['computer_id'])
        selected_piece_ids = []
        for slot_key, _, allow_multiple in COMPONENT_SLOTS:
            if allow_multiple:
                values = request.form.getlist(f'slot_{slot_key}')
                selected_piece_ids.extend(int(value) for value in values if value)
            else:
                value = request.form.get(f'slot_{slot_key}')
                if value:
                    selected_piece_ids.append(int(value))

        piece_counter = Counter(selected_piece_ids)

        try:
            with db.session.begin_nested():
                computer = Product.query.get_or_404(computer_id)
                if computer.category != 'Computador':
                    raise ValueError('Produto selecionado não é um computador.')

                piece_ids = list(piece_counter.keys())
                pieces = Product.query.filter(Product.id.in_(piece_ids)).all()
                pieces_by_id = {piece.id: piece for piece in pieces}

                for piece_id, qty in piece_counter.items():
                    piece = pieces_by_id.get(piece_id)
                    if not piece or piece.category != 'Peça':
                        raise ValueError('Uma das peças selecionadas é inválida.')
                    if piece.stock < qty:
                        raise ValueError(
                            f'Não foi possível finalizar: {piece.name} insuficiente no estoque'
                        )

                custo_total = Decimal('0.00')
                for piece_id, qty in piece_counter.items():
                    piece = pieces_by_id[piece_id]
                    piece.stock -= qty
                    custo_total += Decimal(qty) * piece.price

                computer.stock += 1
                preco_sugerido = (custo_total * Decimal('1.20')).quantize(Decimal('0.01'))

                montagem = ComputerAssembly(
                    id_computador=computer.id,
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
                f'Montagem concluída! Custo total R$ {custo_total:.2f} | '
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
        computers=computers,
        parts_by_class=parts_by_class,
        component_slots=COMPONENT_SLOTS,
        latest_assemblies=latest_assemblies,
    )


@app.route('/clientes', methods=['GET', 'POST'])
def clientes():
    if request.method == 'POST':
        client = Client(
            name=request.form['name'],
            phone=request.form.get('phone'),
            email=request.form.get('email'),
        )
        db.session.add(client)
        db.session.commit()
        flash('Cliente cadastrado com sucesso!', 'success')
        return redirect(url_for('clientes'))

    clients = Client.query.order_by(Client.id.desc()).all()
    return render_template('clients.html', clients=clients)


@app.route('/vendas', methods=['GET', 'POST'])
def vendas():
    products = Product.query.order_by(Product.name).all()
    clients = Client.query.order_by(Client.name).all()

    if request.method == 'POST':
        client_id = int(request.form['client_id'])
        product_id = int(request.form['product_id'])
        quantity = int(request.form['quantity'])

        product = Product.query.get_or_404(product_id)
        if quantity <= 0 or quantity > product.stock:
            flash('Quantidade inválida para o estoque disponível.', 'danger')
            return redirect(url_for('vendas'))

        total = Decimal(quantity) * product.price
        product.stock -= quantity

        sale = Sale(
            client_id=client_id,
            product_id=product_id,
            quantity=quantity,
            total=total,
        )
        db.session.add(sale)
        db.session.commit()
        flash('Venda registrada com sucesso!', 'success')
        return redirect(url_for('vendas'))

    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    return render_template('sales.html', sales=sales, products=products, clients=clients)


@app.route('/cobrancas', methods=['GET', 'POST'])
def cobrancas():
    if request.method == 'POST':
        sale_id = int(request.form['sale_id'])
        charge = Charge(
            sale_id=sale_id,
            mercado_pago_reference=request.form['mercado_pago_reference'],
            status=request.form['status'],
            payment_confirmed_at=datetime.utcnow() if request.form['status'] == 'confirmado' else None,
        )
        db.session.add(charge)
        db.session.commit()
        flash('Cobrança registrada com sucesso!', 'success')
        return redirect(url_for('cobrancas'))

    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    charges = Charge.query.order_by(Charge.id.desc()).all()
    return render_template('charges.html', charges=charges, sales=sales)


@app.route('/cobrancas/<int:charge_id>/confirmar', methods=['POST'])
def confirmar_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    charge.status = 'confirmado'
    charge.payment_confirmed_at = datetime.utcnow()
    db.session.commit()
    flash('Pagamento confirmado!', 'success')
    return redirect(url_for('cobrancas'))


with app.app_context():
    db.create_all()

    # Migração simples para bancos SQLite já existentes.
    columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(product)'))]
    if 'component_class' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN component_class VARCHAR(50)'))
        db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
