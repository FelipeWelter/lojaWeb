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
        product = Product(
            name=request.form['name'],
            category=request.form['category'],
            stock=int(request.form['stock']),
            price=Decimal(request.form['price']),
            photo_url=request.form.get('photo_url') or None,
        )
        db.session.add(product)
        db.session.commit()
        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('produtos'))

    products = Product.query.order_by(Product.id.desc()).all()
    return render_template('products.html', products=products)


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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
