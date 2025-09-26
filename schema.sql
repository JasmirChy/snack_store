-- Create database
CREATE DATABASE IF NOT EXISTS snack_store;
USE snack_store;

-- Users table
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Categories table
CREATE TABLE categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

-- Products table
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT,
    title VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    image VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
);

-- Cart items table
CREATE TABLE cart_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- Orders table
CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    address TEXT NOT NULL,
    payment_method ENUM('cod', 'online') NOT NULL,
    payment_proof VARCHAR(255),
    status ENUM('pending','confirmed', 'packed', 'shipped','out_of_delivery', 'delivered', 'cancelled') DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
ALTER TABLE orders
ADD COLUMN tracking_number VARCHAR(100) AFTER payment_proof;
ALTER TABLE orders 
ADD COLUMN payment_status ENUM('pending', 'paid', 'failed') DEFAULT 'pending',
ADD COLUMN khalti_token VARCHAR(255),
ADD COLUMN khalti_transaction_id VARCHAR(255),
ADD COLUMN paid_at TIMESTAMP NULL;


-- Order items table
CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- Banners table
CREATE TABLE banners (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(100),
    slider_text TEXT,
    image VARCHAR(255) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE slider_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type ENUM('image','video') NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    title VARCHAR(100),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Settings table
CREATE TABLE settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    key_name VARCHAR(50) UNIQUE NOT NULL,
    value TEXT NOT NULL
);


-- Payments table
CREATE TABLE payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    user_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    method ENUM('cod', 'online') NOT NULL,
    proof VARCHAR(255), -- stores receipt image / transaction id screenshot
    status ENUM('pending', 'completed', 'failed') DEFAULT 'pending',
    transaction_id VARCHAR(100), -- optional, store gateway txn ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);


-- CREATE TABLE reviews (
--     id INT AUTO_INCREMENT PRIMARY KEY,
--     type ENUM('image', 'video') NOT NULL,
--     file_path VARCHAR(255) NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );

CREATE TABLE reviews (
id INT AUTO_INCREMENT PRIMARY KEY,
type ENUM('image', 'video') NOT NULL,
file_path VARCHAR(255) NOT NULL,
video varchar(255) NOT NULL,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE product_images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- Add index for better performance
CREATE INDEX idx_product_images_product_id ON product_images(product_id);
CREATE INDEX idx_product_images_primary ON product_images(is_primary);

-- Insert sample data
INSERT INTO categories (name) VALUES 
('Chips'), 
('Chocolate'), 
('Nuts'), 
('Cookies');

INSERT INTO products (category_id, title, description, price, stock, image) VALUES
(1, 'Potato Chips', 'Crispy and delicious potato chips', 2.99, 100, 'chips.jpg'),
(2, 'Milk Chocolate Bar', 'Creamy milk chocolate', 3.49, 80, 'chocolate.jpg'),
(3, 'Salted Almonds', 'Premium roasted almonds', 4.99, 50, 'almonds.jpg'),
(4, 'Chocolate Chip Cookies', 'Classic cookies with chocolate chips', 2.49, 120, 'cookies.jpg');

INSERT INTO banners (title, image, active) VALUES
('Summer Sale!', 'banner1.jpg', TRUE);

INSERT INTO settings (key_name, value) VALUES
('payment_qr', 'qr-code.png');

-- Create admin user (password: admin123)
INSERT INTO users (name, email, password_hash, is_admin) VALUES 
('Admin ', 'jasmirchy@gmail.com', '$2a$12$AEI6LcLJyquViKBTe5h9DOM.bN3cPV/BmlPUpWbt73liCBSvwC9Ty', TRUE);