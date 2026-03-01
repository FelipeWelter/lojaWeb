from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
import json
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
from io import BytesIO
import re
import unicodedata

from flask import Flask, flash, make_response, redirect, render_template, request, session, url_for
from flask_mail import Mail, Message

from crud import ClientDTO, GenericCrudService, ProductDTO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from services.estoque_service import buscar_pecas_disponiveis, buscar_pecas_por_classe
from utils.financeiro import calcular_margem_lucro, calcular_preco_sugerido

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
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'feliwelter@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'pfflmknbhgwsugch')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME', 'feliwelter@gmail.com'))
app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT', 'lojaweb-reset-salt')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['LOGIN_THROTTLE_MAX_ATTEMPTS'] = int(os.getenv('LOGIN_THROTTLE_MAX_ATTEMPTS', '5'))
app.config['LOGIN_THROTTLE_BLOCK_MINUTES'] = int(os.getenv('LOGIN_THROTTLE_BLOCK_MINUTES', '15'))
app.config['PIX_KEY'] = os.getenv('PIX_KEY', '').strip()
app.config['PIX_RECEIVER_NAME'] = os.getenv('PIX_RECEIVER_NAME', 'LOJAWEB TECNOLOGIA').strip()
app.config['PIX_RECEIVER_CITY'] = os.getenv('PIX_RECEIVER_CITY', 'SAO PAULO').strip()
app.config['BRANDING_UPLOAD_FOLDER'] = 'static/uploads/branding'

db = SQLAlchemy(app)
mail = Mail(app)

product_service = GenericCrudService(model=None, db=db)
client_service = GenericCrudService(model=None, db=db)


class Product(db.Model):
    """Classe `Product`: Representa um produto no sistema de loja."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False, default='Peça')
    stock = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    photo_url = db.Column(db.String(255), nullable=True)
    component_class = db.Column(db.String(50), nullable=True)
    serial_number = db.Column(db.String(120), nullable=True)
    ram_ddr = db.Column(db.String(30), nullable=True)
    ram_frequency = db.Column(db.String(30), nullable=True)
    ram_size = db.Column(db.String(30), nullable=True)
    ram_brand = db.Column(db.String(60), nullable=True)
    psu_watts = db.Column(db.String(30), nullable=True)
    psu_brand = db.Column(db.String(60), nullable=True)
    gpu_memory = db.Column(db.String(30), nullable=True)
    gpu_brand = db.Column(db.String(60), nullable=True)
    gpu_manufacturer = db.Column(db.String(30), nullable=True)
    storage_type = db.Column(db.String(20), nullable=True)
    storage_capacity = db.Column(db.String(30), nullable=True)
    storage_brand = db.Column(db.String(60), nullable=True)
    cpu_brand = db.Column(db.String(60), nullable=True)
    cpu_manufacturer = db.Column(db.String(60), nullable=True)
    cpu_model = db.Column(db.String(80), nullable=True)
    motherboard_brand = db.Column(db.String(60), nullable=True)
    motherboard_model = db.Column(db.String(80), nullable=True)
    motherboard_socket = db.Column(db.String(40), nullable=True)
    motherboard_chipset = db.Column(db.String(40), nullable=True)
    cabinet_brand = db.Column(db.String(60), nullable=True)
    cabinet_description = db.Column(db.String(180), nullable=True)
    fan_brand = db.Column(db.String(60), nullable=True)
    fan_description = db.Column(db.String(180), nullable=True)
    peripheral_mouse = db.Column(db.String(120), nullable=True)
    peripheral_keyboard = db.Column(db.String(120), nullable=True)
    peripheral_monitor = db.Column(db.String(120), nullable=True)
    peripheral_power_cable = db.Column(db.String(120), nullable=True)
    peripheral_hdmi_cable = db.Column(db.String(120), nullable=True)
    images = db.relationship('ProductImage', backref='product', cascade='all, delete-orphan', order_by='ProductImage.position')
    active = db.Column(db.Boolean, nullable=False, default=True)

    @property
    def inventory_spec_summary(self):
        specs = []

        def add_spec(label, value):
            """Função `add_spec`: adiciona uma especificação ao resumo do inventário."""
            cleaned = (value or '').strip()
            if cleaned:
                specs.append(f'{label}: {cleaned}')

        add_spec('Classe', COMPONENT_CLASS_LABELS.get(self.component_class, self.component_class or ''))
        add_spec('Fabricante', self.motherboard_brand or self.cpu_manufacturer or self.gpu_manufacturer)
        add_spec('Marca', self.ram_brand or self.gpu_brand or self.storage_brand or self.psu_brand)
        add_spec('Modelo', self.motherboard_model or self.cpu_model)
        add_spec('Socket', self.motherboard_socket)
        add_spec('Chipset', self.motherboard_chipset)
        add_spec('DDR', self.ram_ddr)
        add_spec('Frequência', self.ram_frequency)
        add_spec('Capacidade RAM', self.ram_size)
        add_spec('Memória GPU', self.gpu_memory)
        add_spec('Armazenamento', self.storage_type)
        add_spec('Capacidade', self.storage_capacity)
        add_spec('Gabinete', self.cabinet_brand)
        add_spec('Descrição', self.cabinet_description)
        add_spec('Fan', self.fan_brand)
        add_spec('Descrição do fan', self.fan_description)
        add_spec('Fonte', self.psu_watts)
        add_spec('Mouse', self.peripheral_mouse)
        add_spec('Teclado', self.peripheral_keyboard)
        add_spec('Monitor', self.peripheral_monitor)
        add_spec('Cabo de força', self.peripheral_power_cable)
        add_spec('Cabo HDMI', self.peripheral_hdmi_cable)
        add_spec('S/N', self.serial_number)

        return ' • '.join(specs)

    @property
    def inventory_display_name(self):
        """Função `inventory_display_name`: retorna o nome de exibição do produto com suas especificações."""
        summary = self.inventory_spec_summary
        return f'{self.name} — {summary}' if summary else self.name

    @property
    def inventory_image_url(self):
        """Função `inventory_image_url`: retorna a URL da imagem do produto para exibição no inventário, seguindo uma lógica de fallback."""
        image_url = self.photo_url
        if not image_url and self.images:
            image_url = self.images[0].image_url

        if not image_url:
            return None

        if image_url.startswith('http://') or image_url.startswith('https://'):
            return image_url
        if image_url.startswith('/static/'):
            return image_url
        if image_url.startswith('static/'):
            return f'/{image_url}'
        if image_url.startswith('uploads/'):
            return f'/static/{image_url}'
        if image_url.startswith('/'):
            return image_url
        return f'/static/uploads/products/{image_url}'


class ProductImage(db.Model):
    """Classe `ProductImage`: representa uma imagem associada a um produto, permitindo múltiplas imagens por produto e controle de posição para ordenação."""
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)


class ProductComposition(db.Model):
    """Classe `ProductComposition`: representa a composição de um produto, associando peças componentes a um produto principal."""
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

    """Classe `AssemblyCustomPart`: 
     representa peças personalizadas adicionadas
     a uma montagem de computador, permitindo controle de
     custo e quantidade para peças que não estão no estoque."""

    id = db.Column(db.Integer, primary_key=True)
    assembly_id = db.Column(db.Integer, db.ForeignKey('montagem_computador.id'), nullable=False)
    slot_key = db.Column(db.String(50), nullable=False)
    part_name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)


class ComputerAssembly(db.Model):
    """Classe `ComputerAssembly`: representa uma montagem de computador, incluindo informações sobre o computador associado, custos, status e notas técnicas."""
    __tablename__ = 'montagem_computador'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    id_computador = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    nome_referencia = db.Column(db.String(120), nullable=True)
    preco_original = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    custo_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    preco_sugerido = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    apply_price_suggestion = db.Column(db.Boolean, nullable=False, default=False)
    canceled = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)
    technical_notes = db.Column(db.Text, nullable=True)
    bios_updated = db.Column(db.Boolean, nullable=False, default=False)
    bios_service_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stress_test_done = db.Column(db.Boolean, nullable=False, default=False)
    stress_test_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    os_installed = db.Column(db.Boolean, nullable=False, default=False)
    os_install_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    computador = db.relationship('Product')
    performed_by = db.relationship('User', foreign_keys=[performed_by_user_id])
    composicao = db.relationship('ProductComposition', backref='montagem', cascade='all, delete-orphan')
    custom_parts = db.relationship('AssemblyCustomPart', backref='assembly', cascade='all, delete-orphan')


class Client(db.Model):
    """Classe `Client`: representa um cliente do sistema, armazenando informações como nome, CPF, telefone e email."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), nullable=True, unique=True)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)


class Sale(db.Model):
    """Classe `Sale`: representa uma venda realizada,
    incluindo informações sobre o cliente, produto, quantidade,
    valores envolvidos, método de pagamento e status de cancelamento."""

    id = db.Column(db.Integer, primary_key=True)
    sale_name = db.Column(db.String(120), nullable=False, default='Venda sem nome')
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    payment_method = db.Column(db.String(30), nullable=False, default='pix')
    canceled = db.Column(db.Boolean, nullable=False, default=False)
    canceled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    client = db.relationship('Client')
    product = db.relationship('Product')
    items = db.relationship('SaleItem', backref='sale', cascade='all, delete-orphan')
    performed_by = db.relationship('User', foreign_keys=[performed_by_user_id])


class SaleItem(db.Model):
    """Classe `SaleItem`: representa um item específico dentro de uma venda,
    permitindo detalhamento de cada produto ou serviço vendido, suas quantidades,
    preços unitários, custos e totais associados."""

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=False)
    line_type = db.Column(db.String(20), nullable=False, default='produto')
    description = db.Column(db.String(180), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    service_record_id = db.Column(db.Integer, db.ForeignKey('service_record.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    line_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    product = db.relationship('Product')
    service_record = db.relationship('ServiceRecord', foreign_keys=[service_record_id])


class Charge(db.Model):
    """Classe `Charge`: representa uma cobrança associada a uma venda ou serviço,
    incluindo detalhes sobre o valor, data de vencimento, status de pagamento e método de pagamento."""

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sale.id'), nullable=True)
    service_id = db.Column(db.Integer, db.ForeignKey('service_record.id'), nullable=True)
    mercado_pago_reference = db.Column(db.String(120), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default='pendente')
    payment_method = db.Column(db.String(30), nullable=False, default='pix')
    is_installment = db.Column(db.Boolean, nullable=False, default=False)
    installment_count = db.Column(db.Integer, nullable=False, default=1)
    installment_value = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    payment_confirmed_at = db.Column(db.DateTime, nullable=True)

    sale = db.relationship('Sale')
    service = db.relationship('ServiceRecord')
    installments = db.relationship('ChargeInstallment', backref='charge', cascade='all, delete-orphan', order_by='ChargeInstallment.installment_number')


class ChargeInstallment(db.Model):
    """Classe `ChargeInstallment`: representa um parcelamento de uma cobrança,
    incluindo detalhes sobre o número da parcela, data de vencimento, valor e status."""

    id = db.Column(db.Integer, primary_key=True)
    charge_id = db.Column(db.Integer, db.ForeignKey('charge.id'), nullable=False)
    installment_number = db.Column(db.Integer, nullable=False, default=1)
    due_date = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default='pendente')
    payment_confirmed_at = db.Column(db.DateTime, nullable=True)


class ServiceRecord(db.Model):
    """Classe `ServiceRecord`: representa um registro de serviço realizado,
    incluindo informações sobre o nome do serviço, nome do cliente, equipamento, preço total e custo."""

    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(120), nullable=False)
    client_name = db.Column(db.String(120), nullable=False)
    equipment = db.Column(db.String(120), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    canceled_at = db.Column(db.DateTime, nullable=True)
    delivery_status = db.Column(db.String(30), nullable=False, default='aguardando')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    performed_by = db.relationship('User', foreign_keys=[performed_by_user_id])


class FixedCost(db.Model):
    """Classe `FixedCost`: representa um custo fixo do sistema, como aluguel, salários ou despesas administrativas."""
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MaintenanceTicket(db.Model):
    """Classe `MaintenanceTicket`: representa um ticket de manutenção para equipamentos,
    incluindo informações sobre o cliente, equipamento, descrição do serviço,
    diagnóstico técnico e status do atendimento."""

    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(120), nullable=False)
    equipment = db.Column(db.String(120), nullable=False)
    service_description = db.Column(db.String(180), nullable=False)
    client_phone = db.Column(db.String(30), nullable=True)
    customer_report = db.Column(db.Text, nullable=True)
    technical_diagnosis = db.Column(db.Text, nullable=True)
    observations = db.Column(db.Text, nullable=True)
    checklist_json = db.Column(db.Text, nullable=True)
    parts_json = db.Column(db.Text, nullable=True)
    labor_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    entry_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    exit_date = db.Column(db.DateTime, nullable=True)
    waiting_parts = db.Column(db.Boolean, nullable=False, default=False)
    parts_stock_applied = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(30), nullable=False, default='em_andamento')
    service_record_id = db.Column(db.Integer, db.ForeignKey('service_record.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    service_record = db.relationship('ServiceRecord', foreign_keys=[service_record_id])


class User(db.Model):
    """Classe `User`: representa um usuário do sistema, armazenando informações como nome, email, senha hash e status de administrador."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class StoreSettings(db.Model):
    """Configurações administrativas editáveis para dados institucionais da loja."""

    id = db.Column(db.Integer, primary_key=True)
    store_name = db.Column(db.String(120), nullable=False, default='LojaWeb Tecnologia')
    store_address = db.Column(db.String(255), nullable=False, default='Rua Exemplo, 123 - Centro')
    store_contact = db.Column(db.String(120), nullable=False, default='contato@lojaweb.local')
    cnpj = db.Column(db.String(30), nullable=True)
    pix_key = db.Column(db.String(255), nullable=True)
    pix_receiver_name = db.Column(db.String(25), nullable=False, default='LOJAWEB TECNOLOGIA')
    pix_receiver_city = db.Column(db.String(15), nullable=False, default='Brasilia-DF')
    logo_path = db.Column(db.String(255), nullable=False, default='logo-lojaweb.svg')
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(db.Model):
    """Classe `AuditLog`: representa um registro de auditoria para ações realizadas no sistema, armazenando informações sobre o usuário, ação, detalhes e timestamp."""
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(180), nullable=False)
    details = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class LoginThrottle(db.Model):
    """Classe `LoginThrottle`: representa um registro de tentativas de login bloqueadas,
    armazenando informações sobre o email do usuário, endereço IP e número de tentativas falhas."""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    blocked_until = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

product_service.model = Product
client_service.model = Client


@app.errorhandler(ValueError)
def handle_value_error(exc):
    flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('dashboard'))


@app.errorhandler(Exception)
def handle_generic_error(exc):
    """Função `handle_generic_error`: captura erros inesperados,
    registra detalhes para análise e informa o usuário de forma genérica,
    evitando exposição de informações sensíveis."""

    app.logger.exception('Erro inesperado: %s', exc)
    flash('Ocorreu um erro inesperado. Tente novamente.', 'danger')
    return redirect(request.referrer or url_for('dashboard'))


def _client_ip():
    """Função `_client_ip`: obtém o endereço IP do cliente, considerando possíveis proxies reversos e garantindo um fallback seguro."""

    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _get_or_create_throttle(email: str, ip_address: str):
    """Função `_get_or_create_throttle`: recupera ou cria um registro de bloqueio de login para um email e IP específicos,
     facilitando o controle de tentativas de login e bloqueios temporários."""

    throttle = LoginThrottle.query.filter_by(email=email, ip_address=ip_address).first()
    if throttle:
        return throttle
    throttle = LoginThrottle(email=email, ip_address=ip_address, failed_attempts=0)
    db.session.add(throttle)
    db.session.flush()
    return throttle


def _recent_failed_attempts(email: str, ip_address: str, window_minutes: int):
    """Função `_recent_failed_attempts`: calcula o número de tentativas de login falhas recentes para um email e IP específicos,
     permitindo implementar lógica de bloqueio baseada em um período de tempo definido."""

    window_start = datetime.utcnow() - timedelta(minutes=window_minutes)
    email_attempts = db.session.query(db.func.sum(LoginThrottle.failed_attempts)).filter(
        LoginThrottle.email == email,
        LoginThrottle.updated_at >= window_start,
    ).scalar() or 0
    ip_attempts = db.session.query(db.func.sum(LoginThrottle.failed_attempts)).filter(
        LoginThrottle.ip_address == ip_address,
        LoginThrottle.updated_at >= window_start,
    ).scalar() or 0
    return email_attempts, ip_attempts


def _login_required(view):
    """Função `_login_required`: decorador para garantir que apenas usuários autenticados acessem rotas protegidas, redirecionando para a página de login caso contrário."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        """Função `wrapped`: verifica a presença de um usuário autenticado na sessão antes de permitir o acesso à rota protegida."""
        if not session.get('user_id'):
            flash('Faça login para continuar.', 'danger')
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def _current_user():
    """Função `_current_user`: recupera o usuário atual da sessão, se autenticado."""
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)


def _admin_required(view):
    """Garante que somente administradores acessem rotas sensíveis do painel."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        current = _current_user()
        if not current or not current.is_admin:
            flash('Apenas administradores podem acessar esta área.', 'danger')
            return redirect(url_for('dashboard'))
        return view(*args, **kwargs)
    return wrapped


def _branding_upload_dir() -> Path:
    """Retorna e cria o diretório de upload para assets de identidade visual."""
    upload_dir = Path(app.root_path) / app.config['BRANDING_UPLOAD_FOLDER']
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _get_store_settings() -> StoreSettings:
    """Carrega (ou cria) o registro único de configurações da loja."""
    settings = StoreSettings.query.first()
    if settings:
        return settings

    settings = StoreSettings(
        store_name='LojaWeb Tecnologia',
        store_address='Rua Exemplo, 123 - Centro',
        store_contact='contato@lojaweb.local',
        cnpj=None,
        pix_key=app.config.get('PIX_KEY', '') or None,
        pix_receiver_name=_sanitize_pix_text(app.config.get('PIX_RECEIVER_NAME', 'LOJAWEB TECNOLOGIA'), max_len=25) or 'LOJAWEB TECNOLOGIA',
        pix_receiver_city=_sanitize_pix_text(app.config.get('PIX_RECEIVER_CITY', 'SAO PAULO'), max_len=15) or 'SAO PAULO',
        logo_path='logo-lojaweb.svg',
    )
    db.session.add(settings)
    db.session.commit()
    return settings


def _apply_store_settings_to_runtime(settings: StoreSettings):
    """Sincroniza dados de Pix editáveis no painel com as configs usadas em runtime."""
    app.config['PIX_KEY'] = (settings.pix_key or '').strip()
    app.config['PIX_RECEIVER_NAME'] = (settings.pix_receiver_name or '').strip() or 'LOJAWEB TECNOLOGIA'
    app.config['PIX_RECEIVER_CITY'] = (settings.pix_receiver_city or '').strip() or 'SAO PAULO'


def _base_template_context() -> dict:
    """Fornece contexto global de branding para navbar/sidebar e demais templates."""
    settings = _get_store_settings()
    _apply_store_settings_to_runtime(settings)
    return {
        'ui_store_name': settings.store_name,
        'ui_store_logo': settings.logo_path,
        'ui_store_has_cnpj': bool((settings.cnpj or '').strip()),
        'user_name': _current_user().name if _current_user() else None,
    }


def _build_reset_token(email: str):
    """Função `_build_reset_token`: gera um token seguro para redefinição de senha."""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])


def _read_reset_token(token: str, max_age_seconds: int = 3600):
    """Função `_read_reset_token`: lê e valida um token de redefinição de senha, garantindo que seja válido e não expirado."""
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=max_age_seconds)


def _log_audit(action: str, details: str):
    """Função `_log_audit`: registra uma ação de auditoria no banco de dados."""
    user = _current_user()
    db.session.add(AuditLog(user_name=user.name if user else 'Sistema', action=action, details=details))


