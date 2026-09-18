"""Amazon Bedrock access for the two BreakFix agents.

Two transports, tried in order, because a hackathon AWS account is not a
controlled environment and the demo cannot hinge on one endpoint being enabled:

  1. `AnthropicBedrockMantle` from the official `anthropic` SDK -- the current
     Messages-API Bedrock endpoint. Preferred.
  2. boto3 `bedrock-runtime.converse` -- the classic path. Zero extra
     dependencies (boto3 ships in the Lambda runtime), so this keeps working
     even if the Anthropic SDK is missing from the bundle.

Both are Amazon Bedrock for the purposes of PRD Section 5.4 / Appendix A.

Neither agent is ever asked to decide correctness -- see evaluator.py.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from common import config

logger = logging.getLogger(__name__)


class BedrockUnavailable(RuntimeError):
    """Raised when no Bedrock transport could produce a response."""


def _messages_via_anthropic_sdk(system: str, user_text: str, max_tokens: int) -> str:
    from anthropic import AnthropicBedrockMantle

    client = AnthropicBedrockMantle(aws_region=config.BEDROCK_REGION)
    response = client.messages.create(
        model=config.BEDROCK_MODEL_ID,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_text}],
    )
    if getattr(response, "stop_reason", None) == "refusal":
        raise BedrockUnavailable("Model declined the request.")
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")


def _messages_via_boto3(system: str, user_text: str, max_tokens: int) -> str:
    import boto3
    from botocore.config import Config as BotoConfig

    client = boto3.client(
        "bedrock-runtime",
        region_name=config.BEDROCK_REGION,
        config=BotoConfig(
            read_timeout=config.BEDROCK_TIMEOUT_SECONDS,
            connect_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )
    response = client.converse(
        modelId=config.BEDROCK_FALLBACK_MODEL_ID,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": max_tokens},
    )
    blocks = response["output"]["message"]["content"]
    return "".join(b.get("text", "") for b in blocks)


def invoke(system: str, user_text: str, max_tokens: Optional[int] = None) -> Tuple[str, str]:
    """Returns (response_text, transport_name). Raises BedrockUnavailable."""
    max_tokens = max_tokens or config.BEDROCK_MAX_TOKENS
    attempts: List[Tuple[str, Any]] = [
        ("bedrock-anthropic-sdk", _messages_via_anthropic_sdk),
        ("bedrock-boto3-converse", _messages_via_boto3),
    ]
    failures = []
    for name, fn in attempts:
        try:
            text = fn(system, user_text, max_tokens)
            if text and text.strip():
                return text, name
            failures.append(f"{name}: empty response")
        except Exception as exc:  # noqa: BLE001 - we genuinely want to try the next transport
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            logger.warning("Bedrock transport %s failed: %s", name, exc)
    raise BedrockUnavailable("; ".join(failures))


# ---------------------------------------------------------------------------
# Structured-output parsing
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_response(text: str, required_keys: List[str]) -> Dict[str, Any]:
    """Pull a JSON object out of a model response.

    Assistant prefill is not available on current models, so rather than forcing
    the shape by prefilling `{`, we ask for JSON in the prompt and parse
    defensively here: raw JSON, then a fenced block, then the outermost braces.
    """
    candidates = [text.strip()]
    fence = _FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            missing = [k for k in required_keys if k not in parsed]
            if missing:
                raise ValueError(f"Model response is missing required keys: {missing}")
            return parsed
    raise ValueError("Model response did not contain a JSON object.")
