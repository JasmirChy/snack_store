import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime

app = Flask(__name__)
app.config.from_pyfile('config.py')

# Initialize MySQL
mysql = MySQL(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, name, email, is_admin):
        self.id = id
        self.name = name
        self.email = email
        self.is_admin = is_admin

@login_manager.user_loader
def load_user(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    
    if user:
        return User(user[0], user[1], user[2], user[4])
    return None

# Utility functions
def get_categories():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM categories")
    categories = cur.fetchall()
    cur.close()
    return categories

def get_cart_count():
    if current_user.is_authenticated and not current_user.is_admin:
        cur = mysql.connection.cursor()
        cur.execute("SELECT SUM(quantity) FROM cart_items WHERE user_id = %s", (current_user.id,))
        count = cur.fetchone()[0] or 0
        cur.close()
        return count
    return 0

def format_currency(amount):
    """Format amount as Nepali currency"""
    try:
        if isinstance(amount, str):
            amount = float(amount)
        return "रु {:,.2f}".format(amount) if amount else "रु 0.00"
    except (ValueError, TypeError):
        return "रु 0.00"

@app.template_filter('format_date')
def format_date_filter(date_value, format_string='%B %d, %Y at %H:%M'):
    if date_value is None:
        return ""
    
    if isinstance(date_value, str):
        try:
            date_value = datetime.strptime(date_value, '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            return date_value
    
    if hasattr(date_value, 'strftime'):
        return date_value.strftime(format_string)
    
    return str(date_value)

@app.context_processor
def inject_global_data():
    cart_count = 0
    if current_user.is_authenticated and not current_user.is_admin:
        cart_count = get_cart_count()
    
    return dict(
        categories=get_categories(),
        cart_count=cart_count,
        format_currency=format_currency,
        format_date=format_date_filter
    )


# Routes
@app.route('/')
def index():
    cur = mysql.connection.cursor()
    
    # Get all active banners for the slider
    cur.execute("SELECT * FROM banners WHERE active = TRUE ORDER BY created_at DESC")
    banners = cur.fetchall()
    
    # Get products
    cur.execute("SELECT * FROM products WHERE stock > 0 ORDER BY created_at DESC LIMIT 8")
    products = cur.fetchall()
    
    cur.close()
    
    return render_template('index.html', banners=banners, products=products)

@app.route('/products')
def products():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    category_id = request.args.get('category')
    
    cur = mysql.connection.cursor()
    
    if category_id:
        cur.execute("SELECT * FROM products WHERE category_id = %s AND stock > 0", (category_id,))
    else:
        cur.execute("SELECT * FROM products WHERE stock > 0")
    
    products = cur.fetchall()
    cur.close()
    
    return render_template('products/list.html', products=products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    cur.close()
    
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('products'))
    
    return render_template('products/detail.html', product=product)

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    if current_user.is_admin:
        flash('Admin users cannot purchase products', 'error')
        return redirect(url_for('admin_dashboard'))
    
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products WHERE id = %s AND stock >= %s", (product_id, quantity))
    product = cur.fetchone()
    
    if not product:
        flash('Product not available in the requested quantity', 'error')
        return redirect(request.referrer)
    
    cur.execute("SELECT * FROM cart_items WHERE user_id = %s AND product_id = %s", (current_user.id, product_id))
    existing_item = cur.fetchone()
    
    if existing_item:
        new_quantity = existing_item[3] + quantity
        cur.execute("UPDATE cart_items SET quantity = %s WHERE id = %s", (new_quantity, existing_item[0]))
    else:
        cur.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)", 
                   (current_user.id, product_id, quantity))
    
    mysql.connection.commit()
    cur.close()
    
    flash('Product added to cart', 'success')
    return redirect(request.referrer)