def _parse_sale_items(form):
    """
    Função `_parse_sale_items`: processa os dados do formulário para itens de venda,
    validando e estruturando as informações de cada item (produto ou serviço)
    para posterior criação dos registros de venda e itens associados.
    
    """

    raw_types = form.getlist('item_type[]')
    raw_product_ids = form.getlist('item_product_id[]')
    raw_service_ids = form.getlist('item_service_id[]')
    raw_descriptions = form.getlist('item_description[]')
    raw_quantities = form.getlist('item_quantity[]')
    raw_unit_prices = form.getlist('item_unit_price[]')
    raw_unit_costs = form.getlist('item_unit_cost[]')

    max_len = max(
        len(raw_types),
        len(raw_product_ids),
        len(raw_service_ids),
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
        service_id_raw = (raw_service_ids[idx] if idx < len(raw_service_ids) else '').strip()
        description = (raw_descriptions[idx] if idx < len(raw_descriptions) else '').strip()
        qty_raw = (raw_quantities[idx] if idx < len(raw_quantities) else '').strip()
        unit_price_raw = (raw_unit_prices[idx] if idx < len(raw_unit_prices) else '').strip()
        unit_cost_raw = (raw_unit_costs[idx] if idx < len(raw_unit_costs) else '').strip()

        if not any([product_id_raw, service_id_raw, description, qty_raw, unit_price_raw, unit_cost_raw]):
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
            'service_record_id': None,
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
        elif service_id_raw:
            try:
                item['service_record_id'] = int(service_id_raw)
            except ValueError as exc:
                raise ValueError(f'Serviço inválido na linha {idx + 1}.') from exc

        if not item['description']:
            item['description'] = 'Item sem descrição'

        item['line_total'] = (item['unit_price'] * Decimal(item['quantity'])).quantize(Decimal('0.01'))
        items.append(item)

    if not items:
        raise ValueError('Adicione ao menos um item (produto ou serviço) na venda.')

    return items


def _save_product_photo(file_storage):
    """
    Função `_save_product_photo`: processa
    o upload de uma foto de produto, validando
    o formato, salvando o arquivo e retornando
    a URL relativa para armazenamento no banco de dados.
    """
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
    """Função `_remove_product_photo_files`: remove arquivos de fotos de produto do sistema, garantindo que apenas arquivos dentro do diretório designado sejam afetados."""
    if not photo_url or not photo_url.startswith('/static/uploads/products/'):
        return

    relative = photo_url.removeprefix('/static/')
    original_path = Path(app.root_path) / 'static' / relative
    if original_path.exists():
        original_path.unlink()


def _collect_selected_piece_inputs(form_data, prefix=''):
    """Função `_collect_selected_piece_inputs`: processa os dados do formulário para coletar as peças selecionadas e itens personalizados,
    estruturando as informações para posterior criação da montagem de computador."""
    selected_piece_ids = []
    custom_items = []

    def _safe_qty(raw_value):
        """Função `_safe_qty`: converte a quantidade de entrada em um inteiro seguro, garantindo que seja pelo menos 1 e tratando valores inválidos."""
        try:
            qty = int(raw_value)
        except (TypeError, ValueError):
            return 1
        return max(1, qty)

    for slot_key, _, allow_multiple in COMPONENT_SLOTS:
        if allow_multiple:
            stock_ids = form_data.getlist(f'{prefix}{slot_key}_stock_ids[]')
            entries = form_data.getlist(f'{prefix}{slot_key}_entries[]')
            qtys = form_data.getlist(f'{prefix}{slot_key}_qtys[]')
            custom_costs = form_data.getlist(f'{prefix}{slot_key}_custom_costs[]')

            for stock_id, entry, qty, custom_cost in zip(stock_ids, entries, qtys, custom_costs):
                qty_value = _safe_qty(qty)
                if stock_id:
                    selected_piece_ids.extend([int(stock_id)] * qty_value)
                    continue

                entry = (entry or '').strip()
                if entry and qty_value > 0:
                    custom_items.append({
                        'slot_key': slot_key,
                        'name': entry,
                        'qty': qty_value,
                        'unit_cost': Decimal(custom_cost or '0'),
                    })
        else:
            stock_id = form_data.get(f'{prefix}slot_{slot_key}_stock_id')
            if stock_id:
                selected_piece_ids.append(int(stock_id))
                continue

            custom_name = (form_data.get(f'{prefix}slot_{slot_key}_entry') or '').strip()
            custom_cost = form_data.get(f'{prefix}slot_{slot_key}_cost') or '0'
            if custom_name:
                custom_items.append({
                    'slot_key': slot_key,
                    'name': custom_name,
                    'qty': 1,
                    'unit_cost': Decimal(custom_cost),
                })

    return selected_piece_ids, custom_items


def _read_optional_service_costs(form_data):
    """Função `_read_optional_service_costs`: lê os custos opcionais de serviços técnicos do formulário, garantindo que sejam valores numéricos válidos e não negativos."""
    def _to_cost(field_name):
        """Função `_to_cost`: converte o valor bruto de entrada em um Decimal seguro, tratando casos de valores ausentes, inválidos ou negativos."""
        raw = (form_data.get(field_name) or '0').strip()
        value = Decimal(raw or '0')
        if value < 0:
            raise ValueError('Valores de serviços técnicos devem ser maiores ou iguais a zero.')
        return value.quantize(Decimal('0.01'))

    return {
        'bios_service_cost': _to_cost('bios_service_cost'),
        'stress_test_cost': _to_cost('stress_test_cost'),
        'os_install_cost': _to_cost('os_install_cost'),
    }


def _calculate_assembly_suggested_pieces_total(piece_counter, pieces_by_id, custom_items=None, markup=Decimal('0.25')):
    """Função `_calculate_assembly_suggested_pieces_total`: calcula o preço sugerido total de peças e itens personalizados em uma montagem de computador, aplicando uma margem de lucro."""
    suggested_total = Decimal('0.00')
    custom_items = custom_items or []

    for piece_id, qty in piece_counter.items():
        piece = pieces_by_id.get(piece_id)
        if not piece:
            continue
        suggested_unit = calcular_preco_sugerido(Decimal(piece.price or 0), markup=markup)
        suggested_total += Decimal(qty) * suggested_unit

    for custom_item in custom_items:
        suggested_unit = calcular_preco_sugerido(Decimal(custom_item['unit_cost'] or 0), markup=markup)
        suggested_total += Decimal(custom_item['qty']) * suggested_unit

    return suggested_total.quantize(Decimal('0.01'))


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
    bios_service_cost=Decimal('0.00'),
    stress_test_cost=Decimal('0.00'),
    os_install_cost=Decimal('0.00'),
    apply_price_suggestion=False,
    current_user=None,
):
    """
    Função `_build_computer_with_parts`: constrói
    ou atualiza um produto do tipo computador com
    base nas peças selecionadas, itens personalizados
    e fotos enviadas, calculando os custos totais e 
    preços sugeridos, e registrando a montagem no banco de dados.
    """
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
            custo_total += Decimal(qty) * Decimal(piece.price or 0)

        for custom_item in custom_items:
            if custom_item['unit_cost'] < 0:
                raise ValueError(f"Custo inválido para peça personalizada: {custom_item['name']}")
            custo_total += Decimal(custom_item['qty']) * custom_item['unit_cost']

        custo_pecas = custo_total.quantize(Decimal('0.01'))
        technical_services_cost = (bios_service_cost + stress_test_cost + os_install_cost).quantize(Decimal('0.01'))
        custo_total = (custo_pecas + technical_services_cost).quantize(Decimal('0.01'))
        preco_sugerido = _calculate_assembly_suggested_pieces_total(piece_counter, pieces_by_id, custom_items)

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
        subtotal_pecas = preco_sugerido if apply_price_suggestion else custo_pecas
        preco_final = (preco_original + subtotal_pecas + technical_services_cost).quantize(Decimal('0.01'))
        if create_stock_item:
            computer.price = preco_final

        montagem = ComputerAssembly(
            id_computador=computer.id,
            nome_referencia=computer_name,
            preco_original=preco_original,
            custo_total=custo_total,
            preco_sugerido=preco_sugerido,
            apply_price_suggestion=apply_price_suggestion,
            technical_notes=(technical_notes or '').strip() or None,
            bios_updated=bios_updated,
            bios_service_cost=bios_service_cost,
            stress_test_done=stress_test_done,
            stress_test_cost=stress_test_cost,
            os_installed=os_installed,
            os_install_cost=os_install_cost,
            performed_by_user_id=current_user.id if current_user else None,
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
        'apply_price_suggestion': apply_price_suggestion,
        'new_photo_urls': uploaded_photo_urls,
        'previous_photo_urls': previous_photo_urls,
        'computer_id': computer.id,
    }


COMPONENT_SLOTS = [
    ('gabinete', 'Gabinete', False),
    ('fans', 'Fans', False),
    ('placa_mae', 'Placa-mãe', False),
    ('placa_video', 'Placa de Vídeo', False),
    ('processador', 'Processador', False),
    ('memoria_ram', 'Memória RAM', True),
    ('armazenamento', 'Armazenamento', True),
    ('fonte', 'Fonte', False),
    ('perifericos', 'Periféricos', False),
]

COMPONENT_CLASS_LABELS = dict((slot_key, slot_label) for slot_key, slot_label, _ in COMPONENT_SLOTS)


PAYMENT_METHODS = [
    ('credito', 'Crédito'),
    ('dinheiro', 'Dinheiro'),
    ('pix', 'Pix'),
    ('boleto', 'Boleto'),
]

PAYMENT_METHOD_LABELS = dict(PAYMENT_METHODS)

SERVICE_DELIVERY_STATUS_LABELS = {
    'aguardando': 'Aguardando retirada',
    'entregue': 'Entregue ao cliente',
    'desistencia': 'Desistência do cliente',
}

MAINTENANCE_STATUS_LABELS = {
    'aguardando_pecas': 'Aguardando peças',
    'em_analise': 'Em análise/Bancada',
    'pronto_retirada': 'Pronto para retirada',
    'cancelado': 'Cancelado',
    # aliases legados
    'em_andamento': 'Em análise/Bancada',
    'concluido': 'Concluído (retirado e pago)',
}

MAINTENANCE_STATUS_OPTIONS = [
    ('aguardando_pecas', 'Aguardando peças'),
    ('em_analise', 'Em análise/Bancada'),
    ('pronto_retirada', 'Pronto para retirada'),
    ('cancelado', 'Cancelado'),
]


def _normalize_maintenance_status(status: str) -> str:
    """Função `_normalize_maintenance_status`: normaliza status legados para os novos valores."""
    value = (status or '').strip()
    if value == 'em_andamento':
        return 'em_analise'
    if value == 'concluido':
        return 'concluido'
    return value if value in dict(MAINTENANCE_STATUS_OPTIONS) else 'em_analise'


def _to_decimal(value, default: str = '0') -> Decimal:
    """Converte valores variados para Decimal sem quebrar em dados legados."""
    raw = str(value if value is not None else default).strip().replace(',', '.')
    if not raw:
        raw = default
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(default)

    if not parsed.is_finite():
        return Decimal(default)
    return parsed


def _to_money_decimal(value, default: str = '0.00') -> Decimal:
    """Normaliza entradas monetárias pt-BR para Decimal com 2 casas."""
    parsed = _to_decimal(value, default=default)
    return parsed.quantize(Decimal('0.01'))


def _sanitize_pix_text(value: str, *, max_len: int) -> str:
    normalized = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode('ascii')
    normalized = re.sub(r'[^A-Za-z0-9 ]+', '', normalized).strip().upper()
    return normalized[:max_len]


def _emv_field(field_id: str, value: str) -> str:
    return f"{field_id}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
    crc = 0xFFFF
    data = payload.encode('utf-8')
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _build_pix_payload(*, amount: Decimal, txid: str) -> str | None:
    pix_key = app.config.get('PIX_KEY', '')
    if not pix_key:
        return None

    merchant_name = _sanitize_pix_text(app.config.get('PIX_RECEIVER_NAME', 'LOJAWEB TECNOLOGIA'), max_len=25) or 'LOJAWEB'
    merchant_city = _sanitize_pix_text(app.config.get('PIX_RECEIVER_CITY', 'SAO PAULO'), max_len=15) or 'SAO PAULO'
    txid_clean = _sanitize_pix_text(txid, max_len=25) or 'LOJAWEB'

    merchant_account_info = ''.join([
        _emv_field('00', 'BR.GOV.BCB.PIX'),
        _emv_field('01', pix_key),
    ])

    amount_str = f"{Decimal(amount or 0).quantize(Decimal('0.01')):.2f}"

    payload_without_crc = ''.join([
        _emv_field('00', '01'),
        _emv_field('26', merchant_account_info),
        _emv_field('52', '0000'),
        _emv_field('53', '986'),
        _emv_field('54', amount_str),
        _emv_field('58', 'BR'),
        _emv_field('59', merchant_name),
        _emv_field('60', merchant_city),
        _emv_field('62', _emv_field('05', txid_clean)),
        '6304',
    ])

    crc = _crc16_ccitt(payload_without_crc)
    return f"{payload_without_crc}{crc}"


def _build_pix_qr_url(payload: str | None) -> str | None:
    if not payload:
        return None
    return f"https://quickchart.io/qr?size=220&text={quote(payload, safe='')}"


def _pisa_link_callback(uri: str, _rel: str | None = None) -> str:
    """Resolve arquivos locais (CSS/imagens) para o xhtml2pdf."""
    if not uri:
        return uri

    if uri.startswith('http://') or uri.startswith('https://') or uri.startswith('data:'):
        return uri

    if uri.startswith('/static/'):
        return str(Path(app.root_path) / uri.lstrip('/'))

    if uri.startswith('static/'):
        return str(Path(app.root_path) / uri)

    return str((Path(app.root_path) / uri).resolve())


def _load_json_list(raw_value: str | None) -> list[dict]:
    """Carrega JSON de lista e retorna apenas itens-objeto válidos."""
    if not raw_value:
        return []
    try:
        loaded = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def _build_maintenance_parts_items(form_data, *, allow_single_fallback: bool = False) -> list[dict]:
    """Normaliza peças selecionadas no formulário de manutenção."""
    part_ids = form_data.getlist('maintenance_part_id[]')
    part_qtys = form_data.getlist('maintenance_part_qty[]')

    if allow_single_fallback and not part_ids and not part_qtys:
        part_ids = [(form_data.get('maintenance_part_id') or '').strip()]
        part_qtys = [(form_data.get('maintenance_part_qty') or '1').strip()]

    parts_items = []
    for idx, raw_part_id in enumerate(part_ids):
        part_id_raw = (raw_part_id or '').strip()
        if not part_id_raw or not part_id_raw.isdigit():
            continue

        product = Product.query.get(int(part_id_raw))
        if not product or product.category != 'Peça':
            continue

        raw_qty = part_qtys[idx] if idx < len(part_qtys) else '1'
        try:
            part_qty = max(1, int((raw_qty or '1').strip()))
        except ValueError:
            part_qty = 1

        parts_items.append({
            'product_id': product.id,
            'name': product.name,
            'quantity': part_qty,
            'unit_price': str(Decimal(product.price or 0).quantize(Decimal('0.01'))),
        })

    return parts_items




def _generate_piece_name(component_class: str | None, form_data) -> str:
    """Função `_generate_piece_name`: gera o nome de uma peça com base em dados do formulário."""
    class_label = COMPONENT_CLASS_LABELS.get(component_class, 'Peça')

    def clean(field: str) -> str:
        """Função `clean`: limpa e normaliza um campo de entrada, garantindo que seja uma string sem espaços extras."""
        return (form_data.get(field) or '').strip()

    specs: list[str] = []
    if component_class == 'memoria_ram':
        specs = [clean('ram_brand'), clean('ram_size'), clean('ram_ddr'), clean('ram_frequency')]
    elif component_class == 'processador':
        specs = [clean('cpu_manufacturer'), clean('cpu_model')]
    elif component_class == 'placa_mae':
        specs = [clean('motherboard_brand'), clean('motherboard_model'), clean('motherboard_socket'), clean('motherboard_chipset')]
    elif component_class == 'placa_video':
        specs = [clean('gpu_brand'), clean('gpu_memory'), clean('gpu_manufacturer')]
    elif component_class == 'armazenamento':
        specs = [clean('storage_brand'), clean('storage_type'), clean('storage_capacity')]
    elif component_class == 'fonte':
        specs = [clean('psu_brand'), clean('psu_watts')]
    elif component_class == 'gabinete':
        specs = [clean('cabinet_brand'), clean('cabinet_description')]
    elif component_class == 'fans':
        specs = [clean('fan_brand'), clean('fan_description')]
    elif component_class == 'perifericos':
        specs = [
            clean('peripheral_mouse'),
            clean('peripheral_keyboard'),
            clean('peripheral_monitor'),
            clean('peripheral_power_cable'),
            clean('peripheral_hdmi_cable'),
        ]

    specs = [item for item in specs if item]
    serial = clean('serial_number')

    if specs:
        generated = f"{class_label} {' '.join(specs)}"
    else:
        generated = class_label

    if serial:
        generated = f"{generated} SN:{serial}"

    return generated[:120].strip()

DEFAULT_MAINTENANCE_CHECKLIST = [
    'Limpeza interna',
    'Troca de pasta térmica',
    'Teste de stress',
    'Instalação de sistema operacional',
]


def _ensure_service_record_from_ticket(ticket: 'MaintenanceTicket', current_user: 'User | None'):
    """
    Função `_ensure_service_record_from_ticket`:
    garante que um registro de serviço seja criado
    para uma OS de manutenção, calculando os custos
    totais com base nas peças e mão de obra, e 
    registrando as informações relevantes do atendimento.
    """
    if ticket.service_record_id:
        return

    parts_items = _load_json_list(ticket.parts_json)

    parts_total = Decimal('0')
    parts_desc = []
    for part in parts_items:
        if not isinstance(part, dict):
            continue
        qty = _to_decimal(part.get('quantity') or 1, default='1')
        unit = _to_decimal(part.get('unit_price') or 0)
        qty_int = max(1, int(qty)) if qty > 0 else 1
        unit_value = unit if unit >= 0 else Decimal('0')
        parts_total += Decimal(qty_int) * unit_value
        parts_desc.append(f"{part.get('name', 'Peça')} x{qty_int}")

    labor = Decimal(ticket.labor_cost or 0)
    total_price = (labor + parts_total).quantize(Decimal('0.01'))

    notes_chunks = []
    if ticket.customer_report:
        notes_chunks.append(f"Relato: {ticket.customer_report}")
    if ticket.technical_diagnosis:
        notes_chunks.append(f"Diagnóstico: {ticket.technical_diagnosis}")
    if ticket.observations:
        notes_chunks.append(f"Observações: {ticket.observations}")
    if parts_desc:
        notes_chunks.append('Peças: ' + ', '.join(parts_desc))

    service = ServiceRecord(
        service_name=f"OS #{ticket.id} - {ticket.service_description}",
        client_name=ticket.client_name,
        equipment=ticket.equipment,
        total_price=total_price,
        discount_amount=Decimal('0.00'),
        cost=parts_total.quantize(Decimal('0.01')),
        notes=' | '.join(notes_chunks) or f"Finalização automática da OS #{ticket.id}.",
        performed_by_user_id=current_user.id if current_user else None,
    )
    db.session.add(service)
    db.session.flush()
    ticket.service_record_id = service.id


def _sync_service_record_from_ticket(ticket: 'MaintenanceTicket'):
    """Função `_sync_service_record_from_ticket`: 
    tualiza o registro de serviço associado a uma 
    OS de manutenção, recalculando os custos totais 
    com base nas peças e mão de obra, e atualizando as
    informações relevantes do atendimento."""

    if not ticket.service_record_id:
        return

    service = ServiceRecord.query.get(ticket.service_record_id)
    if not service:
        return

    parts_items = _load_json_list(ticket.parts_json)
    parts_total = Decimal('0.00')
    parts_desc = []

    for part in parts_items:
        qty = max(1, int(_to_decimal(part.get('quantity') or 1, default='1')))
        unit = _to_decimal(part.get('unit_price') or 0)
        unit_value = unit if unit >= 0 else Decimal('0')
        parts_total += Decimal(qty) * unit_value
        parts_desc.append(f"{part.get('name', 'Peça')} x{qty}")

    labor = Decimal(ticket.labor_cost or 0).quantize(Decimal('0.01'))
    service.service_name = f"OS #{ticket.id} - {ticket.service_description}"
    service.client_name = ticket.client_name
    service.equipment = ticket.equipment
    service.cost = parts_total.quantize(Decimal('0.01'))
    service.total_price = (parts_total + labor).quantize(Decimal('0.01'))

    notes_chunks = []
    if ticket.customer_report:
        notes_chunks.append(f"Relato: {ticket.customer_report}")
    if ticket.technical_diagnosis:
        notes_chunks.append(f"Diagnóstico: {ticket.technical_diagnosis}")
    if ticket.observations:
        notes_chunks.append(f"Observações: {ticket.observations}")
    if parts_desc:
        notes_chunks.append('Peças: ' + ', '.join(parts_desc))

    if notes_chunks:
        service.notes = ' | '.join(notes_chunks)


def _apply_ticket_parts_stock(ticket: 'MaintenanceTicket'):
    """Função `_apply_ticket_parts_stock`: aplica a redução 
    de estoque para as peças utilizadas em uma OS de manutenção,
     garantindo que o estoque seja atualizado corretamente e 
     evitando múltiplas aplicações."""

    if ticket.parts_stock_applied:
        return

    parts_items = _load_json_list(ticket.parts_json)

    if not parts_items:
        ticket.parts_stock_applied = True
        return

    required_by_product_id: dict[int, int] = {}
    for part in parts_items:
        if not isinstance(part, dict):
            continue
        product_id = part.get('product_id')
        if product_id is None:
            continue
        try:
            product_id_int = int(product_id)
        except (TypeError, ValueError):
            continue

        try:
            qty = int(part.get('quantity') or 1)
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, qty)
        required_by_product_id[product_id_int] = required_by_product_id.get(product_id_int, 0) + qty

    if not required_by_product_id:
        ticket.parts_stock_applied = True
        return

    products = Product.query.filter(Product.id.in_(required_by_product_id.keys())).all()
    products_by_id = {product.id: product for product in products}

    missing_ids = sorted(set(required_by_product_id.keys()) - set(products_by_id.keys()))
    if missing_ids:
        raise ValueError('Uma ou mais peças da OS não existem mais no estoque.')

    for product_id, qty in required_by_product_id.items():
        product = products_by_id[product_id]
        if int(product.stock or 0) < qty:
            raise ValueError(f'Estoque insuficiente para a peça "{product.name}". Necessário: {qty}, disponível: {product.stock}.')

    for product_id, qty in required_by_product_id.items():
        product = products_by_id[product_id]
        product.stock = int(product.stock or 0) - qty

    ticket.parts_stock_applied = True


