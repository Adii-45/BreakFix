"""Central configuration for all BreakFix Lambdas.

Everything is environment-driven so the same code runs in Lambda and locally.
Set BREAKFIX_STORAGE=local to use the on-disk JSON store instead of DynamoDB
(used for local development and the offline authoring pipeline).
"""
import os

# --- Storage -----------------------------------------------------------------
STORAGE_BACKEND = os.environ.get("BREAKFIX_STORAGE", "dynamodb").lower()
LOCAL_STORE_PATH = os.environ.get(
    "BREAKFIX_LOCAL_STORE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".localdb"),
)

CHALLENGES_TABLE = os.environ.get("CHALLENGES_TABLE", "breakfix-challenges")
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "breakfix-sessions")
RESULTS_TABLE = os.environ.get("RESULTS_TABLE", "breakfix-results")
RESULTS_SCORE_GSI = os.environ.get("RESULTS_SCORE_GSI", "score-index")
CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "breakfix-connections")

# --- Real-time (Part 2) ------------------------------------------------------
WEBSOCKET_ENDPOINT = os.environ.get("WEBSOCKET_ENDPOINT", "")   # wss://.../stage
# A session counts toward "people solving this now" only while it could still
# plausibly be in progress: its own time limit plus a short grace period. Without
# this, an abandoned tab would inflate presence forever.
PRESENCE_GRACE_SECONDS = int(os.environ.get("PRESENCE_GRACE_SECONDS", "90"))
ACTIVITY_FEED_LIMIT = int(os.environ.get("ACTIVITY_FEED_LIMIT", "12"))

# --- Live authoring (Part 3) -------------------------------------------------
# Fail-closed: with no passphrase configured every admin route returns 503, so an
# unconfigured deployment exposes nothing rather than defaulting to open.
ADMIN_PASSPHRASE = os.environ.get("ADMIN_PASSPHRASE", "")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")

# --- EventBridge (Part 4.3) --------------------------------------------------
EVENT_BUS_NAME = os.environ.get("EVENT_BUS_NAME", "")

# --- CloudWatch system status (Part 4.2) -------------------------------------
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"
METRICS_WINDOW_MINUTES = int(os.environ.get("METRICS_WINDOW_MINUTES", "60"))

# --- Difficulty calibration (Part 4.1) ---------------------------------------
# Below this many scored submissions a pass rate is noise, so the UI keeps
# showing the curated static label instead of a misleading percentage.
CALIBRATION_MIN_SAMPLE = int(os.environ.get("CALIBRATION_MIN_SAMPLE", "5"))

AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

# --- Bedrock -----------------------------------------------------------------
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", AWS_REGION)
# Model id for the Anthropic-SDK Bedrock transport (Bedrock ids take an
# "anthropic." prefix). The boto3 bedrock-runtime fallback uses the regional
# inference-profile id form instead, hence the second variable.
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-opus-5")
BEDROCK_FALLBACK_MODEL_ID = os.environ.get("BEDROCK_FALLBACK_MODEL_ID", "us.anthropic.claude-opus-5")
BEDROCK_MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", "2000"))
BEDROCK_TIMEOUT_SECONDS = float(os.environ.get("BEDROCK_TIMEOUT_SECONDS", "20"))
# When Bedrock is unreachable (no creds, throttling, model not enabled) the
# submit path must still return a result. Correctness is never affected by this
# flag -- it comes from the Test Runner. Only the qualitative layer degrades.
ALLOW_EVALUATOR_FALLBACK = os.environ.get("ALLOW_EVALUATOR_FALLBACK", "true").lower() == "true"

# --- Test Runner sandbox (Section 8.0 / Section 11) --------------------------
SANDBOX_WALL_TIMEOUT_SECONDS = float(os.environ.get("SANDBOX_WALL_TIMEOUT_SECONDS", "5"))
SANDBOX_PER_TEST_TIMEOUT_SECONDS = float(os.environ.get("SANDBOX_PER_TEST_TIMEOUT_SECONDS", "2"))
SANDBOX_MEMORY_LIMIT_MB = int(os.environ.get("SANDBOX_MEMORY_LIMIT_MB", "256"))
SANDBOX_MAX_CODE_BYTES = int(os.environ.get("SANDBOX_MAX_CODE_BYTES", "20000"))
SANDBOX_MAX_OUTPUT_BYTES = int(os.environ.get("SANDBOX_MAX_OUTPUT_BYTES", "100000"))

# --- API ---------------------------------------------------------------------
CORS_ALLOW_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")
LEADERBOARD_LIMIT = int(os.environ.get("LEADERBOARD_LIMIT", "10"))
MAX_DISPLAY_NAME_LENGTH = 32
