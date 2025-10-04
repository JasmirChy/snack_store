import os
import config
from flask import Flask,flash, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_mysqldb import MySQL
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
from flask_mail import Mail, Message
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
app = Flask(__name__)
app.config.from_pyfile('config.py')
mail=Mail(app)
# Initialize MySQL
mysql = MySQL(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def send_admin_notification():
    sender_email = "info.swadgalli@gmail.com"
    sender_password = "chfy qktf tnuz esgl"  # use app password if Gmail
    admin_email = "jasmirchy@gmail.com"
    
    subject = "New Order Alert"
    body = "Dear Admin, New Order is arrived. Hurry up! \n A new order has been placed in your snack store website."
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = admin_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e:
        print("Failed to send notification:", e)


def send_customer_order_placed_email(to_email, customer_name, order_id, product_names):
    sender_email = "info.swadgalli@gmail.com"
    sender_password = "chfy qktf tnuz esgl"  # Gmail app password

    subject = f"Your New Order with oeder id #{order_id} has been placed successfully!"
    products_list = ", ".join(product_names)

    body = f"""
    SwadGaLLi
    
    Hello {customer_name},

    Your order (Order ID: {order_id}) has been placed successfully.

    Products in your order: {products_list}

    Thank you for shopping with SwadGaLLi!
    """

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
            print(f"Order placed email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send order placed email: {e}")


def send_customer_order_status_email(to_email, customer_name, order_id, status, tracking_number=None):
    sender_email = "info.swadgalli@gmail.com"
    sender_password = "chfy qktf tnuz esgl"   # Gmail app password

    # Map DB statuses → customer-friendly labels
    status_map = {
        "pending": "Pending",
        "confirmed": "Confirmed",
        "packed": "Packed",
        "shipped": "Shipped",
        "out_for_delivery": "Out for Delivery",
        "delivered": "Delivered",
        "cancelled": "Cancelled"
    }

    # Use mapped label if exists, fallback to capitalized raw value
    friendly_status = status_map.get(status, status.capitalize())

    subject = f"Update on your Order #{order_id}"
    tracking_info = f"\nTracking Number: {tracking_number}" if tracking_number else ""

    body = f"""
    Hello {customer_name},

    Your order (Order ID: {order_id}) has been {friendly_status}.

     {tracking_info}

    Thank you for shopping with SwadGaLLi!
    """

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
            # print(f"Status email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send status email: {e}")



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

# for discount finctionality
def has_discount(product):
    """Check if product has active discount"""
    try:
        # Common structure: id, category_id, title, description, price, stock, image, discount_percent, original_price, created_at
        if len(product) > 7 and product[7] is not None:
            discount_percent = float(product[7])
            return discount_percent > 0
        return False
    except (TypeError, ValueError, IndexError):
        return False

def get_discount_info(product):
    """Get discount information for product"""
    try:
        # Handle different product structures
        if len(product) >= 9:
            # New structure with explicit fields (admin_products route)
            discount_percent = product[7] if product[7] is not None else 0
            current_price = float(product[4]) if product[4] is not None else 0.0
            
            if discount_percent and float(discount_percent) > 0:
                discount_percent_float = float(discount_percent)
                
                # Use original_price if available, otherwise use current price
                if len(product) > 8 and product[8] is not None:
                    original_price = float(product[8])
                else:
                    original_price = current_price
                
                discounted_price = calculate_discounted_price(original_price, discount_percent_float)
                
                return {
                    'has_discount': True,
                    'discount_percent': discount_percent_float,
                    'original_price': original_price,
                    'discounted_price': discounted_price,
                    'you_save': original_price - discounted_price
                }
        
        # Fallback for no discount or older structure
        current_price = float(product[4]) if len(product) > 4 and product[4] is not None else 0.0
        return {
            'has_discount': False,
            'discount_percent': 0,
            'original_price': current_price,
            'discounted_price': current_price,
            'you_save': 0
        }
            
    except (TypeError, ValueError, IndexError) as e:
        print(f"Error in get_discount_info: {e}")
        # Ultimate fallback
        current_price = float(product[4]) if len(product) > 4 and product[4] is not None else 0.0
        return {
            'has_discount': False,
            'discount_percent': 0,
            'original_price': current_price,
            'discounted_price': current_price,
            'you_save': 0
        }
def calculate_discounted_price(original_price, discount_percent):
    """Calculate discounted price from original price and discount percentage"""
    try:
        original = float(original_price)
        discount = float(discount_percent)
        
        if discount > 0:
            discount_amount = original * (discount / 100)
            return max(0, original - discount_amount)
        return original
    except (TypeError, ValueError):
        return float(original_price)
# Update the format_currency function to handle discount display
def format_currency(amount):
    """Format amount as Nepali currency"""
    try:
        if isinstance(amount, str):
            amount = float(amount)
        return "रु {:,.2f}".format(amount) if amount else "रु 0.00"
    except (ValueError, TypeError):
        return "रु 0.00"

# Update the context processor
@app.context_processor
def inject_global_data():
    cart_count = 0
    if current_user.is_authenticated and not current_user.is_admin:
        cart_count = get_cart_count()
    
    return dict(
        categories=get_categories(),
        cart_count=cart_count,
        format_currency=format_currency,
        format_date=format_date_filter,
        get_primary_image=get_primary_image,
        get_image_count=get_image_count,
        calculate_discounted_price=calculate_discounted_price,
        has_discount=has_discount,
        get_discount_info=get_discount_info
    )

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

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not old_password or not new_password or not confirm_password:
            flash("All fields are required", "error")
            return redirect(url_for('change_password'))

        # fetch current user record
        cur = mysql.connection.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (current_user.id,))
        user = cur.fetchone()
        cur.close()

        if not user or not check_password_hash(user[0], old_password):
            flash("Old password is incorrect", "error")
            return redirect(url_for('change_password'))

        if new_password != confirm_password:
            flash("New password and confirm password do not match", "error")
            return redirect(url_for('change_password'))

        # update new password
        new_hash = generate_password_hash(new_password)
        cur = mysql.connection.cursor()
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, current_user.id))
        mysql.connection.commit()
        cur.close()

        flash("Password changed successfully", "success")
        return redirect(url_for('index'))

    return render_template('auth/change_password.html')

