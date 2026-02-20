from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from io import BytesIO
import os
from pathlib import Path
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///loja.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-change-me'
app.config['UPLOAD_FOLDER'] = 'static/uploads/products'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT', 'lojaweb-reset-salt')

db = SQLAlchemy(app)
mail = Mail(app)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, default='Peça')
    stock = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    photo_url = db.Column(db.String(255), nullable=True)
    component_class = db.Column(db.String(50), nullable=True)
    serial_number = db.Column(db.String(120), nullable=True)
    images = db.relationship('ProductImage', backref='product', cascade='all, delete-orphan', order_by='ProductImage.position')


class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)


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


class AssemblyCustomPart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assembly_id = db.Column(db.Integer, db.ForeignKey('montagem_computador.id'), nullable=False)
    slot_key = db.Column(db.String(50), nullable=False)
    part_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)


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
    canceled = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)
    technical_notes = db.Column(db.Text, nullable=True)
    bios_updated = db.Column(db.Boolean, nullable=False, default=False)
    stress_test_done = db.Column(db.Boolean, nullable=False, default=False)
    os_installed = db.Column(db.Boolean, nullable=False, default=False)

    computador = db.relationship('Product')
    composicao = db.relationship('ProductComposition', backref='montagem', cascade='all, delete-orphan')
    custom_parts = db.relationship('AssemblyCustomPart', backref='assembly', cascade='all, delete-orphan')


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


class ServiceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(120), nullable=False)
    client_name = db.Column(db.String(120), nullable=False)
    equipment = db.Column(db.String(120), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class FixedCost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MaintenanceTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(120), nullable=False)
    equipment = db.Column(db.String(120), nullable=False)
    service_description = db.Column(db.String(180), nullable=False)
    entry_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    exit_date = db.Column(db.DateTime, nullable=True)
    waiting_parts = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(30), nullable=False, default='em_andamento')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(180), nullable=False)
    details = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def _login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            flash('Faça login para continuar.', 'danger')
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def _current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)


def _build_reset_token(email: str):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])


def _read_reset_token(token: str, max_age_seconds: int = 3600):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=max_age_seconds)


def _log_audit(action: str, details: str):
    user = _current_user()
    db.session.add(AuditLog(user_name=user.name if user else 'Sistema', action=action, details=details))


def _html_to_pdf(html: str):
    output = BytesIO()
    status = pisa.CreatePDF(src=html, dest=output)
    if status.err:
        raise ValueError('Erro ao gerar PDF.')
    output.seek(0)
    return output


def _receipt_style():
    return """
    <style>
      body { font-family: Helvetica, Arial, sans-serif; color: #1f2937; font-size: 11px; }
      .header { border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 14px; }
      .brand { font-size: 20px; color: #1d4ed8; font-weight: bold; }
      .meta { color: #374151; }
      .box { border: 1px solid #d1d5db; padding: 10px; margin: 8px 0; }
      .title { font-size: 14px; font-weight: bold; margin-bottom: 8px; }
      table { width: 100%; border-collapse: collapse; }
      th, td { border: 1px solid #d1d5db; padding: 6px; text-align: left; }
      th { background: #eff6ff; }
      .total { margin-top: 12px; font-size: 13px; font-weight: bold; text-align: right; }
      .footer { margin-top: 20px; color: #6b7280; font-size: 10px; }
    </style>
    """


def _render_sale_receipt_html(sale: Sale):
    return f"""
    <html><head>{_receipt_style()}</head><body>
      <div class='header'>
        <div class='brand'>LojaWeb - Recibo de Venda</div>
        <div class='meta'>Emissão: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}</div>
      </div>
      <div class='box'><div class='title'>Dados do cliente</div>
        Nome: {sale.client.name}<br/>CPF: {sale.client.cpf or '-'}<br/>Telefone: {sale.client.phone or '-'}
      </div>
      <table><tr><th>Venda</th><th>Produto</th><th>Qtd</th><th>Subtotal</th><th>Total</th></tr>
      <tr><td>{sale.sale_name}</td><td>{sale.product.name}</td><td>{sale.quantity}</td><td>R$ {Decimal(sale.subtotal):.2f}</td><td>R$ {Decimal(sale.total):.2f}</td></tr></table>
      <div class='total'>Total do recibo: R$ {Decimal(sale.total):.2f}</div>
      <div class='footer'>Documento gerado automaticamente pelo sistema LojaWeb.</div>
    </body></html>
    """


def _render_assembly_receipt_html(assembly: ComputerAssembly):
    items = []
    for item in assembly.composicao:
        if item.peca:
            items.append(f"<tr><td>{item.peca.name}</td><td>{item.quantidade_utilizada}</td><td>Estoque</td></tr>")
    for custom in assembly.custom_parts:
        items.append(f"<tr><td>{custom.part_name}</td><td>{custom.quantity}</td><td>Personalizado</td></tr>")
    rows = ''.join(items) or '<tr><td colspan="3">Sem itens</td></tr>'
    return f"""
    <html><head>{_receipt_style()}</head><body>
      <div class='header'>
        <div class='brand'>LojaWeb - Orçamento de Montagem</div>
        <div class='meta'>Emissão: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}</div>
      </div>
      <div class='box'><div class='title'>Montagem #{assembly.id}</div>
        Referência: {assembly.nome_referencia}<br/>Computador: {assembly.computador.name}
      </div>
      <table><tr><th>Componente</th><th>Qtd</th><th>Origem</th></tr>{rows}</table>
      <div class='total'>Custo: R$ {Decimal(assembly.custo_total):.2f} | Sugerido: R$ {Decimal(assembly.preco_sugerido):.2f}</div>
      <div class='footer'>Documento gerado automaticamente pelo sistema LojaWeb.</div>
    </body></html>
    """


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