def _parts_quantity_map(parts_items: list[dict] | None) -> dict[int, int]:
    """Função `_parts_quantity_map`: constrói um mapa de quantidade por ID de produto a partir da lista de peças, facilitando o cálculo de deltas de estoque."""
    quantity_map: dict[int, int] = {}
    for part in parts_items or []:
        if not isinstance(part, dict):
            continue
        product_id = part.get('product_id')
        if product_id is None:
            continue
        try:
            product_id_int = int(product_id)
        except (TypeError, ValueError):
            continue

        try:
            qty = int(part.get('quantity') or 1)
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, qty)
        quantity_map[product_id_int] = quantity_map.get(product_id_int, 0) + qty
    return quantity_map


def _sync_ticket_parts_stock_delta(previous_parts_items: list[dict], current_parts_items: list[dict]):
    """Função `_sync_ticket_parts_stock_delta`: 
    Calcula o delta de estoque entre as peças anteriores e atuais de uma OS de manutenção, aplicando as alterações necessárias no estoque dos produtos envolvidos."""
    previous_map = _parts_quantity_map(previous_parts_items)
    current_map = _parts_quantity_map(current_parts_items)
    all_product_ids = set(previous_map.keys()) | set(current_map.keys())
    if not all_product_ids:
        return

    products = Product.query.filter(Product.id.in_(all_product_ids)).all()
    products_by_id = {product.id: product for product in products}

    missing_ids = sorted(all_product_ids - set(products_by_id.keys()))
    if missing_ids:
        raise ValueError('Uma ou mais peças da OS não existem mais no estoque.')

    deltas: dict[int, int] = {}
    for product_id in all_product_ids:
        delta = current_map.get(product_id, 0) - previous_map.get(product_id, 0)
        if delta:
            deltas[product_id] = delta

    for product_id, delta in deltas.items():
        if delta <= 0:
            continue
        product = products_by_id[product_id]
        if int(product.stock or 0) < delta:
            raise ValueError(f'Estoque insuficiente para a peça "{product.name}". Necessário: {delta}, disponível: {product.stock}.')

    for product_id, delta in deltas.items():
        product = products_by_id[product_id]
        product.stock = int(product.stock or 0) - delta



@app.context_processor
def inject_base_context():
    """Injeta dados visuais da loja em todos os templates renderizados."""
    return _base_template_context()


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Função `login`: 
    Gerencia o processo de autenticação de usuários, 
    incluindo verificação de credenciais, aplicação de 
    políticas de bloqueio por tentativas falhas, 
    e manutenção da sessão do usuário."""
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

        max_attempts = app.config['LOGIN_THROTTLE_MAX_ATTEMPTS']
        block_minutes = app.config['LOGIN_THROTTLE_BLOCK_MINUTES']
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            throttle.failed_attempts += 1
            throttle.updated_at = datetime.utcnow()
            email_attempts, ip_attempts = _recent_failed_attempts(email, ip_address, block_minutes)
            if email_attempts >= max_attempts or ip_attempts >= max_attempts:
                block_until = now + timedelta(minutes=block_minutes)
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

        LoginThrottle.query.filter(
            (LoginThrottle.email == email) | (LoginThrottle.ip_address == ip_address)
        ).update(
            {
                LoginThrottle.failed_attempts: 0,
                LoginThrottle.blocked_until: None,
                LoginThrottle.updated_at: datetime.utcnow(),
            },
            synchronize_session=False,
        )
        session.permanent = remember_me
        session['user_id'] = user.id
        session['user_name'] = user.name
        db.session.commit()
        flash('Login realizado com sucesso!', 'success')
        return redirect(url_for('dashboard'))
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Função `logout`: 
    Encerra a sessão do usuário, limpando os dados de autenticação e redirecionando para a página de login."""
    session.clear()
    flash('Sessão encerrada.', 'success')
    return redirect(url_for('login'))


@app.route('/usuarios', methods=['GET', 'POST'])
@_login_required
@_admin_required
def usuarios():
    """Função `usuarios`: 
    Gerencia a visualização e criação de usuários, 
    permitindo que administradores vejam a lista de 
    usuários existentes e adicionem novos usuários ao
    sistema, com validação de dados e feedback apropriado."""

    current = _current_user()

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
@_admin_required
def editar_usuario(user_id: int):
    """Função `editar_usuario`: permite que administradores editem os detalhes de um usuário existente,"""
    current = _current_user()

    user = User.query.get_or_404(user_id)
    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    is_admin = request.form.get('is_admin') == 'on'
    new_password = request.form.get('password') or ''

    if not name or not email:
        flash('Nome e e-mail são obrigatórios para edição.', 'danger')
        return redirect(url_for('usuarios'))

    if new_password and len(new_password) < 6:
        flash('A nova senha deve conter ao menos 6 caracteres.', 'danger')
        return redirect(url_for('usuarios'))

    duplicated = User.query.filter(User.email == email, User.id != user.id).first()
    if duplicated:
        flash('Já existe outro usuário com este e-mail.', 'danger')
        return redirect(url_for('usuarios'))

    user.name = name
    user.email = email
    user.is_admin = is_admin
    if new_password:
        user.password_hash = generate_password_hash(new_password)
    _log_audit('Edição de usuário', f'Usuário {current.name} editou o cadastro de {user.name} ({user.email}).')
    db.session.commit()
    flash('Usuário atualizado com sucesso!', 'success')
    return redirect(url_for('usuarios'))


@app.route('/usuarios/<int:user_id>/remover', methods=['POST'])
@_login_required
@_admin_required
def remover_usuario(user_id: int):
    """Função `remover_usuario`: permite que administradores removam um usuário existente,
     garantindo que um usuário não possa remover a si mesmo e registrando a ação para auditoria."""
    current = _current_user()

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




@app.route('/admin')
@_login_required
@_admin_required
def admin_panel():
    """Renderiza painel administrativo centralizando configurações da loja e ações críticas."""
    settings = _get_store_settings()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_panel.html', settings=settings, users=users)


@app.route('/admin/configuracoes', methods=['POST'])
@_login_required
@_admin_required
def salvar_configuracoes_admin():
    """Persiste configurações de identidade visual, dados da loja e chave Pix."""
    settings = _get_store_settings()

    settings.store_name = (request.form.get('store_name') or '').strip() or settings.store_name
    settings.store_address = (request.form.get('store_address') or '').strip() or settings.store_address
    settings.store_contact = (request.form.get('store_contact') or '').strip() or settings.store_contact
    settings.cnpj = (request.form.get('cnpj') or '').strip() or None
    settings.pix_key = (request.form.get('pix_key') or '').strip() or None

    pix_receiver_name = _sanitize_pix_text(request.form.get('pix_receiver_name') or settings.store_name, max_len=25)
    pix_receiver_city = _sanitize_pix_text(request.form.get('pix_receiver_city') or 'SAO PAULO', max_len=15)
    settings.pix_receiver_name = pix_receiver_name or 'LOJAWEB TECNOLOGIA'
    settings.pix_receiver_city = pix_receiver_city or 'SAO PAULO'

    logo_file = request.files.get('store_logo')
    if logo_file and logo_file.filename:
        filename = secure_filename(logo_file.filename)
        ext = Path(filename).suffix.lower()
        allowed = {'.png', '.jpg', '.jpeg', '.svg', '.webp'}
        if ext not in allowed:
            flash('Formato de logo inválido. Use PNG, JPG, SVG ou WEBP.', 'danger')
            return redirect(url_for('admin_panel'))

        final_name = f'brand-logo{ext}'
        logo_path = _branding_upload_dir() / final_name
        logo_file.save(logo_path)
        settings.logo_path = f'uploads/branding/{final_name}'

    _apply_store_settings_to_runtime(settings)
    _log_audit('Configurações administrativas', f'Usuário {_current_user().name} atualizou os dados da loja e branding.')
    db.session.commit()
    flash('Configurações administrativas salvas com sucesso.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/limpar-clientes', methods=['POST'])
@_login_required
@_admin_required
def limpar_clientes_admin():
    """Remove todos os clientes cadastrados após confirmação explícita no formulário."""
    confirmation = (request.form.get('confirm_clients') or '').strip().upper()
    if confirmation != 'LIMPAR CLIENTES':
        flash('Confirmação inválida para limpeza de clientes.', 'danger')
        return redirect(url_for('admin_panel'))

    total = Client.query.count()
    Client.query.delete()
    _log_audit('Limpeza de clientes', f'Usuário {_current_user().name} removeu {total} cliente(s).')
    db.session.commit()
    flash(f'{total} cliente(s) removido(s) com sucesso.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/limpar-estoque', methods=['POST'])
@_login_required
@_admin_required
def limpar_estoque_admin():
    """Executa limpeza de estoque apenas quando a frase de verificação for confirmada."""
    verification_phrase = (request.form.get('stock_verification') or '').strip().upper()
    if verification_phrase != 'LIMPAR ESTOQUE':
        flash('Verificação inválida. Digite "LIMPAR ESTOQUE" para confirmar.', 'danger')
        return redirect(url_for('admin_panel'))

    products = Product.query.filter(Product.category != 'Serviço').all()
    changed = 0
    for product in products:
        if int(product.stock or 0) != 0:
            product.stock = 0
            changed += 1

    _log_audit('Limpeza de estoque', f'Usuário {_current_user().name} zerou o estoque de {changed} produto(s).')
    db.session.commit()
    flash(f'Estoque zerado para {changed} produto(s).', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/imprimir/<string:tipo>/<int:record_id>')
@_login_required
def imprimir(tipo: str, record_id: int):
    """Gera documentos de impressão com dados operacionais e branding configurável."""
    assembly_data = None
    settings = _get_store_settings()
    if tipo == 'venda':
        data = Sale.query.get_or_404(record_id)
        sale_items = data.items or []
        sale_charges = Charge.query.filter_by(sale_id=data.id).order_by(Charge.id.asc()).all()
        charge_status_labels = {
            'confirmado': 'Pago',
            'recebido': 'Pago',
            'parcial': 'Parcial',
            'atrasado': 'Pendente',
            'vencido': 'Pendente',
            'pendente': 'Pendente',
            'cancelado': 'Cancelado',
        }
        payment_status_label = 'Pendente'
        active_sale_charges = [charge for charge in sale_charges if charge.status != 'cancelado']
        if active_sale_charges and all(_charge_balance(charge) <= 0 for charge in active_sale_charges):
            payment_status_label = 'Pago'
        elif any(Decimal(charge.amount_paid or 0) > 0 for charge in active_sale_charges):
            payment_status_label = 'Parcial'

        payment_lines = []
        for charge in sale_charges:
            charge_total = _charge_total_amount(charge)
            charge_paid = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
            installments = _charge_installments(charge)
            installment_lines = []
            if installments:
                for installment in installments:
                    installment_amount = Decimal(installment.amount or 0).quantize(Decimal('0.01'))
                    installment_paid = Decimal(installment.amount_paid or 0).quantize(Decimal('0.01'))
                    installment_lines.append({
                        'number': installment.installment_number,
                        'due_date': installment.due_date,
                        'amount': installment_amount,
                        'amount_paid': installment_paid,
                        'status_label': 'Pago' if installment_paid >= installment_amount else 'Pendente',
                    })
            elif charge.is_installment and (charge.installment_count or 1) > 1:
                base_due = charge.due_date or data.created_at.date()
                base_amount = Decimal(charge.installment_value or 0).quantize(Decimal('0.01'))
                for number in range(1, (charge.installment_count or 1) + 1):
                    installment_due = base_due + timedelta(days=(number - 1) * 30)
                    installment_lines.append({
                        'number': number,
                        'due_date': installment_due,
                        'amount': base_amount,
                        'amount_paid': Decimal('0.00'),
                        'status_label': 'Pendente',
                    })

            payment_lines.append({
                'method_label': PAYMENT_METHOD_LABELS.get(charge.payment_method, charge.payment_method.title()),
                'status_label': charge_status_labels.get(charge.status, 'Pendente'),
                'due_date': charge.due_date,
                'amount': charge_total,
                'amount_paid': charge_paid,
                'balance': (charge_total - charge_paid).quantize(Decimal('0.01')),
                'installments': installment_lines,
            })

        assembly_data = None
        assembly_product_id = None
        if sale_items:
            for line in sale_items:
                if line.line_type == 'produto' and line.product and line.product.category == 'Computador':
                    assembly_product_id = line.product.id
                    break
        elif data.product and data.product.category == 'Computador':
            assembly_product_id = data.product.id

        if assembly_product_id:
            assembly_data = (
                ComputerAssembly.query
                .filter_by(id_computador=assembly_product_id)
                .order_by(ComputerAssembly.created_at.desc())
                .first()
            )

        sale_line_items = []
        service_receipt_lines = []
        for line in sale_items:
            sale_line_items.append({
                'item': line.description,
                'quantity': line.quantity,
                'unit_price': line.unit_price,
                'total': line.line_total,
            })
            if line.line_type == 'servico' and line.service_record:
                service_receipt_lines.append({
                    'service_name': line.service_record.service_name,
                    'equipment': line.service_record.equipment,
                    'notes': line.service_record.notes or 'Sem observações.',
                    'total_price': Decimal(line.service_record.total_price or 0),
                    'cost': Decimal(line.service_record.cost or 0),
                })

        if not sale_line_items:
            sale_line_items = [{
                'item': data.product.name,
                'quantity': data.quantity,
                'unit_price': data.product.price,
                'total': data.total,
            }]

        assembly_receipt_items = []
        if assembly_data:
            for part in assembly_data.composicao:
                if not part.peca:
                    continue
                assembly_receipt_items.append({
                    'item': part.peca.name,
                    'source_label': 'Estoque',
                    'quantity': part.quantidade_utilizada,
                    'unit_price': Decimal(part.peca.price or 0),
                    'total': Decimal(part.quantidade_utilizada) * Decimal(part.peca.price or 0),
                })
            for custom in assembly_data.custom_parts:
                assembly_receipt_items.append({
                    'item': custom.part_name,
                    'source_label': 'Item personalizado',
                    'quantity': custom.quantity,
                    'unit_price': Decimal(custom.unit_cost or 0),
                    'total': Decimal(custom.quantity) * Decimal(custom.unit_cost or 0),
                })

        pix_qr_payload = None
        pix_qr_url = None
        if payment_status_label == 'Pendente':
            pix_qr_payload = _build_pix_payload(amount=Decimal(data.total or 0), txid=f'VEN{data.id}')
            pix_qr_url = _build_pix_qr_url(pix_qr_payload)

        settings = _get_store_settings()
        context = {
            'document_title': f'Recibo de Venda #{data.id}',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': data.created_at,
            'record_code': f'VEN-{data.id}',
            'client_name': data.client.name,
            'items': sale_line_items,
            'subtotal': data.subtotal,
            'gross_total': data.subtotal,
            'discount_amount': data.discount_amount,
            'total': data.total,
            'payment_method_label': PAYMENT_METHOD_LABELS.get(data.payment_method, data.payment_method.title()),
            'payment_status_label': payment_status_label,
            'payment_lines': payment_lines,
            'technical': {
                'bios': 'Não se aplica',
                'stress': 'Não se aplica',
                'os': 'Não se aplica',
            },
            'notes': f'Venda: {data.sale_name}',
            'performed_by_name': data.performed_by.name if data.performed_by else 'Não identificado',
            'assembly_inline': assembly_data,
            'assembly_receipt_items': assembly_receipt_items,
            'service_receipt_lines': service_receipt_lines,
            'pix_qr_payload': pix_qr_payload,
            'pix_qr_url': pix_qr_url,
            'pix_key': app.config.get('PIX_KEY', ''),
            'store_address': settings.store_address,
            'store_cnpj': settings.cnpj,
            'store_logo': settings.logo_path,
        }
    elif tipo == 'montagem':
        data = ComputerAssembly.query.get_or_404(record_id)
        apply_suggestion = bool(data.apply_price_suggestion)
        items = []
        for item in data.composicao:
            base_unit_price = Decimal(item.peca.price or 0)
            unit_price = calcular_preco_sugerido(base_unit_price, markup=Decimal('0.25')) if apply_suggestion else base_unit_price
            items.append({
                'item': item.peca.name,
                'source_label': 'Estoque',
                'sku': item.peca.serial_number,
                'quantity': item.quantidade_utilizada,
                'unit_price': unit_price,
                'total': Decimal(item.quantidade_utilizada) * unit_price,
            })

        for custom in data.custom_parts:
            base_unit_price = Decimal(custom.unit_cost or 0)
            unit_price = calcular_preco_sugerido(base_unit_price, markup=Decimal('0.25')) if apply_suggestion else base_unit_price
            items.append({
                'item': custom.part_name,
                'source_label': 'Item Personalizado',
                'sku': None,
                'quantity': custom.quantity,
                'unit_price': unit_price,
                'total': Decimal(custom.quantity) * unit_price,
            })

        service_items = []
        if Decimal(data.bios_service_cost or 0) > 0:
            service_items.append({
                'item': 'Serviço técnico: atualização de BIOS',
                'source_label': 'Serviço',
                'sku': None,
                'quantity': 1,
                'unit_price': Decimal(data.bios_service_cost or 0),
                'total': Decimal(data.bios_service_cost or 0),
            })
        if Decimal(data.stress_test_cost or 0) > 0:
            service_items.append({
                'item': 'Serviço técnico: teste de stress',
                'source_label': 'Serviço',
                'sku': None,
                'quantity': 1,
                'unit_price': Decimal(data.stress_test_cost or 0),
                'total': Decimal(data.stress_test_cost or 0),
            })
        if Decimal(data.os_install_cost or 0) > 0:
            service_items.append({
                'item': 'Serviço técnico: instalação de sistema operacional',
                'source_label': 'Serviço',
                'sku': None,
                'quantity': 1,
                'unit_price': Decimal(data.os_install_cost or 0),
                'total': Decimal(data.os_install_cost or 0),
            })

        items.extend(service_items)
        assembly_total = sum((item['total'] for item in items), Decimal('0.00')).quantize(Decimal('0.01'))
        context = {
            'document_title': f'Recibo de Montagem #{data.id}',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': data.created_at,
            'record_code': f'MON-{data.id}',
            'client_name': data.nome_referencia or data.computador.name,
            'items': items,
            'subtotal': assembly_total,
            'total': assembly_total,
            'is_assembly_label': True,
            'assembly_name': data.nome_referencia or data.computador.name,
            'assembly_id': data.id,
            'assembly_qr_url': f'https://quickchart.io/qr?size=180&text=montagem:{data.id}',
            'technical': {
                'bios': 'Sim' if data.bios_updated else 'Não',
                'stress': 'Sim' if data.stress_test_done else 'Não',
                'os': 'Sim' if data.os_installed else 'Não',
            },
            'notes': data.technical_notes or 'Sem observações técnicas.',
            'performed_by_name': data.performed_by.name if data.performed_by else 'Não identificado',
            'assembly_inline': assembly_data,
        }
    elif tipo == 'manutencao':
        data = MaintenanceTicket.query.get_or_404(record_id)
        parts_items = _load_json_list(data.parts_json)

        items = [
            {
                'item': data.service_description,
                'quantity': 1,
                'unit_price': Decimal(data.labor_cost or 0),
                'total': Decimal(data.labor_cost or 0),
            }
        ]
        subtotal = Decimal(data.labor_cost or 0)

        for part in parts_items:
            qty = _to_decimal(part.get('quantity') or 1, default='1')
            unit = _to_money_decimal(part.get('unit_price') or 0)
            total = qty * unit
            subtotal += total
            items.append({
                'item': f"Peça: {part.get('name', 'Item de estoque')}",
                'quantity': qty,
                'unit_price': unit,
                'total': total,
            })

        context = {
            'document_title': f'Recibo de Ordem de Serviço #{data.id}',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': data.entry_date,
            'record_code': f'OS-{data.id}',
            'client_name': data.client_name,
            'items': items,
            'subtotal': subtotal,
            'total': subtotal,
            'technical': {
                'bios': data.customer_report or 'Não informado',
                'stress': data.technical_diagnosis or 'Não informado',
                'os': MAINTENANCE_STATUS_LABELS.get(data.status, data.status),
            },
            'notes': (data.observations or 'Sem observações.') + ' | Garantia de 30 dias para mão de obra e peças substituídas com defeito de fabricação.',
            'performed_by_name': f'Equipe Técnica {settings.store_name}',
        }
    elif tipo == 'servico':
        data = ServiceRecord.query.get_or_404(record_id)
        subtotal = (Decimal(data.total_price or 0) + Decimal(data.discount_amount or 0)).quantize(Decimal('0.01'))
        context = {
            'document_title': f'Recibo de Serviço #{data.id}',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': data.created_at,
            'record_code': f'SER-{data.id}',
            'client_name': data.client_name,
            'items': [{
                'item': data.service_name,
                'quantity': 1,
                'unit_price': subtotal,
                'total': data.total_price,
            }],
            'subtotal': subtotal,
            'discount_amount': data.discount_amount,
            'total': data.total_price,
            'technical': {
                'bios': 'Não se aplica',
                'stress': 'Não se aplica',
                'os': 'Não se aplica',
            },
            'notes': data.notes or f'Equipamento atendido: {data.equipment}',
            'performed_by_name': data.performed_by.name if data.performed_by else 'Não identificado',
            'assembly_inline': assembly_data,
        }
    elif tipo == 'cliente_relatorio':
        client = Client.query.get_or_404(record_id)
        scope = (request.args.get('scope') or 'compras').strip()
        via = (request.args.get('via') or 'cliente').strip()
        sales = Sale.query.filter_by(client_id=client.id).order_by(Sale.created_at.desc()).all()
        pending_charges = (
            Charge.query
            .join(Sale, Charge.sale_id == Sale.id)
            .filter(Sale.client_id == client.id, Charge.status == 'pendente')
            .order_by(Charge.id.desc())
            .all()
        )
        items = []
        subtotal = Decimal('0.00')
        if scope == 'inadimplentes':
            for charge in pending_charges:
                balance = _charge_balance(charge)
                subtotal += balance
                items.append({
                    'item': f'Débito {charge.mercado_pago_reference}',
                    'serial_number': f'COB-{charge.id}',
                    'quantity': 1,
                    'unit_price': balance,
                    'total': balance,
                })
        else:
            for sale in sales:
                sale_total = Decimal(sale.total or 0)
                subtotal += sale_total
                payload = {
                    'item': f"{sale.sale_name} ({sale.created_at.strftime('%d/%m/%Y')})",
                    'serial_number': f"VEN-{sale.id}",
                    'quantity': 1,
                    'unit_price': sale_total,
                    'total': sale_total,
                }
                if via == 'gerente':
                    cost_total = sum((Decimal(i.unit_cost or 0) * Decimal(i.quantity or 0)) for i in sale.items)
                    margin_value = sale_total - cost_total
                    margin_percent = calcular_margem_lucro(cost_total, sale_total)
                    payload['source_label'] = (
                        f'Custo: R$ {cost_total:.2f} | Margem: R$ {margin_value:.2f} ({margin_percent:.2f}%)'
                    )
                items.append(payload)

        context = {
            'document_title': f'Relatório de Cliente - {client.name}',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': datetime.utcnow(),
            'record_code': f'CLI-{client.id}',
            'client_name': client.name,
            'items': items or [{
                'item': 'Sem compras registradas',
                'serial_number': '-',
                'quantity': 0,
                'unit_price': Decimal('0.00'),
                'total': Decimal('0.00'),
            }],
            'subtotal': subtotal,
            'discount_amount': Decimal('0.00'),
            'total': subtotal,
            'technical': {
                'bios': client.cpf or '-',
                'stress': client.phone or '-',
                'os': client.email or '-',
            },
            'notes': f'Relatório em modo "{scope}" ({via}).',
            'performed_by_name': _current_user().name if _current_user() else 'Sistema',
        }
    elif tipo == 'cliente_quitacao':
        charge = Charge.query.get_or_404(record_id)
        sale = charge.sale
        if not sale:
            flash('Cobrança sem venda associada para quitação.', 'danger')
            return redirect(url_for('clientes'))
        paid_value = Decimal(sale.total or 0)
        context = {
            'document_title': f'Recibo de Quitação #{charge.id}',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': charge.payment_confirmed_at or datetime.utcnow(),
            'record_code': f'QUIT-{charge.id}',
            'client_name': sale.client.name,
            'items': [{
                'item': f'Quitação da cobrança {charge.mercado_pago_reference}',
                'serial_number': f'VEN-{sale.id}',
                'quantity': 1,
                'unit_price': paid_value,
                'total': paid_value,
            }],
            'subtotal': paid_value,
            'discount_amount': Decimal('0.00'),
            'total': paid_value,
            'technical': {
                'bios': f'Status: {charge.status}',
                'stress': f'Método: {charge.payment_method}',
                'os': (charge.payment_confirmed_at.strftime('%d/%m/%Y %H:%M') if charge.payment_confirmed_at else datetime.utcnow().strftime('%d/%m/%Y %H:%M')),
            },
            'notes': 'Recibo emitido para comprovação de pagamento da dívida pendente.',
            'performed_by_name': _current_user().name if _current_user() else 'Sistema',
        }

    elif tipo == 'cobranca_relatorio':
        pending_charges = Charge.query.order_by(Charge.id.desc()).all()
        today = datetime.utcnow().date()
        items = []
        subtotal = Decimal('0.00')

        for charge in pending_charges:
            balance = _charge_balance(charge)
            if balance <= 0 or charge.status == 'cancelado':
                continue

            due_date_label = charge.due_date.strftime('%d/%m/%Y') if charge.due_date else 'Sem vencimento'
            overdue_days = (today - charge.due_date).days if charge.due_date and charge.due_date < today else 0
            source = charge.sale.client.name if charge.sale and charge.sale.client else (charge.service.client_name if charge.service else 'Origem avulsa')
            subtotal += balance
            items.append({
                'item': f'{source} - Ref: {charge.mercado_pago_reference}',
                'serial_number': f'Vencto: {due_date_label}',
                'quantity': 1,
                'unit_price': balance,
                'total': balance,
                'source_label': f'{overdue_days} dia(s) em atraso' if overdue_days > 0 else 'No prazo',
            })

        context = {
            'document_title': 'Relatório de Inadimplência',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': datetime.utcnow(),
            'record_code': f'REL-COB-{datetime.utcnow().strftime("%Y%m%d%H%M")}',
            'client_name': 'Uso interno',
            'items': items or [{
                'item': 'Sem débitos pendentes',
                'serial_number': '-',
                'quantity': 0,
                'unit_price': Decimal('0.00'),
                'total': Decimal('0.00'),
                'source_label': '-',
            }],
            'subtotal': subtotal,
            'discount_amount': Decimal('0.00'),
            'total': subtotal,
            'technical': {'bios': 'N/A', 'stress': 'N/A', 'os': 'N/A'},
            'notes': 'Documento interno para acompanhamento de inadimplência.',
            'performed_by_name': _current_user().name if _current_user() else 'Sistema',
        }
    elif tipo == 'cobranca_recibo_parcial':
        charge = Charge.query.get_or_404(record_id)
        total_amount = _charge_total_amount(charge)
        paid_amount = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
        balance = (total_amount - paid_amount).quantize(Decimal('0.01'))
        source = charge.sale.client.name if charge.sale and charge.sale.client else (charge.service.client_name if charge.service else 'Cliente avulso')

        context = {
            'document_title': f'Recibo de Pagamento Parcial #{charge.id}',
            'store_name': settings.store_name,
            'store_contact': settings.store_contact,
            'record_date': datetime.utcnow(),
            'record_code': f'PARC-{charge.id}',
            'client_name': source,
            'items': [{
                'item': f'Cobrança {charge.mercado_pago_reference}',
                'serial_number': f'Total: R$ {total_amount:.2f}',
                'quantity': 1,
                'unit_price': paid_amount,
                'total': paid_amount,
                'source_label': f'Saldo devedor: R$ {balance:.2f}',
            }],
            'subtotal': total_amount,
            'discount_amount': Decimal('0.00'),
            'total': paid_amount,
            'technical': {
                'bios': f'Valor Total: R$ {total_amount:.2f}',
                'stress': f'Valor Pago: R$ {paid_amount:.2f}',
                'os': f'Saldo Devedor: R$ {balance:.2f}',
            },
            'notes': 'Recibo parcial: [Valor Total] - [Valor Pago] = [Saldo Devedor].',
            'performed_by_name': _current_user().name if _current_user() else 'Sistema',
        }
    else:
        flash('Tipo de impressão inválido.', 'danger')
        return redirect(url_for('dashboard'))

    context.setdefault('store_name', settings.store_name)
    context.setdefault('store_contact', settings.store_contact)
    context.setdefault('store_address', settings.store_address)
    context.setdefault('store_cnpj', settings.cnpj)
    context.setdefault('store_logo', settings.logo_path)

    pdf_preview_mode = request.args.get('pdf_preview') == '1'
    is_pdf_render = pisa is not None and (request.args.get('preview') != '1' or pdf_preview_mode)
    context.setdefault('is_pdf_render', is_pdf_render)

    html = render_template('print_receipt.html', **context)

    # Permite pré-visualização HTML do recibo para validação de layout no navegador.
    if request.args.get('preview') == '1':
        return html

    if pisa is None:
        return html

    pdf_buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=pdf_buffer, link_callback=_pisa_link_callback)
    if status.err:
        flash('Não foi possível gerar PDF. Exibindo versão HTML para impressão.', 'danger')
        return html

    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename="{tipo}-{record_id}.pdf"'
    return response




