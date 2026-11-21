
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict


class ConnectorConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    connector_type: Literal[
        "postgresql",
        "mysql",
        "mongodb",
        "supabase",
        "mssql",
        "sqlite",
        "oracle",
        "mariadb",
        "cockroachdb",
        "redis",
        "cassandra",
        "neo4j",
        "elasticsearch",
        "clickhouse",
        "influxdb",
        "couchdb",
    ]

    host: str = Field(..., min_length=1, max_length=255)

    port: Optional[int] = Field(
        default=None,
        ge=1,
        le=65535
    )

    database: str = Field(
        ...,
        min_length=1,
        max_length=255
    )

    username: Optional[str] = Field(
        default=None,
        max_length=255
    )

    password: Optional[str] = Field(
        default=None,
        max_length=500
    )


class ConnectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    connector_type: Literal[
        "postgresql",
        "mysql",
        "mongodb",
        "supabase",
        "mssql",
        "sqlite",
        "oracle",
        "mariadb",
        "cockroachdb",
        "redis",
        "cassandra",
        "neo4j",
        "elasticsearch",
        "clickhouse",
        "influxdb",
        "couchdb",
    ]
    status: str
    database: str