def _collect_selected_piece_inputs(form_data, prefix=''):
    selected_piece_ids = []
    custom_items = []

    for slot_key, _, allow_multiple in COMPONENT_SLOTS:
        if allow_multiple:
            ids = form_data.getlist(f'{prefix}{slot_key}_ids[]')
            qtys = form_data.getlist(f'{prefix}{slot_key}_qtys[]')
            custom_names = form_data.getlist(f'{prefix}{slot_key}_custom_names[]')
            custom_costs = form_data.getlist(f'{prefix}{slot_key}_custom_costs[]')

            for piece_id, qty, custom_name, custom_cost in zip(ids, qtys, custom_names, custom_costs):
                qty_value = int(qty) if qty else 0
                if piece_id and qty:
                    selected_piece_ids.extend([int(piece_id)] * qty_value)
                    continue

                custom_name = (custom_name or '').strip()
                if custom_name and qty_value > 0:
                    custom_items.append({
                        'slot_key': slot_key,
                        'name': custom_name,
                        'qty': qty_value,
                        'unit_cost': Decimal(custom_cost or '0'),
                    })
        else:
            value = form_data.get(f'{prefix}slot_{slot_key}')
            if value:
                selected_piece_ids.append(int(value))
                continue

            custom_name = (form_data.get(f'{prefix}custom_{slot_key}_name') or '').strip()
            custom_cost = form_data.get(f'{prefix}custom_{slot_key}_cost') or '0'
            if custom_name:
                custom_items.append({
                    'slot_key': slot_key,
                    'name': custom_name,
                    'qty': 1,
                    'unit_cost': Decimal(custom_cost),
                })

    return selected_piece_ids, custom_items