@app.route('/policy')
@login_required
def policy():
    return render_template('policy.html')

@app.route('/admin/slider')
@login_required
def admin_slider():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM slider_items ORDER BY created_at DESC")
    items = cur.fetchall()
    cur.close()
    return render_template('admin/slider.html', items=items)

@app.route('/suggest', methods=['GET'])
def suggest():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT id, title 
        FROM products 
        WHERE title LIKE %s 
        LIMIT 5
    """, (f"%{query}%",))
    results = cur.fetchall()
    cur.close()

    # Convert to list of dicts
    suggestions = [{"id": r[0], "title": r[1]} for r in results]
    return jsonify(suggestions)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    cur = mysql.connection.cursor()

    if query:
        cur.execute("""
            SELECT * FROM products 
            WHERE title LIKE %s OR description LIKE %s
        """, (f"%{query}%", f"%{query}%"))
        results = cur.fetchall()
    else:
        results = []

    cur.close()

    return render_template("search_results.html", query=query, results=results)


@app.route('/admin/slider/add', methods=['POST'])
@login_required
def admin_add_slider():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    file = request.files['file']
    title = request.form.get('title')
    details = request.form.get('details')
    media_type = request.form.get('type')

    if file and file.filename != '':
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        folder = os.path.join(app.config['UPLOAD_FOLDER'], 'slider')
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename)
        file.save(filepath)

        # store relative path (uploads/slider/file.jpg)
        db_path = f"uploads/slider/{filename}"

        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO slider_items (type, file_path, title, details) VALUES (%s, %s, %s, %s)",
            (media_type, db_path, title, details)
        )
        mysql.connection.commit()
        cur.close()
        flash("Slider item added successfully", "success")

    return redirect(url_for('admin_slider'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash("Unauthorized access!", "danger")
        return redirect(url_for('admin_users'))

    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    mysql.connection.commit()
    cursor.close()

    flash("User deleted successfully!", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/slider/delete/<int:item_id>')
@login_required
def admin_delete_slider(item_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM slider_items WHERE id = %s", (item_id,))
    mysql.connection.commit()
    cur.close()
    flash("Slider item deleted", "info")
    return redirect(url_for('admin_slider'))

# Routes

@app.route('/')
def index():
    cur = mysql.connection.cursor()
    
    # Get all active banners for the slider
    cur.execute("SELECT * FROM banners WHERE active = TRUE ORDER BY created_at DESC")
    banners = cur.fetchall()

    # Get slider items
    cur.execute("SELECT * FROM slider_items ORDER BY created_at DESC")
    slider_items = cur.fetchall()
    
    # Get products WITH DISCOUNT FIELDS - explicitly select all fields including discount columns
    cur.execute("""
        SELECT 
            id, 
            category_id, 
            title, 
            description, 
            price, 
            stock, 
            image, 
            discount_percent, 
            original_price, 
            created_at 
        FROM products 
        WHERE stock > 0 
        ORDER BY created_at DESC 
        LIMIT 8
    """)
    products = cur.fetchall()
    
    # 🔥 Get reviews (important!)
    cur.execute("SELECT id, type, file_path FROM reviews ORDER BY created_at DESC")
    reviews = cur.fetchall()
    
    cur.close()
    
    return render_template(
        'index.html',
        slider_items=slider_items,
        banners=banners,
        products=products,
        reviews=reviews   # 👈 pass reviews to template
    )
# View all reviews
@app.route('/admin/reviews')
@login_required
def admin_reviews():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, type, file_path, created_at FROM reviews ORDER BY created_at DESC")
    reviews = cur.fetchall()
    cur.close()
    return render_template('admin/reviews.html', reviews=reviews)


# Add review
@app.route('/admin/reviews/add', methods=['POST'])
@login_required
def admin_add_review():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    file = request.files['file']
    rtype = request.form.get('type')

    if not file or file.filename == '':
        flash("No file selected", "error")
        return redirect(url_for('admin_reviews'))

    if not allowed_file(file.filename):
        flash("File type not allowed", "error")
        return redirect(url_for('admin_reviews'))

    # Check file size
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)
    if file_length > 20 * 1024 * 1024:  # 20 MB
        flash("File size exceeds 20 MB", "error")
        return redirect(url_for('admin_reviews'))

    # Save file
    filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'reviews')
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    file.save(filepath)

    db_path = f"uploads/reviews/{filename}"

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO reviews (type, file_path) VALUES (%s, %s)", (rtype, db_path))
    mysql.connection.commit()
    cur.close()

    flash("Review uploaded successfully", "success")
    return redirect(url_for('admin_reviews'))


# Delete review
@app.route('/admin/reviews/delete/<int:review_id>')
@login_required
def admin_delete_review(review_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
    mysql.connection.commit()
    cur.close()

    flash("Review deleted successfully", "info")
    return redirect(url_for('admin_reviews'))



@app.route('/products')
def products():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    category_id = request.args.get('category')
    
    cur = mysql.connection.cursor()
    
    if category_id:
        cur.execute("""
            SELECT 
                id, 
                category_id, 
                title, 
                description, 
                price, 
                stock, 
                image, 
                discount_percent, 
                original_price, 
                created_at 
            FROM products 
            WHERE category_id = %s AND stock > 0
        """, (category_id,))
    else:
        cur.execute("""
            SELECT 
                id, 
                category_id, 
                title, 
                description, 
                price, 
                stock, 
                image, 
                discount_percent, 
                original_price, 
                created_at 
            FROM products 
            WHERE stock > 0
        """)
    
    products = cur.fetchall()
    cur.close()
    
    return render_template('products/list.html', products=products)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    cur = mysql.connection.cursor()
    
    # Get product with explicit field selection including discount fields
    cur.execute("""
        SELECT 
            id, 
            category_id, 
            title, 
            description, 
            price, 
            stock, 
            image, 
            discount_percent, 
            original_price, 
            created_at 
        FROM products 
        WHERE id = %s
    """, (product_id,))
    
    product = cur.fetchone()
    
    if not product:
        flash('Product not found', 'error')
        cur.close()
        return redirect(url_for('products'))
    
    # Get all images for this product
    cur.execute("SELECT * FROM product_images WHERE product_id = %s ORDER BY is_primary DESC, created_at ASC", (product_id,))
    product_images = cur.fetchall()
    
    cur.close()
    
    return render_template('products/detail.html', product=product, product_images=product_images)

# Add a helper function to get primary image
def get_primary_image(product_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT filename FROM product_images WHERE product_id = %s AND is_primary = TRUE LIMIT 1", (product_id,))
    result = cur.fetchone()
    cur.close()
    
    if result:
        return result[0]
    return None

# Update the inject_global_data function if needed for product listings
@app.context_processor
def inject_global_data():
    cart_count = 0
    if current_user.is_authenticated and not current_user.is_admin:
        cart_count = get_cart_count()
    
    return dict(
        categories=get_categories(),
        cart_count=cart_count,
        format_currency=format_currency,
        format_date=format_date_filter,
        get_primary_image=get_primary_image  
    )

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
        SELECT ci.id, p.id, p.title, p.price, p.discount_percent, p.original_price, p.image, ci.quantity
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.user_id = %s
    """, (current_user.id,))
    
    cart_items_data = cur.fetchall()
    cart_items = []
    grand_total = 0
    total_savings = 0
    has_discounted_items = False
    
    for item in cart_items_data:
        # Extract product data
        cart_item_id = item[0]
        product_id = item[1]
        title = item[2]
        price = item[3]
        discount_percent = item[4] if item[4] else 0
        original_price = item[5]
        image = item[6]
        quantity = item[7]
        
        # Calculate discount information
        discount_info = get_discount_info({
            0: product_id,
            1: None,  # category_id not needed
            2: title,
            3: None,  # description not needed
            4: price,
            5: None,  # stock not needed
            6: image,
            7: discount_percent,
            8: original_price
        })
        
        # Calculate item totals
        item_total_original = price * quantity
        item_total_discounted = discount_info['discounted_price'] * quantity
        item_savings = discount_info['you_save'] * quantity
        
        # Prepare cart item data
        cart_item = {
            'id': cart_item_id,
            'product_id': product_id,
            'title': title,
            'price': price,
            'image': image,
            'quantity': quantity,
            'discount_info': discount_info,
            'item_total_original': item_total_original,
            'item_total_discounted': item_total_discounted,
            'item_savings': item_savings,
            'display_price': discount_info['discounted_price'] if discount_info['has_discount'] else price
        }
        
        cart_items.append(cart_item)
        grand_total += item_total_discounted
        total_savings += item_savings
        
        if discount_info['has_discount']:
            has_discounted_items = True
    
    cur.close()
    
    return render_template('cart/index.html', 
                         cart_items=cart_items, 
                         grand_total=grand_total,
                         total_savings=total_savings,
                         has_discounted_items=has_discounted_items)

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


