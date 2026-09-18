"""Storage adapter: DynamoDB in AWS, an on-disk JSON store locally.

Both adapters expose the same tiny interface so handlers never branch on
environment. Section 6 of the PRD defines the three tables; the leaderboard
(6.4) is a derived read over Results, not a fourth write path.

Adaptation note vs PRD 6.4: DynamoDB cannot sort a GSI globally without a
partition key, so every Results item carries a constant `leaderboard_pk`
("GLOBAL") and the GSI is (leaderboard_pk HASH, score RANGE). Querying it
backwards gives top-N-by-score in one call, which is what the PRD asked for.
"""
import json
import os
import threading
from decimal import Decimal
from typing import Any, Dict, List, Optional

from common import config

LEADERBOARD_PK_VALUE = "GLOBAL"


def _to_jsonable(obj: Any) -> Any:
    """DynamoDB hands back Decimals; the API must emit plain JSON numbers."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def _to_dynamo(obj: Any) -> Any:
    """DynamoDB rejects floats; convert on the way in."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dynamo(v) for v in obj]
    return obj


class LocalStore:
    """File-backed store used for local dev, tests and the offline pipeline."""

    _lock = threading.Lock()

    def __init__(self, path: Optional[str] = None):
        self.path = path or config.LOCAL_STORE_PATH
        os.makedirs(self.path, exist_ok=True)

    def _file(self, name: str) -> str:
        return os.path.join(self.path, f"{name}.json")

    def _read(self, name: str) -> Dict[str, Dict]:
        try:
            with open(self._file(name), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, name: str, data: Dict[str, Dict]) -> None:
        tmp = self._file(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self._file(name))

    # -- challenges ---------------------------------------------------------
    def put_challenge(self, item: Dict) -> None:
        with self._lock:
            data = self._read("challenges")
            data[item["challenge_id"]] = item
            self._write("challenges", data)

    def get_challenge(self, challenge_id: str) -> Optional[Dict]:
        return self._read("challenges").get(challenge_id)

    def list_challenges(self) -> List[Dict]:
        return sorted(self._read("challenges").values(), key=lambda c: c["challenge_id"])

    # -- sessions -----------------------------------------------------------
    def put_session(self, item: Dict) -> None:
        with self._lock:
            data = self._read("sessions")
            data[item["session_id"]] = item
            self._write("sessions", data)

    def get_session(self, session_id: str) -> Optional[Dict]:
        return self._read("sessions").get(session_id)

    def set_session_status(self, session_id: str, status: str) -> None:
        with self._lock:
            data = self._read("sessions")
            if session_id in data:
                data[session_id]["status"] = status
                self._write("sessions", data)

    # -- results ------------------------------------------------------------
    def put_result(self, item: Dict) -> None:
        with self._lock:
            data = self._read("results")
            data[item["session_id"]] = item
            self._write("results", data)

    def get_result(self, session_id: str) -> Optional[Dict]:
        return self._read("results").get(session_id)

    def top_results(self, limit: int) -> List[Dict]:
        rows = list(self._read("results").values())
        rows.sort(key=lambda r: (-int(r.get("score", 0)), int(r.get("time_taken_seconds", 10**9))))
        return rows[:limit]

    def count_sessions(self) -> int:
        return len(self._read("sessions"))

    def all_results(self) -> List[Dict]:
        return list(self._read("results").values())

    def all_sessions(self) -> List[Dict]:
        return list(self._read("sessions").values())

    def recent_results(self, limit: int) -> List[Dict]:
        rows = list(self._read("results").values())
        rows.sort(key=lambda r: int(r.get("submitted_at", 0)), reverse=True)
        return rows[:limit]

    # -- websocket connections ---------------------------------------------
    def put_connection(self, connection_id: str, meta: Optional[Dict] = None) -> None:
        with self._lock:
            data = self._read("connections")
            data[connection_id] = {"connection_id": connection_id, **(meta or {})}
            self._write("connections", data)

    def delete_connection(self, connection_id: str) -> None:
        with self._lock:
            data = self._read("connections")
            if data.pop(connection_id, None) is not None:
                self._write("connections", data)

    def list_connections(self) -> List[str]:
        return list(self._read("connections").keys())


