
from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.core.mongodb_adapter import get_mongodb_client


def discover_mongodb_schema(connector):
    """
    Discover MongoDB collections and infer their fields
    from sample documents.
    """

    client = None

    try:
        client = get_mongodb_client(connector)

        database = client[connector.database]

        collection_names = database.list_collection_names()

        collections = []

        for collection_name in sorted(collection_names):

            collection = database[collection_name]

            # Read a small sample to infer document fields
            sample_documents = list(
                collection.find(
                    {},
                    limit=20
                )
            )

            fields = {}

            for document in sample_documents:

                for field_name, field_value in document.items():

                    if field_name not in fields:
                        fields[field_name] = set()

                    fields[field_name].add(
                        type(field_value).__name__
                    )

            collections.append({
                "collection_name": collection_name,
                "document_count": collection.count_documents({}),
                "sample_size": len(sample_documents),
                "fields": [
                    {
                        "field_name": field_name,
                        "data_types": sorted(data_types)
                    }
                    for field_name, data_types in sorted(fields.items())
                ]
            })

        return {
            "database": connector.database,
            "connector_type": "mongodb",
            "total_collections": len(collections),
            "collections": collections
        }

    except PyMongoError as error:
        raise HTTPException(
            status_code=500,
            detail=f"MongoDB schema discovery failed: {str(error)}"
        )

    finally:
        if client:
            client.close()