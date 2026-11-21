
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.core.mongodb_adapter import get_mongodb_client


def _serialize_doc(doc):
    """Convert ObjectId and other BSON types to strings."""
    if isinstance(doc, dict):
        return {k: _serialize_doc(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_serialize_doc(item) for item in doc]
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc


def execute_mongodb_query(
    connector,
    collection_name,
    operation,
    query=None,
    projection=None,
    limit=50
):
    """
    Execute supported MongoDB read operations.

    Supported operations:
    - find
    - count
    - aggregate
    """

    client = None

    try:
        client = get_mongodb_client(connector)

        database = client[connector.database]
        collection = database[collection_name]

        if operation == "aggregate":
            query = query if isinstance(query, list) else []
        else:
            query = query if isinstance(query, dict) else {}

        if operation == "find":

            documents = list(
                collection.find(
                    query,
                    projection
                ).limit(limit)
            )

            return {
                "success": True,
                "operation": "find",
                "collection": collection_name,
                "count": len(documents),
                "results": [_serialize_doc(d) for d in documents]
            }

        elif operation == "count":

            count = collection.count_documents(query)

            return {
                "success": True,
                "operation": "count",
                "collection": collection_name,
                "count": count
            }

        elif operation == "aggregate":

            documents = list(
                collection.aggregate(query)
            )

            return {
                "success": True,
                "operation": "aggregate",
                "collection": collection_name,
                "count": len(documents),
                "results": [_serialize_doc(d) for d in documents][:limit]
            }

        else:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported MongoDB operation. "
                    "Use find, count or aggregate."
                )
            )

    except HTTPException:
        raise

    except PyMongoError as error:

        raise HTTPException(
            status_code=400,
            detail=f"MongoDB query execution failed: {str(error)}"
        )

    finally:
        if client:
            client.close()