class DynamoStore:
    """DynamoDB-backed store. On-demand billing only (PRD Section 11, Cost)."""

    def __init__(self):
        import boto3  # imported lazily so local mode needs no AWS SDK at import time

        self._ddb = boto3.resource("dynamodb", region_name=config.AWS_REGION)
        self.challenges = self._ddb.Table(config.CHALLENGES_TABLE)
        self.sessions = self._ddb.Table(config.SESSIONS_TABLE)
        self.results = self._ddb.Table(config.RESULTS_TABLE)
        self.connections = self._ddb.Table(config.CONNECTIONS_TABLE)

    # -- challenges ---------------------------------------------------------
    def put_challenge(self, item: Dict) -> None:
        self.challenges.put_item(Item=_to_dynamo(item))

    def get_challenge(self, challenge_id: str) -> Optional[Dict]:
        resp = self.challenges.get_item(Key={"challenge_id": challenge_id})
        item = resp.get("Item")
        return _to_jsonable(item) if item else None

    def list_challenges(self) -> List[Dict]:
        # Five seed rows -- a scan is correct and cheap here; revisit only if the
        # challenge catalogue ever grows past a single page.
        items: List[Dict] = []
        kwargs: Dict[str, Any] = {
            # bug_category is deliberately NOT projected -- naming the bug class would
            # hand the student half the answer before the timer starts.
            "ProjectionExpression": "challenge_id, repo_name, function_name, difficulty, #lang, "
                                    "time_limit_seconds, tests_total, code_preview, "
                                    "student_facing_summary, symptom_description, source_url, #st",
            "ExpressionAttributeNames": {"#lang": "language", "#st": "status"},
        }
        while True:
            resp = self.challenges.scan(**kwargs)
            items.extend(_to_jsonable(resp.get("Items", [])))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return sorted(items, key=lambda c: c["challenge_id"])

    # -- sessions -----------------------------------------------------------
    def put_session(self, item: Dict) -> None:
        self.sessions.put_item(Item=_to_dynamo(item))

    def get_session(self, session_id: str) -> Optional[Dict]:
        resp = self.sessions.get_item(Key={"session_id": session_id})
        item = resp.get("Item")
        return _to_jsonable(item) if item else None

    def set_session_status(self, session_id: str, status: str) -> None:
        self.sessions.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status},
        )

    # -- results ------------------------------------------------------------
    def put_result(self, item: Dict) -> None:
        item = dict(item)
        item["leaderboard_pk"] = LEADERBOARD_PK_VALUE
        self.results.put_item(Item=_to_dynamo(item))

    def get_result(self, session_id: str) -> Optional[Dict]:
        resp = self.results.get_item(Key={"session_id": session_id})
        item = resp.get("Item")
        return _to_jsonable(item) if item else None

    def top_results(self, limit: int) -> List[Dict]:
        from boto3.dynamodb.conditions import Key

        resp = self.results.query(
            IndexName=config.RESULTS_SCORE_GSI,
            KeyConditionExpression=Key("leaderboard_pk").eq(LEADERBOARD_PK_VALUE),
            ScanIndexForward=False,          # highest score first
            Limit=max(limit * 3, limit),     # over-fetch so the tie-break below is meaningful
        )
        rows = _to_jsonable(resp.get("Items", []))
        rows.sort(key=lambda r: (-int(r.get("score", 0)), int(r.get("time_taken_seconds", 10**9))))
        return rows[:limit]

    def count_sessions(self) -> int:
        # Small tables at seed-data scale; a counting scan is the cheap option.
        total, kwargs = 0, {"Select": "COUNT"}
        while True:
            resp = self.sessions.scan(**kwargs)
            total += resp.get("Count", 0)
            if "LastEvaluatedKey" not in resp:
                return total
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def all_results(self) -> List[Dict]:
        items, kwargs = [], {
            "ProjectionExpression": "session_id, challenge_id, score, time_taken_seconds, correct",
        }
        while True:
            resp = self.results.scan(**kwargs)
            items.extend(_to_jsonable(resp.get("Items", [])))
            if "LastEvaluatedKey" not in resp:
                return items
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def all_sessions(self) -> List[Dict]:
        items, kwargs = [], {
            "ProjectionExpression": "session_id, challenge_id, #s, start_time, user_display_name",
            "ExpressionAttributeNames": {"#s": "status"},
        }
        while True:
            resp = self.sessions.scan(**kwargs)
            items.extend(_to_jsonable(resp.get("Items", [])))
            if "LastEvaluatedKey" not in resp:
                return items
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def recent_results(self, limit: int) -> List[Dict]:
        items, kwargs = [], {}
        while True:
            resp = self.results.scan(**kwargs)
            items.extend(_to_jsonable(resp.get("Items", [])))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        items.sort(key=lambda r: int(r.get("submitted_at", 0)), reverse=True)
        return items[:limit]

    # -- websocket connections ---------------------------------------------
    def put_connection(self, connection_id: str, meta: Optional[Dict] = None) -> None:
        item = {"connection_id": connection_id, **(meta or {})}
        self.connections.put_item(Item=_to_dynamo(item))

    def delete_connection(self, connection_id: str) -> None:
        self.connections.delete_item(Key={"connection_id": connection_id})

    def list_connections(self) -> List[str]:
        ids, kwargs = [], {"ProjectionExpression": "connection_id"}
        while True:
            resp = self.connections.scan(**kwargs)
            ids.extend(i["connection_id"] for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                return ids
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


_store = None


def get_store():
    """Process-wide singleton -- Lambda reuses it across warm invocations."""
    global _store
    if _store is None:
        _store = LocalStore() if config.STORAGE_BACKEND == "local" else DynamoStore()
    return _store


def reset_store() -> None:
    """Test hook: drop the cached singleton so env changes take effect."""
    global _store
    _store = None