@app.route('/admin/products/delete_image/<int:image_id>', methods=['POST'])
@login_required
def admin_delete_product_image(image_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    
    # Get image info before deleting
    cur.execute("SELECT product_id, filename FROM product_images WHERE id = %s", (image_id,))
    image_info = cur.fetchone()
    
    if image_info:
        product_id, filename = image_info
        
        # Delete from database
        cur.execute("DELETE FROM product_images WHERE id = %s", (image_id,))
        mysql.connection.commit()
        
        # Delete physical file
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting image file: {e}")
    
    cur.close()
    flash('Image deleted successfully', 'success')
    return redirect(url_for('admin_edit_product', product_id=product_id))

@app.route('/admin/products/set_primary_image/<int:image_id>', methods=['POST'])
@login_required
def admin_set_primary_image(image_id):
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    
    # Get product_id first
    cur.execute("SELECT product_id FROM product_images WHERE id = %s", (image_id,))
    result = cur.fetchone()
    
    if result:
        product_id = result[0]
        
        # Reset all primary flags for this product
        cur.execute("UPDATE product_images SET is_primary = FALSE WHERE product_id = %s", (product_id,))
        
        # Set the selected image as primary
        cur.execute("UPDATE product_images SET is_primary = TRUE WHERE id = %s", (image_id,))
        mysql.connection.commit()
    
    cur.close()
    flash('Primary image updated successfully', 'success')
    return redirect(url_for('admin_edit_product', product_id=product_id))


# Add this function to your app.py to count images for each product
def get_image_count(product_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM product_images WHERE product_id = %s", (product_id,))
    count = cur.fetchone()[0] or 0
    cur.close()
    return count

# Also add this to your context processor if you want to use it in templates
@app.context_processor
def inject_global_data():
    cart_count = 0
    if current_user.is_authenticated and not current_user.is_admin:
        cart_count = get_cart_count()
    
    return dict(
        categories=get_categories(),
        cart_count=cart_count,
        format_currency=format_currency,
        format_date=format_date_filter,
        get_primary_image=get_primary_image,
        get_image_count=get_image_count  # Add this line
    )

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if current_user.is_admin:
        flash('Admin users cannot checkout orders', 'error')
        return redirect(url_for('admin_dashboard'))

    cur = mysql.connection.cursor()

    # Fetch QR setting (tuple: id, key_name, value)
    cur.execute("SELECT * FROM settings WHERE key_name='payment_qr'")
    qr_setting = cur.fetchone()

    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        country = request.form.get('country')
        city = request.form.get('city')
        postal_code = request.form.get('postal_code')
        street = request.form.get('street')
        payment_method = request.form.get('payment_method')

        # For online payment, check if proof is uploaded
        payment_proof = request.files.get('payment_proof') if payment_method == 'online' else None
        if payment_method == 'online' and not payment_proof:
            flash('Please upload payment proof before placing the order.', 'error')
            return redirect(url_for('checkout'))

        address = f"{name}\n{street}\n{city}, {postal_code}\n{country}\nPhone: {phone}"

        # Fetch cart items with discount information
        cur.execute("""
            SELECT p.id, p.title, p.price, p.discount_percent, p.original_price, ci.quantity
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.user_id = %s
        """, (current_user.id,))
        cart_items_data = cur.fetchall()

        if not cart_items_data:
            flash('Your cart is empty', 'error')
            return redirect(url_for('cart'))

        # Calculate totals
        total_amount = 0.0
        total_original_amount = 0.0
        total_savings = 0.0
        order_items_data = []

        for item in cart_items_data:
            product_id, title, price, discount_percent, original_price, quantity = item
            price_float = float(price) if price is not None else 0.0
            discount_percent_float = float(discount_percent) if discount_percent is not None else 0.0
            original_price_float = float(original_price) if original_price is not None else price_float
            quantity_int = int(quantity)

            if discount_percent_float > 0:
                actual_original_price = original_price_float
                actual_discounted_price = calculate_discounted_price(actual_original_price, discount_percent_float)
            else:
                actual_original_price = price_float
                actual_discounted_price = price_float

            item_total = actual_discounted_price * quantity_int
            item_original_total = actual_original_price * quantity_int
            item_savings = float(item_original_total - item_total)

            total_amount += item_total
            total_original_amount += item_original_total
            total_savings += item_savings

            order_items_data.append({
                'product_id': product_id,
                'quantity': quantity_int,
                'unit_price': actual_discounted_price
            })

        # Stock check
        for item in cart_items_data:
            product_id, _, _, _, _, quantity = item
            cur.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
            stock_result = cur.fetchone()
            stock_quantity = stock_result[0] if stock_result else 0
            if stock_quantity < int(quantity):
                flash('Not enough stock for one or more products', 'error')
                cur.close()
                return redirect(url_for('cart'))

        # Insert order
        cur.execute("""
            INSERT INTO orders (user_id, total_amount, address, payment_method, status, payment_proof)
            VALUES (%s, %s, %s, %s, 'pending', %s)
        """, (
            current_user.id,
            total_amount,
            address,
            payment_method,
            payment_proof.filename if payment_proof else None
        ))
        order_id = cur.lastrowid
        mysql.connection.commit()

        # Fetch product names for email
        product_ids = [item[0] for item in cart_items_data]
        product_names = []
        if product_ids:
            cur.execute(
                "SELECT title FROM products WHERE id IN (%s)" % ",".join(["%s"]*len(product_ids)),
                product_ids
            )
            product_names = [row[0] for row in cur.fetchall()]

        # ✅ Send customer order placed email
        send_customer_order_placed_email(
            to_email=current_user.email,
            customer_name=current_user.name,
            order_id=order_id,
            product_names=product_names
        )

        # Save uploaded proof if online
        if payment_method == 'online' and payment_proof:
            filename = secure_filename(f"{uuid.uuid4().hex}_{payment_proof.filename}")
            proof_path = os.path.join(app.config['UPLOAD_FOLDER'], 'payment_proofs', filename)
            os.makedirs(os.path.dirname(proof_path), exist_ok=True)
            payment_proof.save(proof_path)

            cur.execute("UPDATE orders SET payment_proof = %s WHERE id = %s", (filename, order_id))
            mysql.connection.commit()

        # Notify admin
        send_admin_notification()

        # Insert order items + update stock
        for item_data in order_items_data:
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (%s, %s, %s, %s)
            """, (order_id, item_data['product_id'], item_data['quantity'], item_data['unit_price']))

            cur.execute("UPDATE products SET stock = stock - %s WHERE id = %s",
                        (item_data['quantity'], item_data['product_id']))

        # Clear cart
        cur.execute("DELETE FROM cart_items WHERE user_id = %s", (current_user.id,))
        mysql.connection.commit()
        cur.close()

        flash('Order placed successfully!' + (f' You saved {format_currency(total_savings)}!' if total_savings > 0 else ''), 'success')
        return redirect(url_for('order_confirmation', order_id=order_id))

    # GET → render checkout page
    cur.execute("""
        SELECT ci.id, p.id, p.title, p.price, p.discount_percent, p.original_price, p.image, ci.quantity
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.user_id = %s
    """, (current_user.id,))
    cart_items_data = cur.fetchall()

    cart_items = []
    grand_total = 0.0
    total_savings = 0.0
    has_discounted_items = False

    for item in cart_items_data:
        cart_item_id, product_id, title, price, discount_percent, original_price, image, quantity = item
        price_float = float(price) if price is not None else 0.0
        discount_percent_float = float(discount_percent) if discount_percent is not None else 0.0
        original_price_float = float(original_price) if original_price is not None else price_float
        quantity_int = int(quantity)

        if discount_percent_float > 0:
            display_original_price = original_price_float
            display_discounted_price = calculate_discounted_price(display_original_price, discount_percent_float)
        else:
            display_original_price = price_float
            display_discounted_price = price_float

        item_total_original = display_original_price * quantity_int
        item_total_discounted = display_discounted_price * quantity_int
        item_savings = item_total_original - item_total_discounted

        cart_item = {
            'id': cart_item_id,
            'product_id': product_id,
            'title': title,
            'price': price_float,
            'image': image,
            'quantity': quantity_int,
            'discount_info': {
                'has_discount': discount_percent_float > 0,
                'discount_percent': discount_percent_float,
                'original_price': display_original_price,
                'discounted_price': display_discounted_price,
                'you_save': display_original_price - display_discounted_price
            },
            'item_total_original': item_total_original,
            'item_total_discounted': item_total_discounted,
            'item_savings': item_savings,
            'display_price': display_discounted_price
        }

        cart_items.append(cart_item)
        grand_total += item_total_discounted
        total_savings += item_savings
        if discount_percent_float > 0:
            has_discounted_items = True

    if not cart_items:
        flash('Your cart is empty', 'error')
        cur.close()
        return redirect(url_for('cart'))

    cur.close()

    return render_template(
        'cart/checkout.html',
        cart_items=cart_items,
        grand_total=grand_total,
        total_savings=total_savings,
        has_discounted_items=has_discounted_items,
        qr_setting=qr_setting
    )

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

@app.route('/delete_order/<int:order_id>', methods=['POST', 'GET'])
@login_required
def admin_delete_order(order_id):
    # Only allow admin to delete orders
    if not current_user.is_admin:
        flash("You are not authorized to perform this action.", "error")
        return redirect(url_for('index'))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM orders WHERE id = %s", (order_id,))
    mysql.connection.commit()
    cur.close()

    flash("Order deleted successfully.", "success")
    return redirect(url_for('orders'))  # Adjust redirect to your orders listing route

@app.route('/my_orders')
@login_required
def user_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()

    # Fetch only the logged-in user's orders
    cur.execute("""
        SELECT id, user_id, total_amount, address, payment_method, status, tracking_number, created_at
        FROM orders
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (current_user.id, per_page, offset))
    orders = cur.fetchall()

    # Count total orders for pagination
    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s", (current_user.id,))
    total_orders = cur.fetchone()[0]
    cur.close()

    total_pages = (total_orders + per_page - 1) // per_page

    return render_template(
        "user_orders.html",
        orders=orders,
        page=page,
        total_pages=total_pages
    )

@app.route('/orders/<int:order_id>')
@login_required
def user_order_detail(order_id):
    user_id = current_user.id
    cursor = mysql.connection.cursor()

    # Fetch order info
    cursor.execute("""
        SELECT id, total_amount, address, payment_method, status, payment_proof, created_at, tracking_number
        FROM orders
        WHERE id = %s AND user_id = %s
    """, (order_id, user_id))
    order = cursor.fetchone()

    if not order:
        flash("Order not found!", "danger")
        return redirect(url_for('user_orders'))

    order = list(order)
    order[1] = float(order[1])  # total_amount

    # Payment proof URL
    payment_proof_url = None
    if order[3] == 'online' and order[5]:
        payment_proof_url = url_for('static', filename='uploads/payment_proofs/' + order[5])

    # ✅ Fetch order items with product image
    cursor.execute("""
        SELECT p.title, oi.quantity, oi.unit_price, p.image
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()

    # ✅ Build proper URLs for product image
    items = [
    {
        "title": i[0],
        "quantity": i[1],
        "unit_price": float(i[2]),
        "image": url_for('static', filename='uploads/products/' + i[3]) if i[3] else url_for('static', filename='images/no-image.png')
    }
    for i in items
    ]

    # Order tracking steps
    steps = [
        ("pending", "Pending", "🕒"),
        ("confirmed", "Confirmed", "✅"),
        ("packed", "Packed", "📦"),
        ("shipped", "Shipped", "🚚"),
        ("out_for_delivery", "Out for Delivery", "📍"),
        ("delivered", "Delivered", "🎉"),
        ("cancelled", "Cancelled", "❌"),
    ]
    status_map = {s[0]: i for i, s in enumerate(steps)}
    current_index = status_map.get(order[4], -1)

    cursor.close()

    return render_template(
        "user_order_detail.html",
        order=order,
        items=items,
        steps=steps,
        current_index=current_index,
        payment_proof_url=payment_proof_url
    )

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
    SELECT 
        o.id,
        o.created_at,
        o.total_amount,
        o.status,
        u.name,
        GROUP_CONCAT(p.title SEPARATOR ', ') AS product_names
    FROM orders o
    JOIN users u ON o.user_id = u.id
    JOIN order_items oi ON oi.order_id = o.id
    JOIN products p ON p.id = oi.product_id
    GROUP BY o.id
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
    
    # Clear existing cart items and add this single product
    cur.execute("DELETE FROM cart_items WHERE user_id = %s", (current_user.id,))
    cur.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)", 
               (current_user.id, product_id, quantity))
    
    mysql.connection.commit()
    cur.close()
    
    return redirect(url_for('checkout'))  # Make sure this matches your checkout route name



@app.route('/admin/products')
@login_required
def admin_products():
    if not current_user.is_admin:
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    cur = mysql.connection.cursor()
    
    # Use explicit field selection to ensure consistent indices
    cur.execute("""
        SELECT 
            p.id, p.category_id, p.title, p.description, p.price, p.stock, p.image,
            p.discount_percent, p.original_price, p.created_at,
            c.name as category_name
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id 
        ORDER BY p.created_at DESC
    """)
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
        discount_percent = float(request.form.get('discount_percent', 0))
        original_price_str = request.form.get('original_price')
        
        # Handle discount logic
        original_price = None
        if discount_percent > 0:
            if original_price_str and original_price_str.strip():
                original_price = float(original_price_str)
            else:
                # If discount is set but no original price provided, use current price as original
                original_price = price
        
        # Validate discount percentage
        if discount_percent < 0 or discount_percent > 100:
            flash('Discount percentage must be between 0 and 100', 'error')
            return redirect(url_for('admin_add_product'))
        
        # Validate original price if provided
        if original_price and original_price <= 0:
            flash('Original price must be greater than 0', 'error')
            return redirect(url_for('admin_add_product'))
        
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO products (title, description, price, stock, category_id, discount_percent, original_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (title, description, price, stock, category_id, discount_percent, original_price))
        
        product_id = cur.lastrowid
        
        # Handle multiple image uploads
        if 'images' in request.files:
            files = request.files.getlist('images')
            primary_set = False
            
            for i, file in enumerate(files):
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    file.save(filepath)
                    
                    # First image becomes primary by default
                    is_primary = not primary_set
                    if is_primary:
                        primary_set = True
                    
                    cur.execute("""
                        INSERT INTO product_images (product_id, filename, is_primary)
                        VALUES (%s, %s, %s)
                    """, (product_id, filename, is_primary))
        
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
        discount_percent = float(request.form.get('discount_percent', 0))
        original_price_str = request.form.get('original_price')
        
        # Handle discount logic
        original_price = None
        if discount_percent > 0:
            if original_price_str and original_price_str.strip():
                original_price = float(original_price_str)
            else:
                # If discount is set but no original price provided, use current price as original
                original_price = price
        else:
            # If discount is 0, clear the original price
            original_price = None
        
        # Validate discount percentage
        if discount_percent < 0 or discount_percent > 100:
            flash('Discount percentage must be between 0 and 100', 'error')
            return redirect(url_for('admin_edit_product', product_id=product_id))
        
        # Validate original price if provided
        if original_price and original_price <= 0:
            flash('Original price must be greater than 0', 'error')
            return redirect(url_for('admin_edit_product', product_id=product_id))
        
        # Check if discount makes sense (discounted price should be lower than original)
        if original_price and discount_percent > 0:
            discounted_price = calculate_discounted_price(original_price, discount_percent)
            if discounted_price >= original_price:
                flash('Discounted price should be lower than original price', 'error')
                return redirect(url_for('admin_edit_product', product_id=product_id))
        
        cur.execute("""
            UPDATE products 
            SET title = %s, description = %s, price = %s, stock = %s, category_id = %s, 
                discount_percent = %s, original_price = %s
            WHERE id = %s
        """, (title, description, price, stock, category_id, discount_percent, original_price, product_id))
        
        # Handle additional image uploads
        if 'images' in request.files:
            files = request.files.getlist('images')
            
            for file in files:
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    file.save(filepath)
                    
                    cur.execute("""
                        INSERT INTO product_images (product_id, filename, is_primary)
                        VALUES (%s, %s, FALSE)
                    """, (product_id, filename))
        
        mysql.connection.commit()
        cur.close()
        
        flash('Product updated successfully', 'success')
        return redirect(url_for('admin_products'))
    
    # GET request - fetch product data
    cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('admin_products'))
    
    # Get all images for this product
    cur.execute("SELECT * FROM product_images WHERE product_id = %s ORDER BY is_primary DESC, created_at ASC", (product_id,))
    product_images = cur.fetchall()
    
    categories = get_categories()
    cur.close()
    
    return render_template('admin/product_form.html', product=product, categories=categories, product_images=product_images)
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
    # page = request.args.get('page', 1, type=int)
    page = int(request.args.get("page", 1))

    per_page = 10
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()
    
    if status_filter:
        cur.execute("""
            SELECT o.*, GROUP_CONCAT(p.title SEPARATOR ', ') as product_names
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status = %s
            GROUP BY o.id
            ORDER BY o.created_at DESC
            LIMIT %s OFFSET %s
        """, (status_filter, per_page, offset))
    else:
        cur.execute("""
            SELECT o.*, GROUP_CONCAT(p.title SEPARATOR ', ') as product_names
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN products p ON oi.product_id = p.id
            GROUP BY o.id
            ORDER BY o.created_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))

    orders = cur.fetchall()

    # Count total orders for pagination
    if status_filter:
        cur.execute("SELECT COUNT(*) FROM orders WHERE status = %s", (status_filter,))
    else:
        cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]
    cur.close()

    total_pages = (total_orders + per_page - 1) // per_page

    return render_template(
        "admin/orders.html",
        orders=orders,
        status_filter=status_filter,
        page=page,
        total_pages=total_pages,
    )
    
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

    # Get customer email + name
    cur.execute("""
        SELECT u.email, u.name, o.id, o.tracking_number
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = %s
    """, (order_id,))
    order = cur.fetchone()
    cur.close()

    if order:
        user_email, user_name, order_id, tracking_no = order
        send_customer_order_status_email(user_email, user_name, order_id, status, tracking_no)

    flash('Order status updated successfully', 'success')
    return redirect(url_for('admin_orders'))

