from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
import os
from pathlib import Path
from uuid import uuid4
from io import BytesIO

from flask import Flask, flash, make_response, redirect, render_template, request, session, url_for
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    from xhtml2pdf import pisa
except ImportError:
    pisa = None

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
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

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
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    canceled = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    client = db.relationship('Client')
    product = db.relationship('Product')
    items = db.relationship('SaleItem', backref='sale', cascade='all, delete-orphan')


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    line_type = db.Column(db.String(20), nullable=False, default='produto')
    description = db.Column(db.String(180), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    line_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    product = db.relationship('Product')


class Charge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey('service_record.id'), nullable=True)
    mercado_pago_reference = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pendente')
    payment_method = db.Column(db.String(30), nullable=False, default='pix')
    payment_confirmed_at = db.Column(db.DateTime, nullable=True)

    sale = db.relationship('Sale')
    service = db.relationship('ServiceRecord')


class ServiceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(120), nullable=False)
    client_name = db.Column(db.String(120), nullable=False)
    equipment = db.Column(db.String(120), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
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


class LoginThrottle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    blocked_until = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def _client_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _get_or_create_throttle(email: str, ip_address: str):
    throttle = LoginThrottle.query.filter_by(email=email, ip_address=ip_address).first()
    if throttle:
        return throttle
    throttle = LoginThrottle(email=email, ip_address=ip_address, failed_attempts=0)
    db.session.add(throttle)
    db.session.flush()
    return throttle


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


def _parse_sale_items(form):
    raw_types = form.getlist('item_type[]')
    raw_product_ids = form.getlist('item_product_id[]')
    raw_descriptions = form.getlist('item_description[]')
    raw_quantities = form.getlist('item_quantity[]')
    raw_unit_prices = form.getlist('item_unit_price[]')
    raw_unit_costs = form.getlist('item_unit_cost[]')

    max_len = max(
        len(raw_types),
        len(raw_product_ids),
        len(raw_descriptions),
        len(raw_quantities),
        len(raw_unit_prices),
        len(raw_unit_costs),
        0,
    )

    items = []
    for idx in range(max_len):
        line_type = (raw_types[idx] if idx < len(raw_types) else '').strip().lower() or 'produto'
        if line_type not in {'produto', 'servico'}:
            line_type = 'produto'

        product_id_raw = (raw_product_ids[idx] if idx < len(raw_product_ids) else '').strip()
        description = (raw_descriptions[idx] if idx < len(raw_descriptions) else '').strip()
        qty_raw = (raw_quantities[idx] if idx < len(raw_quantities) else '').strip()
        unit_price_raw = (raw_unit_prices[idx] if idx < len(raw_unit_prices) else '').strip()
        unit_cost_raw = (raw_unit_costs[idx] if idx < len(raw_unit_costs) else '').strip()

        if not any([product_id_raw, description, qty_raw, unit_price_raw, unit_cost_raw]):
            continue

        try:
            quantity = int(qty_raw or '1')
        except ValueError as exc:
            raise ValueError(f'Quantidade inválida na linha {idx + 1}.') from exc

        if quantity <= 0:
            raise ValueError(f'Quantidade deve ser maior que zero na linha {idx + 1}.')

        try:
            unit_price = Decimal(unit_price_raw or '0')
            unit_cost = Decimal(unit_cost_raw or '0')
        except InvalidOperation as exc:
            raise ValueError(f'Preço/custo inválido na linha {idx + 1}.') from exc

        if unit_price < 0 or unit_cost < 0:
            raise ValueError(f'Preço/custo não pode ser negativo na linha {idx + 1}.')

        item = {
            'line_type': line_type,
            'product_id': None,
            'description': description,
            'quantity': quantity,
            'unit_price': unit_price.quantize(Decimal('0.01')),
            'unit_cost': unit_cost.quantize(Decimal('0.01')),
        }

        if line_type == 'produto':
            if not product_id_raw:
                raise ValueError(f'Selecione um produto na linha {idx + 1}.')
            try:
                item['product_id'] = int(product_id_raw)
            except ValueError as exc:
                raise ValueError(f'Produto inválido na linha {idx + 1}.') from exc

        if not item['description']:
            item['description'] = 'Item sem descrição'

        item['line_total'] = (item['unit_price'] * Decimal(item['quantity'])).quantize(Decimal('0.01'))
        items.append(item)

    if not items:
        raise ValueError('Adicione ao menos um item (produto ou serviço) na venda.')

    return items


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

    def _safe_qty(raw_value):
        try:
            qty = int(raw_value)
        except (TypeError, ValueError):
            return 1
        return max(1, qty)

    for slot_key, _, allow_multiple in COMPONENT_SLOTS:
        if allow_multiple:
            ids = form_data.getlist(f'{prefix}{slot_key}_ids[]')
            qtys = form_data.getlist(f'{prefix}{slot_key}_qtys[]')
            custom_names = form_data.getlist(f'{prefix}{slot_key}_custom_names[]')
            custom_costs = form_data.getlist(f'{prefix}{slot_key}_custom_costs[]')

            for piece_id, qty, custom_name, custom_cost in zip(ids, qtys, custom_names, custom_costs):
                qty_value = _safe_qty(qty)
                if piece_id:
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
        remember_me = request.form.get('remember_me') == 'on'
        ip_address = _client_ip()

        if not email or not password:
            flash('Preencha e-mail e senha para continuar.', 'danger')
            return redirect(url_for('login'))

        throttle = _get_or_create_throttle(email, ip_address)
        now = datetime.utcnow()
        blocked_by_email = LoginThrottle.query.filter(
            LoginThrottle.email == email,
            LoginThrottle.blocked_until.isnot(None),
            LoginThrottle.blocked_until > now,
        ).order_by(LoginThrottle.blocked_until.desc()).first()
        blocked_by_ip = LoginThrottle.query.filter(
            LoginThrottle.ip_address == ip_address,
            LoginThrottle.blocked_until.isnot(None),
            LoginThrottle.blocked_until > now,
        ).order_by(LoginThrottle.blocked_until.desc()).first()
        active_block = blocked_by_email or blocked_by_ip
        if active_block:
            remaining = int((active_block.blocked_until - now).total_seconds() // 60) + 1
            flash(f'Muitas tentativas de login. Tente novamente em {remaining} minuto(s).', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            throttle.failed_attempts += 1
            throttle.updated_at = datetime.utcnow()
            email_attempts = db.session.query(db.func.sum(LoginThrottle.failed_attempts)).filter(LoginThrottle.email == email).scalar() or 0
            ip_attempts = db.session.query(db.func.sum(LoginThrottle.failed_attempts)).filter(LoginThrottle.ip_address == ip_address).scalar() or 0
            if email_attempts >= 5 or ip_attempts >= 5:
                block_until = now + timedelta(minutes=15)
                LoginThrottle.query.filter(
                    (LoginThrottle.email == email) | (LoginThrottle.ip_address == ip_address)
                ).update(
                    {
                        LoginThrottle.blocked_until: block_until,
                        LoginThrottle.updated_at: datetime.utcnow(),
                    },
                    synchronize_session=False,
                )
            db.session.commit()
            flash('E-mail ou senha incorretos. Verifique os dados e tente novamente.', 'danger')
            return redirect(url_for('login'))

        throttle.failed_attempts = 0
        throttle.blocked_until = None
        throttle.updated_at = datetime.utcnow()
        session.permanent = remember_me
        session['user_id'] = user.id
        db.session.commit()
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


@app.route('/usuarios/<int:user_id>/editar', methods=['POST'])
@_login_required
def editar_usuario(user_id: int):
    current = _current_user()
    if not current or not current.is_admin:
        flash('Apenas administradores podem editar usuários.', 'danger')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    is_admin = request.form.get('is_admin') == 'on'

    if not name or not email:
        flash('Nome e e-mail são obrigatórios para edição.', 'danger')
        return redirect(url_for('usuarios'))

    duplicated = User.query.filter(User.email == email, User.id != user.id).first()
    if duplicated:
        flash('Já existe outro usuário com este e-mail.', 'danger')
        return redirect(url_for('usuarios'))

    user.name = name
    user.email = email
    user.is_admin = is_admin
    _log_audit('Edição de usuário', f'Usuário {current.name} editou o cadastro de {user.name} ({user.email}).')
    db.session.commit()
    flash('Usuário atualizado com sucesso!', 'success')
    return redirect(url_for('usuarios'))


@app.route('/usuarios/<int:user_id>/remover', methods=['POST'])
@_login_required
def remover_usuario(user_id: int):
    current = _current_user()
    if not current or not current.is_admin:
        flash('Apenas administradores podem remover usuários.', 'danger')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    if user.id == current.id:
        flash('Você não pode remover seu próprio usuário.', 'danger')
        return redirect(url_for('usuarios'))

    user_name = user.name
    user_email = user.email
    db.session.delete(user)
    _log_audit('Remoção de usuário', f'Usuário {current.name} removeu o usuário {user_name} ({user_email}).')
    db.session.commit()
    flash('Usuário removido com sucesso!', 'success')
    return redirect(url_for('usuarios'))


@app.route('/imprimir/<string:tipo>/<int:record_id>')
@_login_required
def imprimir(tipo: str, record_id: int):
    if tipo == 'venda':
        data = Sale.query.get_or_404(record_id)
        sale_items = data.items or []
        context = {
            'document_title': f'Recibo de Venda #{data.id}',
            'store_name': 'LojaWeb',
            'store_contact': 'contato@lojaweb.local',
            'record_date': data.created_at,
            'record_code': f'VEN-{data.id}',
            'client_name': data.client.name,
            'items': [
                {
                    'item': line.description,
                    'quantity': line.quantity,
                    'unit_price': line.unit_price,
                    'total': line.line_total,
                }
                for line in sale_items
            ] or [{
                'item': data.product.name,
                'quantity': data.quantity,
                'unit_price': data.product.price,
                'total': data.total,
            }],
            'subtotal': data.subtotal,
            'discount_amount': data.discount_amount,
            'total': data.total,
            'technical': {
                'bios': 'Não se aplica',
                'stress': 'Não se aplica',
                'os': 'Não se aplica',
            },
            'notes': f'Venda: {data.sale_name}',
        }
    elif tipo == 'montagem':
        data = ComputerAssembly.query.get_or_404(record_id)
        items = [
            {
                'item': item.peca.name,
                'quantity': item.quantidade_utilizada,
                'unit_price': item.peca.price,
                'total': Decimal(item.quantidade_utilizada) * Decimal(item.peca.price),
            }
            for item in data.composicao
        ]
        items.extend(
            {
                'item': custom.part_name,
                'quantity': custom.quantity,
                'unit_price': custom.unit_cost,
                'total': Decimal(custom.quantity) * Decimal(custom.unit_cost),
            }
            for custom in data.custom_parts
        )
        context = {
            'document_title': f'Recibo de Montagem #{data.id}',
            'store_name': 'LojaWeb',
            'store_contact': 'contato@lojaweb.local',
            'record_date': data.created_at,
            'record_code': f'MON-{data.id}',
            'client_name': data.nome_referencia or data.computador.name,
            'items': items,
            'subtotal': data.custo_total,
            'total': data.preco_original + data.custo_total,
            'technical': {
                'bios': 'Sim' if data.bios_updated else 'Não',
                'stress': 'Sim' if data.stress_test_done else 'Não',
                'os': 'Sim' if data.os_installed else 'Não',
            },
            'notes': data.technical_notes or 'Sem observações técnicas.',
        }
    else:
        flash('Tipo de impressão inválido.', 'danger')
        return redirect(url_for('dashboard'))

    html = render_template('print_receipt.html', **context)
    if pisa is None:
        return html

    pdf_buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=pdf_buffer)
    if status.err:
        flash('Não foi possível gerar PDF. Exibindo versão HTML para impressão.', 'danger')
        return html

    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename="{tipo}-{record_id}.pdf"'
    return response


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
        db.func.coalesce(db.func.sum(SaleItem.line_total - (SaleItem.unit_cost * SaleItem.quantity)), 0)
    ).join(Sale, Sale.id == SaleItem.sale_id).filter(
        Sale.canceled.is_(False), Sale.created_at >= start_date
    ).scalar()
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
            db.func.coalesce(db.func.sum(db.func.coalesce(Sale.total, ServiceRecord.total_price, 0)), 0),
        )
        .outerjoin(Sale, Sale.id == Charge.sale_id)
        .outerjoin(ServiceRecord, ServiceRecord.id == Charge.service_id)
        .filter(
            db.or_(
                db.and_(Charge.sale_id.isnot(None), Sale.canceled.is_(False), Sale.created_at >= start_date),
                db.and_(Charge.service_id.isnot(None), ServiceRecord.created_at >= start_date),
            )
        )
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
        db.session.query(Product.name, db.func.coalesce(db.func.sum(SaleItem.quantity), 0).label('qty'))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.canceled.is_(False), Sale.created_at >= start_date, SaleItem.line_type == 'produto')
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
            create_stock_item = request.form.get('create_stock_item', 'on') == 'on'
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
        create_stock_item = request.form.get('create_stock_item', 'on') == 'on'
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
        notes = (request.form.get('notes') or '').strip() or None

        client_id_raw = (request.form.get('client_id') or '').strip()
        if client_id_raw:
            try:
                client = Client.query.get(int(client_id_raw))
            except ValueError:
                client = None
            if client:
                client_name = client.name

        try:
            total_price = Decimal(request.form.get('total_price') or '0')
            discount_amount = Decimal(request.form.get('discount_amount') or '0')
            cost = Decimal(request.form.get('cost') or '0')
        except InvalidOperation:
            flash('Preço, desconto e custo devem ser numéricos.', 'danger')
            return redirect(url_for('servicos'))

        if not service_name or not client_name or not equipment:
            flash('Preencha serviço, cliente e equipamento.', 'danger')
            return redirect(url_for('servicos'))

        if total_price < 0 or discount_amount < 0 or cost < 0:
            flash('Preço, desconto e custo devem ser maiores ou iguais a zero.', 'danger')
            return redirect(url_for('servicos'))

        if discount_amount > total_price:
            flash('Desconto não pode ser maior que o valor cobrado do serviço.', 'danger')
            return redirect(url_for('servicos'))

        final_service_price = (total_price - discount_amount).quantize(Decimal('0.01'))

        service = ServiceRecord(
            service_name=service_name,
            client_name=client_name,
            equipment=equipment,
            total_price=final_service_price,
            discount_amount=discount_amount.quantize(Decimal('0.01')),
            cost=cost,
            notes=notes,
        )
        db.session.add(service)
        db.session.flush()

        if request.form.get('generate_charge') == 'on':
            charge_reference = (request.form.get('charge_reference') or '').strip()
            if not charge_reference:
                flash('Informe a referência da cobrança para o serviço.', 'danger')
                db.session.rollback()
                return redirect(url_for('servicos'))

            charge_status = (request.form.get('charge_status') or 'pendente').strip()
            if charge_status not in {'pendente', 'confirmado', 'cancelado'}:
                charge_status = 'pendente'

            charge_payment_method = (request.form.get('charge_payment_method') or 'pix').strip()
            if charge_payment_method not in PAYMENT_METHOD_LABELS:
                charge_payment_method = 'pix'

            db.session.add(
                Charge(
                    service_id=service.id,
                    mercado_pago_reference=charge_reference,
                    status=charge_status,
                    payment_method=charge_payment_method,
                    payment_confirmed_at=datetime.utcnow() if charge_status == 'confirmado' else None,
                )
            )

        db.session.commit()
        flash('Serviço realizado cadastrado com sucesso!', 'success')
        return redirect(url_for('servicos'))

    recent_services = ServiceRecord.query.order_by(ServiceRecord.created_at.desc()).limit(10).all()
    maintenance_tickets = MaintenanceTicket.query.order_by(MaintenanceTicket.entry_date.desc()).limit(20).all()
    clients = Client.query.order_by(Client.name.asc()).all()
    return render_template(
        'services.html',
        services=service_catalog,
        recent_services=recent_services,
        maintenance_tickets=maintenance_tickets,
        clients=clients,
        payment_methods=PAYMENT_METHODS,
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

        if not sale_name:
            flash('Informe um nome para identificar a venda.', 'danger')
            return redirect(url_for('vendas'))

        try:
            parsed_items = _parse_sale_items(request.form)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('vendas'))

        product_ids = [item['product_id'] for item in parsed_items if item['line_type'] == 'produto']
        products_by_id = {}
        service_placeholder = None
        if product_ids:
            fetched_products = Product.query.filter(Product.id.in_(product_ids)).all()
            products_by_id = {prod.id: prod for prod in fetched_products}

        for idx, item in enumerate(parsed_items, start=1):
            if item['line_type'] != 'produto':
                continue
            product = products_by_id.get(item['product_id'])
            if not product:
                flash(f'Produto inválido na linha {idx}.', 'danger')
                return redirect(url_for('vendas'))
            if item['quantity'] > product.stock:
                flash(f'Estoque insuficiente para {product.name} na linha {idx}.', 'danger')
                return redirect(url_for('vendas'))
            if item['unit_price'] == Decimal('0.00'):
                item['unit_price'] = Decimal(product.price).quantize(Decimal('0.01'))
                item['line_total'] = (item['unit_price'] * Decimal(item['quantity'])).quantize(Decimal('0.01'))
            if item['unit_cost'] == Decimal('0.00'):
                item['unit_cost'] = Decimal(product.cost_price or 0).quantize(Decimal('0.01'))
            if not item['description'] or item['description'] == 'Item sem descrição':
                item['description'] = product.name

        subtotal = sum((item['line_total'] for item in parsed_items), Decimal('0.00')).quantize(Decimal('0.01'))

        try:
            discount_amount = Decimal(request.form.get('discount_amount') or '0').quantize(Decimal('0.01'))
        except InvalidOperation:
            flash('Desconto inválido para a venda.', 'danger')
            return redirect(url_for('vendas'))

        if discount_amount < 0:
            flash('Desconto da venda não pode ser negativo.', 'danger')
            return redirect(url_for('vendas'))

        if discount_amount > subtotal:
            flash('Desconto da venda não pode ser maior que o subtotal.', 'danger')
            return redirect(url_for('vendas'))

        total = (subtotal - discount_amount).quantize(Decimal('0.01'))

        if product_ids:
            anchor_product_id = product_ids[0]
        else:
            service_placeholder = Product.query.filter_by(category='Serviço', name='Serviço avulso').first()
            if not service_placeholder:
                service_placeholder = Product(
                    name='Serviço avulso',
                    category='Serviço',
                    stock=999999,
                    price=Decimal('0.00'),
                    cost_price=Decimal('0.00'),
                )
                db.session.add(service_placeholder)
                db.session.flush()
            anchor_product_id = service_placeholder.id

        sale = Sale(
            sale_name=sale_name,
            client_id=client_id,
            product_id=anchor_product_id,
            quantity=1,
            subtotal=subtotal,
            discount_amount=discount_amount,
            total=total,
        )
        db.session.add(sale)
        db.session.flush()

        for item in parsed_items:
            if item['line_type'] == 'produto':
                product = products_by_id[item['product_id']]
                product.stock -= item['quantity']

            db.session.add(
                SaleItem(
                    sale_id=sale.id,
                    line_type=item['line_type'],
                    description=item['description'],
                    product_id=item['product_id'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                    unit_cost=item['unit_cost'],
                    line_total=item['line_total'],
                )
            )

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
        if sale.items:
            for line in sale.items:
                if line.line_type == 'produto' and line.product:
                    line.product.stock += line.quantity
        elif sale.product:
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
        sale_id_raw = (request.form.get('sale_id') or '').strip()
        service_id_raw = (request.form.get('service_id') or '').strip()

        try:
            sale_id = int(sale_id_raw) if sale_id_raw else None
            service_id = int(service_id_raw) if service_id_raw else None
        except ValueError:
            flash('Origem da cobrança inválida.', 'danger')
            return redirect(url_for('cobrancas'))

        if not sale_id and not service_id:
            flash('Selecione uma venda ou serviço para gerar a cobrança.', 'danger')
            return redirect(url_for('cobrancas'))

        if sale_id and service_id:
            flash('Selecione apenas uma origem: venda ou serviço.', 'danger')
            return redirect(url_for('cobrancas'))

        charge = Charge(
            sale_id=sale_id,
            service_id=service_id,
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
    services = ServiceRecord.query.order_by(ServiceRecord.created_at.desc()).limit(200).all()
    charges = Charge.query.order_by(Charge.id.desc()).all()
    return render_template('charges.html', charges=charges, sales=sales, services=services, payment_methods=PAYMENT_METHODS)


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
    db.session.execute(
        db.text(
            'CREATE TABLE IF NOT EXISTS login_throttle ('
            'id INTEGER PRIMARY KEY, '
            'email VARCHAR(120) NOT NULL, '
            'ip_address VARCHAR(45) NOT NULL, '
            'failed_attempts INTEGER NOT NULL DEFAULT 0, '
            'blocked_until DATETIME, '
            'updated_at DATETIME NOT NULL'
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
            'discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0, '
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
            'CREATE TABLE IF NOT EXISTS sale_item ('
            'id INTEGER PRIMARY KEY, '
            'sale_id INTEGER NOT NULL, '
            'line_type VARCHAR(20) NOT NULL DEFAULT "produto", '
            'description VARCHAR(180) NOT NULL, '
            'product_id INTEGER, '
            'quantity INTEGER NOT NULL DEFAULT 1, '
            'unit_price NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'unit_cost NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'line_total NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'FOREIGN KEY(sale_id) REFERENCES sale (id), '
            'FOREIGN KEY(product_id) REFERENCES product (id)'
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
    if 'discount_amount' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'canceled' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN canceled BOOLEAN NOT NULL DEFAULT 0'))
    if 'canceled_at' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN canceled_at DATETIME'))
    db.session.commit()

    service_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(service_record)'))]
    if 'discount_amount' not in service_columns:
        db.session.execute(db.text('ALTER TABLE service_record ADD COLUMN discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0'))
    db.session.commit()

    client_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(client)'))]
    if 'cpf' not in client_columns:
        db.session.execute(db.text('ALTER TABLE client ADD COLUMN cpf VARCHAR(14)'))
    db.session.execute(db.text('CREATE UNIQUE INDEX IF NOT EXISTS ux_client_cpf ON client (cpf)'))
    db.session.commit()

    charge_columns_info = list(db.session.execute(db.text('PRAGMA table_info(charge)')))
    charge_columns = [row[1] for row in charge_columns_info]
    if 'payment_method' not in charge_columns:
        db.session.execute(db.text("ALTER TABLE charge ADD COLUMN payment_method VARCHAR(30) NOT NULL DEFAULT 'pix'"))
    if 'service_id' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN service_id INTEGER'))

    sale_id_info = next((row for row in charge_columns_info if row[1] == 'sale_id'), None)
    sale_id_is_not_null = bool(sale_id_info and sale_id_info[3] == 1)
    if sale_id_is_not_null:
        db.session.execute(db.text('ALTER TABLE charge RENAME TO charge_old'))
        db.session.execute(
            db.text(
                'CREATE TABLE charge ('
                'id INTEGER PRIMARY KEY, '
                'sale_id INTEGER, '
                'service_id INTEGER, '
                'mercado_pago_reference VARCHAR(120) NOT NULL, '
                "status VARCHAR(30) NOT NULL DEFAULT 'pendente', "
                "payment_method VARCHAR(30) NOT NULL DEFAULT 'pix', "
                'payment_confirmed_at DATETIME, '
                'FOREIGN KEY(sale_id) REFERENCES sale (id), '
                'FOREIGN KEY(service_id) REFERENCES service_record (id)'
                ')'
            )
        )
        db.session.execute(
            db.text(
                'INSERT INTO charge (id, sale_id, mercado_pago_reference, status, payment_method, payment_confirmed_at) '
                'SELECT id, sale_id, mercado_pago_reference, status, payment_method, payment_confirmed_at FROM charge_old'
            )
        )
        db.session.execute(db.text('DROP TABLE charge_old'))

    db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
