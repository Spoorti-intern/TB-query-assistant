
from sqlalchemy import inspect
from fastapi import HTTPException


def discover_database_schema(engine, connector_type, database_name):
    """
    Dynamically discover tables, views, columns,
    primary keys and foreign keys.

    Supports:
    - PostgreSQL
    - Supabase PostgreSQL
    - MySQL
    """

    try:
        connector_type = connector_type.lower()
        inspector = inspect(engine)

        # Select database schema
        if connector_type in ("postgresql", "supabase"):
            schema_name = "public"

        elif connector_type == "mysql":
            schema_name = database_name

        elif connector_type in ("mssql", "sqlserver"):
            schema_name = "dbo"

        elif connector_type in ("sqlite",):
            schema_name = None  # SQLite has no schema concept

        elif connector_type in ("oracle",):
            schema_name = database_name.upper() if database_name else None

        elif connector_type in ("mariadb",):
            schema_name = database_name

        elif connector_type in ("cockroachdb",):
            schema_name = "public"

        else:
            # Fallback: try "public" schema (works for most SQL DBs)
            schema_name = "public"

        # Discover tables and views
        table_names = inspector.get_table_names(
            schema=schema_name
        )

        view_names = inspector.get_view_names(
            schema=schema_name
        )

        all_objects = sorted(set(table_names + view_names))

        # For large databases, return just table names (fast path)
        if len(all_objects) > 50:
            return {
                "database": database_name,
                "connector_type": connector_type,
                "schema": schema_name,
                "total_tables": len(all_objects),
                "table_names": all_objects,
                "note": f"Large database with {len(all_objects)} tables. Use search_tables to find specific tables."
            }

        tables = []

        for table_name in all_objects:

            is_table = table_name in table_names

            columns = inspector.get_columns(
                table_name,
                schema=schema_name
            )

            # Primary key information
            primary_key = (
                inspector.get_pk_constraint(
                    table_name,
                    schema=schema_name
                )
                if is_table else {}
            )

            # Foreign key information
            foreign_keys = []

            if is_table:
                foreign_keys = inspector.get_foreign_keys(
                    table_name,
                    schema=schema_name
                )

            tables.append({
                "table_name": table_name,
                "object_type": (
                    "table" if is_table else "view"
                ),
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
            "database": database_name,
            "connector_type": connector_type,
            "schema": schema_name,
            "total_tables": len(tables),
            "tables": tables
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Schema discovery failed: {str(error)}"
        )