def send_admin_order_cancel_email(order_id, customer_name, customer_email):
    sender_email = "info.swadgalli@gmail.com"
    sender_password = "chfy qktf tnuz esgl"  # Gmail app password
    admin_email = "jasmirchy@gmail.com"

    subject = f"Order #{order_id} Cancelled by Customer"
    body = f"Order #{order_id} has been cancelled by the customer.\nCustomer Name: {customer_name}\nCustomer Email: {customer_email}"

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = admin_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, admin_email, msg.as_string())
    except Exception as e:
        print(f"Failed to send admin email: {e}")

def send_customer_order_cancel_email(to_email, customer_name, order_id):
    sender_email = "info.swadgalli@gmail.com"
    sender_password = "chfy qktf tnuz esgl"

    subject = f"Your Order #{order_id} has been Cancelled"
    body = f"Hello {customer_name},\n\nYour order (Order ID: {order_id}) has been successfully cancelled by you.\n\nThank you for shopping with SwadGaLLi!"

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
    except Exception as e:
        print(f"Failed to send customer email: {e}")

@app.route('/cancel_order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    cur = mysql.connection.cursor()
    
    # Get order details
    cur.execute("SELECT status, user_id FROM orders WHERE id = %s", (order_id,))
    order = cur.fetchone()
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('user_orders'))

    status, user_id = order

    # Check if order can be cancelled
    if status in ['shipped', 'delivered', 'cancelled']:
        flash('This order cannot be cancelled', 'error')
        cur.close()
        return redirect(url_for('user_orders'))

    # Update order status
    cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s", (order_id,))
    mysql.connection.commit()

    # Get user info for email
    cur.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()

    if user:
        user_email, user_name = user

        # 1️⃣ Send email to admin
        send_admin_order_cancel_email(order_id, user_name, user_email)

        # 2️⃣ Send email to customer
        send_customer_order_cancel_email(user_email, user_name, order_id)

    flash('Order cancelled successfully', 'success')
    return redirect(url_for('user_orders'))


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
    
    return render_template('admin/banners.html', banners=banners)

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