@app.route('/produtos/imprimir-etiquetas', methods=['POST'])
@_login_required
def imprimir_etiquetas_produtos():
    """Função `imprimir_etiquetas_produtos`: 
     gera etiquetas de produtos selecionados, permitindo exportação em PDF ou visualização em HTML para impressão direta."""
    product_ids = [int(pid) for pid in request.form.getlist('product_ids') if str(pid).isdigit()]
    if not product_ids:
        flash('Selecione ao menos um item para imprimir etiquetas.', 'danger')
        return redirect(url_for('produtos'))

    items = Product.query.filter(Product.id.in_(product_ids)).order_by(Product.name).all()
    if not items:
        flash('Nenhum item válido foi encontrado para impressão.', 'danger')
        return redirect(url_for('produtos'))

    html = render_template('print_labels.html', products=items)
    if pisa is None:
        return html

    pdf_buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=pdf_buffer, link_callback=_pisa_link_callback)
    if status.err:
        flash('Não foi possível gerar PDF das etiquetas. Exibindo versão HTML para impressão.', 'danger')
        return html

    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename="etiquetas-produtos.pdf"'
    return response


@app.route('/produtos/imprimir-inventario', methods=['POST'])
@_login_required
def imprimir_inventario_produtos():
    """Função `imprimir_inventario_produtos`: 
     gera um relatório de inventário completo dos produtos em estoque,
     com totais de quantidade, valor de custo e valor de venda,
     permitindo exportação em PDF ou visualização em HTML para impressão direta."""
    products = buscar_pecas_disponiveis(Product)

    total_stock = sum(int(p.stock or 0) for p in products)
    total_cost = sum(Decimal(p.cost_price or 0) * Decimal(p.stock or 0) for p in products)
    total_sale = sum(Decimal(p.price or 0) * Decimal(p.stock or 0) for p in products)

    html = render_template(
        'print_inventory.html',
        products=products,
        total_stock=total_stock,
        total_cost=total_cost,
        total_sale=total_sale,
    )
    if pisa is None:
        return html

    pdf_buffer = BytesIO()
    status = pisa.CreatePDF(html, dest=pdf_buffer, link_callback=_pisa_link_callback)
    if status.err:
        flash('Não foi possível gerar PDF do inventário. Exibindo versão HTML para impressão.', 'danger')
        return html

    response = make_response(pdf_buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename="inventario-estoque.pdf"'
    return response


@app.route('/recuperar-senha', methods=['GET', 'POST'])
def recuperar_senha():
    """Função `recuperar_senha`: 
     permite que usuários iniciem o processo de recuperação de senha fornecendo seu e-mail,"""
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
    """Função `redefinir_senha`: permite que usuários redefinam sua senha após clicar no link de recuperação enviado por e-mail."""
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
    """Função `dashboard`:  exibe um painel de controle com métricas e gráficos de vendas, serviços, custos e lucros, com filtros por período."""
    period = request.args.get('period', 'month')
    now = datetime.utcnow()
    start_date = None
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == '7d':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        period = 'month'
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    sales_query = Sale.query.filter(Sale.canceled.is_(False), Sale.created_at >= start_date)
    service_query = ServiceRecord.query.filter(ServiceRecord.created_at >= start_date)
    fixed_cost_query = FixedCost.query.filter(FixedCost.created_at >= start_date)
    fixed_costs = fixed_cost_query.order_by(FixedCost.created_at.desc()).all()
    maintenance_query = MaintenanceTicket.query.filter(MaintenanceTicket.entry_date >= start_date)

    product_count = Product.query.count()
    total_stock = db.session.query(db.func.coalesce(db.func.sum(Product.stock), 0)).scalar()
    sales_count = sales_query.count()
    services_count = service_query.count()
    period_charges = (
        db.session.query(Charge)
        .outerjoin(Sale, Sale.id == Charge.sale_id)
        .outerjoin(ServiceRecord, ServiceRecord.id == Charge.service_id)
        .filter(
            Charge.status != 'cancelado',
            db.or_(
                db.and_(Charge.sale_id.isnot(None), Sale.canceled.is_(False), Sale.created_at >= start_date),
                db.and_(Charge.service_id.isnot(None), ServiceRecord.created_at >= start_date),
            ),
        )
        .all()
    )

    pending_charges = 0
    pending_receivable_total = Decimal('0.00')

    total_sales_amount = Decimal('0.00')
    total_services_amount = Decimal('0.00')
    payment_method_totals: dict[str, Decimal] = {}
    payment_method_counts: dict[str, int] = {}
    for charge in period_charges:
        paid = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
        balance = _charge_balance(charge)

        if charge.status != 'cancelado' and balance > 0:
            pending_charges += 1
            pending_receivable_total += balance

        if charge.sale_id:
            total_sales_amount += paid
        if charge.service_id:
            total_services_amount += paid

        method = charge.payment_method or 'pix'
        payment_method_counts[method] = payment_method_counts.get(method, 0) + 1
        payment_method_totals[method] = payment_method_totals.get(method, Decimal('0.00')) + paid

    sales_revenue = db.session.query(
        db.func.coalesce(db.func.sum(SaleItem.line_total), 0)
    ).join(Sale, Sale.id == SaleItem.sale_id).filter(
        Sale.canceled.is_(False), Sale.created_at >= start_date
    ).scalar()
    sales_parts_cost = db.session.query(
        db.func.coalesce(db.func.sum(SaleItem.unit_cost * SaleItem.quantity), 0)
    ).join(Sale, Sale.id == SaleItem.sale_id).filter(
        Sale.canceled.is_(False), Sale.created_at >= start_date
    ).scalar()
    service_revenue = db.session.query(
        db.func.coalesce(db.func.sum(ServiceRecord.total_price), 0)
    ).filter(ServiceRecord.created_at >= start_date).scalar()
    service_cost = db.session.query(
        db.func.coalesce(db.func.sum(ServiceRecord.cost), 0)
    ).filter(ServiceRecord.created_at >= start_date).scalar()

    sales_profit = Decimal(sales_revenue or 0) - Decimal(sales_parts_cost or 0)
    service_profit = Decimal(service_revenue or 0) - Decimal(service_cost or 0)
    total_fixed_costs = db.session.query(db.func.coalesce(db.func.sum(FixedCost.amount), 0)).filter(
        FixedCost.created_at >= start_date
    ).scalar()
    total_profit = sales_profit + service_profit

    sale_cost_map = {
        int(sale_id): Decimal(cost or 0).quantize(Decimal('0.01'))
        for sale_id, cost in db.session.query(
            SaleItem.sale_id,
            db.func.coalesce(db.func.sum(SaleItem.unit_cost * SaleItem.quantity), 0),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.canceled.is_(False), Sale.created_at >= start_date)
        .group_by(SaleItem.sale_id)
        .all()
    }
    service_cost_map = {
        int(service.id): Decimal(service.cost or 0).quantize(Decimal('0.01'))
        for service in ServiceRecord.query.filter(ServiceRecord.created_at >= start_date).all()
    }

    paid_by_sale_id: dict[int, Decimal] = {}
    paid_by_service_id: dict[int, Decimal] = {}
    sale_totals: dict[int, Decimal] = {}
    service_totals: dict[int, Decimal] = {}

    for charge in period_charges:
        if charge.status == 'cancelado':
            continue

        paid_amount = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
        if paid_amount <= 0:
            continue

        if charge.sale_id and charge.sale:
            paid_by_sale_id[charge.sale_id] = paid_by_sale_id.get(charge.sale_id, Decimal('0.00')) + paid_amount
            sale_totals[charge.sale_id] = Decimal(charge.sale.total or 0).quantize(Decimal('0.01'))
        elif charge.service_id and charge.service:
            paid_by_service_id[charge.service_id] = paid_by_service_id.get(charge.service_id, Decimal('0.00')) + paid_amount
            service_totals[charge.service_id] = Decimal(charge.service.total_price or 0).quantize(Decimal('0.01'))

    realized_profit = Decimal('0.00')
    for sale_id, paid_amount in paid_by_sale_id.items():
        sale_total = sale_totals.get(sale_id, Decimal('0.00'))
        if sale_total <= 0:
            continue

        ratio = min(Decimal('1.00'), (paid_amount / sale_total))
        sale_cost = sale_cost_map.get(sale_id, Decimal('0.00'))
        sale_margin = sale_total - sale_cost
        realized_profit += sale_margin * ratio

    for service_id, paid_amount in paid_by_service_id.items():
        service_total = service_totals.get(service_id, Decimal('0.00'))
        if service_total <= 0:
            continue

        ratio = min(Decimal('1.00'), (paid_amount / service_total))
        service_cost_value = service_cost_map.get(service_id, Decimal('0.00'))
        service_margin = service_total - service_cost_value
        realized_profit += service_margin * ratio

    net_profit = realized_profit - Decimal(total_fixed_costs or 0)
    maintenance_in_progress = maintenance_query.filter(MaintenanceTicket.status != 'concluido').count()
    maintenance_waiting_parts = maintenance_query.filter(MaintenanceTicket.waiting_parts.is_(True), MaintenanceTicket.status != 'concluido').count()

    payment_method_summary = [
        (method, payment_method_counts.get(method, 0), payment_method_totals.get(method, Decimal('0.00')))
        for method, _label in PAYMENT_METHODS
        if payment_method_counts.get(method, 0) > 0
    ]
    latest_sales = sales_query.order_by(Sale.created_at.desc()).limit(5).all()
    latest_services = service_query.order_by(ServiceRecord.created_at.desc()).limit(5).all()
    recent_charges = Charge.query.order_by(Charge.id.desc()).all()

    charges_by_sale_id: dict[int, list[Charge]] = {}
    charges_by_service_id: dict[int, list[Charge]] = {}
    for charge in recent_charges:
        if charge.sale_id:
            charges_by_sale_id.setdefault(charge.sale_id, []).append(charge)
        if charge.service_id:
            charges_by_service_id.setdefault(charge.service_id, []).append(charge)

    finalized_sales = {
        sale.id for sale in latest_sales if _is_sale_finalized_by_payment(sale, charges_by_sale_id.get(sale.id, []))
    }
    finalized_services = {
        service.id
        for service in latest_services
        if _is_service_finalized_by_payment(service, charges_by_service_id.get(service.id, []))
    }

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
        pending_receivable_total=pending_receivable_total,
        total_sales_amount=total_sales_amount,
        total_services_amount=total_services_amount,
        total_profit=total_profit,
        total_fixed_costs=total_fixed_costs,
        fixed_costs=fixed_costs,
        net_profit=net_profit,
        maintenance_in_progress=maintenance_in_progress,
        maintenance_waiting_parts=maintenance_waiting_parts,
        payment_method_summary=payment_method_summary,
        payment_method_labels=PAYMENT_METHOD_LABELS,
        latest_sales=latest_sales,
        latest_services=latest_services,
        finalized_sales=finalized_sales,
        finalized_services=finalized_services,
        period=period,
        chart_months=chart_months,
        chart_sales_totals=chart_sales_totals,
        top_products_labels=top_products_labels,
        top_products_values=top_products_values,
    )


@app.route('/gestao-inventario')
@_login_required
def gestao_inventario():
    """Função `gestao_inventario`:  exibe uma interface de gestão de inventário com listagem de produtos,
     filtros por categoria e classe, e opções para cadastro, edição e exclusão de itens em estoque."""
    products = Product.query.order_by(Product.category, Product.name).all()
    categories = sorted({p.category for p in products})
    return render_template('inventory_management.html', products=products, categories=categories, component_slots=COMPONENT_SLOTS)