@app.route('/cart')
@login_required
def cart():
    if current_user.is_admin:
        flash('Admin users cannot access shopping cart', 'error')
        return redirect(url_for('admin_dashboard'))
    
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT ci.id, p.id, p.title, p.price, p.image, ci.quantity, (p.price * ci.quantity) as total
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.user_id = %s
    """, (current_user.id,))
    
    cart_items = cur.fetchall()
    grand_total = sum(item[6] for item in cart_items)
    
    cur.close()
    
    return render_template('cart/index.html', cart_items=cart_items, grand_total=grand_total)

@app.route('/update_cart', methods=['POST'])
@login_required
def update_cart():
    if current_user.is_admin:
        flash('Admin users cannot modify shopping cart', 'error')
        return redirect(url_for('admin_dashboard'))
    
    cart_item_id = request.form.get('cart_item_id')
    quantity = int(request.form.get('quantity', 1))
    
    if quantity <= 0:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM cart_items WHERE id = %s AND user_id = %s", (cart_item_id, current_user.id))
        mysql.connection.commit()
        cur.close()
        flash('Item removed from cart', 'success')
    else:
        cur = mysql.connection.cursor()
        cur.execute("UPDATE cart_items SET quantity = %s WHERE id = %s AND user_id = %s", 
                   (quantity, cart_item_id, current_user.id))
        mysql.connection.commit()
        cur.close()
        flash('Cart updated', 'success')
    
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if current_user.is_admin:
        flash('Admin users cannot checkout orders', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        country = request.form.get('country')
        city = request.form.get('city')
        postal_code = request.form.get('postal_code')
        street = request.form.get('street')
        payment_method = request.form.get('payment_method')
        
        address = f"{name}\n{street}\n{city}, {postal_code}\n{country}\nPhone: {phone}"
        
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT p.id, p.price, ci.quantity, (p.price * ci.quantity) as total
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.user_id = %s
        """, (current_user.id,))
        
        cart_items = cur.fetchall()
        
        if not cart_items:
            flash('Your cart is empty', 'error')
            return redirect(url_for('cart'))
        
        total_amount = sum(item[3] for item in cart_items)
        
        for item in cart_items:
            cur.execute("SELECT stock FROM products WHERE id = %s", (item[0],))
            stock = cur.fetchone()[0]
            if stock < item[2]:
                flash(f'Not enough stock for product ID {item[0]}', 'error')
                return redirect(url_for('cart'))
        
        cur.execute("""
            INSERT INTO orders (user_id, total_amount, address, payment_method, status)
            VALUES (%s, %s, %s, %s, 'pending')
        """, (current_user.id, total_amount, address, payment_method))
        
        order_id = cur.lastrowid
        
        for item in cart_items:
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (%s, %s, %s, %s)
            """, (order_id, item[0], item[2], item[1]))
            
            cur.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (item[2], item[0]))
        
        cur.execute("DELETE FROM cart_items WHERE user_id = %s", (current_user.id,))
        
        mysql.connection.commit()
        cur.close()
        
        flash('Order placed successfully!', 'success')
        return redirect(url_for('order_confirmation', order_id=order_id))
    
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT ci.id, p.id, p.title, p.price, p.image, ci.quantity, (p.price * ci.quantity) as total
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.user_id = %s
    """, (current_user.id,))
    
    cart_items = cur.fetchall()
    grand_total = sum(item[6] for item in cart_items)
    
    if not cart_items:
        flash('Your cart is empty', 'error')
        return redirect(url_for('cart'))
    
    cur.close()
    
    return render_template('cart/checkout.html', cart_items=cart_items, grand_total=grand_total)

