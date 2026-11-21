"""
NoSQL database adapters for Redis, Cassandra, Neo4j, Elasticsearch, InfluxDB, CouchDB.
Each adapter provides: get_client, test_connection, discover_schema, search, execute_query.
"""

import json
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# REDIS
# ═══════════════════════════════════════════════

def get_redis_client(connector):
    import redis
    from app.core.crypto import decrypt_password
    password = decrypt_password(connector.password) if connector.password else None
    return redis.Redis(
        host=connector.host,
        port=connector.port or 6379,
        db=int(connector.database or 0),
        password=password if password else None,
        decode_responses=True,
        socket_timeout=10,
        socket_connect_timeout=5,
    )


def test_redis_connection(connector):
    client = get_redis_client(connector)
    info = client.info("server")
    client.close()
    return {
        "success": True,
        "message": f"Redis {info.get('redis_version', '?')} connected!",
        "database": connector.database or "0",
        "username": info.get("redis_mode", "standalone"),
    }


def discover_redis_schema(connector):
    client = get_redis_client(connector)
    info = client.info("keyspace")
    db_key = f"db{connector.database or 0}"
    key_count = info.get(db_key, {}).get("keys", 0) if isinstance(info.get(db_key), dict) else 0

    # Sample some keys to show types
    cursor, keys = client.scan(count=100)
    sample_keys = {}
    for key in keys[:50]:
        key_type = client.type(key)
        sample_keys[key] = key_type
    client.close()

    return {
        "type": "redis",
        "database": connector.database or "0",
        "total_keys": key_count,
        "sample_keys": sample_keys,
    }


def search_redis(connector, keyword):
    client = get_redis_client(connector)
    matches = []
    cursor = 0
    pattern = f"*{keyword}*"
    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=200)
        for key in keys:
            key_type = client.type(key)
            matches.append({"key": key, "type": key_type})
            if len(matches) >= 20:
                break
        if cursor == 0 or len(matches) >= 20:
            break
    client.close()
    return {"matches": matches, "keyword": keyword}


def execute_redis_query(connector, query_data):
    """Execute a Redis command. query_data = {"command": "GET", "args": ["key"]}"""
    client = get_redis_client(connector)
    command = query_data.get("command", "").upper()
    args = query_data.get("args", [])

    # Block dangerous commands
    dangerous = {"FLUSHDB", "FLUSHALL", "DEL", "UNLINK", "SHUTDOWN", "DEBUG", "CONFIG", "SLAVEOF", "REPLICAOF"}
    if command in dangerous:
        client.close()
        return {"error": f"Blocked dangerous command: {command}. Only read commands allowed."}

    try:
        result = client.execute_command(command, *args)
        client.close()

        # Format result
        if isinstance(result, (list, tuple)):
            return {"command": f"{command} {' '.join(str(a) for a in args)}", "result": [str(r) for r in result], "count": len(result)}
        elif isinstance(result, dict):
            return {"command": f"{command} {' '.join(str(a) for a in args)}", "result": {str(k): str(v) for k, v in result.items()}}
        else:
            return {"command": f"{command} {' '.join(str(a) for a in args)}", "result": str(result)}
    except Exception as exc:
        client.close()
        return {"error": str(exc)}


# ═══════════════════════════════════════════════
# CASSANDRA
# ═══════════════════════════════════════════════

def get_cassandra_session(connector):
    from cassandra.cluster import Cluster
    from cassandra.auth import PlainTextAuthProvider
    from app.core.crypto import decrypt_password

    password = decrypt_password(connector.password) if connector.password else None
    auth = None
    if connector.username and password:
        auth = PlainTextAuthProvider(username=connector.username, password=password)

    cluster = Cluster(
        contact_points=[connector.host],
        port=connector.port or 9042,
        auth_provider=auth,
        connect_timeout=10,
    )
    session = cluster.connect(connector.database or None)
    return session, cluster