def _build_computer_with_parts(
    computer_name,
    original_price_new,
    selected_piece_ids,
    custom_items=None,
    photo_files=None,
    create_stock_item=True,
    technical_notes=None,
    bios_updated=False,
    stress_test_done=False,
    os_installed=False,
):
    custom_items = custom_items or []
    photo_files = photo_files or []
    piece_counter = Counter(selected_piece_ids)
    uploaded_photo_urls = []
    previous_photo_urls = []

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

        for custom_item in custom_items:
            if custom_item['unit_cost'] < 0:
                raise ValueError(f"Custo inválido para peça personalizada: {custom_item['name']}")
            custo_total += Decimal(custom_item['qty']) * custom_item['unit_cost']

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

        for photo_file in photo_files:
            if not photo_file or not photo_file.filename:
                continue
            photo_url, _ = _save_product_photo(photo_file)
            uploaded_photo_urls.append(photo_url)

        if uploaded_photo_urls:
            if not computer.photo_url:
                computer.photo_url = uploaded_photo_urls[0]
            existing_positions = [img.position for img in computer.images] or [0]
            next_position = max(existing_positions) + 1
            for url in uploaded_photo_urls:
                db.session.add(ProductImage(product_id=computer.id, image_url=url, position=next_position))
                next_position += 1

        if create_stock_item:
            computer.stock += 1
        preco_base_informado = original_price_new
        if computer.id and preco_base_informado == 0 and Decimal(computer.price) > 0:
            preco_base_informado = Decimal(computer.price)

        preco_original = preco_base_informado
        preco_final = (preco_original + custo_total).quantize(Decimal('0.01'))
        if create_stock_item:
            computer.price = preco_final

        montagem = ComputerAssembly(
            id_computador=computer.id,
            nome_referencia=computer_name,
            preco_original=preco_original,
            custo_total=custo_total,
            preco_sugerido=preco_sugerido,
            technical_notes=(technical_notes or '').strip() or None,
            bios_updated=bios_updated,
            stress_test_done=stress_test_done,
            os_installed=os_installed,
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

        for custom_item in custom_items:
            db.session.add(
                AssemblyCustomPart(
                    assembly_id=montagem.id,
                    slot_key=custom_item['slot_key'],
                    part_name=custom_item['name'],
                    quantity=custom_item['qty'],
                    unit_cost=custom_item['unit_cost'],
                )
            )

    return {
        'preco_original': preco_original,
        'custo_total': custo_total,
        'preco_final': preco_final,
        'preco_sugerido': preco_sugerido,
        'new_photo_urls': uploaded_photo_urls,
        'previous_photo_urls': previous_photo_urls,
    }


COMPONENT_SLOTS = [
    ('gabinete', 'Gabinete', False),
    ('placa_mae', 'Placa-mãe', False),
    ('placa_video', 'Placa de Vídeo', False),
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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash('Credenciais inválidas.', 'danger')
            return redirect(url_for('login'))
        session['user_id'] = user.id
        flash('Login realizado com sucesso!', 'success')
        return redirect(url_for('dashboard'))
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sessão encerrada.', 'success')
    return redirect(url_for('login'))


@app.route('/usuarios', methods=['GET', 'POST'])
@_login_required
def usuarios():
    current = _current_user()
    if not current or not current.is_admin:
        flash('Apenas administradores podem gerenciar usuários.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        is_admin = request.form.get('is_admin') == 'on'
        if not name or not email or len(password) < 6:
            flash('Preencha nome, e-mail e senha com ao menos 6 caracteres.', 'danger')
            return redirect(url_for('usuarios'))
        if User.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'danger')
            return redirect(url_for('usuarios'))

        user = User(name=name, email=email, password_hash=generate_password_hash(password), is_admin=is_admin)
        db.session.add(user)
        _log_audit('Criação de usuário', f'Usuário {current.name} criou o usuário {name} ({email}).')
        db.session.commit()
        flash('Usuário criado com sucesso!', 'success')
        return redirect(url_for('usuarios'))

    return render_template('users.html', users=User.query.order_by(User.created_at.desc()).all())


@app.route('/recuperar-senha', methods=['GET', 'POST'])
def recuperar_senha():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = _build_reset_token(user.email)
            reset_url = url_for('redefinir_senha', token=token, _external=True)
            msg = Message('Recuperação de senha - LojaWeb', recipients=[user.email])
            msg.body = f'Olá, {user.name}! Use o link para redefinir sua senha: {reset_url}'
            try:
                mail.send(msg)
                flash('E-mail de recuperação enviado com sucesso.', 'success')
            except Exception:
                flash('Não foi possível enviar e-mail. Verifique as credenciais do Gmail no servidor.', 'danger')
        else:
            flash('Se o e-mail existir, enviaremos as instruções.', 'success')
        return redirect(url_for('recuperar_senha'))

    return render_template('recover_password.html')


@app.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def redefinir_senha(token: str):
    try:
        email = _read_reset_token(token)
    except (SignatureExpired, BadSignature):
        flash('Link inválido ou expirado.', 'danger')
        return redirect(url_for('recuperar_senha'))

    user = User.query.filter_by(email=email).first_or_404()
    if request.method == 'POST':
        password = request.form.get('password') or ''
        if len(password) < 6:
            flash('A nova senha deve ter ao menos 6 caracteres.', 'danger')
            return redirect(url_for('redefinir_senha', token=token))
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash('Senha redefinida com sucesso. Faça login.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)


@app.route('/')
@_login_required
def dashboard():
    period = request.args.get('period', 'month')
    now = datetime.utcnow()
    start_date = None
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == '7d':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        period = 'month'
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    sales_query = Sale.query.filter(Sale.canceled.is_(False), Sale.created_at >= start_date)
    service_query = ServiceRecord.query.filter(ServiceRecord.created_at >= start_date)
    fixed_cost_query = FixedCost.query.filter(FixedCost.created_at >= start_date)
    maintenance_query = MaintenanceTicket.query.filter(MaintenanceTicket.entry_date >= start_date)

    product_count = Product.query.count()
    total_stock = db.session.query(db.func.coalesce(db.func.sum(Product.stock), 0)).scalar()
    sales_count = sales_query.count()
    services_count = service_query.count()
    pending_charges = Charge.query.filter(Charge.status != 'confirmado').count()
    total_sales_amount = db.session.query(db.func.coalesce(db.func.sum(Sale.total), 0)).filter(
        Sale.canceled.is_(False), Sale.created_at >= start_date
    ).scalar()
    total_services_amount = db.session.query(db.func.coalesce(db.func.sum(ServiceRecord.total_price), 0)).filter(
        ServiceRecord.created_at >= start_date
    ).scalar()
    sales_profit = db.session.query(
        db.func.coalesce(db.func.sum(Sale.total - (Product.cost_price * Sale.quantity)), 0)
    ).join(Product, Product.id == Sale.product_id).filter(Sale.canceled.is_(False), Sale.created_at >= start_date).scalar()
    service_profit = db.session.query(
        db.func.coalesce(db.func.sum(ServiceRecord.total_price - ServiceRecord.cost), 0)
    ).filter(ServiceRecord.created_at >= start_date).scalar()
    total_fixed_costs = db.session.query(db.func.coalesce(db.func.sum(FixedCost.amount), 0)).filter(
        FixedCost.created_at >= start_date
    ).scalar()
    total_profit = sales_profit + service_profit
    net_profit = total_profit - total_fixed_costs
    maintenance_in_progress = maintenance_query.filter(MaintenanceTicket.status != 'concluido').count()
    maintenance_waiting_parts = maintenance_query.filter(MaintenanceTicket.waiting_parts.is_(True), MaintenanceTicket.status != 'concluido').count()

    payment_method_summary = (
        db.session.query(
            Charge.payment_method,
            db.func.count(Charge.id),
            db.func.coalesce(db.func.sum(Sale.total), 0),
        )
        .join(Sale, Sale.id == Charge.sale_id)
        .filter(Sale.canceled.is_(False), Sale.created_at >= start_date)
        .group_by(Charge.payment_method)
        .all()
    )
    latest_sales = sales_query.order_by(Sale.created_at.desc()).limit(5).all()

    monthly_sales = (
        db.session.query(
            db.func.strftime('%Y-%m', Sale.created_at).label('month'),
            db.func.coalesce(db.func.sum(Sale.total), 0),
        )
        .filter(Sale.canceled.is_(False))
        .group_by('month')
        .order_by('month')
        .all()
    )
    chart_months = [row[0] for row in monthly_sales]
    chart_sales_totals = [float(row[1]) for row in monthly_sales]

    top_products = (
        db.session.query(Product.name, db.func.coalesce(db.func.sum(Sale.quantity), 0).label('qty'))
        .join(Sale, Sale.product_id == Product.id)
        .filter(Sale.canceled.is_(False), Sale.created_at >= start_date)
        .group_by(Product.id)
        .order_by(db.desc('qty'))
        .limit(5)
        .all()
    )
    top_products_labels = [row[0] for row in top_products]
    top_products_values = [int(row[1]) for row in top_products]

    return render_template(
        'dashboard.html',
        product_count=product_count,
        total_stock=total_stock,
        sales_count=sales_count,
        services_count=services_count,
        pending_charges=pending_charges,
        total_sales_amount=total_sales_amount,
        total_services_amount=total_services_amount,
        total_profit=total_profit,
        total_fixed_costs=total_fixed_costs,
        net_profit=net_profit,
        maintenance_in_progress=maintenance_in_progress,
        maintenance_waiting_parts=maintenance_waiting_parts,
        payment_method_summary=payment_method_summary,
        payment_method_labels=PAYMENT_METHOD_LABELS,
        latest_sales=latest_sales,
        period=period,
        chart_months=chart_months,
        chart_sales_totals=chart_sales_totals,
        top_products_labels=top_products_labels,
        top_products_values=top_products_values,
    )


@app.route('/produtos', methods=['GET', 'POST'])
@_login_required
def produtos():
    if request.method == 'POST':
        form_mode = request.form.get('form_mode')
        if form_mode == 'assembled_computer':
            computer_name = (request.form.get('computer_name') or '').strip()
            if not computer_name:
                flash('Informe o nome do computador montado.', 'danger')
                return redirect(url_for('produtos'))

            original_price_new = Decimal(request.form.get('computer_original_price') or '0')
            selected_piece_ids, custom_items = _collect_selected_piece_inputs(request.form)
            photo_files = request.files.getlist('photo_files')
            create_stock_item = request.form.get('create_stock_item') == 'on'
            technical_notes = request.form.get('technical_notes')
            bios_updated = request.form.get('bios_updated') == 'on'
            stress_test_done = request.form.get('stress_test_done') == 'on'
            os_installed = request.form.get('os_installed') == 'on'

            try:
                result = _build_computer_with_parts(
                    computer_name=computer_name,
                    original_price_new=original_price_new,
                    selected_piece_ids=selected_piece_ids,
                    custom_items=custom_items,
                    photo_files=photo_files,
                    create_stock_item=create_stock_item,
                    technical_notes=technical_notes,
                    bios_updated=bios_updated,
                    stress_test_done=stress_test_done,
                    os_installed=os_installed,
                )
                db.session.commit()
                flash(
                    f'Computador montado cadastrado! Preço base R$ {result["preco_original"]:.2f} + '
                    f'peças R$ {result["custo_total"]:.2f} = preço final R$ {result["preco_final"]:.2f} | '
                    f'Preço sugerido R$ {result["preco_sugerido"]:.2f}.',
                    'success',
                )
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), 'danger')

            return redirect(url_for('produtos'))

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
            serial_number=(request.form.get('serial_number') or '').strip() or None,
        )
        db.session.add(product)
        db.session.commit()
        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('produtos'))

    products = Product.query.order_by(Product.category, Product.component_class, Product.name).all()
    parts_by_class = {
        slot_key: Product.query.filter_by(category='Peça', component_class=slot_key).order_by(Product.name).all()
        for slot_key, _, _ in COMPONENT_SLOTS
    }
    return render_template(
        'products.html',
        products=products,
        parts_by_class=parts_by_class,
        component_slots=COMPONENT_SLOTS,
    )


