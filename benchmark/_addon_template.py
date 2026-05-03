"""Mitmproxy addon for capturing usage data from Kiro's API responses.

This script is loaded by mitmdump as an addon. It must NOT import from the
benchmark package — it runs in mitmdump's own process.

Kiro routes API traffic through AWS (generateAssistantResponse) using the
Amazon Event Stream binary format. The AWS backend does not expose raw
input_tokens/output_tokens — instead, each response stream ends with a
credit usage event: {"unit": "credit", "usage": 0.213}

This addon captures that credit usage value as the primary metric. Credit
usage is proportional to token consumption, making it valid for A/B
comparison of baseline vs treatment runs.

The JSONL output path is read from the BENCHMARK_JSONL_PATH environment variable.
"""

import json
import os
import struct
import time


def _parse_amazon_eventstream_events(raw_bytes):
    """Parse Amazon Event Stream binary format into a list of (headers, payload) tuples.

    The format is:
      - 4 bytes: total length (big-endian)
      - 4 bytes: headers length (big-endian)
      - 4 bytes: prelude CRC
      - <headers_length> bytes: headers
      - remaining (total - headers - 16): payload
      - 4 bytes: message CRC

    Each header:
      - 1 byte: name length
      - <name_length> bytes: name (utf-8)
      - 1 byte: value type (7 = string)
      - 2 bytes: value length (big-endian)
      - <value_length> bytes: value
    """
    events = []
    offset = 0

    while offset + 12 <= len(raw_bytes):
        try:
            total_length = struct.unpack(">I", raw_bytes[offset:offset + 4])[0]
            headers_length = struct.unpack(">I", raw_bytes[offset + 4:offset + 8])[0]
        except struct.error:
            break

        if total_length < 16 or offset + total_length > len(raw_bytes):
            break

        headers_start = offset + 12
        headers_end = headers_start + headers_length
        payload_start = headers_end
        payload_end = offset + total_length - 4

        headers = {}
        h_offset = headers_start
        while h_offset < headers_end:
            if h_offset >= len(raw_bytes):
                break
            name_len = raw_bytes[h_offset]
            h_offset += 1
            name = raw_bytes[h_offset:h_offset + name_len].decode("utf-8", errors="replace")
            h_offset += name_len
            value_type = raw_bytes[h_offset]
            h_offset += 1
            if value_type == 7:  # string
                val_len = struct.unpack(">H", raw_bytes[h_offset:h_offset + 2])[0]
                h_offset += 2
                value = raw_bytes[h_offset:h_offset + val_len].decode("utf-8", errors="replace")
                h_offset += val_len
                headers[name] = value
            else:
                break

        payload = raw_bytes[payload_start:payload_end]
        events.append((headers, payload))
        offset += total_length

    return events


class UsageCaptureAddon:
    """Mitmproxy addon that intercepts Kiro API traffic and logs credit usage."""

    def __init__(self):
        self.output_path = os.environ.get("BENCHMARK_JSONL_PATH", "/tmp/benchmark_tokens.jsonl")
        self.log_file = open(self.output_path, "a")

    def _write_entry(self, entry):
        """Write a JSON entry to the JSONL log file."""
        self.log_file.write(json.dumps(entry) + "\n")
        self.log_file.flush()

    def _extract_usage_from_eventstream(self, raw_bytes):
        """Extract credit usage from Amazon Event Stream binary format.

        Kiro's AWS backend sends credit usage and context percentage in the
        final events of each generateAssistantResponse stream:
          {"contextUsagePercentage": 2.57}
          {"unit": "credit", "usage": 0.213}

        Returns:
            A dict with credit_usage and context_usage_pct, or None.
        """
        events = _parse_amazon_eventstream_events(raw_bytes)

        credit_usage = None
        context_pct = None

        for headers, payload in events:
            try:
                data = json.loads(payload.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
                continue

            # Credit usage event: {"unit": "credit", "usage": 0.213}
            if "usage" in data and "unit" in data:
                credit_usage = data["usage"]

            # Context window percentage: {"contextUsagePercentage": 2.57}
            if "contextUsagePercentage" in data:
                context_pct = data["contextUsagePercentage"]

        if credit_usage is not None:
            return {
                "credit_usage": credit_usage,
                "context_usage_pct": context_pct,
            }
        return None

    def response(self, flow):
        """Intercept responses from AWS and extract credit usage."""
        host = flow.request.host
        if "anthropic" not in host and "amazonaws.com" not in host:
            return

        timestamp = time.time()
        content_type = flow.response.headers.get("content-type", "")

        # Skip non-chat endpoints
        path = flow.request.path.split("?")[0]
        skip_paths = ["/getUsageLimits", "/ListAvailableModels", "/mcp",
                      "/listFeatureEvaluations", "/sendTelemetryEvent"]
        if any(path.endswith(p) for p in skip_paths):
            return

        try:
            raw_content = flow.response.content
            if not raw_content:
                return
        except AttributeError:
            return

        usage = None

        # Amazon Event Stream (binary) — primary path for Kiro
        if "amazon.eventstream" in content_type:
            usage = self._extract_usage_from_eventstream(raw_content)

        if usage:
            # Write with both the real metric (credit_usage) and the legacy
            # fields (input_tokens/output_tokens) for pipeline compatibility.
            # input_tokens = millicredits (credit_usage * 1000), output_tokens = 0.
            millicredits = int(usage["credit_usage"] * 1000)
            entry = {
                "type": "token_usage",
                "credit_usage": usage["credit_usage"],
                "millicredits": millicredits,
                "input_tokens": millicredits,
                "output_tokens": 0,
                "context_usage_pct": usage.get("context_usage_pct"),
                "timestamp": timestamp,
            }
            self._write_entry(entry)

    def request(self, flow):
        """Inspect requests for MCP tool calls (Context Lens tools)."""
        host = flow.request.host
        if "anthropic" not in host and "amazonaws.com" not in host:
            return

        try:
            content = flow.request.content.decode("utf-8", errors="replace")
        except AttributeError:
            return

        mcp_tools = ["context_index", "context_query", "context_expand"]
        tools_found = [tool for tool in mcp_tools if tool in content]

        if tools_found:
            entry = {
                "type": "mcp_tool_call",
                "tools": tools_found,
                "timestamp": time.time(),
            }
            self._write_entry(entry)


addons = [UsageCaptureAddon()]