@app.route('/produtos', methods=['GET', 'POST'])
@_login_required
def produtos():
    """Função `produtos`: permite cadastro de novos produtos no estoque,
     incluindo peças avulsas e computadores montados, com validação de dados,
      upload de fotos e cálculo de preços sugeridos."""
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
                    current_user=_current_user(),
                )
                db.session.commit()
                flash(
                    f'Computador montado cadastrado! Preço base R$ {result["preco_original"]:.2f} + '
                    f'peças R$ {result["custo_total"]:.2f} = preço final R$ {result["preco_final"]:.2f} | '
                    f'Preço sugerido das peças avulsas (+20%) R$ {result["preco_sugerido"]:.2f}.',
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

        generated_piece_name = _generate_piece_name(component_class, request.form) if category == 'Peça' else (request.form.get('name') or '').strip()
        apply_suggested_price = request.form.get('apply_suggested_price') == 'on'

        base_cost = _to_money_decimal(request.form.get('cost_price'))
        freight_fees = _to_money_decimal(request.form.get('freight_fees'))
        suggested_price = calcular_preco_sugerido(base_cost + freight_fees, markup=Decimal('0.25'))
        sale_price = suggested_price if apply_suggested_price else _to_money_decimal(request.form.get('price'))

        product_dto = ProductDTO(
            name=generated_piece_name,
            category=category,
            stock=int(request.form['stock']),
            price=sale_price,
            cost_price=base_cost,
            component_class=component_class,
            serial_number=(request.form.get('serial_number') or '').strip() or None,
        )
        product_dto.validate()
        product = product_service.create(
            name=product_dto.name,
            category=product_dto.category,
            stock=product_dto.stock,
            price=product_dto.price,
            cost_price=product_dto.cost_price,
            photo_url=photo_url,
            component_class=product_dto.component_class,
            serial_number=product_dto.serial_number,
            ram_ddr=(request.form.get('ram_ddr') or '').strip() or None,
            ram_frequency=(request.form.get('ram_frequency') or '').strip() or None,
            ram_size=(request.form.get('ram_size') or '').strip() or None,
            ram_brand=(request.form.get('ram_brand') or '').strip() or None,
            psu_watts=(request.form.get('psu_watts') or '').strip() or None,
            psu_brand=(request.form.get('psu_brand') or '').strip() or None,
            gpu_memory=(request.form.get('gpu_memory') or '').strip() or None,
            gpu_brand=(request.form.get('gpu_brand') or '').strip() or None,
            gpu_manufacturer=(request.form.get('gpu_manufacturer') or '').strip() or None,
            storage_type=(request.form.get('storage_type') or '').strip() or None,
            storage_capacity=(request.form.get('storage_capacity') or '').strip() or None,
            storage_brand=(request.form.get('storage_brand') or '').strip() or None,
            cpu_brand=None,
            cpu_manufacturer=(request.form.get('cpu_manufacturer') or '').strip() or None,
            cpu_model=(request.form.get('cpu_model') or '').strip() or None,
            motherboard_brand=(request.form.get('motherboard_brand') or '').strip() or None,
            motherboard_model=(request.form.get('motherboard_model') or '').strip() or None,
            motherboard_socket=(request.form.get('motherboard_socket') or '').strip() or None,
            motherboard_chipset=(request.form.get('motherboard_chipset') or '').strip() or None,
            cabinet_brand=(request.form.get('cabinet_brand') or '').strip() or None,
            cabinet_description=(request.form.get('cabinet_description') or '').strip() or None,
            fan_brand=(request.form.get('fan_brand') or '').strip() or None,
            fan_description=(request.form.get('fan_description') or '').strip() or None,
            peripheral_mouse=(request.form.get('peripheral_mouse') or '').strip() or None,
            peripheral_keyboard=(request.form.get('peripheral_keyboard') or '').strip() or None,
            peripheral_monitor=(request.form.get('peripheral_monitor') or '').strip() or None,
            peripheral_power_cable=(request.form.get('peripheral_power_cable') or '').strip() or None,
            peripheral_hdmi_cable=(request.form.get('peripheral_hdmi_cable') or '').strip() or None,
        )
        db.session.commit()
        flash('Produto cadastrado com sucesso!', 'success')
        return redirect(url_for('produtos'))

    products = Product.query.filter_by(active=True).order_by(Product.category, Product.component_class, Product.name).all()
    parts_by_class = buscar_pecas_por_classe(Product, COMPONENT_SLOTS)

    edit_product = None
    edit_product_id = request.args.get('edit_product_id', type=int)
    if edit_product_id:
        edit_product = Product.query.get(edit_product_id)
        if not edit_product:
            flash('Produto para edição não encontrado.', 'danger')
        elif edit_product.category != 'Peça' or not edit_product.component_class:
            flash('A edição guiada está disponível apenas para produtos da categoria Peça.', 'danger')
            edit_product = None

    return render_template(
        'products.html',
        products=products,
        parts_by_class=parts_by_class,
        component_slots=COMPONENT_SLOTS,
        edit_product=edit_product,
        return_to=(request.args.get('return_to') or '').strip() or None,
    )


@app.route('/produtos/<int:product_id>/atualizar_foto', methods=['POST'])
@_login_required
def atualizar_foto_produto(product_id: int):
    """
    Função `atualizar_foto_produto`: permite atualizar a galeria de fotos de um produto específico,
     adicionando novas imagens e definindo a primeira imagem adicionada como foto principal se o produto ainda não tiver uma.
     """
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
    """Função `editar_produto`: permite editar os dados de um produto existente no estoque."""
    product = Product.query.get_or_404(product_id)

    return_to = (request.form.get('return_to') or '').strip()
    fallback_edit_url = url_for('produtos', edit_product_id=product.id, return_to=return_to) if return_to else url_for('produtos', edit_product_id=product.id)
    success_redirect = return_to or url_for('produtos')

    category = request.form.get('category') or product.category
    component_class = request.form.get('component_class') or None

    if category != 'Peça':
        component_class = None
    elif not component_class:
        flash('Informe a classe da peça para produtos da categoria Peça.', 'danger')
        return redirect(fallback_edit_url)

    old_price = Decimal(product.price)
    apply_suggested_price = request.form.get('apply_suggested_price') == 'on'
    base_cost = _to_money_decimal(request.form.get('cost_price'))
    freight_fees = _to_money_decimal(request.form.get('freight_fees'))
    suggested_price = calcular_preco_sugerido(base_cost + freight_fees, markup=Decimal('0.25'))
    new_price = suggested_price if apply_suggested_price else _to_money_decimal(request.form.get('price'))

    product.name = _generate_piece_name(component_class, request.form) if category == 'Peça' else (request.form.get('name') or product.name).strip()
    product.category = category
    product.stock = int(request.form.get('stock') or 0)
    product.price = new_price
    product.cost_price = base_cost
    product.component_class = component_class
    product.serial_number = (request.form.get('serial_number') or '').strip() or None
    if 'ram_ddr' in request.form:
        product.ram_ddr = (request.form.get('ram_ddr') or '').strip() or None
    if 'ram_frequency' in request.form:
        product.ram_frequency = (request.form.get('ram_frequency') or '').strip() or None
    if 'ram_size' in request.form:
        product.ram_size = (request.form.get('ram_size') or '').strip() or None
    if 'ram_brand' in request.form:
        product.ram_brand = (request.form.get('ram_brand') or '').strip() or None
    if 'psu_watts' in request.form:
        product.psu_watts = (request.form.get('psu_watts') or '').strip() or None
    if 'psu_brand' in request.form:
        product.psu_brand = (request.form.get('psu_brand') or '').strip() or None
    if 'gpu_memory' in request.form:
        product.gpu_memory = (request.form.get('gpu_memory') or '').strip() or None
    if 'gpu_brand' in request.form:
        product.gpu_brand = (request.form.get('gpu_brand') or '').strip() or None
    if 'gpu_manufacturer' in request.form:
        product.gpu_manufacturer = (request.form.get('gpu_manufacturer') or '').strip() or None
    if 'storage_type' in request.form:
        product.storage_type = (request.form.get('storage_type') or '').strip() or None
    if 'storage_capacity' in request.form:
        product.storage_capacity = (request.form.get('storage_capacity') or '').strip() or None
    if 'storage_brand' in request.form:
        product.storage_brand = (request.form.get('storage_brand') or '').strip() or None
    product.cpu_brand = None
    if 'cpu_manufacturer' in request.form:
        product.cpu_manufacturer = (request.form.get('cpu_manufacturer') or '').strip() or None
    if 'cpu_model' in request.form:
        product.cpu_model = (request.form.get('cpu_model') or '').strip() or None
    if 'motherboard_brand' in request.form:
        product.motherboard_brand = (request.form.get('motherboard_brand') or '').strip() or None
    if 'motherboard_model' in request.form:
        product.motherboard_model = (request.form.get('motherboard_model') or '').strip() or None
    if 'motherboard_socket' in request.form:
        product.motherboard_socket = (request.form.get('motherboard_socket') or '').strip() or None
    if 'motherboard_chipset' in request.form:
        product.motherboard_chipset = (request.form.get('motherboard_chipset') or '').strip() or None
    if 'cabinet_brand' in request.form:
        product.cabinet_brand = (request.form.get('cabinet_brand') or '').strip() or None
    if 'cabinet_description' in request.form:
        product.cabinet_description = (request.form.get('cabinet_description') or '').strip() or None
    if 'fan_brand' in request.form:
        product.fan_brand = (request.form.get('fan_brand') or '').strip() or None
    if 'fan_description' in request.form:
        product.fan_description = (request.form.get('fan_description') or '').strip() or None
    if 'peripheral_mouse' in request.form:
        product.peripheral_mouse = (request.form.get('peripheral_mouse') or '').strip() or None
    if 'peripheral_keyboard' in request.form:
        product.peripheral_keyboard = (request.form.get('peripheral_keyboard') or '').strip() or None
    if 'peripheral_monitor' in request.form:
        product.peripheral_monitor = (request.form.get('peripheral_monitor') or '').strip() or None
    if 'peripheral_power_cable' in request.form:
        product.peripheral_power_cable = (request.form.get('peripheral_power_cable') or '').strip() or None
    if 'peripheral_hdmi_cable' in request.form:
        product.peripheral_hdmi_cable = (request.form.get('peripheral_hdmi_cable') or '').strip() or None

    if old_price != new_price:
        _log_audit(
            'Alteração de preço',
            f'Usuário {_current_user().name} alterou o preço do item {product.name} de R$ {old_price:.2f} para R$ {new_price:.2f} em {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}.',
        )

    db.session.commit()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(success_redirect)


@app.route('/produtos/<int:product_id>/remover', methods=['POST'])
@_login_required
def remover_produto(product_id: int):
    """Função `remover_produto`: permite inativar um produto existente no estoque."""
    product = Product.query.get_or_404(product_id)

    if not product.active:
        flash('Produto já está inativo.', 'danger')
    else:
        product_service.soft_delete(product)
        db.session.commit()
        flash('Produto inativado com sucesso!', 'success')

    return redirect(request.referrer or url_for('produtos'))


@app.route('/produtos/<int:product_id>/ativar', methods=['POST'])
@_login_required
def ativar_produto(product_id: int):
    """Função `ativar_produto`: permite reativar um produto inativo no estoque."""
    product = Product.query.get_or_404(product_id)

    if product.active:
        flash('Produto já está ativo.', 'danger')
    else:
        product.active = True
        db.session.commit()
        flash('Produto ativado com sucesso!', 'success')

    return redirect(request.referrer or url_for('produtos'))




@app.route('/produtos/<int:product_id>/excluir', methods=['POST'])
@_login_required
def excluir_produto(product_id: int):
    """Função `excluir_produto`: permite excluir permanentemente um produto do estoque."""
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Produto excluído permanentemente.', 'success')
    return redirect(request.referrer or url_for('gestao_inventario'))


def _build_assembly_edit_data(latest_assemblies):
    """
    Função `_build_assembly_edit_data`: constrói os dados necessários
     para exibir as montagens de computadores recentes na interface de
      montagem, organizando as peças selecionadas, peças personalizadas
       e linhas de peças múltiplas para cada montagem.
     Retorna um dicionário estruturado com as informações de cada montagem
      para facilitar a renderização na interface de usuário.
     """
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
                    'piece_name': item.peca.name,
                    'qty': item.quantidade_utilizada,
                    'custom_name': '',
                    'custom_cost': '0',
                })
            else:
                single_selected[slot_key] = {
                    'piece_id': item.id_peca,
                    'piece_name': item.peca.name,
                }

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
                multi_rows[slot_key].append({'piece_id': '', 'piece_name': '', 'qty': 1, 'custom_name': '', 'custom_cost': '0'})

        data[assembly.id] = {
            'single_selected': single_selected,
            'single_custom': single_custom,
            'multi_rows': multi_rows,
        }

    return data

@app.route('/montar_pc', methods=['GET', 'POST'])
@app.route('/montar-pc', methods=['GET', 'POST'])
@_login_required
def montar_pc():
    """
    Função `montar_pc`: exibe a interface de montagem de computadores,
    permitindo aos usuários selecionar peças do estoque, adicionar peças
    personalizadas, fazer upload de fotos da montagem e salvar a configuração 
    como um produto montado. No modo POST, processa os dados enviados pelo formulário,
    valida as entradas, constrói a montagem do computador com as peças selecionadas
    e personalizadas, calcula os preços e salva a montagem no banco de dados,
    com a opção de enviar a montagem para o carrinho de vendas.
    No modo GET, exibe a interface de montagem com as peças disponíveis,
    as montagens recentes e, se aplicável, os dados para edição de uma montagem existente.
     """
    current = _current_user()
    parts_by_class = buscar_pecas_por_classe(Product, COMPONENT_SLOTS)

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
        optional_costs = _read_optional_service_costs(request.form)
        send_to_sales = request.form.get('send_to_sales') == 'on'
        apply_price_suggestion = request.form.get('apply_price_suggestion') == 'on'

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
                bios_service_cost=optional_costs['bios_service_cost'],
                stress_test_cost=optional_costs['stress_test_cost'],
                os_install_cost=optional_costs['os_install_cost'],
                apply_price_suggestion=apply_price_suggestion,
                current_user=current,
            )
            db.session.commit()
            flash(
                f'Montagem concluída! Preço base R$ {result["preco_original"]:.2f} + '
                f'peças R$ {result["custo_total"]:.2f} = preço final R$ {result["preco_final"]:.2f} | '
                f'Sugestão de peças avulsas (+20%) R$ {result["preco_sugerido"]:.2f} '
                f'({"aplicada" if result["apply_price_suggestion"] else "não aplicada"}).',
                'success',
            )
            if send_to_sales and result.get('computer_id'):
                flash('Montagem enviada para o carrinho de vendas.', 'success')
                return redirect(url_for('vendas', assembled_product_id=result['computer_id']))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')

        return redirect(url_for('montar_pc'))

    latest_assemblies = ComputerAssembly.query.order_by(ComputerAssembly.created_at.desc()).limit(20).all()
    edit_assembly = None
    edit_assembly_id = request.args.get('edit_assembly_id', type=int)
    if edit_assembly_id:
        edit_assembly = ComputerAssembly.query.get(edit_assembly_id)
        if not edit_assembly:
            flash('Montagem para edição não encontrada.', 'danger')

    assemblies_for_edit_data = list(latest_assemblies)
    if edit_assembly and all(item.id != edit_assembly.id for item in assemblies_for_edit_data):
        assemblies_for_edit_data.append(edit_assembly)

    return render_template(
        'assemble_pc.html',
        parts_by_class=parts_by_class,
        component_slots=COMPONENT_SLOTS,
        latest_assemblies=latest_assemblies,
        assembly_edit_data=_build_assembly_edit_data(assemblies_for_edit_data),
        edit_assembly=edit_assembly,
    )


@app.route('/montagens/<int:assembly_id>/editar', methods=['POST'])
@_login_required
def editar_montagem(assembly_id: int):
    assembly = ComputerAssembly.query.get_or_404(assembly_id)

    if assembly.canceled:
        flash('Não é possível editar uma montagem cancelada.', 'danger')
        return redirect(url_for('montar_pc'))

    nome_referencia = (request.form.get('computer_name') or '').strip()
    if not nome_referencia:
        flash('Informe um nome de referência para a montagem.', 'danger')
        return redirect(url_for('montar_pc'))

    try:
        preco_original = Decimal(request.form.get('computer_original_price') or '0')
    except Exception:
        flash('Preço original inválido.', 'danger')
        return redirect(url_for('montar_pc'))

    if preco_original < 0:
        flash('Preço original não pode ser negativo.', 'danger')
        return redirect(url_for('montar_pc'))

    selected_piece_ids, custom_items = _collect_selected_piece_inputs(request.form)
    apply_price_suggestion = request.form.get('apply_price_suggestion') == 'on'
    optional_costs = _read_optional_service_costs(request.form)
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
            custo_total += Decimal(qty) * Decimal(piece.price or 0)

        for custom_item in custom_items:
            if custom_item['unit_cost'] < 0:
                raise ValueError(f"Custo inválido para peça personalizada: {custom_item['name']}")
            custo_total += Decimal(custom_item['qty']) * custom_item['unit_cost']

        assembly.nome_referencia = nome_referencia
        technical_services_cost = (
            optional_costs['bios_service_cost']
            + optional_costs['stress_test_cost']
            + optional_costs['os_install_cost']
        ).quantize(Decimal('0.01'))
        assembly.preco_original = preco_original
        custo_pecas = custo_total.quantize(Decimal('0.01'))
        assembly.custo_total = (custo_pecas + technical_services_cost).quantize(Decimal('0.01'))
        assembly.preco_sugerido = _calculate_assembly_suggested_pieces_total(piece_counter_new, pieces_by_id, custom_items)
        assembly.apply_price_suggestion = apply_price_suggestion
        assembly.technical_notes = (request.form.get('technical_notes') or '').strip() or None
        assembly.bios_updated = request.form.get('bios_updated') == 'on'
        assembly.bios_service_cost = optional_costs['bios_service_cost']
        assembly.stress_test_done = request.form.get('stress_test_done') == 'on'
        assembly.stress_test_cost = optional_costs['stress_test_cost']
        assembly.os_installed = request.form.get('os_installed') == 'on'
        assembly.os_install_cost = optional_costs['os_install_cost']

        computer = assembly.computador
        if computer and computer.stock > 0:
            subtotal_pecas = assembly.preco_sugerido if apply_price_suggestion else custo_pecas
            computer.price = (preco_original + subtotal_pecas + technical_services_cost).quantize(Decimal('0.01'))

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

    computer = assembly.computador

    if not assembly.canceled:
        if computer and computer.stock > 0:
            computer.stock -= 1

        for item in assembly.composicao:
            if item.peca:
                item.peca.stock += item.quantidade_utilizada

    should_delete_computer = False
    if computer and computer.category == 'Computador' and computer.stock <= 0:
        computer.stock = 0
        related_assemblies = ComputerAssembly.query.filter(
            ComputerAssembly.id_computador == computer.id,
            ComputerAssembly.id != assembly.id,
        ).count()
        should_delete_computer = related_assemblies == 0

    db.session.delete(assembly)
    if should_delete_computer and computer:
        db.session.delete(computer)
    db.session.commit()
    flash('Montagem excluída com sucesso!', 'success')
    return redirect(url_for('montar_pc'))




