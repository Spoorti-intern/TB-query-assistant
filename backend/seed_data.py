import os
import pymysql

conn = pymysql.connect(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", "3306")),
    user=os.getenv("MYSQL_USER", "root"),
    password=os.getenv("MYSQL_PASSWORD", ""),
    database=os.getenv("MYSQL_DATABASE", "defaultdb"),
    ssl={"ssl": True} if os.getenv("MYSQL_SSL") else None,
)

cur = conn.cursor()

# Drop existing tables (order matters for FK)
cur.execute("DROP TABLE IF EXISTS orders")
cur.execute("DROP TABLE IF EXISTS products")
cur.execute("DROP TABLE IF EXISTS customers")

# Create customers
cur.execute("""
CREATE TABLE customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    city VARCHAR(100),
    joined_date DATE
)
""")

# Create products
cur.execute("""
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10,2) NOT NULL,
    stock INT DEFAULT 0
)
""")

# Create orders
cur.execute("""
CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    order_date DATE,
    total DECIMAL(10,2),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
)
""")

# Insert customers
customers = [
    ("Alice Johnson", "alice@example.com", "New York", "2023-01-15"),
    ("Bob Smith", "bob@example.com", "Los Angeles", "2023-02-20"),
    ("Carol White", "carol@example.com", "Chicago", "2023-03-10"),
    ("David Brown", "david@example.com", "Houston", "2023-04-05"),
    ("Eva Martinez", "eva@example.com", "Phoenix", "2023-05-18"),
    ("Frank Lee", "frank@example.com", "New York", "2023-06-22"),
    ("Grace Kim", "grace@example.com", "Chicago", "2023-07-30"),
    ("Henry Wilson", "henry@example.com", "Los Angeles", "2023-08-14"),
    ("Ivy Chen", "ivy@example.com", "Seattle", "2023-09-01"),
    ("Jack Davis", "jack@example.com", "Denver", "2023-10-11"),
]
cur.executemany(
    "INSERT INTO customers (name, email, city, joined_date) VALUES (%s,%s,%s,%s)",
    customers,
)

# Insert products
products = [
    ("Wireless Mouse", "Electronics", 29.99, 150),
    ("Mechanical Keyboard", "Electronics", 89.99, 75),
    ("USB-C Hub", "Electronics", 49.99, 200),
    ("Notebook Pack", "Stationery", 12.50, 500),
    ("Desk Lamp", "Home Office", 34.99, 120),
    ("Monitor Stand", "Home Office", 59.99, 60),
    ("Webcam HD", "Electronics", 69.99, 90),
    ("Ergonomic Chair", "Furniture", 299.99, 25),
    ("Standing Desk Mat", "Furniture", 44.99, 180),
    ("Cable Organizer", "Accessories", 9.99, 350),
]
cur.executemany(
    "INSERT INTO products (name, category, price, stock) VALUES (%s,%s,%s,%s)",
    products,
)

# Insert orders
orders = [
    (1, 1, 2, "2024-01-10", 59.98),
    (1, 3, 1, "2024-01-15", 49.99),
    (2, 2, 1, "2024-02-03", 89.99),
    (3, 5, 1, "2024-02-14", 34.99),
    (3, 4, 3, "2024-02-14", 37.50),
    (4, 8, 1, "2024-03-01", 299.99),
    (5, 7, 2, "2024-03-10", 139.98),
    (6, 1, 1, "2024-03-22", 29.99),
    (6, 10, 5, "2024-03-22", 49.95),
    (7, 6, 1, "2024-04-05", 59.99),
    (8, 9, 2, "2024-04-18", 89.98),
    (9, 2, 1, "2024-05-02", 89.99),
    (9, 3, 2, "2024-05-02", 99.98),
    (10, 5, 1, "2024-05-20", 34.99),
    (2, 10, 3, "2024-06-01", 29.97),
]
cur.executemany(
    "INSERT INTO orders (customer_id, product_id, quantity, order_date, total) VALUES (%s,%s,%s,%s,%s)",
    orders,
)

conn.commit()

# Verify
for table in ("customers", "products", "orders"):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    print(f"{table}: {cur.fetchone()[0]} rows")

cur.close()
conn.close()
print("Done!")