@app.route('/produtos/<int:product_id>/atualizar_foto', methods=['POST'])
@_login_required
def atualizar_foto_produto(product_id: int):
    product = Product.query.get_or_404(product_id)
    photo_files = request.files.getlist('photo_files')

    valid_files = [file for file in photo_files if file and file.filename]
    if not valid_files:
        flash('Selecione ao menos uma imagem para atualizar a galeria do produto.', 'danger')
        return redirect(url_for('produtos'))

    try:
        existing_positions = [img.position for img in product.images] or [0]
        next_position = max(existing_positions) + 1
        first_new_url = None

        for photo_file in valid_files:
            photo_url, _ = _save_product_photo(photo_file)
            if not first_new_url:
                first_new_url = photo_url
            db.session.add(ProductImage(product_id=product.id, image_url=photo_url, position=next_position))
            next_position += 1

        if not product.photo_url and first_new_url:
            product.photo_url = first_new_url

        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('produtos'))

    flash('Galeria de fotos atualizada com sucesso!', 'success')
    return redirect(url_for('produtos'))


@app.route('/produtos/<int:product_id>/editar', methods=['POST'])
@_login_required
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

    old_price = Decimal(product.price)
    new_price = Decimal(request.form.get('price') or '0')

    product.name = name
    product.category = category
    product.stock = int(request.form.get('stock') or 0)
    product.price = new_price
    product.cost_price = Decimal(request.form.get('cost_price') or '0')
    product.component_class = component_class
    product.serial_number = (request.form.get('serial_number') or '').strip() or None

    if old_price != new_price:
        _log_audit(
            'Alteração de preço',
            f'Usuário {_current_user().name} alterou o preço do item {product.name} de R$ {old_price:.2f} para R$ {new_price:.2f} em {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}.',
        )

    db.session.commit()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(url_for('produtos'))


