
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from fastapi import HTTPException

from app.core.crypto import decrypt_password


def get_mongodb_client(connector):
    """
    Create a MongoDB client using saved connector details.
    """

    client = None

    try:
        password = decrypt_password(connector.password)

        if connector.username and password:
            client = MongoClient(
                host=connector.host,
                port=connector.port or 27017,
                username=connector.username,
                password=password,
                authSource=connector.database,
                serverSelectionTimeoutMS=5000
            )

        else:
            client = MongoClient(
                host=connector.host,
                port=connector.port or 27017,
                serverSelectionTimeoutMS=5000
            )

        return client

    except PyMongoError as error:
        if client:
            client.close()

        raise HTTPException(
            status_code=400,
            detail=f"MongoDB client creation failed: {str(error)}"
        )


def test_mongodb_connection(connector):
    """
    Verify MongoDB connectivity and return database information.
    """

    client = None

    try:
        client = get_mongodb_client(connector)

        client.admin.command("ping")

        database = client[connector.database]

        return {
            "success": True,
            "message": "MongoDB connection successful!",
            "database": connector.database,
            "collections": database.list_collection_names()
        }

    except PyMongoError as error:
        raise HTTPException(
            status_code=400,
            detail=f"MongoDB connection failed: {str(error)}"
        )

    finally:
        if client:
            client.close()