def test_cassandra_connection(connector):
    session, cluster = get_cassandra_session(connector)
    row = session.execute("SELECT release_version FROM system.local").one()
    version = row.release_version if row else "unknown"
    cluster.shutdown()
    return {
        "success": True,
        "message": f"Cassandra {version} connected!",
        "database": connector.database or "system",
        "username": connector.username or "anonymous",
    }


def discover_cassandra_schema(connector):
    session, cluster = get_cassandra_session(connector)
    keyspace = connector.database

    rows = session.execute(
        "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
        [keyspace]
    )
    tables = {}
    for row in rows:
        tbl = row.table_name
        cols_rows = session.execute(
            "SELECT column_name, type FROM system_schema.columns WHERE keyspace_name = %s AND table_name = %s",
            [keyspace, tbl]
        )
        tables[tbl] = {"columns": [{"name": c.column_name, "type": c.type} for c in cols_rows]}

    cluster.shutdown()
    return {"type": "cassandra", "database": keyspace, "tables": tables}


def search_cassandra(connector, keyword):
    session, cluster = get_cassandra_session(connector)
    keyspace = connector.database
    keyword_lower = keyword.lower()

    rows = session.execute(
        "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
        [keyspace]
    )
    matches = []
    for row in rows:
        tbl = row.table_name
        if keyword_lower in tbl.lower():
            cols_rows = session.execute(
                "SELECT column_name, type FROM system_schema.columns WHERE keyspace_name = %s AND table_name = %s",
                [keyspace, tbl]
            )
            matches.append({"table": tbl, "columns": [c.column_name for c in cols_rows], "match": "table_name"})
        else:
            cols_rows = session.execute(
                "SELECT column_name, type FROM system_schema.columns WHERE keyspace_name = %s AND table_name = %s",
                [keyspace, tbl]
            )
            matched = [c.column_name for c in cols_rows if keyword_lower in c.column_name.lower()]
            if matched:
                matches.append({"table": tbl, "matched_columns": matched, "match": "column_name"})

    cluster.shutdown()
    return {"matches": matches[:10], "keyword": keyword}