@app.route('/produtos/<int:product_id>/remover', methods=['POST'])
@_login_required
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




def _build_assembly_edit_data(latest_assemblies):
    slot_multiple = {slot_key: allow_multiple for slot_key, _, allow_multiple in COMPONENT_SLOTS}
    slot_defaults = {slot_key: {'name': '', 'cost': '0'} for slot_key, _, allow_multiple in COMPONENT_SLOTS if not allow_multiple}

    data = {}
    for assembly in latest_assemblies:
        single_selected = {}
        single_custom = {k: {'name': v['name'], 'cost': v['cost']} for k, v in slot_defaults.items()}
        multi_rows = {slot_key: [] for slot_key, _, allow_multiple in COMPONENT_SLOTS if allow_multiple}

        for item in assembly.composicao:
            if not item.peca:
                continue
            slot_key = item.peca.component_class
            if not slot_key:
                continue
            if slot_multiple.get(slot_key):
                multi_rows.setdefault(slot_key, []).append({
                    'piece_id': item.id_peca,
                    'qty': item.quantidade_utilizada,
                    'custom_name': '',
                    'custom_cost': '0',
                })
            else:
                single_selected[slot_key] = item.id_peca

        for custom in assembly.custom_parts:
            if slot_multiple.get(custom.slot_key):
                multi_rows.setdefault(custom.slot_key, []).append({
                    'piece_id': '',
                    'qty': custom.quantity,
                    'custom_name': custom.part_name,
                    'custom_cost': f'{Decimal(custom.unit_cost):.2f}',
                })
            else:
                single_custom[custom.slot_key] = {
                    'name': custom.part_name,
                    'cost': f'{Decimal(custom.unit_cost):.2f}',
                }

        for slot_key in list(multi_rows.keys()):
            if not multi_rows[slot_key]:
                multi_rows[slot_key].append({'piece_id': '', 'qty': 1, 'custom_name': '', 'custom_cost': '0'})

        data[assembly.id] = {
            'single_selected': single_selected,
            'single_custom': single_custom,
            'multi_rows': multi_rows,
        }

    return data

@app.route('/montar_pc', methods=['GET', 'POST'])
@_login_required
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

        selected_piece_ids, custom_items = _collect_selected_piece_inputs(request.form)
        photo_files = request.files.getlist('photo_files')
        create_stock_item = request.form.get('create_stock_item') == 'on'
        technical_notes = request.form.get('technical_notes')
        bios_updated = request.form.get('bios_updated') == 'on'
        stress_test_done = request.form.get('stress_test_done') == 'on'
        os_installed = request.form.get('os_installed') == 'on'

        try:
            result = _build_computer_with_parts(
                computer_name=computer_name,
                original_price_new=original_price_new,
                selected_piece_ids=selected_piece_ids,
                custom_items=custom_items,
                photo_files=photo_files,
                create_stock_item=create_stock_item,
                technical_notes=technical_notes,
                bios_updated=bios_updated,
                stress_test_done=stress_test_done,
                os_installed=os_installed,
            )
            db.session.commit()
            flash(
                f'Montagem concluída! Preço base R$ {result["preco_original"]:.2f} + '
                f'peças R$ {result["custo_total"]:.2f} = preço final R$ {result["preco_final"]:.2f} | '
                f'Preço sugerido R$ {result["preco_sugerido"]:.2f}.',
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
        assembly_edit_data=_build_assembly_edit_data(latest_assemblies),
    )


