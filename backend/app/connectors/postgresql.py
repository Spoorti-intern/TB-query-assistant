
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL


def discover_postgresql_schema(connector):
    """
    Discover tables, columns, primary keys and foreign keys
    from a connected PostgreSQL database.
    """

    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=connector.username,
        password=connector.password,
        host=connector.host,
        port=connector.port or 5432,
        database=connector.database
    )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5}
    )

    try:
        inspector = inspect(engine)

        tables = []

        for table_name in inspector.get_table_names(
            schema="public"
        ):
            columns = inspector.get_columns(
                table_name,
                schema="public"
            )

            primary_key = inspector.get_pk_constraint(
                table_name,
                schema="public"
            )

            foreign_keys = inspector.get_foreign_keys(
                table_name,
                schema="public"
            )

            tables.append({
                "table_name": table_name,
                "columns": [
                    {
                        "column_name": column["name"],
                        "data_type": str(column["type"]),
                        "nullable": column["nullable"]
                    }
                    for column in columns
                ],
                "primary_key": primary_key.get(
                    "constrained_columns", []
                ),
                "foreign_keys": [
                    {
                        "columns": fk.get(
                            "constrained_columns", []
                        ),
                        "referred_table": fk.get(
                            "referred_table"
                        ),
                        "referred_columns": fk.get(
                            "referred_columns", []
                        )
                    }
                    for fk in foreign_keys
                ]
            })

        return {
            "database": connector.database,
            "total_tables": len(tables),
            "tables": tables
        }

    finally:
        engine.dispose()