@app.route('/servicos', methods=['GET', 'POST'])
@_login_required
def servicos():
    current = _current_user()
    service_catalog = [
        {'name': 'Montagem Premium', 'price': Decimal('199.90'), 'description': 'Montagem completa, organização de cabos e validação final.'},
        {'name': 'Upgrade e Limpeza', 'price': Decimal('149.90'), 'description': 'Troca de componentes com limpeza interna e pasta térmica.'},
        {'name': 'Diagnóstico Avançado', 'price': Decimal('99.90'), 'description': 'Checklist de desempenho, temperatura e estabilidade.'},
    ]

    if request.method == 'POST':
        form_type = request.form.get('form_type', 'service_record')

        if form_type == 'maintenance_ticket':
            client_name = (request.form.get('maintenance_client_entry') or '').strip()
            client_phone = (request.form.get('maintenance_client_phone') or '').strip() or None
            maintenance_client_id = (request.form.get('maintenance_client_id') or '').strip()
            if maintenance_client_id:
                try:
                    maintenance_client = Client.query.get(int(maintenance_client_id))
                except ValueError:
                    maintenance_client = None
                if maintenance_client:
                    client_name = maintenance_client.name
                    client_phone = maintenance_client.phone or client_phone
            equipment = (request.form.get('maintenance_equipment') or '').strip()
            service_description = (request.form.get('maintenance_service_description') or '').strip()
            customer_report = (request.form.get('maintenance_customer_report') or '').strip() or None
            technical_diagnosis = (request.form.get('maintenance_technical_diagnosis') or '').strip() or None
            observations = (request.form.get('maintenance_observations') or '').strip() or None
            entry_date_raw = request.form.get('maintenance_entry_date')
            status = _normalize_maintenance_status(request.form.get('maintenance_status') or 'em_analise')

            checklist_items = [
                {'label': item, 'done': request.form.get(f'check_{idx}') == 'on'}
                for idx, item in enumerate(DEFAULT_MAINTENANCE_CHECKLIST)
            ]

            labor_cost_raw = (request.form.get('maintenance_labor_cost') or '0').strip()
            parts_items = []

            try:
                labor_cost = Decimal(labor_cost_raw or '0').quantize(Decimal('0.01'))
            except InvalidOperation:
                flash('Mão de obra inválida.', 'danger')
                return redirect(url_for('servicos'))

            if labor_cost < 0:
                flash('Mão de obra deve ser maior ou igual a zero.', 'danger')
                return redirect(url_for('servicos'))

            parts_items = _build_maintenance_parts_items(request.form, allow_single_fallback=True)

            client_name = client_name or 'Não informado'
            equipment = equipment or 'Não informado'
            service_description = service_description or 'A definir'

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
                    client_phone=client_phone,
                    equipment=equipment,
                    service_description=service_description,
                    customer_report=customer_report,
                    technical_diagnosis=technical_diagnosis,
                    observations=observations,
                    checklist_json=json.dumps(checklist_items, ensure_ascii=False),
                    parts_json=json.dumps(parts_items, ensure_ascii=False) if parts_items else None,
                    labor_cost=labor_cost,
                    entry_date=entry_date,
                    waiting_parts=status == 'aguardando_pecas',
                    status=status,
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
            performed_by_user_id=current.id if current else None,
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

    edit_ticket = None
    edit_ticket_id_raw = (request.args.get('edit_ticket_id') or '').strip()
    if edit_ticket_id_raw:
        try:
            edit_ticket = MaintenanceTicket.query.get(int(edit_ticket_id_raw))
        except ValueError:
            flash('Ordem de serviço inválida para edição.', 'danger')
            return redirect(url_for('servicos'))

        if edit_ticket is None:
            flash('Ordem de serviço não encontrada para edição.', 'danger')
            return redirect(url_for('servicos'))

    recent_services = ServiceRecord.query.order_by(ServiceRecord.created_at.desc()).all()
    maintenance_tickets = MaintenanceTicket.query.order_by(MaintenanceTicket.entry_date.desc()).limit(80).all()
    maintenance_parts_map = {}
    maintenance_checklist_map = {}
    for ticket in maintenance_tickets:
        maintenance_parts_map[ticket.id] = _load_json_list(ticket.parts_json)
        checklist_items = _load_json_list(ticket.checklist_json)

        done_labels = {
            (item.get('label') or '').strip()
            for item in checklist_items
            if item.get('done') and (item.get('label') or '').strip()
        }
        maintenance_checklist_map[ticket.id] = done_labels

    active_tickets = [
        ticket for ticket in maintenance_tickets
        if _normalize_maintenance_status(ticket.status) in {'em_analise', 'aguardando_pecas'}
    ]
    ready_for_pickup_tickets = [
        ticket for ticket in maintenance_tickets
        if _normalize_maintenance_status(ticket.status) == 'pronto_retirada'
    ]
    concluded_tickets = [
        ticket for ticket in maintenance_tickets
        if _normalize_maintenance_status(ticket.status) == 'concluido'
    ]

    linked_service_ids = {ticket.service_record_id for ticket in maintenance_tickets if ticket.service_record_id}
    standalone_services = [service for service in recent_services if service.id not in linked_service_ids]
    service_by_id = {service.id: service for service in recent_services}
    maintenance_service_map = {
        ticket.id: service_by_id.get(ticket.service_record_id)
        for ticket in maintenance_tickets
        if ticket.service_record_id
    }

    service_ids = [service.id for service in recent_services]
    service_charges = Charge.query.filter(Charge.service_id.in_(service_ids) if service_ids else db.false()).all()
    charges_by_service_id: dict[int, list[Charge]] = {}
    for charge in service_charges:
        if charge.service_id:
            charges_by_service_id.setdefault(charge.service_id, []).append(charge)

    sale_item_service_rows = []
    try:
        sale_item_service_rows = (
            db.session.query(SaleItem.service_record_id, Charge)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Charge, Charge.sale_id == Sale.id)
            .filter(
                SaleItem.service_record_id.in_(service_ids) if service_ids else db.false(),
                Sale.canceled.is_(False),
            )
            .all()
        )
    except SQLAlchemyError as exc:
        app.logger.warning('Falha ao carregar cobranças de serviços vinculadas à venda: %s', exc)
    seen_service_charge_pairs: set[tuple[int, int]] = set()
    for service_record_id, charge in sale_item_service_rows:
        if not service_record_id or not charge:
            continue
        pair_key = (int(service_record_id), int(charge.id))
        if pair_key in seen_service_charge_pairs:
            continue
        seen_service_charge_pairs.add(pair_key)
        charges_by_service_id.setdefault(int(service_record_id), []).append(charge)

    unified_service_history = []

    for ticket in ready_for_pickup_tickets:
        linked_service = service_by_id.get(ticket.service_record_id)
        linked_charges = charges_by_service_id.get(linked_service.id, []) if linked_service else []
        payment_ok = _is_service_finalized_by_payment(linked_service, linked_charges) if linked_service else False
        unified_service_history.append({
            'stage': 'pronto_retirada',
            'type': 'os_pronta',
            'date': ticket.exit_date or ticket.entry_date,
            'ticket': ticket,
            'service': linked_service,
            'service_name': linked_service.service_name if linked_service else f"OS #{ticket.id} - {ticket.service_description}",
            'client_name': linked_service.client_name if linked_service else ticket.client_name,
            'equipment': linked_service.equipment if linked_service else ticket.equipment,
            'total_price': Decimal(linked_service.total_price or 0) if linked_service else Decimal('0.00'),
            'delivery_status': linked_service.delivery_status if linked_service else 'aguardando',
            'payment_status': 'pago' if payment_ok else 'pendente',
            'delivered_at': linked_service.delivered_at if linked_service else None,
        })

    for ticket in concluded_tickets:
        linked_service = service_by_id.get(ticket.service_record_id)
        linked_charges = charges_by_service_id.get(linked_service.id, []) if linked_service else []
        payment_ok = _is_service_finalized_by_payment(linked_service, linked_charges) if linked_service else False
        unified_service_history.append({
            'stage': 'concluido',
            'type': 'os_concluida',
            'date': (linked_service.delivered_at if linked_service else None) or ticket.exit_date or ticket.entry_date,
            'ticket': ticket,
            'service': linked_service,
            'service_name': linked_service.service_name if linked_service else f"OS #{ticket.id} - {ticket.service_description}",
            'client_name': linked_service.client_name if linked_service else ticket.client_name,
            'equipment': linked_service.equipment if linked_service else ticket.equipment,
            'total_price': Decimal(linked_service.total_price or 0) if linked_service else Decimal('0.00'),
            'delivery_status': linked_service.delivery_status if linked_service else 'aguardando',
            'payment_status': 'pago' if payment_ok else 'pendente',
            'delivered_at': linked_service.delivered_at if linked_service else None,
        })

    for service in standalone_services:
        linked_charges = charges_by_service_id.get(service.id, [])
        payment_ok = _is_service_finalized_by_payment(service, linked_charges)
        stage = 'concluido' if service.delivery_status in {'entregue', 'desistencia'} else 'pronto_retirada'
        unified_service_history.append({
            'stage': stage,
            'type': 'servico_avulso',
            'date': service.delivered_at or service.created_at,
            'ticket': None,
            'service': service,
            'service_name': service.service_name,
            'client_name': service.client_name,
            'equipment': service.equipment,
            'total_price': Decimal(service.total_price or 0),
            'delivery_status': service.delivery_status,
            'payment_status': 'pago' if payment_ok else 'pendente',
            'delivered_at': service.delivered_at,
        })

    unified_service_history.sort(key=lambda item: item.get('date') or datetime.min, reverse=True)

    ready_ticket_finance_map = {}
    for ticket in ready_for_pickup_tickets:
        linked_service = maintenance_service_map.get(ticket.id)
        if not linked_service:
            continue
        linked_charges = charges_by_service_id.get(linked_service.id, [])
        ready_ticket_finance_map[ticket.id] = {
            'payment_ok': _is_service_finalized_by_payment(linked_service, linked_charges),
            'delivery_status': linked_service.delivery_status,
            'delivered_at': linked_service.delivered_at,
        }

    clients = Client.query.order_by(Client.name.asc()).all()
    products = Product.query.filter(Product.active.is_(True), Product.category == 'Peça', Product.stock > 0).order_by(Product.name.asc()).all()
    return render_template(
        'services.html',
        services=service_catalog,
        maintenance_tickets=maintenance_tickets,
        active_tickets=active_tickets,
        ready_for_pickup_tickets=ready_for_pickup_tickets,
        concluded_tickets=concluded_tickets,
        maintenance_status_labels=MAINTENANCE_STATUS_LABELS,
        maintenance_status_options=MAINTENANCE_STATUS_OPTIONS,
        maintenance_checklist=DEFAULT_MAINTENANCE_CHECKLIST,
        maintenance_parts_map=maintenance_parts_map,
        maintenance_checklist_map=maintenance_checklist_map,
        maintenance_service_map=maintenance_service_map,
        service_delivery_status_labels=SERVICE_DELIVERY_STATUS_LABELS,
        edit_ticket=edit_ticket,
        unified_service_history=unified_service_history,
        clients=clients,
        products=products,
        payment_methods=PAYMENT_METHODS,
    )


@app.route('/manutencoes/<int:ticket_id>/atualizar', methods=['POST'])
@_login_required
def atualizar_manutencao(ticket_id: int):
    ticket = MaintenanceTicket.query.get_or_404(ticket_id)
    action = (request.form.get('action') or '').strip()
    current = _current_user()

    if action == 'finalizar':
        status = 'pronto_retirada'
        ticket.status = status
        ticket.waiting_parts = False
        ticket.exit_date = datetime.utcnow()

        try:
            _apply_ticket_parts_stock(ticket)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
            return redirect(url_for('servicos'))

        _ensure_service_record_from_ticket(ticket, current)

        db.session.commit()
        flash('OS finalizada, enviada ao histórico e pronta para cobrança/recibo.', 'success')
        return redirect(url_for('servicos'))

    if action == 'editar':
        previous_parts_items = _load_json_list(ticket.parts_json)

        ticket.client_name = (request.form.get('maintenance_client_entry') or '').strip() or 'Não informado'
        ticket.client_phone = (request.form.get('maintenance_client_phone') or '').strip() or None
        ticket.equipment = (request.form.get('maintenance_equipment') or '').strip() or 'Não informado'
        ticket.service_description = (request.form.get('maintenance_service_description') or '').strip() or 'A definir'
        ticket.customer_report = (request.form.get('maintenance_customer_report') or '').strip() or None
        ticket.technical_diagnosis = (request.form.get('maintenance_technical_diagnosis') or '').strip() or None
        ticket.observations = (request.form.get('maintenance_observations') or '').strip() or None

        status = _normalize_maintenance_status(request.form.get('maintenance_status') or request.form.get('status') or ticket.status)

        labor_cost_raw = (request.form.get('maintenance_labor_cost') or '0').strip()
        try:
            labor_cost = Decimal(labor_cost_raw or '0').quantize(Decimal('0.01'))
        except InvalidOperation:
            flash('Mão de obra inválida.', 'danger')
            return redirect(url_for('servicos'))
        if labor_cost < 0:
            flash('Mão de obra deve ser maior ou igual a zero.', 'danger')
            return redirect(url_for('servicos'))
        ticket.labor_cost = labor_cost

        checklist_items = [
            {'label': item, 'done': request.form.get(f'check_{idx}') == 'on'}
            for idx, item in enumerate(DEFAULT_MAINTENANCE_CHECKLIST)
        ]
        ticket.checklist_json = json.dumps(checklist_items, ensure_ascii=False)

        parts_items = _build_maintenance_parts_items(request.form)

        ticket.parts_json = json.dumps(parts_items, ensure_ascii=False) if parts_items else None

        if ticket.parts_stock_applied:
            try:
                _sync_ticket_parts_stock_delta(previous_parts_items, parts_items)
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), 'danger')
                return redirect(url_for('servicos'))

        entry_date_raw = request.form.get('maintenance_entry_date')
        if entry_date_raw:
            try:
                ticket.entry_date = datetime.fromisoformat(entry_date_raw)
            except ValueError:
                flash('Data de entrada inválida.', 'danger')
                return redirect(url_for('servicos', edit_ticket_id=ticket.id))

        exit_date_raw = request.form.get('exit_date')
        if status == 'pronto_retirada' and not exit_date_raw:
            ticket.exit_date = datetime.utcnow()
        elif exit_date_raw:
            try:
                ticket.exit_date = datetime.fromisoformat(exit_date_raw)
            except ValueError:
                flash('Data de saída inválida.', 'danger')
                return redirect(url_for('servicos'))
        elif status != 'pronto_retirada':
            ticket.exit_date = None

        ticket.status = status
        ticket.waiting_parts = status == 'aguardando_pecas'
        if status == 'pronto_retirada':
            try:
                _apply_ticket_parts_stock(ticket)
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), 'danger')
                return redirect(url_for('servicos'))
            _ensure_service_record_from_ticket(ticket, current)

        _sync_service_record_from_ticket(ticket)
        db.session.commit()
        flash('OS atualizada com sucesso!', 'success')
        return redirect(url_for('servicos'))

    status = _normalize_maintenance_status(request.form.get('maintenance_status') or request.form.get('status') or ticket.status)
    exit_date_raw = request.form.get('exit_date')
    if status == 'pronto_retirada' and not exit_date_raw:
        ticket.exit_date = datetime.utcnow()
    elif exit_date_raw:
        try:
            ticket.exit_date = datetime.fromisoformat(exit_date_raw)
        except ValueError:
            flash('Data de saída inválida.', 'danger')
            return redirect(url_for('servicos'))
    elif status != 'pronto_retirada':
        ticket.exit_date = None

    ticket.status = status
    ticket.waiting_parts = status == 'aguardando_pecas'
    db.session.commit()
    flash('Status da manutenção atualizado!', 'success')
    return redirect(url_for('servicos'))




@app.route('/servicos/<int:service_id>/confirmar-retirada', methods=['POST'])
@_login_required
def confirmar_retirada_servico(service_id: int):
    service = ServiceRecord.query.get_or_404(service_id)
    action = (request.form.get('action') or 'entregue').strip()

    if action == 'desistencia':
        service.delivery_status = 'desistencia'
    else:
        service.delivery_status = 'entregue'

    service.delivered_at = datetime.utcnow()
    if service.delivery_status != 'desistencia':
        service.canceled_at = None
    else:
        service.canceled_at = datetime.utcnow()

    _sync_service_ticket_status(service.id)
    db.session.commit()
    flash('Fluxo de retirada atualizado com sucesso!', 'success')
    return redirect(url_for('servicos'))



@app.route('/servicos/<int:service_id>/editar', methods=['POST'])
@_login_required
def editar_servico(service_id: int):
    service = ServiceRecord.query.get_or_404(service_id)

    service_name = (request.form.get('service_name') or '').strip()
    client_name = (request.form.get('client_name') or '').strip()
    equipment = (request.form.get('equipment') or '').strip()
    notes = (request.form.get('notes') or '').strip() or None

    if not service_name or not client_name or not equipment:
        flash('Preencha serviço, cliente e equipamento para editar.', 'danger')
        return redirect(url_for('servicos'))

    try:
        total_price = Decimal((request.form.get('total_price') or '0').replace(',', '.')).quantize(Decimal('0.01'))
        cost = Decimal((request.form.get('cost') or '0').replace(',', '.')).quantize(Decimal('0.01'))
    except InvalidOperation:
        flash('Valores inválidos para edição do serviço.', 'danger')
        return redirect(url_for('servicos'))

    if total_price < 0 or cost < 0:
        flash('Preço e custo devem ser maiores ou iguais a zero.', 'danger')
        return redirect(url_for('servicos'))

    service.service_name = service_name
    service.client_name = client_name
    service.equipment = equipment
    service.total_price = total_price
    service.cost = cost
    service.notes = notes

    db.session.commit()
    flash('Serviço atualizado com sucesso!', 'success')
    return redirect(url_for('servicos'))


@app.route('/servicos/<int:service_id>/excluir', methods=['POST'])
@_login_required
def excluir_servico(service_id: int):
    service = ServiceRecord.query.get_or_404(service_id)

    linked_tickets = MaintenanceTicket.query.filter_by(service_record_id=service.id).all()
    for ticket in linked_tickets:
        ticket.service_record_id = None
        normalized_status = _normalize_maintenance_status(ticket.status)
        if normalized_status in {'pronto_retirada', 'concluido'}:
            ticket.status = 'em_analise'
            ticket.exit_date = None

    Charge.query.filter_by(service_id=service.id).update(
        {Charge.service_id: None},
        synchronize_session=False,
    )

    db.session.delete(service)
    db.session.commit()
    flash('Serviço excluído com sucesso!', 'success')
    return redirect(url_for('servicos'))


@app.route('/dashboard/custos-fixos', methods=['POST'])
@_login_required
def cadastrar_custo_fixo():
    """
     - Recebe os dados do formulário para criar um novo custo fixo.
     - Valida os dados de entrada (descrição e valor).
     - Se os dados forem válidos, cria um novo registro de custo fixo no banco
    """
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


