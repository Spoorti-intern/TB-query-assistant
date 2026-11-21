
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from fastapi import HTTPException

from app.core.crypto import decrypt_password


def get_connector_engine(connector):
    """
    Create a database engine based on connector type.
    Supports PostgreSQL and MySQL.
    Supabase PostgreSQL connections use SSL.
    """

    connector_type = connector.connector_type.lower()

    password = decrypt_password(connector.password)

    try:
        if connector_type in ("postgresql", "supabase"):

            database_url = URL.create(
                drivername="postgresql+psycopg",
                username=connector.username,
                password=password,
                host=connector.host,
                port=connector.port or 5432,
                database=connector.database
            )

            connect_args = {
                "connect_timeout": 5
            }

            # Enable SSL for cloud PostgreSQL providers
            if (
                connector_type == "supabase"
                or "supabase.co" in connector.host
                or "pooler.supabase.com" in connector.host
                or "neon.tech" in connector.host
                or "aivencloud.com" in connector.host
            ):
                connect_args["sslmode"] = "require"

            return create_engine(
                database_url,
                pool_pre_ping=True,
                pool_timeout=10,
                pool_recycle=300,
                pool_size=2,
                max_overflow=3,
                connect_args=connect_args
            )

        elif connector_type == "mysql":

            database_url = URL.create(
                drivername="mysql+pymysql",
                username=connector.username,
                password=password,
                host=connector.host,
                port=connector.port or 3306,
                database=connector.database
            )

            connect_args = {
                "connect_timeout": 5,
                "read_timeout": 30,
                "write_timeout": 10,
            }

            # Enable SSL for cloud MySQL providers (Aiven, PlanetScale, etc.)
            if (
                "aivencloud.com" in connector.host
                or "planetscale" in connector.host
            ):
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connect_args["ssl"] = ssl_context

            return create_engine(
                database_url,
                pool_pre_ping=True,
                pool_timeout=10,
                pool_recycle=300,
                pool_size=2,
                max_overflow=3,
                connect_args=connect_args
            )

        elif connector_type == "mssql":

            database_url = URL.create(
                drivername="mssql+pymssql",
                username=connector.username,
                password=password,
                host=connector.host,
                port=connector.port or 1433,
                database=connector.database
            )

            connect_args = {
                "login_timeout": 10,
            }

            return create_engine(
                database_url,
                pool_pre_ping=True,
                pool_timeout=10,
                pool_recycle=300,
                pool_size=2,
                max_overflow=3,
                connect_args=connect_args
            )

        elif connector_type == "sqlite":

            # SQLite uses file path as database
            db_path = connector.database or ":memory:"
            database_url = f"sqlite:///{db_path}"

            return create_engine(
                database_url,
                pool_pre_ping=True,
                connect_args={"timeout": 10},
            )

        elif connector_type == "oracle":

            database_url = URL.create(
                drivername="oracle+oracledb",
                username=connector.username,
                password=password,
                host=connector.host,
                port=connector.port or 1521,
                database=connector.database,
            )

            return create_engine(
                database_url,
                pool_pre_ping=True,
                pool_timeout=10,
                pool_recycle=300,
                pool_size=2,
                max_overflow=3,
                thick_mode=False,
            )

        elif connector_type == "mariadb":

            database_url = URL.create(
                drivername="mysql+pymysql",
                username=connector.username,
                password=password,
                host=connector.host,
                port=connector.port or 3306,
                database=connector.database,
            )

            connect_args = {
                "connect_timeout": 5,
                "read_timeout": 30,
                "write_timeout": 10,
            }

            return create_engine(
                database_url,
                pool_pre_ping=True,
                pool_timeout=10,
                pool_recycle=300,
                pool_size=2,
                max_overflow=3,
                connect_args=connect_args,
            )

        elif connector_type == "cockroachdb":

            database_url = URL.create(
                drivername="postgresql+psycopg",
                username=connector.username,
                password=password,
                host=connector.host,
                port=connector.port or 26257,
                database=connector.database,
            )

            connect_args = {"connect_timeout": 5, "sslmode": "require"}

            return create_engine(
                database_url,
                pool_pre_ping=True,
                pool_timeout=10,
                pool_recycle=300,
                pool_size=2,
                max_overflow=3,
                connect_args=connect_args,
            )

        elif connector_type in ("mongodb", "redis", "cassandra", "neo4j",
                                "elasticsearch", "clickhouse", "influxdb", "couchdb"):

            raise HTTPException(
                status_code=501,
                detail=(
                    f"{connector_type} uses a dedicated adapter, not SQLAlchemy. "
                    "Use the appropriate NoSQL adapter instead."
                )
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported connector type: {connector_type}"
            )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"Database engine creation failed: {str(error)}"
        )