@app.route('/order_confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    if current_user.is_admin:
        flash('Admin users cannot view order confirmations', 'error')
        return redirect(url_for('admin_dashboard'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order = cur.fetchone()
    
    cur.execute("SELECT * FROM settings WHERE key_name = 'payment_qr'")
    qr_setting = cur.fetchone()
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('index'))
    
    cur.execute("""
        SELECT oi.*, p.title, p.image
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = %s
    """, (order_id,))
    
    order_items = cur.fetchall()
    cur.close()
    
    return render_template('orders/confirmation.html', order=order, order_items=order_items, qr_setting=qr_setting)

@app.route('/orders')
@login_required
def orders():
    if current_user.is_admin:
        flash('Admin users cannot view customer orders here. Use the admin panel.', 'error')
        return redirect(url_for('admin_orders'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC", (current_user.id,))
    orders = cur.fetchall()
    
    order_items = {}
    for order in orders:
        cur.execute("""
            SELECT oi.*, p.title, p.image
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order[0],))
        order_items[order[0]] = cur.fetchall()
    
    cur.close()
    
    return render_template('orders/list.html', orders=orders, order_items=order_items)

@app.route('/upload_payment_proof/<int:order_id>', methods=['POST'])
@login_required
def upload_payment_proof(order_id):
    if current_user.is_admin:
        flash('Admin users cannot upload payment proof', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if 'payment_proof' not in request.files:
        flash('No file selected', 'error')
        return redirect(request.referrer)
    
    file = request.files['payment_proof']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(request.referrer)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'payment_proofs', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)
        
        cur = mysql.connection.cursor()
        cur.execute("UPDATE orders SET payment_proof = %s WHERE id = %s AND user_id = %s", 
                   (filename, order_id, current_user.id))
        mysql.connection.commit()
        cur.close()
        
        flash('Payment proof uploaded successfully', 'success')
        return redirect(request.referrer)
    
    flash('Invalid file type', 'error')
    return redirect(request.referrer)

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/register.html')
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cur.fetchone()
        
        if existing_user:
            flash('Email already registered', 'error')
            return render_template('auth/register.html')
        
        password_hash = generate_password_hash(password)
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)", 
                   (name, email, password_hash))
        mysql.connection.commit()
        cur.close()
        
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        
        if user and check_password_hash(user[3], password):
            user_obj = User(user[0], user[1], user[2], user[4])
            login_user(user_obj, remember=remember)
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            if user_obj.is_admin:
                flash('Admin login successful', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Login successful', 'success')
                return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# Admin routes
@app.route('/admin')
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM users WHERE is_admin = FALSE")
    total_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
    pending_orders = cur.fetchone()[0]
    
    cur.execute("""
        SELECT o.id, o.created_at, o.total_amount, o.status, u.name 
        FROM orders o 
        JOIN users u ON o.user_id = u.id 
        ORDER BY o.created_at DESC 
        LIMIT 5
    """)
    recent_orders = cur.fetchall()
    
    cur.execute("SELECT * FROM banners WHERE active = TRUE ORDER BY created_at DESC LIMIT 1")
    active_banner = cur.fetchone()
    
    cur.close()
    
    return render_template('admin/dashboard.html', 
                         total_orders=total_orders,
                         total_products=total_products,
                         total_users=total_users,
                         pending_orders=pending_orders,
                         recent_orders=recent_orders,
                         active_banner=active_banner)

@app.route('/buy_now', methods=['POST'])
@login_required
def buy_now():
    if current_user.is_admin:
        flash('Admin users cannot purchase products', 'error')
        return redirect(url_for('admin_dashboard'))
    
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products WHERE id = %s AND stock >= %s", (product_id, quantity))
    product = cur.fetchone()
    
    if not product:
        flash('Product not available in the requested quantity', 'error')
        return redirect(request.referrer)
    
    cur.execute("DELETE FROM cart_items WHERE user_id = %s", (current_user.id,))
    cur.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)", 
               (current_user.id, product_id, quantity))
    
    mysql.connection.commit()
    cur.close()
    
    return redirect(url_for('checkout'))

@app.route('/admin/products')
@login_required
def admin_products():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT p.*, c.name as category_name FROM products p LEFT JOIN categories c ON p.category_id = c.id ORDER BY p.created_at DESC")
    products = cur.fetchall()
    cur.close()
    
    return render_template('admin/products.html', products=products)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        stock = int(request.form.get('stock'))
        category_id = request.form.get('category_id')
        
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                image_filename = filename
        
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO products (title, description, price, stock, category_id, image)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, description, price, stock, category_id, image_filename))
        
        mysql.connection.commit()
        cur.close()
        
        flash('Product added successfully', 'success')
        return redirect(url_for('admin_products'))
    
    categories = get_categories()
    return render_template('admin/product_form.html', categories=categories)

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_product(product_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        stock = int(request.form.get('stock'))
        category_id = request.form.get('category_id')
        
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                image_filename = filename
        
        if image_filename:
            cur.execute("""
                UPDATE products 
                SET title = %s, description = %s, price = %s, stock = %s, category_id = %s, image = %s
                WHERE id = %s
            """, (title, description, price, stock, category_id, image_filename, product_id))
        else:
            cur.execute("""
                UPDATE products 
                SET title = %s, description = %s, price = %s, stock = %s, category_id = %s
                WHERE id = %s
            """, (title, description, price, stock, category_id, product_id))
        
        mysql.connection.commit()
        cur.close()
        
        flash('Product updated successfully', 'success')
        return redirect(url_for('admin_products'))
    
    cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    
    categories = get_categories()
    cur.close()
    
    return render_template('admin/product_form.html', product=product, categories=categories)

@app.route('/admin/products/delete/<int:product_id>')
@login_required
def admin_delete_product(product_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
    mysql.connection.commit()
    cur.close()
    
    flash('Product deleted successfully', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    cur = mysql.connection.cursor()
    
    if status_filter:
        query = """
            SELECT o.*, u.name as user_name 
            FROM orders o 
            JOIN users u ON o.user_id = u.id 
            WHERE o.status = %s 
            ORDER BY o.created_at DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(query, (status_filter, per_page, (page-1)*per_page))
        orders = cur.fetchall()
        
        count_query = "SELECT COUNT(*) FROM orders WHERE status = %s"
        cur.execute(count_query, (status_filter,))
        count_result = cur.fetchone()
        total_orders = count_result[0] if count_result else 0
    else:
        query = """
            SELECT o.*, u.name as user_name 
            FROM orders o 
            JOIN users u ON o.user_id = u.id 
            ORDER BY o.created_at DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(query, (per_page, (page-1)*per_page))
        orders = cur.fetchall()
        
        count_query = "SELECT COUNT(*) FROM orders"
        cur.execute(count_query)
        count_result = cur.fetchone()
        total_orders = count_result[0] if count_result else 0
    
    total_pages = (total_orders + per_page - 1) // per_page if total_orders > 0 else 1
    
    cur.close()
    
    return render_template('admin/orders.html', orders=orders, page=page, 
                         total_pages=total_pages, status_filter=status_filter)

@app.route('/admin/orders/update_status/<int:order_id>', methods=['POST'])
@login_required
def admin_update_order_status(order_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    status = request.form.get('status')
    tracking_number = request.form.get('tracking_number', '')
    
    cur = mysql.connection.cursor()
    
    if tracking_number:
        cur.execute("UPDATE orders SET status = %s, tracking_number = %s WHERE id = %s", 
                   (status, tracking_number, order_id))
    else:
        cur.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
    
    mysql.connection.commit()
    
    cur.execute("SELECT u.email, u.name, o.id FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = %s", (order_id,))
    order = cur.fetchone()
    cur.close()
    
    flash('Order status updated successfully', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/orders/<int:order_id>')
@login_required
def admin_order_detail(order_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT 
            o.id, 
            o.total_amount, 
            o.address, 
            o.payment_method, 
            o.payment_proof,
            o.status,
            o.tracking_number,
            o.created_at,
            u.name as user_name,
            u.email as user_email
        FROM orders o 
        JOIN users u ON o.user_id = u.id 
        WHERE o.id = %s
    """, (order_id,))
    order = cur.fetchone()
    
    cur.execute("""
        SELECT 
            oi.id,
            oi.order_id,
            oi.product_id,
            oi.quantity,
            oi.unit_price,
            p.title as product_name,
            p.image as product_image
        FROM order_items oi 
        JOIN products p ON oi.product_id = p.id 
        WHERE oi.order_id = %s
    """, (order_id,))
    order_items = cur.fetchall()
    
    cur.close()
    
    return render_template('admin/order_detail.html', order=order, order_items=order_items)

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE is_admin = FALSE ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.close()
    
    return render_template('admin/users.html', users=users)

# Serve banner images
@app.route('/banners/<path:filename>')
def serve_banner(filename):
    try:
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'banners'), filename)
    except Exception as e:
        print(f"Error serving banner {filename}: {e}")
        # Fallback to static path
        return redirect(url_for('static', filename='uploads/banners/' + filename))

@app.route('/admin/banners')
@login_required
def admin_banners():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM banners ORDER BY created_at DESC")
    banners = cur.fetchall()
    cur.close()
    
    return render_template('admin/banner.html', banners=banners)

@app.route('/admin/banners/add', methods=['GET', 'POST'])
@login_required
def admin_add_banner():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        slider_text = request.form.get('slider_text', '')
        active = bool(request.form.get('active'))
        
        if 'image' not in request.files:
            flash('No image file', 'error')
            return redirect(request.referrer)
        
        file = request.files['image']
        if file.filename == '':
            flash('No image selected', 'error')
            return redirect(request.referrer)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'banners', filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            file.save(filepath)
            
            if active:
                cur = mysql.connection.cursor()
                cur.execute("UPDATE banners SET active = FALSE")
                mysql.connection.commit()
            
            cur.execute("INSERT INTO banners (title, slider_text, image, active) VALUES (%s, %s, %s, %s)", (title, slider_text, filename, active))
            mysql.connection.commit()
            cur.close()
            
            flash('Banner added successfully', 'success')
            return redirect(url_for('admin_banners'))
    
    return render_template('admin/banner_form.html')

@app.route('/admin/banners/edit/<int:banner_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_banner(banner_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    
    if request.method == 'POST':
        title = request.form.get('title')
        slider_text = request.form.get('slider_text', '')
        active = bool(request.form.get('active'))
        
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'banners', filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                image_filename = filename
        
        if active:
            cur.execute("UPDATE banners SET active = FALSE WHERE id != %s", (banner_id,))
            mysql.connection.commit()
        
        if image_filename:
            cur.execute("UPDATE banners SET title = %s, slider_text = %s, image = %s, active = %s WHERE id = %s", 
                       (title, slider_text, image_filename, active, banner_id))
        else:
            cur.execute("UPDATE banners SET title = %s, slider_text = %s, active = %s WHERE id = %s", 
                       (title, slider_text, active, banner_id))
        
        mysql.connection.commit()
        cur.close()
        
        flash('Banner updated successfully', 'success')
        return redirect(url_for('admin_banners'))
    
    cur.execute("SELECT * FROM banners WHERE id = %s", (banner_id,))
    banner = cur.fetchone()
    cur.close()
    
    return render_template('admin/banner_form.html', banner=banner)

@app.route('/admin/banners/delete/<int:banner_id>')
@login_required
def admin_delete_banner(banner_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM banners WHERE id = %s", (banner_id,))
    mysql.connection.commit()
    cur.close()
    
    flash('Banner deleted successfully', 'success')
    return redirect(url_for('admin_banners'))

@app.route('/admin/banners/set_active/<int:banner_id>')
@login_required
def admin_set_active_banner(banner_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("UPDATE banners SET active = FALSE")
    cur.execute("UPDATE banners SET active = TRUE WHERE id = %s", (banner_id,))
    mysql.connection.commit()
    cur.close()
    
    flash('Banner set as active', 'success')
    return redirect(url_for('admin_banners'))

@app.route('/admin/settings')
@login_required
def admin_settings():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM settings WHERE key_name = 'payment_qr'")
    qr_setting = cur.fetchone()
    
    if not qr_setting:
        cur.execute("INSERT INTO settings (key_name, value) VALUES ('payment_qr', '')")
        mysql.connection.commit()
        cur.execute("SELECT * FROM settings WHERE key_name = 'payment_qr'")
        qr_setting = cur.fetchone()
    
    cur.close()
    
    return render_template('admin/settings.html', qr_setting=qr_setting)

@app.route('/admin/settings/update_qr', methods=['POST'])
@login_required
def admin_update_qr():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if 'qr_image' not in request.files:
        flash('No QR image file', 'error')
        return redirect(request.referrer)
    
    file = request.files['qr_image']
    if file.filename == '':
        flash('No QR image selected', 'error')
        return redirect(request.referrer)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'payment_qr', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)
        
        cur = mysql.connection.cursor()
        cur.execute("UPDATE settings SET value = %s WHERE key_name = 'payment_qr'", (filename,))
        mysql.connection.commit()
        cur.close()
        
        flash('QR code updated successfully', 'success')
        return redirect(url_for('admin_settings'))

# Helper function for file uploads
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

if __name__ == '__main__':
    app.run(debug=True)