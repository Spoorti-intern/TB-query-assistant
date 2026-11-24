from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models.connector import Connector
from app.models.user import User
from app.schemas.connector import ConnectorConfig, ConnectorResponse

from app.core.connector_manager import get_connector_engine
from app.core.schema_manager import discover_database_schema
from app.core.mongodb_adapter import test_mongodb_connection
from app.core.mongodb_schema_manager import discover_mongodb_schema
from app.core.crypto import encrypt_password
from app.core import nosql_adapters
from app.core.auth import get_current_user


router = APIRouter(
    prefix="/api/connectors",
    tags=["Connectors"]
)


# CREATE CONNECTOR
@router.post(
    "/",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED
)
def create_connector(
    connector_data: ConnectorConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = connector_data.model_dump()
    if data.get("password"):
        data["password"] = encrypt_password(data["password"])

    new_connector = Connector(
        **data,
        status="configured",
        user_id=str(current_user.id),
    )

    try:
        db.add(new_connector)
        db.commit()
        db.refresh(new_connector)

        return new_connector

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to save database connector."
        )


# GET ALL CONNECTORS
@router.get("/", response_model=list[ConnectorResponse])
def get_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Connector).filter(Connector.user_id == str(current_user.id)).all()


# TEST DATABASE CONNECTION
@router.post("/{connector_id}/test")
def test_connector_connection(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connector = db.query(Connector).filter(
        Connector.id == connector_id,
        Connector.user_id == str(current_user.id),
    ).first()

    if not connector:
        raise HTTPException(
            status_code=404,
            detail="Connector not found"
        )

    engine = None

    try:

        # MONGODB CONNECTION
        if connector.connector_type == "mongodb":

            result = test_mongodb_connection(connector)

            connector.status = "connected"
            db.commit()

            return {
                **result,
                "connector_id": connector.id,
                "status": connector.status
            }

        # NOSQL ADAPTERS (Redis, Cassandra, Neo4j, Elasticsearch, ClickHouse, InfluxDB, CouchDB)
        nosql_testers = {
            "redis": nosql_adapters.test_redis_connection,
            "cassandra": nosql_adapters.test_cassandra_connection,
            "neo4j": nosql_adapters.test_neo4j_connection,
            "elasticsearch": nosql_adapters.test_elasticsearch_connection,
            "clickhouse": nosql_adapters.test_clickhouse_connection,
            "influxdb": nosql_adapters.test_influxdb_connection,
            "couchdb": nosql_adapters.test_couchdb_connection,
        }

        if connector.connector_type in nosql_testers:
            result = nosql_testers[connector.connector_type](connector)
            connector.status = "connected"
            db.commit()
            return {
                **result,
                "connector_id": connector.id,
                "status": connector.status,
            }

        # SQL DATABASES (PostgreSQL, MySQL, MSSQL, SQLite, Oracle, MariaDB, CockroachDB)
        engine = get_connector_engine(connector)

        with engine.connect() as connection:

            if connector.connector_type in ("postgresql", "supabase", "cockroachdb"):

                result = connection.execute(
                    text(
                        "SELECT current_database(), current_user"
                    )
                ).fetchone()

            elif connector.connector_type in ("mysql", "mariadb"):

                result = connection.execute(
                    text(
                        "SELECT DATABASE(), CURRENT_USER()"
                    )
                ).fetchone()

            elif connector.connector_type == "mssql":

                result = connection.execute(
                    text(
                        "SELECT DB_NAME(), SUSER_SNAME()"
                    )
                ).fetchone()

            elif connector.connector_type == "sqlite":

                result = connection.execute(
                    text("SELECT 'sqlite', 'local'")
                ).fetchone()

            elif connector.connector_type == "oracle":

                result = connection.execute(
                    text(
                        "SELECT SYS_CONTEXT('USERENV','DB_NAME'), "
                        "SYS_CONTEXT('USERENV','SESSION_USER') FROM DUAL"
                    )
                ).fetchone()

            else:
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported database connector."
                )

            database_name = result[0]
            username = result[1]

        connector.status = "connected"
        db.commit()

        return {
            "success": True,
            "message": (
                f"{connector.connector_type.upper()} "
                "connection successful!"
            ),
            "database": database_name,
            "username": username,
            "connector_id": connector.id,
            "status": connector.status
        }

    except HTTPException:
        raise

    except Exception as error:

        db.rollback()

        connector.status = "connection_failed"
        db.commit()

        raise HTTPException(
            status_code=400,
            detail=(
                f"Connection test failed: "
                f"{type(error).__name__}: {error}"
            )
        )

    finally:
        if engine:
            engine.dispose()


# DISCOVER DATABASE SCHEMA
@router.get("/{connector_id}/schema")
def get_connector_schema(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connector = db.query(Connector).filter(
        Connector.id == connector_id,
        Connector.user_id == str(current_user.id),
    ).first()

    if not connector:
        raise HTTPException(
            status_code=404,
            detail="Connector not found"
        )

    if connector.status != "connected":
        raise HTTPException(
            status_code=400,
            detail=(
                "Please test and connect this database "
                "before discovering its schema."
            )
        )

    # MONGODB SCHEMA DISCOVERY
    if connector.connector_type == "mongodb":

        schema = discover_mongodb_schema(connector)

        return {
            "success": True,
            "message": "MongoDB schema discovered successfully!",
            "connector_id": connector.id,
            **schema
        }

    # NOSQL SCHEMA DISCOVERY
    nosql_discoverers = {
        "redis": nosql_adapters.discover_redis_schema,
        "cassandra": nosql_adapters.discover_cassandra_schema,
        "neo4j": nosql_adapters.discover_neo4j_schema,
        "elasticsearch": nosql_adapters.discover_elasticsearch_schema,
        "clickhouse": nosql_adapters.discover_clickhouse_schema,
        "influxdb": nosql_adapters.discover_influxdb_schema,
        "couchdb": nosql_adapters.discover_couchdb_schema,
    }

    if connector.connector_type in nosql_discoverers:
        try:
            schema = nosql_discoverers[connector.connector_type](connector)
            return {
                "success": True,
                "message": f"{connector.connector_type} schema discovered!",
                "connector_id": connector.id,
                **schema,
            }
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Schema discovery failed: {str(error)}"
            )

    # SQL DATABASE SCHEMA DISCOVERY (PostgreSQL, MySQL, MSSQL, SQLite, Oracle, MariaDB, CockroachDB)
    engine = None

    try:
        engine = get_connector_engine(connector)

        schema = discover_database_schema(
            engine=engine,
            connector_type=connector.connector_type,
            database_name=connector.database
        )

        return {
            "success": True,
            "message": "Database schema discovered successfully!",
            "connector_id": connector.id,
            **schema
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Schema discovery failed: {str(error)}"
        )

    finally:
        if engine:
            engine.dispose()


# GET SINGLE CONNECTOR
@router.get(
    "/{connector_id}",
    response_model=ConnectorResponse
)
def get_connector(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connector = db.query(Connector).filter(
        Connector.id == connector_id,
        Connector.user_id == str(current_user.id),
    ).first()

    if not connector:
        raise HTTPException(
            status_code=404,
            detail="Connector not found"
        )

    return connector


# DELETE CONNECTOR
@router.delete("/{connector_id}")
def delete_connector(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connector = db.query(Connector).filter(
        Connector.id == connector_id,
        Connector.user_id == str(current_user.id),
    ).first()

    if not connector:
        raise HTTPException(
            status_code=404,
            detail="Connector not found"
        )

    db.delete(connector)
    db.commit()

    return {
        "message": "Connector deleted successfully"
    }