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
