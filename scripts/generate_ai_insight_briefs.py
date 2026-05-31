#!/usr/bin/env python3
"""Generate deterministic AI-style insight briefs from a report context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_trading.ai_briefs import (  # noqa: E402
    build_ai_insight_briefs,
    render_ai_briefs_html,
    render_ai_briefs_markdown,
)
from stock_trading.ai_prompt_packets import build_prompt_packet_context  # noqa: E402
from stock_trading.llm_research_briefs import (  # noqa: E402
    MockLLMResearchBriefClient,
    build_llm_research_briefs,
    write_llm_research_brief_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate auditable AI insight brief artifacts.")
    parser.add_argument("--context", default="", help="Report context JSON path. Defaults to today's report context if present.")
    parser.add_argument("--output-dir", default=str(ROOT / "reports"), help="Directory for generated brief artifacts.")
    parser.add_argument("--llm-research-briefs", action="store_true", help="Also generate optional LLM research-brief draft artifacts from prompt packets.")
    parser.add_argument("--prompt-packets", default="", help="Approved AI prompt packet JSON path for LLM research briefs. Defaults to packets built from --context.")
    parser.add_argument("--mock-llm", action="store_true", help="Use a deterministic mock LLM client. Without this, LLM brief generation is dry-run/refusal only.")
    args = parser.parse_args()

    context_path = Path(args.context) if args.context else sorted((ROOT / "reports").glob("report-context-*.json"))[-1]
    context = json.loads(context_path.read_text())
    report_date = str(context.get("metadata", {}).get("report_date") or context_path.stem.rsplit("-", 1)[-1])
    brief_context = build_ai_insight_briefs(context)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"ai-insight-briefs-{report_date}.md"
    json_path = output_dir / f"ai-insight-briefs-{report_date}.json"
    html_path = output_dir / f"ai-insight-briefs-{report_date}.html"

    markdown_path.write_text(render_ai_briefs_markdown(brief_context))
    json_path.write_text(json.dumps(brief_context, indent=2))
    html_path.write_text(render_ai_briefs_html(brief_context))

    print(f"Wrote {markdown_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {html_path}")
    if args.llm_research_briefs:
        packet_context = (
            json.loads(Path(args.prompt_packets).read_text())
            if args.prompt_packets
            else build_prompt_packet_context(context)
        )
        client = MockLLMResearchBriefClient() if args.mock_llm else None
        llm_context = build_llm_research_briefs(packet_context, client=client)
        for path in write_llm_research_brief_artifacts(llm_context, output_dir, report_date):
            print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