@app.route('/montagens/<int:assembly_id>/editar', methods=['POST'])
@_login_required
def editar_montagem(assembly_id: int):
    assembly = ComputerAssembly.query.get_or_404(assembly_id)

    if assembly.canceled:
        flash('Não é possível editar uma montagem cancelada.', 'danger')
        return redirect(url_for('montar_pc'))

    nome_referencia = (request.form.get('nome_referencia') or '').strip()
    if not nome_referencia:
        flash('Informe um nome de referência para a montagem.', 'danger')
        return redirect(url_for('montar_pc'))

    try:
        preco_original = Decimal(request.form.get('preco_original') or '0')
    except Exception:
        flash('Preço original inválido.', 'danger')
        return redirect(url_for('montar_pc'))

    if preco_original < 0:
        flash('Preço original não pode ser negativo.', 'danger')
        return redirect(url_for('montar_pc'))

    selected_piece_ids, custom_items = _collect_selected_piece_inputs(request.form, prefix='edit_')
    piece_counter_new = Counter(selected_piece_ids)

    try:
        existing_counter = Counter()
        for item in assembly.composicao:
            if item.id_peca:
                existing_counter[item.id_peca] += item.quantidade_utilizada

        all_piece_ids = set(existing_counter.keys()) | set(piece_counter_new.keys())
        pieces = Product.query.filter(Product.id.in_(all_piece_ids)).all() if all_piece_ids else []
        pieces_by_id = {piece.id: piece for piece in pieces}

        for piece_id, qty in existing_counter.items():
            piece = pieces_by_id.get(piece_id)
            if piece:
                piece.stock += qty

        for piece_id, qty in piece_counter_new.items():
            piece = pieces_by_id.get(piece_id)
            if not piece or piece.category != 'Peça':
                raise ValueError('Uma das peças selecionadas é inválida.')
            if piece.stock < qty:
                raise ValueError(f'Não foi possível salvar edição: {piece.name} insuficiente no estoque')

        custo_total = Decimal('0.00')
        for piece_id, qty in piece_counter_new.items():
            piece = pieces_by_id[piece_id]
            piece.stock -= qty
            custo_total += Decimal(qty) * (piece.cost_price or piece.price)

        for custom_item in custom_items:
            if custom_item['unit_cost'] < 0:
                raise ValueError(f"Custo inválido para peça personalizada: {custom_item['name']}")
            custo_total += Decimal(custom_item['qty']) * custom_item['unit_cost']

        assembly.nome_referencia = nome_referencia
        assembly.preco_original = preco_original
        assembly.custo_total = custo_total.quantize(Decimal('0.01'))
        assembly.preco_sugerido = (Decimal(assembly.custo_total) * Decimal('1.20')).quantize(Decimal('0.01'))
        assembly.technical_notes = (request.form.get('technical_notes') or '').strip() or None
        assembly.bios_updated = request.form.get('bios_updated') == 'on'
        assembly.stress_test_done = request.form.get('stress_test_done') == 'on'
        assembly.os_installed = request.form.get('os_installed') == 'on'

        computer = assembly.computador
        if computer and computer.stock > 0:
            computer.price = (preco_original + assembly.custo_total).quantize(Decimal('0.01'))

        ProductComposition.query.filter_by(id_montagem=assembly.id).delete()
        AssemblyCustomPart.query.filter_by(assembly_id=assembly.id).delete()

        for piece_id, qty in piece_counter_new.items():
            db.session.add(
                ProductComposition(
                    id_computador=assembly.id_computador,
                    id_peca=piece_id,
                    quantidade_utilizada=qty,
                    id_montagem=assembly.id,
                )
            )

        for custom_item in custom_items:
            db.session.add(
                AssemblyCustomPart(
                    assembly_id=assembly.id,
                    slot_key=custom_item['slot_key'],
                    part_name=custom_item['name'],
                    quantity=custom_item['qty'],
                    unit_cost=custom_item['unit_cost'],
                )
            )

        db.session.commit()
        flash('Montagem atualizada com sucesso!', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')

    return redirect(url_for('montar_pc'))


@app.route('/montagens/<int:assembly_id>/cancelar', methods=['POST'])
@_login_required
def cancelar_montagem(assembly_id: int):
    assembly = ComputerAssembly.query.get_or_404(assembly_id)

    if assembly.canceled:
        flash('Esta montagem já está cancelada.', 'danger')
        return redirect(url_for('montar_pc'))

    computer = assembly.computador
    if not computer:
        flash('Computador associado à montagem não encontrado.', 'danger')
        return redirect(url_for('montar_pc'))

    if computer.stock <= 0:
        flash('Não é possível cancelar: não há unidade em estoque para estorno.', 'danger')
        return redirect(url_for('montar_pc'))

    for item in assembly.composicao:
        if item.peca:
            item.peca.stock += item.quantidade_utilizada

    computer.stock -= 1
    assembly.canceled = True
    assembly.canceled_at = datetime.utcnow()

    db.session.commit()
    flash('Montagem cancelada e estoque estornado com sucesso!', 'success')
    return redirect(url_for('montar_pc'))


@app.route('/montagens/<int:assembly_id>/excluir', methods=['POST'])
@_login_required
def excluir_montagem(assembly_id: int):
    assembly = ComputerAssembly.query.get_or_404(assembly_id)

    if not assembly.canceled:
        computer = assembly.computador
        if computer and computer.stock > 0:
            computer.stock -= 1

        for item in assembly.composicao:
            if item.peca:
                item.peca.stock += item.quantidade_utilizada

    db.session.delete(assembly)
    db.session.commit()
    flash('Montagem excluída com sucesso!', 'success')
    return redirect(url_for('montar_pc'))




@app.route('/servicos', methods=['GET', 'POST'])
@_login_required
def servicos():
    service_catalog = [
        {'name': 'Montagem Premium', 'price': Decimal('199.90'), 'description': 'Montagem completa, organização de cabos e validação final.'},
        {'name': 'Upgrade e Limpeza', 'price': Decimal('149.90'), 'description': 'Troca de componentes com limpeza interna e pasta térmica.'},
        {'name': 'Diagnóstico Avançado', 'price': Decimal('99.90'), 'description': 'Checklist de desempenho, temperatura e estabilidade.'},
    ]

    if request.method == 'POST':
        form_type = request.form.get('form_type', 'service_record')

        if form_type == 'maintenance_ticket':
            client_name = (request.form.get('maintenance_client_name') or '').strip()
            equipment = (request.form.get('maintenance_equipment') or '').strip()
            service_description = (request.form.get('maintenance_service_description') or '').strip()
            entry_date_raw = request.form.get('maintenance_entry_date')
            waiting_parts = request.form.get('maintenance_waiting_parts') == 'on'

            if not client_name or not equipment or not service_description:
                flash('Preencha cliente, equipamento e serviço em manutenção.', 'danger')
                return redirect(url_for('servicos'))

            entry_date = datetime.utcnow()
            if entry_date_raw:
                try:
                    entry_date = datetime.fromisoformat(entry_date_raw)
                except ValueError:
                    flash('Data de entrada inválida.', 'danger')
                    return redirect(url_for('servicos'))

            db.session.add(
                MaintenanceTicket(
                    client_name=client_name,
                    equipment=equipment,
                    service_description=service_description,
                    entry_date=entry_date,
                    waiting_parts=waiting_parts,
                    status='aguardando_pecas' if waiting_parts else 'em_andamento',
                )
            )
            db.session.commit()
            flash('Computador em manutenção cadastrado com sucesso!', 'success')
            return redirect(url_for('servicos'))

        service_name = (request.form.get('service_name') or '').strip()
        client_name = (request.form.get('client_name') or '').strip()
        equipment = (request.form.get('equipment') or '').strip()
        total_price = Decimal(request.form.get('total_price') or '0')
        cost = Decimal(request.form.get('cost') or '0')
        notes = (request.form.get('notes') or '').strip() or None

        if not service_name or not client_name or not equipment:
            flash('Preencha serviço, cliente e equipamento.', 'danger')
            return redirect(url_for('servicos'))

        if total_price < 0 or cost < 0:
            flash('Preço e custo devem ser maiores ou iguais a zero.', 'danger')
            return redirect(url_for('servicos'))

        service = ServiceRecord(
            service_name=service_name,
            client_name=client_name,
            equipment=equipment,
            total_price=total_price,
            cost=cost,
            notes=notes,
        )
        db.session.add(service)
        db.session.commit()
        flash('Serviço realizado cadastrado com sucesso!', 'success')
        return redirect(url_for('servicos'))

    recent_services = ServiceRecord.query.order_by(ServiceRecord.created_at.desc()).limit(10).all()
    maintenance_tickets = MaintenanceTicket.query.order_by(MaintenanceTicket.entry_date.desc()).limit(20).all()
    return render_template(
        'services.html',
        services=service_catalog,
        recent_services=recent_services,
        maintenance_tickets=maintenance_tickets,
    )


@app.route('/manutencoes/<int:ticket_id>/atualizar', methods=['POST'])
@_login_required
def atualizar_manutencao(ticket_id: int):
    ticket = MaintenanceTicket.query.get_or_404(ticket_id)
    status = request.form.get('status') or ticket.status
    waiting_parts = request.form.get('waiting_parts') == 'on'
    exit_date_raw = request.form.get('exit_date')

    if status == 'concluido' and not exit_date_raw:
        ticket.exit_date = datetime.utcnow()
    elif exit_date_raw:
        try:
            ticket.exit_date = datetime.fromisoformat(exit_date_raw)
        except ValueError:
            flash('Data de saída inválida.', 'danger')
            return redirect(url_for('servicos'))

    ticket.status = status
    ticket.waiting_parts = waiting_parts
    if waiting_parts and status != 'concluido':
        ticket.status = 'aguardando_pecas'

    db.session.commit()
    flash('Status da manutenção atualizado!', 'success')
    return redirect(url_for('servicos'))


@app.route('/dashboard/custos-fixos', methods=['POST'])
@_login_required
def cadastrar_custo_fixo():
    description = (request.form.get('description') or '').strip()
    amount = Decimal(request.form.get('amount') or '0')

    if not description:
        flash('Informe a descrição do custo fixo.', 'danger')
        return redirect(url_for('dashboard'))
    if amount < 0:
        flash('O valor do custo fixo não pode ser negativo.', 'danger')
        return redirect(url_for('dashboard'))

    db.session.add(FixedCost(description=description, amount=amount))
    db.session.commit()
    flash('Custo fixo adicionado ao financeiro!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/clientes', methods=['GET', 'POST'])
@_login_required
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
@_login_required
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
@_login_required
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
@_login_required
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
@_login_required
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
@_login_required
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
@_login_required
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
@_login_required
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
@_login_required
def confirmar_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    charge.status = 'confirmado'
    charge.payment_confirmed_at = datetime.utcnow()
    db.session.commit()
    flash('Pagamento confirmado!', 'success')
    return redirect(url_for('cobrancas'))


@app.route('/cobrancas/<int:charge_id>/cancelar', methods=['POST'])
@_login_required
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


@app.route('/vendas/<int:sale_id>/imprimir')
@_login_required
def imprimir_venda(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)
    pdf = _html_to_pdf(_render_sale_receipt_html(sale))
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=f'recibo-venda-{sale.id}.pdf')