@app.route('/dashboard/custos-fixos/<int:fixed_cost_id>/editar', methods=['POST'])
@_login_required
def editar_custo_fixo(fixed_cost_id: int):
    fixed_cost = FixedCost.query.get_or_404(fixed_cost_id)
    description = (request.form.get('description') or '').strip()
    amount_raw = (request.form.get('amount') or '0').strip().replace(',', '.')

    if not description:
        flash('Informe a descrição do custo fixo.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        amount = Decimal(amount_raw)
    except InvalidOperation:
        flash('Valor inválido para custo fixo.', 'danger')
        return redirect(url_for('dashboard'))

    if amount < 0:
        flash('O valor do custo fixo não pode ser negativo.', 'danger')
        return redirect(url_for('dashboard'))

    fixed_cost.description = description
    fixed_cost.amount = amount.quantize(Decimal('0.01'))
    db.session.commit()
    flash('Custo fixo atualizado com sucesso!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/dashboard/custos-fixos/<int:fixed_cost_id>/excluir', methods=['POST'])
@_login_required
def excluir_custo_fixo(fixed_cost_id: int):
    fixed_cost = FixedCost.query.get_or_404(fixed_cost_id)
    db.session.delete(fixed_cost)
    db.session.commit()
    flash('Custo fixo excluído com sucesso!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/clientes', methods=['GET', 'POST'])
@_login_required
def clientes():
    if request.method == 'POST':
        saved, message, category = _persist_client_from_form(request.form)
        flash(message, category)
        if saved:
            db.session.commit()
        return redirect(url_for('clientes'))

    service_counts = dict(
        db.session.query(Sale.client_id, db.func.count(Sale.id))
        .filter(Sale.canceled.is_(False))
        .group_by(Sale.client_id)
        .all()
    )

    clients = (
        db.session.query(Client)
        .outerjoin(Sale, Sale.client_id == Client.id)
        .filter(Client.active.is_(True))
        .group_by(Client.id)
        .order_by(db.func.lower(Client.name).asc())
        .all()
    )
    clients_summary = []
    for client in clients:
        sales = Sale.query.filter_by(client_id=client.id).order_by(Sale.created_at.desc()).limit(5).all()
        pending_charges = (
            Charge.query
            .join(Sale, Charge.sale_id == Sale.id)
            .filter(Sale.client_id == client.id, Charge.status == 'pendente')
            .order_by(Charge.id.desc())
            .all()
        )
        total_spent = db.session.query(db.func.coalesce(db.func.sum(Sale.total), 0)).filter(
            Sale.client_id == client.id,
            Sale.canceled == False,
        ).scalar()

        clients_summary.append({
            'id': client.id,
            'name': client.name,
            'initial': (client.name[:1] if client.name else '#').upper(),
            'initials': ''.join([part[0] for part in client.name.split()[:2]]).upper() if client.name else '--',
            'cpf': client.cpf,
            'phone': client.phone,
            'email': client.email,
            'service_count': service_counts.get(client.id, 0),
            'total_spent': total_spent or Decimal('0.00'),
            'sales': sales,
            'pending_charges': pending_charges,
        })

    edit_client_id = request.args.get('edit_client_id', type=int)
    editing_client = next((item for item in clients_summary if item['id'] == edit_client_id), None)

    return render_template('clients.html', clients=clients_summary, editing_client=editing_client)


def _persist_client_from_form(form_data):

    raw_client_id = (form_data.get('client_id') or '').strip()
    client_id = int(raw_client_id) if raw_client_id.isdigit() else None
    client = Client.query.get_or_404(client_id) if client_id else None

    name = (form_data.get('name') or '').strip()
    cpf = (form_data.get('cpf') or '').strip() or None
    if not name:
        return False, 'Informe o nome do cliente.', 'danger'

    duplicate_cpf_query = Client.query.filter(Client.cpf == cpf)
    duplicate_name_query = Client.query.filter(db.func.lower(Client.name) == name.lower())
    if client:
        duplicate_cpf_query = duplicate_cpf_query.filter(Client.id != client.id)
        duplicate_name_query = duplicate_name_query.filter(Client.id != client.id)

    if cpf and duplicate_cpf_query.first():
        return False, 'Este CPF/CNPJ já está cadastrado para outro cliente.', 'danger'

    if duplicate_name_query.first():
        return False, f'O nome "{name}" já está cadastrado. Atualize o cliente existente.', 'danger'

    client_dto = ClientDTO(name=name, cpf=cpf, phone=form_data.get('phone'), email=form_data.get('email'))
    client_dto.validate()

    if client:
        client.name = client_dto.name
        client.cpf = client_dto.cpf
        client.phone = client_dto.phone
        client.email = client_dto.email
        return True, 'Cliente atualizado com sucesso!', 'success'

    client_service.create(name=client_dto.name, cpf=client_dto.cpf, phone=client_dto.phone, email=client_dto.email)
    return True, 'Cliente cadastrado com sucesso!', 'success'


@app.route('/clientes/mesclar', methods=['POST'])
@_login_required
def mesclar_clientes():
    source_id = request.form.get('source_client_id', type=int)
    target_id = request.form.get('target_client_id', type=int)
    if not source_id or not target_id or source_id == target_id:
        flash('Selecione dois clientes diferentes para mesclar.', 'danger')
        return redirect(url_for('clientes'))

    source = Client.query.get_or_404(source_id)
    target = Client.query.get_or_404(target_id)

    Sale.query.filter_by(client_id=source.id).update({'client_id': target.id})
    source_name = source.name
    db.session.delete(source)
    db.session.commit()
    flash(f'Cliente {source_name} foi mesclado em {target.name} com o histórico transferido.', 'success')
    return redirect(url_for('clientes'))


@app.route('/clientes/<int:client_id>/editar', methods=['GET', 'POST'])
@_login_required
def editar_cliente(client_id: int):
    client = Client.query.get_or_404(client_id)

    if request.method == 'POST':
        payload = request.form.to_dict(flat=True)
        payload['client_id'] = str(client.id)
        saved, message, category = _persist_client_from_form(payload)
        flash(message, category)
        if saved:
            db.session.commit()
        return redirect(url_for('clientes'))

    return redirect(url_for('clientes', edit_client_id=client.id))


@app.route('/clientes/<int:client_id>/remover', methods=['POST'])
@_login_required
def remover_cliente(client_id: int):
    client = Client.query.get_or_404(client_id)
    active_sales = Sale.query.filter_by(client_id=client.id, canceled=False).first()
    if active_sales:
        flash('Não é possível remover cliente com vendas ativas.', 'danger')
        return redirect(url_for('clientes'))

    client_service.soft_delete(client)
    db.session.commit()
    flash('Cliente removido com sucesso!', 'success')
    return redirect(url_for('clientes'))


@app.route('/vendas', methods=['GET', 'POST'])
@_login_required
def vendas():
    current = _current_user()
    products = buscar_pecas_disponiveis(Product)
    clients = db.session.query(Client).filter(Client.active.is_(True)).group_by(Client.id).order_by(db.func.lower(Client.name)).all()
    services = ServiceRecord.query.order_by(ServiceRecord.created_at.desc()).all()
    latest_assemblies = (
        ComputerAssembly.query
        .filter(ComputerAssembly.canceled.is_(False))
        .order_by(ComputerAssembly.created_at.desc())
        .all()
    )
    assembly_total_by_product = {}
    for assembly in latest_assemblies:
        if assembly.id_computador in assembly_total_by_product:
            continue

        pieces_sale_total = Decimal('0.00')
        for comp in assembly.composicao:
            if not comp.peca:
                continue
            pieces_sale_total += Decimal(comp.quantidade_utilizada or 0) * Decimal(comp.peca.price or 0)

        technical_services_total = (
            Decimal(assembly.bios_service_cost or 0)
            + Decimal(assembly.stress_test_cost or 0)
            + Decimal(assembly.os_install_cost or 0)
        )

        # Valor importado no PDV para montagem: peças + serviços técnicos adicionais.
        assembly_total_by_product[assembly.id_computador] = (pieces_sale_total + technical_services_total).quantize(Decimal('0.01'))

    if request.method == 'POST':
        sale_name = (request.form.get('sale_name') or '').strip()
        client_id_raw = (request.form.get('client_id') or '').strip()

        try:
            client_id = int(client_id_raw)
        except ValueError:
            flash('Selecione um cliente válido para finalizar a venda.', 'danger')
            return redirect(url_for('vendas'))

        selected_client = Client.query.get(client_id)
        if not selected_client or not selected_client.active:
            flash('O cliente selecionado não está mais disponível. Atualize a página e tente novamente.', 'danger')
            return redirect(url_for('vendas'))

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
            service_placeholder = Product.query.filter_by(name='Serviço avulso').first()
            if not service_placeholder:
                service_placeholder = Product(
                    name='Serviço avulso',
                    category='Serviço',
                    stock=0,
                    price=Decimal('0.00'),
                    cost_price=Decimal('0.00'),
                    active=False,
                )
                db.session.add(service_placeholder)
                db.session.flush()
            else:
                service_placeholder.category = 'Serviço'
                service_placeholder.stock = 0
                service_placeholder.price = Decimal('0.00')
                service_placeholder.cost_price = Decimal('0.00')
                service_placeholder.active = False
            anchor_product_id = service_placeholder.id

        payment_method = (request.form.get('payment_method') or 'pix').strip()
        if payment_method not in PAYMENT_METHOD_LABELS:
            payment_method = 'pix'

        payment_flow = 'aprazo' if request.form.get('payment_flow_aprazo') == 'on' else 'avista'

        due_date = None
        installment_due_dates: list[date] = []
        if payment_flow == 'aprazo':
            due_date_raw = (request.form.get('due_date') or '').strip()
            if due_date_raw:
                try:
                    due_date = _parse_date_input(due_date_raw)
                except ValueError as exc:
                    flash(str(exc), 'danger')
                    return redirect(url_for('vendas'))
            else:
                due_date = (datetime.utcnow() + timedelta(days=30)).date()

            due_dates_raw = request.form.getlist('installment_due_date[]')
            for idx, raw_due_date in enumerate(due_dates_raw, start=1):
                due_raw = (raw_due_date or '').strip()
                if not due_raw:
                    continue
                try:
                    parsed_due = _parse_date_input(due_raw)
                except ValueError:
                    flash(f'Data de vencimento inválida na parcela {idx}.', 'danger')
                    return redirect(url_for('vendas'))
                installment_due_dates.append(parsed_due)

        try:
            sale = Sale(
                sale_name=sale_name,
                client_id=client_id,
                product_id=anchor_product_id,
                quantity=1,
                subtotal=subtotal,
                discount_amount=discount_amount,
                total=total,
                payment_method=payment_method,
                performed_by_user_id=current.id if current else None,
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
                        service_record_id=item.get('service_record_id'),
                        quantity=item['quantity'],
                        unit_price=item['unit_price'],
                        unit_cost=item['unit_cost'],
                        line_total=item['line_total'],
                    )
                )

            _deactivate_sold_assembled_products(sale)

            charge_reference = (request.form.get('charge_reference') or '').strip() or f'VENDA-{sale.id}'
            installment_count_raw = (request.form.get('installment_count') or '1').strip()
            try:
                installment_count = max(1, int(installment_count_raw or '1'))
            except ValueError:
                installment_count = 1
            is_installment = payment_flow == 'aprazo' and installment_count > 1
            if payment_flow != 'aprazo':
                installment_count = 1

            charge = Charge(
                sale_id=sale.id,
                mercado_pago_reference=charge_reference,
                due_date=due_date,
                amount=total,
                amount_paid=total if payment_flow == 'avista' else Decimal('0.00'),
                status='confirmado' if payment_flow == 'avista' else 'pendente',
                payment_method=payment_method,
                is_installment=is_installment,
                installment_count=installment_count,
                installment_value=(total / Decimal(installment_count)).quantize(Decimal('0.01')) if installment_count > 0 else total,
                payment_confirmed_at=datetime.utcnow() if payment_flow == 'avista' else None,
            )
            db.session.add(charge)
            db.session.flush()
            _ensure_charge_installments(charge, due_dates=installment_due_dates)
            _normalize_charge_status(charge)

            if sale and _is_sale_finalized_by_payment(sale, [charge]):
                _delete_paid_sold_assembled_products(sale)

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash('Não foi possível finalizar a venda devido a uma inconsistência de dados. Confira os itens e tente novamente.', 'danger')
            return redirect(url_for('vendas'))

        flash('Venda registrada com sucesso e enviada para o fluxo financeiro!', 'success')
        return redirect(url_for('vendas', print_sale_id=sale.id))

    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    finance_charges = Charge.query.order_by(Charge.id.desc()).all()

    finance_installments: dict[int, list[ChargeInstallment]] = {}
    for charge in finance_charges:
        _ensure_charge_installments(charge)
        finance_installments[charge.id] = _charge_installments(charge)
    db.session.flush()

    today = datetime.utcnow().date()
    next_week = today + timedelta(days=7)
    paid_today = Decimal('0.00')
    cash_pending_total = Decimal('0.00')
    cash_overdue_total = Decimal('0.00')
    charge_overdue_total = Decimal('0.00')
    charge_pending_total = Decimal('0.00')
    charge_received_total = Decimal('0.00')

    for charge in finance_charges:
        total_amount = _charge_total_amount(charge)
        paid_amount = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
        balance = _charge_balance(charge)
        status_ui = _charge_ui_status(charge)

        if charge.payment_confirmed_at and charge.payment_confirmed_at.date() == today:
            paid_today += paid_amount

        if charge.status != 'cancelado' and balance > 0:
            cash_pending_total += balance
            if charge.due_date and charge.due_date < today:
                cash_overdue_total += balance

        if status_ui == 'vencido' and balance > 0:
            charge_overdue_total += balance
        elif status_ui == 'pendente' and charge.due_date and today <= charge.due_date <= next_week and balance > 0:
            charge_pending_total += balance
        if status_ui == 'recebido':
            charge_received_total += total_amount

    finalized_sale_ids: set[int] = set()
    sale_ids = [sale.id for sale in sales]
    if sale_ids:
        charges = Charge.query.filter(Charge.sale_id.in_(sale_ids)).all()
        charges_by_sale_id: dict[int, list[Charge]] = {}
        for charge in charges:
            if not charge.sale_id:
                continue
            charges_by_sale_id.setdefault(charge.sale_id, []).append(charge)

        for sale in sales:
            if _is_sale_finalized_by_payment(sale, charges_by_sale_id.get(sale.id, [])):
                finalized_sale_ids.add(sale.id)

    assembled_product_id_raw = (request.args.get('assembled_product_id') or '').strip()
    prefill_product = None
    if assembled_product_id_raw:
        try:
            prefill_product = Product.query.get(int(assembled_product_id_raw))
        except ValueError:
            prefill_product = None

    return render_template(
        'sales.html',
        sales=sales,
        products=products,
        clients=clients,
        services=services,
        finalized_sale_ids=finalized_sale_ids,
        finance_charges=finance_charges,
        paid_today=paid_today,
        cash_pending_total=cash_pending_total,
        cash_overdue_total=cash_overdue_total,
        charge_overdue_total=charge_overdue_total,
        charge_pending_total=charge_pending_total,
        charge_received_total=charge_received_total,
        charge_ui_status=_charge_ui_status,
        charge_balance=_charge_balance,
        charge_total_amount=_charge_total_amount,
        payment_method_labels=PAYMENT_METHOD_LABELS,
        finance_installments=finance_installments,
        prefill_product=prefill_product,
        calcular_margem_lucro=calcular_margem_lucro,
        assembly_total_by_product=assembly_total_by_product,
    )


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
                    if line.product.category == 'Computador':
                        line.product.active = True
        elif sale.product:
            sale.product.stock += sale.quantity
            if sale.product.category == 'Computador':
                sale.product.active = True
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


