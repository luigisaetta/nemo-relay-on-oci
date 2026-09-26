"""Esegue il grafo con un modello finto (nessuna chiamata a OCI) e riassume gli eventi Relay."""

import asyncio
import json
from collections import Counter
from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from oci_ops_graph import run


class FakeOCIModel(GenericFakeChatModel):
    """Fake OCI-compatible model used for an offline Relay smoke test."""

    model_id: str = "meta.llama-3.3-70b-instruct"

    def bind_tools(self, tools, **kwargs):
        return self


def usage(i, o):
    """Build deterministic OCI-style usage metadata.

    Args:
        i: Number of input tokens.
        o: Number of output tokens.

    Returns:
        Token-usage mapping accepted by the fake model messages.
    """
    return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}


script = iter(
    [
        AIMessage(content="ops", usage_metadata=usage(40, 1)),  # router
        AIMessage(  # ops_agent: chiede un tool
            content="",
            tool_calls=[
                {
                    "name": "get_gpu_capacity",
                    "args": {"region": "eu-frankfurt-1", "shape": "BM.GPU.H100.8"},
                    "id": "c1",
                }
            ],
            usage_metadata=usage(300, 20),
        ),
        AIMessage(
            content="Si': 2 host H100 disponibili in AD-1. Consiglio self-hosting su OKE.",
            usage_metadata=usage(350, 30),
        ),
    ]
)

out = Path("observability")
for f in out.glob("*"):
    f.unlink()

final = asyncio.run(
    run(FakeOCIModel(messages=script), "Posso eseguire Nemotron su H100 a Francoforte?")
)
print("\n--- messaggi finali")
for m in final["messages"]:
    print(f"[{m.type}] {m.text or m.tool_calls}")

events = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
print("\n--- eventi ATOF:", len(events))
print(
    Counter(
        f"{e.get('kind')}:{e.get('category') or e.get('scope_type') or ''}:{e.get('name')}"
        for e in events
    ).most_common()
)
print("\n--- file:", sorted(p.name for p in out.iterdir()))
