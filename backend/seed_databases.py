"""Seed sample tables with test data into Supabase and Neon PostgreSQL databases."""

import psycopg

import os

DATABASES = {
    "Supabase": os.getenv("SUPABASE_DATABASE_URL", "postgresql://user:pass@localhost:5432/postgres"),
    "Neon": os.getenv("NEON_DATABASE_URL", "postgresql://user:pass@localhost:5432/neondb"),
}

DDL = """
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    city VARCHAR(100),
    joined_date DATE NOT NULL
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(80),
    price NUMERIC(10,2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    order_date DATE NOT NULL,
    total NUMERIC(10,2) NOT NULL
);
"""

CUSTOMERS = """
INSERT INTO customers (name, email, city, joined_date) VALUES
('Alice Johnson',   'alice@example.com',   'New York',      '2023-01-15'),
('Bob Smith',       'bob@example.com',     'San Francisco', '2023-02-20'),
('Charlie Lee',     'charlie@example.com', 'Chicago',       '2023-03-10'),
('Diana Patel',     'diana@example.com',   'Houston',       '2023-04-05'),
('Ethan Brown',     'ethan@example.com',   'Phoenix',       '2023-05-18'),
('Fiona Garcia',    'fiona@example.com',   'Philadelphia',  '2023-06-22'),
('George Wilson',   'george@example.com',  'San Antonio',   '2023-07-30'),
('Hannah Davis',    'hannah@example.com',  'Dallas',        '2023-08-14'),
('Ivan Martinez',   'ivan@example.com',    'Austin',        '2023-09-01'),
('Julia Anderson',  'julia@example.com',   'Seattle',       '2023-10-11');
"""

PRODUCTS = """
INSERT INTO products (name, category, price, stock) VALUES
('Wireless Mouse',      'Electronics',  29.99,  150),
('Mechanical Keyboard', 'Electronics',  89.99,  75),
('USB-C Hub',           'Electronics',  49.99,  200),
('Standing Desk',       'Furniture',    349.99, 30),
('Ergonomic Chair',     'Furniture',    499.99, 20),
('Monitor Arm',         'Furniture',    79.99,  60),
('Notebook Pack (3)',    'Stationery',   12.99,  500),
('Gel Pen Set',         'Stationery',   8.99,   400),
('Desk Lamp',           'Lighting',     45.99,  100),
('Webcam HD',           'Electronics',  69.99,  90);
"""

ORDERS = """
INSERT INTO orders (customer_id, product_id, quantity, order_date, total) VALUES
(1, 1, 2, '2024-01-10', 59.98),
(1, 3, 1, '2024-01-15', 49.99),
(2, 2, 1, '2024-02-01', 89.99),
(3, 5, 1, '2024-02-14', 499.99),
(4, 4, 1, '2024-03-03', 349.99),
(5, 7, 3, '2024-03-20', 38.97),
(6, 9, 2, '2024-04-05', 91.98),
(7, 10, 1, '2024-04-18', 69.99),
(8, 6, 1, '2024-05-02', 79.99),
(9, 8, 4, '2024-05-15', 35.96),
(10, 1, 1, '2024-06-01', 29.99),
(2, 4, 1, '2024-06-10', 349.99),
(3, 3, 2, '2024-07-04', 99.98),
(5, 9, 1, '2024-07-20', 45.99),
(8, 2, 1, '2024-08-01', 89.99);
"""


def seed(name: str, dsn: str):
    print(f"\n{'='*50}")
    print(f"Seeding {name} ...")
    print(f"{'='*50}")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            print("  Tables created.")
            cur.execute(CUSTOMERS)
            print(f"  Inserted {cur.rowcount} customers.")
            cur.execute(PRODUCTS)
            print(f"  Inserted {cur.rowcount} products.")
            cur.execute(ORDERS)
            print(f"  Inserted {cur.rowcount} orders.")

            # Quick verification
            for table in ("customers", "products", "orders"):
                cur.execute(f"SELECT count(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  {table}: {count} rows")
        conn.commit()
    print(f"  {name} seeded successfully!")


if __name__ == "__main__":
    for db_name, dsn in DATABASES.items():
        seed(db_name, dsn)
    print("\nAll done.")