def _parse_date_input(value: str | None):
    raw = (value or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError('Data de vencimento inválida. Use o formato AAAA-MM-DD.')


def _charge_total_amount(charge: Charge) -> Decimal:
    amount = Decimal(charge.amount or 0).quantize(Decimal('0.01'))
    if amount > 0:
        return amount
    if charge.sale:
        return Decimal(charge.sale.total or 0).quantize(Decimal('0.01'))
    if charge.service:
        return Decimal(charge.service.total_price or 0).quantize(Decimal('0.01'))
    return Decimal('0.00')


def _charge_installments(charge: Charge) -> list[ChargeInstallment]:
    installments = sorted(charge.installments or [], key=lambda item: item.installment_number)
    return installments


def _ensure_charge_installments(charge: Charge, due_dates: list[date] | None = None):
    count = max(1, int(charge.installment_count or 1))
    amount_total = _charge_total_amount(charge)
    existing = _charge_installments(charge)

    if count == 1:
        for item in existing:
            db.session.delete(item)
        charge.installment_count = 1
        charge.installment_value = amount_total.quantize(Decimal('0.01'))
        return

    if existing and len(existing) == count and not due_dates:
        return

    for item in existing:
        db.session.delete(item)

    base_due = charge.due_date or datetime.utcnow().date()
    base_value = (amount_total / Decimal(count)).quantize(Decimal('0.01'))
    remainder = (amount_total - (base_value * Decimal(count))).quantize(Decimal('0.01'))

    for number in range(1, count + 1):
        parcel_amount = base_value
        if number == count:
            parcel_amount = (parcel_amount + remainder).quantize(Decimal('0.01'))
        if due_dates and len(due_dates) >= number and due_dates[number - 1]:
            due_date = due_dates[number - 1]
        else:
            due_date = base_due + timedelta(days=(number - 1) * 30)
        db.session.add(ChargeInstallment(
            charge_id=charge.id,
            installment_number=number,
            due_date=due_date,
            amount=parcel_amount,
            amount_paid=Decimal('0.00'),
            status='pendente',
        ))

    charge.installment_value = base_value


def _refresh_charge_from_installments(charge: Charge):
    installments = _charge_installments(charge)
    if not installments:
        return

    amount = Decimal('0.00')
    paid = Decimal('0.00')
    due_dates = []

    for item in installments:
        amount += Decimal(item.amount or 0)
        paid += Decimal(item.amount_paid or 0)
        if item.due_date:
            due_dates.append(item.due_date)

    charge.amount = amount.quantize(Decimal('0.01'))
    charge.amount_paid = paid.quantize(Decimal('0.01'))
    if due_dates:
        charge.due_date = min(due_dates)


def _charge_balance(charge: Charge) -> Decimal:
    total = _charge_total_amount(charge)
    paid = Decimal(charge.amount_paid or 0)
    return (total - paid).quantize(Decimal('0.01'))


def _normalize_charge_status(charge: Charge):
    installments = _charge_installments(charge)
    if charge.status == 'cancelado':
        charge.payment_confirmed_at = None
        for item in installments:
            item.status = 'cancelado'
            item.payment_confirmed_at = None
        return

    if installments:
        for item in installments:
            item_total = Decimal(item.amount or 0).quantize(Decimal('0.01'))
            item_paid = Decimal(item.amount_paid or 0).quantize(Decimal('0.01'))
            if item_paid >= item_total:
                item.status = 'confirmado'
                item.payment_confirmed_at = item.payment_confirmed_at or datetime.utcnow()
            elif item_paid > 0:
                item.status = 'parcial'
                item.payment_confirmed_at = None
            elif item.due_date and item.due_date < datetime.utcnow().date():
                item.status = 'atrasado'
                item.payment_confirmed_at = None
            else:
                item.status = 'pendente'
                item.payment_confirmed_at = None
        _refresh_charge_from_installments(charge)

    balance = _charge_balance(charge)
    if balance <= 0:
        charge.status = 'confirmado'
        charge.payment_confirmed_at = charge.payment_confirmed_at or datetime.utcnow()
    elif Decimal(charge.amount_paid or 0) > 0:
        charge.status = 'parcial'
        charge.payment_confirmed_at = None
    elif charge.due_date and charge.due_date < datetime.utcnow().date():
        charge.status = 'atrasado'
        charge.payment_confirmed_at = None
    else:
        charge.status = 'pendente'
        charge.payment_confirmed_at = None


def _charge_ui_status(charge: Charge):
    if charge.status == 'cancelado':
        return 'cancelado'

    balance = _charge_balance(charge)
    if balance <= 0:
        return 'recebido'

    if charge.due_date and charge.due_date < datetime.utcnow().date():
        return 'vencido'

    return 'pendente'


def _is_sale_finalized_by_payment(sale: Sale, charges: list[Charge]) -> bool:
    has_active_charge = False
    for charge in charges:
        if charge.status == 'cancelado':
            continue
        has_active_charge = True

        charge_total = _charge_total_amount(charge)
        paid_amount = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
        if paid_amount < charge_total:
            return False
    return has_active_charge


def _is_service_finalized_by_payment(service: ServiceRecord, charges: list[Charge]) -> bool:
    has_active_charge = False
    for charge in charges:
        if charge.status == 'cancelado':
            continue
        has_active_charge = True

        charge_total = _charge_total_amount(charge)
        paid_amount = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
        if paid_amount < charge_total:
            return False
    return has_active_charge



def _sync_service_ticket_status(service_id: int | None):
    if not service_id:
        return
    service = ServiceRecord.query.get(service_id)
    if not service:
        return

    ticket = MaintenanceTicket.query.filter_by(service_record_id=service_id).first()
    if not ticket:
        return

    if service.delivery_status in {'entregue', 'desistencia'}:
        ticket.status = 'concluido'
        if not ticket.exit_date:
            ticket.exit_date = service.delivered_at or datetime.utcnow()
    elif _normalize_maintenance_status(ticket.status) == 'concluido':
        ticket.status = 'pronto_retirada'


def _is_service_fully_delivered(service: ServiceRecord, charges: list[Charge]) -> bool:
    return _is_service_finalized_by_payment(service, charges) and service.delivery_status == 'entregue'


def _deactivate_sold_assembled_products(sale: Sale):
    if not sale:
        return

    for line in sale.items or []:
        if line.line_type != 'produto' or not line.product:
            continue
        if line.product.category != 'Computador':
            continue
        line.product.active = False


def _delete_paid_sold_assembled_products(sale: Sale):
    if not sale:
        return

    sale_items = sale.items or []
    for line in sale_items:
        if line.line_type != 'produto' or not line.product:
            continue
        if line.product.category != 'Computador':
            continue

        product = line.product
        if (product.stock or 0) > 0:
            continue

        sale_line_refs = SaleItem.query.filter_by(product_id=product.id).all()
        for sale_line in sale_line_refs:
            sale_line.product_id = None

        assembly_records = ComputerAssembly.query.filter_by(id_computador=product.id).all()
        for assembly in assembly_records:
            db.session.delete(assembly)

        db.session.delete(product)




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

        sale_ref = Sale.query.get(sale_id) if sale_id else None
        service_ref = ServiceRecord.query.get(service_id) if service_id else None

        try:
            due_date = _parse_date_input(request.form.get('due_date'))
            amount_paid = Decimal((request.form.get('amount_paid') or '0').replace(',', '.')).quantize(Decimal('0.01'))
            discount_amount = Decimal((request.form.get('charge_discount') or '0').replace(',', '.')).quantize(Decimal('0.01'))
        except (ValueError, InvalidOperation) as exc:
            flash(str(exc) if isinstance(exc, ValueError) else 'Valor inválido para cobrança.', 'danger')
            return redirect(url_for('cobrancas'))

        if amount_paid < 0 or discount_amount < 0:
            flash('Valores de cobrança não podem ser negativos.', 'danger')
            return redirect(url_for('cobrancas'))

        source_total = Decimal(sale_ref.total or 0) if sale_ref else Decimal(service_ref.total_price or 0)
        amount = (source_total - discount_amount).quantize(Decimal('0.01'))
        if amount < 0:
            flash('O desconto não pode ser maior que o valor total da venda/serviço.', 'danger')
            return redirect(url_for('cobrancas'))

        is_installment = request.form.get('is_installment') == 'on'
        installment_count_raw = (request.form.get('installment_count') or '1').strip()
        try:
            installment_count = int(installment_count_raw or '1')
        except ValueError:
            installment_count = 1
        installment_count = max(1, installment_count)
        if not is_installment:
            installment_count = 1
        installment_base = amount
        if installment_base <= 0 and sale_id:
            sale_ref = Sale.query.get(sale_id)
            installment_base = Decimal(sale_ref.total or 0) if sale_ref else Decimal('0')
        if installment_base <= 0 and service_id:
            service_ref = ServiceRecord.query.get(service_id)
            installment_base = Decimal(service_ref.total_price or 0) if service_ref else Decimal('0')
        installment_value = (installment_base / Decimal(installment_count or 1)).quantize(Decimal('0.01')) if installment_base > 0 else Decimal('0.00')

        charge = Charge(
            sale_id=sale_id,
            service_id=service_id,
            mercado_pago_reference=request.form['mercado_pago_reference'],
            status=request.form['status'],
            payment_method=request.form['payment_method'],
            due_date=due_date,
            amount=amount,
            amount_paid=amount_paid,
            is_installment=is_installment,
            installment_count=installment_count,
            installment_value=installment_value,
        )
        db.session.add(charge)
        db.session.flush()
        _ensure_charge_installments(charge)
        _normalize_charge_status(charge)

        if charge.service_id and charge.status == 'confirmado':
            _sync_service_ticket_status(charge.service_id)

        db.session.commit()
        flash('Cobrança registrada com sucesso!', 'success')
        return redirect(url_for('cobrancas'))

    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    maintenance_service_rows = (
        db.session.query(MaintenanceTicket, ServiceRecord)
        .join(ServiceRecord, ServiceRecord.id == MaintenanceTicket.service_record_id)
        .order_by(MaintenanceTicket.id.desc())
        .all()
    )
    maintenance_service_ids = {service.id for _, service in maintenance_service_rows}
    standalone_services = (
        ServiceRecord.query
        .filter(~ServiceRecord.id.in_(maintenance_service_ids) if maintenance_service_ids else db.true())
        .order_by(ServiceRecord.created_at.desc())
        .all()
    )
    charges = Charge.query.order_by(Charge.id.desc()).all()

    today = datetime.utcnow().date()
    next_week = today + timedelta(days=7)
    overdue_total = Decimal('0.00')
    pending_total = Decimal('0.00')
    received_total = Decimal('0.00')

    for charge in charges:
        status_ui = _charge_ui_status(charge)
        balance = _charge_balance(charge)
        total_amount = _charge_total_amount(charge)
        if status_ui == 'vencido' and balance > 0:
            overdue_total += balance
        elif status_ui == 'pendente' and charge.due_date and today <= charge.due_date <= next_week and balance > 0:
            pending_total += balance
        if status_ui == 'recebido':
            received_total += total_amount

    return render_template(
        'charges.html',
        charges=charges,
        sales=sales,
        maintenance_service_rows=maintenance_service_rows,
        standalone_services=standalone_services,
        payment_methods=PAYMENT_METHODS,
        overdue_total=overdue_total,
        pending_total=pending_total,
        received_total=received_total,
        today=today,
        charge_ui_status=_charge_ui_status,
        charge_balance=_charge_balance,
        charge_total_amount=_charge_total_amount,
    )


@app.route('/cobrancas/<int:charge_id>/editar', methods=['POST'])
@_login_required
def editar_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    charge.payment_method = request.form['payment_method']
    charge.status = request.form['status']
    charge.mercado_pago_reference = (request.form.get('mercado_pago_reference') or '').strip()
    charge.is_installment = request.form.get('is_installment') == 'on'

    if not charge.mercado_pago_reference:
        flash('Informe a referência da cobrança.', 'danger')
        return redirect(url_for('cobrancas'))

    try:
        charge.due_date = _parse_date_input(request.form.get('due_date'))
        charge.amount = Decimal((request.form.get('amount') or '0').replace(',', '.')).quantize(Decimal('0.01'))
        paid_increment = Decimal((request.form.get('amount_paid') or '0').replace(',', '.')).quantize(Decimal('0.01'))
    except (ValueError, InvalidOperation) as exc:
        flash(str(exc) if isinstance(exc, ValueError) else 'Valor inválido para cobrança.', 'danger')
        return redirect(url_for('cobrancas'))

    if charge.amount < 0 or paid_increment < 0:
        flash('Valores de cobrança não podem ser negativos.', 'danger')
        return redirect(url_for('cobrancas'))

    charge.amount_paid = (Decimal(charge.amount_paid or 0) + paid_increment).quantize(Decimal('0.01'))

    installment_count_raw = (request.form.get('installment_count') or '1').strip()
    try:
        charge.installment_count = max(1, int(installment_count_raw or '1'))
    except ValueError:
        charge.installment_count = 1
    if not charge.is_installment:
        charge.installment_count = 1
    installment_base = _charge_total_amount(charge)
    charge.installment_value = (Decimal(installment_base or 0) / Decimal(charge.installment_count or 1)).quantize(Decimal('0.01')) if Decimal(installment_base or 0) > 0 else Decimal('0.00')

    _ensure_charge_installments(charge)
    _normalize_charge_status(charge)

    if charge.service_id and charge.status == 'confirmado':
        _sync_service_ticket_status(charge.service_id)

    db.session.commit()
    flash('Cobrança atualizada com sucesso!', 'success')
    return redirect(url_for('cobrancas'))


@app.route('/cobrancas/<int:charge_id>/confirmar', methods=['POST'])
@_login_required
def confirmar_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    _ensure_charge_installments(charge)
    installments = _charge_installments(charge)
    installment_number_raw = (request.form.get('installment_number') or '').strip()
    amount_raw = (request.form.get('amount_paid') or '').strip().replace(',', '.')

    if amount_raw:
        try:
            amount = Decimal(amount_raw).quantize(Decimal('0.01'))
        except InvalidOperation:
            flash('Valor inválido para confirmação de pagamento.', 'danger')
            return redirect(request.referrer or url_for('cobrancas'))

        if amount <= 0:
            flash('Informe um valor maior que zero para confirmar o pagamento.', 'danger')
            return redirect(request.referrer or url_for('cobrancas'))

        if installments:
            if not installment_number_raw:
                flash('Selecione a parcela paga para vendas parceladas.', 'danger')
                return redirect(request.referrer or url_for('cobrancas'))

            try:
                installment_number = int(installment_number_raw)
            except ValueError:
                flash('Parcela inválida para confirmação de pagamento.', 'danger')
                return redirect(request.referrer or url_for('cobrancas'))

            installment = ChargeInstallment.query.filter_by(
                charge_id=charge.id,
                installment_number=installment_number,
            ).first()
            if not installment:
                flash('Parcela não encontrada para esta cobrança.', 'danger')
                return redirect(request.referrer or url_for('cobrancas'))

            max_amount = Decimal(installment.amount or 0).quantize(Decimal('0.01'))
            installment.amount_paid = min(max_amount, (Decimal(installment.amount_paid or 0) + amount).quantize(Decimal('0.01')))
        else:
            charge_total = _charge_total_amount(charge)
            charge.amount_paid = min(charge_total, (Decimal(charge.amount_paid or 0) + amount).quantize(Decimal('0.01')))

        _normalize_charge_status(charge)
        if charge.service_id and charge.status == 'confirmado':
            _sync_service_ticket_status(charge.service_id)
        if charge.sale_id and charge.status == 'confirmado':
            _delete_paid_sold_assembled_products(charge.sale)

        db.session.commit()
        flash('Pagamento registrado com sucesso!', 'success')
        return redirect(request.referrer or url_for('cobrancas'))

    if installments:
        for item in installments:
            item.amount_paid = Decimal(item.amount or 0).quantize(Decimal('0.01'))
            item.status = 'confirmado'
            item.payment_confirmed_at = datetime.utcnow()
    else:
        charge.amount_paid = _charge_total_amount(charge)

    _normalize_charge_status(charge)

    if charge.service_id:
        _sync_service_ticket_status(charge.service_id)
    if charge.sale_id and charge.status == 'confirmado':
        _delete_paid_sold_assembled_products(charge.sale)

    db.session.commit()
    flash('Pagamento confirmado!', 'success')
    return redirect(request.referrer or url_for('cobrancas'))


@app.route('/cobrancas/<int:charge_id>/parcelas/<int:installment_number>/pagar', methods=['POST'])
@_login_required
def pagar_parcela_cobranca(charge_id: int, installment_number: int):
    charge = Charge.query.get_or_404(charge_id)
    _ensure_charge_installments(charge)
    installment = ChargeInstallment.query.filter_by(charge_id=charge.id, installment_number=installment_number).first_or_404()

    amount_raw = (request.form.get('amount_paid') or str(Decimal(installment.amount or 0))).strip().replace(',', '.')
    try:
        amount = Decimal(amount_raw).quantize(Decimal('0.01'))
    except InvalidOperation:
        flash('Valor inválido para baixa da parcela.', 'danger')
        return redirect(request.referrer or url_for('vendas'))

    if amount <= 0:
        flash('Informe um valor maior que zero para a parcela.', 'danger')
        return redirect(request.referrer or url_for('vendas'))

    max_amount = Decimal(installment.amount or 0).quantize(Decimal('0.01'))
    installment.amount_paid = min(max_amount, (Decimal(installment.amount_paid or 0) + amount).quantize(Decimal('0.01')))

    _normalize_charge_status(charge)
    if charge.service_id and charge.status == 'confirmado':
        _sync_service_ticket_status(charge.service_id)

    db.session.commit()
    flash(f'Parcela {installment_number} baixada com sucesso.', 'success')
    return redirect(request.referrer or url_for('vendas'))


@app.route('/cobrancas/<int:charge_id>/parcelas/<int:installment_number>/editar', methods=['POST'])
@_login_required
def editar_parcela_cobranca(charge_id: int, installment_number: int):
    charge = Charge.query.get_or_404(charge_id)
    _ensure_charge_installments(charge)
    installment = ChargeInstallment.query.filter_by(charge_id=charge.id, installment_number=installment_number).first_or_404()

    try:
        installment.due_date = _parse_date_input(request.form.get('due_date'))
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(request.referrer or url_for('vendas'))

    amount_raw = (request.form.get('amount') or installment.amount or '0').__str__().strip().replace(',', '.')
    try:
        new_amount = Decimal(amount_raw).quantize(Decimal('0.01'))
    except InvalidOperation:
        flash('Valor inválido para a parcela.', 'danger')
        return redirect(request.referrer or url_for('vendas'))

    if new_amount < 0:
        flash('Valor da parcela não pode ser negativo.', 'danger')
        return redirect(request.referrer or url_for('vendas'))

    installment.amount = new_amount
    if Decimal(installment.amount_paid or 0) > new_amount:
        installment.amount_paid = new_amount

    _normalize_charge_status(charge)

    db.session.commit()
    flash(f'Parcela {installment_number} atualizada.', 'success')
    return redirect(request.referrer or url_for('vendas'))


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




@app.route('/cobrancas/<int:charge_id>/excluir', methods=['POST'])
@_login_required
def excluir_cobranca(charge_id: int):
    charge = Charge.query.get_or_404(charge_id)
    db.session.delete(charge)
    db.session.commit()
    flash('Cobrança excluída com sucesso!', 'success')
    return redirect(url_for('cobrancas'))



@app.route('/caixa')
@_login_required
def caixa():
    today = datetime.utcnow().date()
    charges = Charge.query.order_by(Charge.id.desc()).all()

    paid_today = Decimal('0.00')
    pending_total = Decimal('0.00')
    overdue_total = Decimal('0.00')

    for charge in charges:
        total_amount = _charge_total_amount(charge)
        paid_amount = Decimal(charge.amount_paid or 0).quantize(Decimal('0.01'))
        balance = (total_amount - paid_amount).quantize(Decimal('0.01'))

        if charge.payment_confirmed_at and charge.payment_confirmed_at.date() == today:
            paid_today += paid_amount

        if charge.status != 'cancelado' and balance > 0:
            pending_total += balance
            if charge.due_date and charge.due_date < today:
                overdue_total += balance

    return render_template(
        'cash_management.html',
        charges=charges,
        paid_today=paid_today,
        pending_total=pending_total,
        overdue_total=overdue_total,
        charge_ui_status=_charge_ui_status,
        charge_balance=_charge_balance,
        charge_total_amount=_charge_total_amount,
        payment_method_labels=PAYMENT_METHOD_LABELS,
    )


@app.route('/clientes/<int:client_id>/historico')
@_login_required
def historico_cliente(client_id: int):
    client = Client.query.get_or_404(client_id)
    sales = Sale.query.filter_by(client_id=client.id).order_by(Sale.created_at.desc()).all()
    maintenances = MaintenanceTicket.query.filter(MaintenanceTicket.client_name == client.name).order_by(MaintenanceTicket.entry_date.desc()).all()
    services = ServiceRecord.query.filter(ServiceRecord.client_name == client.name).order_by(ServiceRecord.created_at.desc()).all()

    sale_ids = [sale.id for sale in sales]
    service_ids = [service.id for service in services]
    charges = Charge.query.filter(
        db.or_(
            Charge.sale_id.in_(sale_ids) if sale_ids else db.false(),
            Charge.service_id.in_(service_ids) if service_ids else db.false(),
        )
    ).all()

    charges_by_sale_id: dict[int, list[Charge]] = {}
    charges_by_service_id: dict[int, list[Charge]] = {}
    for charge in charges:
        if charge.sale_id:
            charges_by_sale_id.setdefault(charge.sale_id, []).append(charge)
        if charge.service_id:
            charges_by_service_id.setdefault(charge.service_id, []).append(charge)

    finalized_sale_ids = {
        sale.id
        for sale in sales
        if _is_sale_finalized_by_payment(sale, charges_by_sale_id.get(sale.id, []))
    }
    finalized_service_ids = {
        service.id
        for service in services
        if _is_service_finalized_by_payment(service, charges_by_service_id.get(service.id, []))
    }

    return render_template(
        'client_history.html',
        client=client,
        sales=sales,
        maintenances=maintenances,
        services=services,
        finalized_sale_ids=finalized_sale_ids,
        finalized_service_ids=finalized_service_ids,
    )


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
    if 'active' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1'))
    if 'ram_ddr' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN ram_ddr VARCHAR(30)'))
    if 'ram_frequency' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN ram_frequency VARCHAR(30)'))
    if 'ram_size' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN ram_size VARCHAR(30)'))
    if 'ram_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN ram_brand VARCHAR(60)'))
    if 'psu_watts' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN psu_watts VARCHAR(30)'))
    if 'psu_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN psu_brand VARCHAR(60)'))
    if 'gpu_memory' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN gpu_memory VARCHAR(30)'))
    if 'gpu_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN gpu_brand VARCHAR(60)'))
    if 'gpu_manufacturer' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN gpu_manufacturer VARCHAR(30)'))
    if 'storage_type' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN storage_type VARCHAR(20)'))
    if 'storage_capacity' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN storage_capacity VARCHAR(30)'))
    if 'storage_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN storage_brand VARCHAR(60)'))
    if 'cpu_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN cpu_brand VARCHAR(60)'))
    if 'cpu_manufacturer' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN cpu_manufacturer VARCHAR(60)'))
    if 'cpu_model' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN cpu_model VARCHAR(80)'))
    if 'motherboard_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN motherboard_brand VARCHAR(60)'))
    if 'motherboard_model' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN motherboard_model VARCHAR(80)'))
    if 'motherboard_socket' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN motherboard_socket VARCHAR(40)'))
    if 'motherboard_chipset' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN motherboard_chipset VARCHAR(40)'))
    if 'cabinet_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN cabinet_brand VARCHAR(60)'))
    if 'cabinet_description' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN cabinet_description VARCHAR(180)'))
    if 'fan_brand' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN fan_brand VARCHAR(60)'))
    if 'fan_description' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN fan_description VARCHAR(180)'))
    if 'peripheral_mouse' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN peripheral_mouse VARCHAR(120)'))
    if 'peripheral_keyboard' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN peripheral_keyboard VARCHAR(120)'))
    if 'peripheral_monitor' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN peripheral_monitor VARCHAR(120)'))
    if 'peripheral_power_cable' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN peripheral_power_cable VARCHAR(120)'))
    if 'peripheral_hdmi_cable' not in columns:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN peripheral_hdmi_cable VARCHAR(120)'))
    db.session.execute(
        db.text(
            "UPDATE product SET stock = 0, active = 0, category = 'Serviço', price = 0, cost_price = 0 "
            "WHERE name = 'Serviço avulso'"
        )
    )
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
            'service_record_id INTEGER, '
            'quantity INTEGER NOT NULL DEFAULT 1, '
            'unit_price NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'unit_cost NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'line_total NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'FOREIGN KEY(sale_id) REFERENCES sale (id), '
            'FOREIGN KEY(product_id) REFERENCES product (id), '
            'FOREIGN KEY(service_record_id) REFERENCES service_record (id)'
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
            'parts_stock_applied BOOLEAN NOT NULL DEFAULT 0, '
            "status VARCHAR(30) NOT NULL DEFAULT 'em_andamento', "
            'service_record_id INTEGER, '
            'created_at DATETIME NOT NULL, '
            'FOREIGN KEY(service_record_id) REFERENCES service_record (id)'
            ')'
        )
    )
    sale_item_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(sale_item)'))]
    if 'service_record_id' not in sale_item_columns:
        db.session.execute(db.text('ALTER TABLE sale_item ADD COLUMN service_record_id INTEGER'))

    maintenance_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(maintenance_ticket)'))]
    if 'client_phone' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN client_phone VARCHAR(30)'))
    if 'customer_report' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN customer_report TEXT'))
    if 'technical_diagnosis' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN technical_diagnosis TEXT'))
    if 'observations' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN observations TEXT'))
    if 'checklist_json' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN checklist_json TEXT'))
    if 'parts_json' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN parts_json TEXT'))
    if 'labor_cost' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN labor_cost NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'service_record_id' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN service_record_id INTEGER'))
    if 'parts_stock_applied' not in maintenance_columns:
        db.session.execute(db.text('ALTER TABLE maintenance_ticket ADD COLUMN parts_stock_applied BOOLEAN NOT NULL DEFAULT 0'))
    db.session.commit()

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
    if 'bios_service_cost' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN bios_service_cost NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'stress_test_done' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN stress_test_done BOOLEAN NOT NULL DEFAULT 0'))
    if 'stress_test_cost' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN stress_test_cost NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'os_installed' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN os_installed BOOLEAN NOT NULL DEFAULT 0'))
    if 'os_install_cost' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN os_install_cost NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'apply_price_suggestion' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN apply_price_suggestion BOOLEAN NOT NULL DEFAULT 0'))
    if 'performed_by_user_id' not in montagem_columns:
        db.session.execute(db.text('ALTER TABLE montagem_computador ADD COLUMN performed_by_user_id INTEGER'))
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
    if 'payment_method' not in sale_columns:
        db.session.execute(db.text("ALTER TABLE sale ADD COLUMN payment_method VARCHAR(30) NOT NULL DEFAULT 'pix'"))
    if 'canceled' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN canceled BOOLEAN NOT NULL DEFAULT 0'))
    if 'canceled_at' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN canceled_at DATETIME'))
    if 'performed_by_user_id' not in sale_columns:
        db.session.execute(db.text('ALTER TABLE sale ADD COLUMN performed_by_user_id INTEGER'))
    db.session.commit()

    service_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(service_record)'))]
    if 'discount_amount' not in service_columns:
        db.session.execute(db.text('ALTER TABLE service_record ADD COLUMN discount_amount NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'performed_by_user_id' not in service_columns:
        db.session.execute(db.text('ALTER TABLE service_record ADD COLUMN performed_by_user_id INTEGER'))
    if 'delivery_status' not in service_columns:
        db.session.execute(db.text("ALTER TABLE service_record ADD COLUMN delivery_status VARCHAR(30) NOT NULL DEFAULT 'aguardando'"))
    if 'delivered_at' not in service_columns:
        db.session.execute(db.text('ALTER TABLE service_record ADD COLUMN delivered_at DATETIME'))
    if 'canceled_at' not in service_columns:
        db.session.execute(db.text('ALTER TABLE service_record ADD COLUMN canceled_at DATETIME'))
    db.session.execute(db.text("UPDATE service_record SET delivery_status = 'aguardando' WHERE delivery_status IS NULL OR TRIM(delivery_status) = ''"))
    db.session.commit()

    client_columns = [row[1] for row in db.session.execute(db.text('PRAGMA table_info(client)'))]
    if 'cpf' not in client_columns:
        db.session.execute(db.text('ALTER TABLE client ADD COLUMN cpf VARCHAR(14)'))
    if 'active' not in client_columns:
        db.session.execute(db.text('ALTER TABLE client ADD COLUMN active BOOLEAN NOT NULL DEFAULT 1'))
    db.session.execute(db.text('CREATE UNIQUE INDEX IF NOT EXISTS ux_client_cpf ON client (cpf)'))
    db.session.commit()

    charge_columns_info = list(db.session.execute(db.text('PRAGMA table_info(charge)')))
    charge_columns = [row[1] for row in charge_columns_info]
    if 'payment_method' not in charge_columns:
        db.session.execute(db.text("ALTER TABLE charge ADD COLUMN payment_method VARCHAR(30) NOT NULL DEFAULT 'pix'"))
    if 'service_id' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN service_id INTEGER'))
    if 'due_date' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN due_date DATE'))
    if 'amount' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN amount NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'amount_paid' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN amount_paid NUMERIC(10,2) NOT NULL DEFAULT 0'))
    if 'is_installment' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN is_installment BOOLEAN NOT NULL DEFAULT 0'))
    if 'installment_count' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN installment_count INTEGER NOT NULL DEFAULT 1'))
    if 'installment_value' not in charge_columns:
        db.session.execute(db.text('ALTER TABLE charge ADD COLUMN installment_value NUMERIC(10,2) NOT NULL DEFAULT 0'))

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
                'due_date DATE, '
                'amount NUMERIC(10,2) NOT NULL DEFAULT 0, '
                'amount_paid NUMERIC(10,2) NOT NULL DEFAULT 0, '
                "status VARCHAR(30) NOT NULL DEFAULT 'pendente', "
                "payment_method VARCHAR(30) NOT NULL DEFAULT 'pix', "
                'is_installment BOOLEAN NOT NULL DEFAULT 0, '
                'installment_count INTEGER NOT NULL DEFAULT 1, '
                'installment_value NUMERIC(10,2) NOT NULL DEFAULT 0, '
                'payment_confirmed_at DATETIME, '
                'FOREIGN KEY(sale_id) REFERENCES sale (id), '
                'FOREIGN KEY(service_id) REFERENCES service_record (id)'
                ')'
            )
        )
        db.session.execute(
            db.text(
                'INSERT INTO charge (id, sale_id, mercado_pago_reference, due_date, amount, amount_paid, status, payment_method, is_installment, installment_count, installment_value, payment_confirmed_at) '
                'SELECT id, sale_id, mercado_pago_reference, NULL, 0, 0, status, payment_method, 0, 1, 0, payment_confirmed_at FROM charge_old'
            )
        )
        db.session.execute(db.text('DROP TABLE charge_old'))

    db.session.execute(
        db.text(
            'CREATE TABLE IF NOT EXISTS charge_installment ('
            'id INTEGER PRIMARY KEY, '
            'charge_id INTEGER NOT NULL, '
            'installment_number INTEGER NOT NULL DEFAULT 1, '
            'due_date DATE, '
            'amount NUMERIC(10,2) NOT NULL DEFAULT 0, '
            'amount_paid NUMERIC(10,2) NOT NULL DEFAULT 0, '
            "status VARCHAR(30) NOT NULL DEFAULT 'pendente', "
            'payment_confirmed_at DATETIME, '
            'FOREIGN KEY(charge_id) REFERENCES charge (id)'
            ')'
        )
    )
    db.session.execute(db.text('CREATE UNIQUE INDEX IF NOT EXISTS ux_charge_installment_number ON charge_installment (charge_id, installment_number)'))
    db.session.commit()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)