@app.route('/montagens/<int:assembly_id>/imprimir')
@_login_required
def imprimir_montagem(assembly_id: int):
    assembly = ComputerAssembly.query.get_or_404(assembly_id)
    pdf = _html_to_pdf(_render_assembly_receipt_html(assembly))
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=f'orcamento-montagem-{assembly.id}.pdf')


@app.route('/clientes/<int:client_id>/historico')
@_login_required
def historico_cliente(client_id: int):
    client = Client.query.get_or_404(client_id)
    sales = Sale.query.filter_by(client_id=client.id).order_by(Sale.created_at.desc()).all()
    maintenances = MaintenanceTicket.query.filter(MaintenanceTicket.client_name == client.name).order_by(MaintenanceTicket.entry_date.desc()).all()
    services = ServiceRecord.query.filter(ServiceRecord.client_name == client.name).order_by(ServiceRecord.created_at.desc()).all()
    return render_template('client_history.html', client=client, sales=sales, maintenances=maintenances, services=services)


@app.route('/logs')
@_login_required
def logs_auditoria():
    return render_template('audit_logs.html', logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(300).all())


@app.route('/produtos/<int:product_id>/alterar-preco', methods=['POST'])
@_login_required
def alterar_preco_produto(product_id: int):
    product = Product.query.get_or_404(product_id)
    old_price = Decimal(product.price)
    new_price = Decimal(request.form.get('new_price') or '0')
    if new_price < 0:
        flash('Preço inválido.', 'danger')
        return redirect(url_for('produtos'))

    product.price = new_price
    _log_audit(
        'Alteração de preço',
        f'Usuário {_current_user().name} alterou o preço do item {product.name} de R$ {old_price:.2f} para R$ {new_price:.2f} em {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}.',
    )
    db.session.commit()
    flash('Preço atualizado com sucesso!', 'success')
    return redirect(url_for('produtos'))