def execute_cassandra_query(connector, cql):
    """Execute a CQL query (read-only)."""
    cql_upper = cql.strip().upper()
    dangerous = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT"}
    tokens = set(cql_upper.split())
    blocked = dangerous & tokens
    if blocked:
        return {"error": f"Blocked dangerous operation: {', '.join(blocked)}. Only SELECT allowed."}

    session, cluster = get_cassandra_session(connector)
    try:
        result = session.execute(cql)
        columns = list(result.column_names) if result.column_names else []
        rows = []
        for row in result:
            rows.append([str(getattr(row, c, None)) for c in columns])
            if len(rows) >= 100:
                break
        cluster.shutdown()
        return {"cql": cql, "columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as exc:
        cluster.shutdown()
        return {"cql": cql, "error": str(exc)}


# ═══════════════════════════════════════════════
# NEO4J
# ═══════════════════════════════════════════════

def get_neo4j_driver(connector):
    from neo4j import GraphDatabase
    from app.core.crypto import decrypt_password

    password = decrypt_password(connector.password) if connector.password else None
    uri = f"bolt://{connector.host}:{connector.port or 7687}"
    auth = (connector.username or "neo4j", password or "")
    return GraphDatabase.driver(uri, auth=auth, connection_timeout=10)


def test_neo4j_connection(connector):
    driver = get_neo4j_driver(connector)
    with driver.session(database=connector.database or "neo4j") as session:
        result = session.run("CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS version")
        record = result.single()
        name = record["name"] if record else "Neo4j"
        version = record["version"] if record else "unknown"
    driver.close()
    return {
        "success": True,
        "message": f"{name} {version} connected!",
        "database": connector.database or "neo4j",
        "username": connector.username or "neo4j",
    }


def discover_neo4j_schema(connector):
    driver = get_neo4j_driver(connector)
    with driver.session(database=connector.database or "neo4j") as session:
        # Get node labels and their properties
        labels_result = session.run("CALL db.labels()")
        labels = [r["label"] for r in labels_result]

        schema = {"node_labels": {}, "relationship_types": []}
        for label in labels[:30]:
            props_result = session.run(
                f"MATCH (n:`{label}`) WITH n LIMIT 1 RETURN keys(n) AS props"
            )
            record = props_result.single()
            props = record["props"] if record else []
            # Get count
            count_result = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
            cnt = count_result.single()["cnt"]
            schema["node_labels"][label] = {"properties": props, "count": cnt}

        # Get relationship types
        rels_result = session.run("CALL db.relationshipTypes()")
        schema["relationship_types"] = [r["relationshipType"] for r in rels_result]

    driver.close()
    return {"type": "neo4j", "database": connector.database or "neo4j", "schema": schema}


def search_neo4j(connector, keyword):
    driver = get_neo4j_driver(connector)
    keyword_lower = keyword.lower()
    matches = []

    with driver.session(database=connector.database or "neo4j") as session:
        labels_result = session.run("CALL db.labels()")
        labels = [r["label"] for r in labels_result]

        for label in labels:
            if keyword_lower in label.lower():
                props_result = session.run(
                    f"MATCH (n:`{label}`) WITH n LIMIT 1 RETURN keys(n) AS props"
                )
                record = props_result.single()
                props = record["props"] if record else []
                matches.append({"label": label, "properties": props, "match": "label"})
            else:
                props_result = session.run(
                    f"MATCH (n:`{label}`) WITH n LIMIT 1 RETURN keys(n) AS props"
                )
                record = props_result.single()
                props = record["props"] if record else []
                matched_props = [p for p in props if keyword_lower in p.lower()]
                if matched_props:
                    matches.append({"label": label, "matched_properties": matched_props, "match": "property"})

    driver.close()
    return {"matches": matches[:10], "keyword": keyword}


def execute_neo4j_query(connector, cypher):
    """Execute a Cypher query (read-only)."""
    cypher_upper = cypher.strip().upper()
    dangerous = {"CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP"}
    tokens = set(cypher_upper.split())
    blocked = dangerous & tokens
    if blocked:
        return {"error": f"Blocked dangerous operation: {', '.join(blocked)}. Only MATCH/RETURN allowed."}

    driver = get_neo4j_driver(connector)
    try:
        with driver.session(database=connector.database or "neo4j") as session:
            result = session.run(cypher)
            records = []
            columns = None
            for record in result:
                if columns is None:
                    columns = list(record.keys())
                row = []
                for val in record.values():
                    if hasattr(val, '__dict__') and hasattr(val, 'id'):
                        # Neo4j Node or Relationship
                        row.append(str(dict(val)))
                    else:
                        row.append(str(val) if not isinstance(val, (str, int, float, bool, type(None))) else val)
                records.append(row)
                if len(records) >= 100:
                    break

        driver.close()
        return {"cypher": cypher, "columns": columns or [], "rows": records, "row_count": len(records)}
    except Exception as exc:
        driver.close()
        return {"cypher": cypher, "error": str(exc)}


# ═══════════════════════════════════════════════
# ELASTICSEARCH
# ═══════════════════════════════════════════════

def get_elasticsearch_client(connector):
    from elasticsearch import Elasticsearch
    from app.core.crypto import decrypt_password

    password = decrypt_password(connector.password) if connector.password else None
    scheme = "https" if connector.port == 443 or (connector.host and "cloud" in connector.host) else "http"
    host = f"{scheme}://{connector.host}:{connector.port or 9200}"

    auth = None
    if connector.username and password:
        auth = (connector.username, password)

    return Elasticsearch(
        [host],
        basic_auth=auth,
        verify_certs=False,
        request_timeout=10,
    )


def test_elasticsearch_connection(connector):
    es = get_elasticsearch_client(connector)
    info = es.info()
    version = info.get("version", {}).get("number", "unknown")
    cluster = info.get("cluster_name", "unknown")
    es.close()
    return {
        "success": True,
        "message": f"Elasticsearch {version} (cluster: {cluster}) connected!",
        "database": connector.database or cluster,
        "username": connector.username or "anonymous",
    }


def discover_elasticsearch_schema(connector):
    es = get_elasticsearch_client(connector)
    indices = es.cat.indices(format="json")
    schema = {}
    for idx in indices[:30]:
        name = idx["index"]
        if name.startswith("."):
            continue  # skip system indices
        try:
            mapping = es.indices.get_mapping(index=name)
            props = mapping[name]["mappings"].get("properties", {})
            schema[name] = {
                "fields": [{"name": k, "type": v.get("type", "object")} for k, v in props.items()],
                "docs": idx.get("docs.count", "?"),
            }
        except Exception:
            schema[name] = {"fields": [], "docs": idx.get("docs.count", "?")}

    es.close()
    return {"type": "elasticsearch", "database": connector.database or "cluster", "indices": schema}


def search_elasticsearch(connector, keyword):
    es = get_elasticsearch_client(connector)
    keyword_lower = keyword.lower()
    indices = es.cat.indices(format="json")
    matches = []

    for idx in indices:
        name = idx["index"]
        if name.startswith("."):
            continue
        if keyword_lower in name.lower():
            try:
                mapping = es.indices.get_mapping(index=name)
                props = mapping[name]["mappings"].get("properties", {})
                matches.append({"index": name, "fields": list(props.keys())[:20], "match": "index_name"})
            except Exception:
                matches.append({"index": name, "fields": [], "match": "index_name"})
        else:
            try:
                mapping = es.indices.get_mapping(index=name)
                props = mapping[name]["mappings"].get("properties", {})
                matched = [k for k in props if keyword_lower in k.lower()]
                if matched:
                    matches.append({"index": name, "matched_fields": matched, "match": "field_name"})
            except Exception:
                pass

    es.close()
    return {"matches": matches[:10], "keyword": keyword}


def execute_elasticsearch_query(connector, query_data):
    """Execute an Elasticsearch query. query_data = {"index": "...", "query": {...}, "size": 50}"""
    es = get_elasticsearch_client(connector)
    index = query_data.get("index", "*")
    query = query_data.get("query", {"match_all": {}})
    size = query_data.get("size", 50)
    sort = query_data.get("sort")
    aggs = query_data.get("aggs") or query_data.get("aggregations")

    try:
        body = {"query": query, "size": min(size, 100)}
        if sort:
            body["sort"] = sort
        if aggs:
            body["aggs"] = aggs

        result = es.search(index=index, body=body)
        hits = result.get("hits", {}).get("hits", [])

        if aggs and result.get("aggregations"):
            # Return aggregation results
            es.close()
            return {
                "es_query": json.dumps(query_data, default=str),
                "aggregations": result["aggregations"],
                "total_hits": result.get("hits", {}).get("total", {}).get("value", 0),
            }

        # Format as table
        if hits:
            columns = list(hits[0]["_source"].keys())
            rows = []
            for hit in hits:
                src = hit["_source"]
                rows.append([str(src.get(c, "")) for c in columns])
        else:
            columns, rows = [], []

        es.close()
        return {
            "es_query": json.dumps(query_data, default=str),
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "total_hits": result.get("hits", {}).get("total", {}).get("value", 0),
        }
    except Exception as exc:
        es.close()
        return {"error": str(exc)}


# ═══════════════════════════════════════════════
# CLICKHOUSE (uses HTTP interface)
# ═══════════════════════════════════════════════

def get_clickhouse_client(connector):
    import clickhouse_connect
    from app.core.crypto import decrypt_password

    password = decrypt_password(connector.password) if connector.password else None
    return clickhouse_connect.get_client(
        host=connector.host,
        port=connector.port or 8123,
        username=connector.username or "default",
        password=password or "",
        database=connector.database or "default",
        connect_timeout=10,
        send_receive_timeout=30,
    )


def test_clickhouse_connection(connector):
    client = get_clickhouse_client(connector)
    result = client.query("SELECT version()")
    version = result.result_rows[0][0] if result.result_rows else "unknown"
    client.close()
    return {
        "success": True,
        "message": f"ClickHouse {version} connected!",
        "database": connector.database or "default",
        "username": connector.username or "default",
    }


def discover_clickhouse_schema(connector):
    client = get_clickhouse_client(connector)
    result = client.query("SHOW TABLES")
    table_names = [r[0] for r in result.result_rows]

    tables = {}
    for tbl in table_names[:50]:
        cols_result = client.query(f"DESCRIBE TABLE `{tbl}`")
        tables[tbl] = {
            "columns": [{"name": r[0], "type": r[1]} for r in cols_result.result_rows]
        }
    client.close()
    return {"type": "clickhouse", "database": connector.database or "default", "tables": tables}


def search_clickhouse(connector, keyword):
    client = get_clickhouse_client(connector)
    keyword_lower = keyword.lower()
    result = client.query("SHOW TABLES")
    table_names = [r[0] for r in result.result_rows]

    matches = []
    for tbl in table_names:
        if keyword_lower in tbl.lower():
            cols = client.query(f"DESCRIBE TABLE `{tbl}`")
            matches.append({"table": tbl, "columns": [r[0] for r in cols.result_rows], "match": "table_name"})
        else:
            cols = client.query(f"DESCRIBE TABLE `{tbl}`")
            matched = [r[0] for r in cols.result_rows if keyword_lower in r[0].lower()]
            if matched:
                matches.append({"table": tbl, "matched_columns": matched, "match": "column_name"})

    client.close()
    return {"matches": matches[:10], "keyword": keyword}


def execute_clickhouse_sql(connector, sql):
    """Execute a ClickHouse SQL query (read-only)."""
    sql_upper = sql.strip().upper()
    forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT"}
    tokens = set(sql_upper.split())
    blocked = forbidden & tokens
    if blocked:
        return {"error": f"Blocked dangerous operation: {', '.join(blocked)}. Only SELECT allowed."}

    client = get_clickhouse_client(connector)
    try:
        result = client.query(sql)
        columns = list(result.column_names) if result.column_names else []
        rows = []
        for row in result.result_rows[:100]:
            rows.append([str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for v in row])
        client.close()
        return {"sql": sql, "columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as exc:
        client.close()
        return {"sql": sql, "error": str(exc)}


# ═══════════════════════════════════════════════
# INFLUXDB
# ═══════════════════════════════════════════════

def get_influxdb_client(connector):
    from influxdb_client import InfluxDBClient
    from app.core.crypto import decrypt_password

    token = decrypt_password(connector.password) if connector.password else ""
    url = f"http://{connector.host}:{connector.port or 8086}"
    org = connector.username or ""
    return InfluxDBClient(url=url, token=token, org=org, timeout=10000)


def test_influxdb_connection(connector):
    client = get_influxdb_client(connector)
    health = client.health()
    client.close()
    return {
        "success": True,
        "message": f"InfluxDB {health.version or '?'} ({health.status}) connected!",
        "database": connector.database or "default",
        "username": connector.username or "org",
    }


def discover_influxdb_schema(connector):
    client = get_influxdb_client(connector)
    query_api = client.query_api()
    bucket = connector.database

    # List measurements
    query = f'import "influxdata/influxdb/schema"\nschema.measurements(bucket: "{bucket}")'
    try:
        tables = query_api.query(query, org=connector.username or "")
        measurements = []
        for table in tables:
            for record in table.records:
                measurements.append(record.get_value())
    except Exception:
        measurements = []

    client.close()
    return {
        "type": "influxdb",
        "database": bucket,
        "measurements": measurements[:50],
    }


def search_influxdb(connector, keyword):
    schema = discover_influxdb_schema(connector)
    keyword_lower = keyword.lower()
    matches = [m for m in schema.get("measurements", []) if keyword_lower in m.lower()]
    return {"matches": [{"measurement": m} for m in matches[:10]], "keyword": keyword}


def execute_influxdb_query(connector, flux_query):
    """Execute a Flux query."""
    client = get_influxdb_client(connector)
    query_api = client.query_api()

    try:
        tables = query_api.query(flux_query, org=connector.username or "")
        rows = []
        columns = None
        for table in tables:
            for record in table.records:
                vals = record.values
                if columns is None:
                    columns = [k for k in vals.keys() if not k.startswith("_") or k in ("_time", "_value", "_field", "_measurement")]
                row = [str(vals.get(c, "")) for c in columns]
                rows.append(row)
                if len(rows) >= 100:
                    break
            if len(rows) >= 100:
                break

        client.close()
        return {"flux_query": flux_query, "columns": columns or [], "rows": rows, "row_count": len(rows)}
    except Exception as exc:
        client.close()
        return {"flux_query": flux_query, "error": str(exc)}


# ═══════════════════════════════════════════════
# COUCHDB
# ═══════════════════════════════════════════════

def get_couchdb_server(connector):
    import couchdb
    from app.core.crypto import decrypt_password

    password = decrypt_password(connector.password) if connector.password else None
    if connector.username and password:
        url = f"http://{connector.username}:{password}@{connector.host}:{connector.port or 5984}/"
    else:
        url = f"http://{connector.host}:{connector.port or 5984}/"
    return couchdb.Server(url)


def test_couchdb_connection(connector):
    server = get_couchdb_server(connector)
    version = server.version()
    return {
        "success": True,
        "message": f"CouchDB {version} connected!",
        "database": connector.database or "default",
        "username": connector.username or "admin",
    }


def discover_couchdb_schema(connector):
    server = get_couchdb_server(connector)
    db = server[connector.database]

    # Sample documents to infer schema
    schema = {"doc_count": db.info().get("doc_count", 0), "sample_fields": {}}
    for doc_id in list(db)[:20]:
        doc = db[doc_id]
        for key in doc:
            if key not in schema["sample_fields"]:
                schema["sample_fields"][key] = type(doc[key]).__name__

    return {"type": "couchdb", "database": connector.database, "schema": schema}


def search_couchdb(connector, keyword):
    server = get_couchdb_server(connector)
    db = server[connector.database]
    keyword_lower = keyword.lower()

    # Search in document keys and field names
    matches = []
    for doc_id in list(db)[:100]:
        if keyword_lower in doc_id.lower():
            matches.append({"doc_id": doc_id, "match": "doc_id"})
        else:
            doc = db[doc_id]
            matched_fields = [k for k in doc if keyword_lower in k.lower()]
            if matched_fields:
                matches.append({"doc_id": doc_id, "matched_fields": matched_fields, "match": "field_name"})
        if len(matches) >= 10:
            break

    return {"matches": matches, "keyword": keyword}


def execute_couchdb_query(connector, query_data):
    """Execute a CouchDB Mango query. query_data = {"selector": {...}, "limit": 50, "fields": [...]}"""
    server = get_couchdb_server(connector)
    db = server[connector.database]

    selector = query_data.get("selector", {})
    limit = min(query_data.get("limit", 50), 100)
    fields = query_data.get("fields")
    sort = query_data.get("sort")

    try:
        mango = {"selector": selector, "limit": limit}
        if fields:
            mango["fields"] = fields
        if sort:
            mango["sort"] = sort

        results = list(db.find(mango))

        if results:
            columns = list(results[0].keys())
            rows = [[str(doc.get(c, "")) for c in columns] for doc in results]
        else:
            columns, rows = [], []

        return {
            "mango_query": json.dumps(query_data, default=str),
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }
    except Exception as exc:
        return {"error": str(exc)}