with app.app_context():
    db.create_all()

    if not User.query.first():
        admin_email = os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@lojaweb.local')
        admin_password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin123')
        db.session.add(User(name='Administrador', email=admin_email, password_hash=generate_password_hash(admin_password), is_admin=True))
        db.session.commit()

    columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(product)'))]
    if 'component_class' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN component_class VARCHAR(50)'))
    if 'cost_price' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN cost_price NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'serial_number' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN serial_number VARCHAR(120)'))
    db.session.commit()

    db.session.execute(
        db.text(
            'CREATE TABLE IF NOT EXISTS product_image ('
            'id INTEGER PRIMARY KEY, '
            'product_id INTEGER NOT NULL, '
            'image_url VARCHAR(255) NOT NULL, '
            'position INTEGER NOT NULL DEFAULT 0, '
            'FOREIGN KEY(product_id) REFERENCES product (id)'
            ')'
        )
    )
    db.session.execute(
        db.text(
            'CREATE TABLE IF NOT EXISTS assembly_custom_part ('
            'id INTEGER PRIMARY KEY, '
            'assembly_id INTEGER NOT NULL, '
            'slot_key VARCHAR(50) NOT NULL, '
            'part_name VARCHAR(120) NOT NULL, '
            'quantity INTEGER NOT NULL DEFAULT 1, '
            'unit_cost NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'FOREIGN KEY(assembly_id) REFERENCES montagem_computador (id)'
            ')'
        )
    )
    db.session.commit()

    db.session.execute(
        db.text(
            'CREATE TABLE IF NOT EXISTS service_record ('
            'id INTEGER PRIMARY KEY, '
            'service_name VARCHAR(120) NOT NULL, '
            'client_name VARCHAR(120) NOT NULL, '
            'equipment VARCHAR(120) NOT NULL, '
            'total_price NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'cost NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'notes TEXT, '
            'created_at DATETIME NOT NULL'
            ')'
        )
    )
    db.session.execute(
        db.text(
            'CREATE TABLE IF NOT EXISTS fixed_cost ('
            'id INTEGER PRIMARY KEY, '
            'description VARCHAR(120) NOT NULL, '
            'amount NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'created_at DATETIME NOT NULL'
            ')'
        )
    )
    db.session.execute(
        db.text(
            'CREATE TABLE IF NOT EXISTS maintenance_ticket ('
            'id INTEGER PRIMARY KEY, '
            'client_name VARCHAR(120) NOT NULL, '
            'equipment VARCHAR(120) NOT NULL, '
            'service_description VARCHAR(180) NOT NULL, '
            'entry_date DATETIME NOT NULL, '
            'exit_date DATETIME, '
            'waiting_parts BOOLEAN NOT NULL DEFAULT 0, '
            "status VARCHAR(30) NOT NULL DEFAULT 'em_andamento', "
            'created_at DATETIME NOT NULL'
            ')'
        )
    )
    db.session.commit()

    montagem_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(montagem_computador)'))]
    if 'nome_referencia' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN nome_referencia VARCHAR(120)'))
    if 'preco_original' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN preco_original NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'canceled' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN canceled BOOLEAN NOT NULL DEFAULT 0'))
    if 'canceled_at' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN canceled_at DATETIME'))
    if 'technical_notes' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN technical_notes TEXT'))
    if 'bios_updated' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN bios_updated BOOLEAN NOT NULL DEFAULT 0'))
    if 'stress_test_done' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN stress_test_done BOOLEAN NOT NULL DEFAULT 0'))
    if 'os_installed' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN os_installed BOOLEAN NOT NULL DEFAULT 0'))
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
