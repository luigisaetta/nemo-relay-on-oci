r"""
Grafo LangGraph su OCI Generative AI, osservato e governato da NVIDIA NeMo Relay.

Flusso:
    START -> router --(ops)------> ops_agent -> approval -> END
                    \-(general)--> general_answer -------> END

Cosa dimostra:
  * NemoRelayCallbackHandler  -> scope per grafo/nodi + mark di interrupt/resume
  * NemoRelayMiddleware       -> chiamate LLM e tool "managed" dentro create_agent
  * relay_chat()              -> chiamata LLM in un nodo custom instradata a mano
                                 nella pipeline Relay (il callback handler NON
                                 registra le chiamate LLM fatte direttamente)
  * checkpointer + interrupt  -> human-in-the-loop con ripresa via Command(resume=...)

Requisiti:
    pip install "nemo-relay[langgraph]>=0.9" langchain-oci

Variabili d'ambiente (nessuna credenziale nel codice):
    OCI_GENAI_MODEL_ID      es. meta.llama-3.3-70b-instruct
    OCI_GENAI_ENDPOINT      es. https://inference.generativeai.eu-frankfurt-1.oci.oraclecloud.com
    OCI_COMPARTMENT_ID      OCID del compartment
    OCI_CONFIG_PROFILE      profilo di ~/.oci/config (default: DEFAULT)
r"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Literal

import nemo_relay
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    convert_to_openai_messages,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_oci import ChatOCIGenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command, interrupt
from nemo_relay import plugin
from nemo_relay.codecs import OpenAIChatCodec
from nemo_relay.integrations.langgraph import (
    NemoRelayCallbackHandler,
    NemoRelayMiddleware,
)

PLUGINS_TOML = Path(__file__).with_name("plugins.toml")


# --------------------------------------------------------------------------- #
# Modello OCI
# --------------------------------------------------------------------------- #
def build_oci_llm() -> BaseChatModel:
    """Build the OCI Generative AI chat model from environment settings.

    Returns:
        A configured OCI chat model.

    Raises:
        KeyError: A required OCI environment variable is not set.
    """

    return ChatOCIGenAI(
        model_id=os.environ["OCI_GENAI_MODEL_ID"],
        service_endpoint=os.environ["OCI_GENAI_ENDPOINT"],
        compartment_id=os.environ["OCI_COMPARTMENT_ID"],
        auth_type="API_KEY",
        auth_profile=os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT"),
        model_kwargs={"temperature": 0, "max_tokens": 800},
    )


def model_id_of(llm: BaseChatModel) -> str:
    """Return the model identifier exposed by a chat model.

    Args:
        llm: Chat model to inspect.

    Returns:
        The configured model identifier, or ``"unknown"`` when unavailable.
    """
    return (
        getattr(llm, "model_id", None) or getattr(llm, "model_name", None) or "unknown"
    )


# --------------------------------------------------------------------------- #
# Chiamata LLM "managed" per nodi custom
# --------------------------------------------------------------------------- #
async def relay_chat(
    llm: BaseChatModel, messages: list[BaseMessage], *, name: str
) -> AIMessage:
    """Invoca il modello passando dalla pipeline NeMo Relay.

    Il payload viene proiettato in formato OpenAI Chat, cosi' OpenAIChatCodec
    permette a guardrail, redazione PII e pricing di "capire" richiesta e
    risposta. Il client ChatOCIGenAI resta dentro la callback.
    """
    model_id = model_id_of(llm)
    codec = OpenAIChatCodec()
    request = nemo_relay.LLMRequest(
        {}, {"model": model_id, "messages": convert_to_openai_messages(messages)}
    )

    async def _call(req: nemo_relay.LLMRequest) -> dict:
        # req.content riflette eventuali modifiche fatte dai request intercept
        ai = await llm.ainvoke(req.content["messages"])
        usage = ai.usage_metadata or {}
        return {
            "id": ai.id or str(uuid.uuid4()),
            "object": "chat.completion",
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": ai.text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

    response = await nemo_relay.llm.execute(
        name, request, _call, model_name=model_id, codec=codec, response_codec=codec
    )
    return AIMessage(content=response["choices"][0]["message"]["content"])


# --------------------------------------------------------------------------- #
# Tool (dati fittizi: sostituisci con chiamate reali all'SDK OCI)
# --------------------------------------------------------------------------- #
@tool
def get_gpu_capacity(region: str, shape: str) -> str:
    """Restituisce la capacita' disponibile per una shape GPU in una region OCI."""
    return f"{shape} in {region}: 2 host disponibili in AD-1, 0 in AD-2."


@tool
def list_genai_models(region: str) -> str:
    """Elenca i modelli chat disponibili in OCI Generative AI per una region."""
    return (
        f"{region}: meta.llama-3.3-70b-instruct, cohere.command-a-03-2025, xai.grok-4"
    )


# --------------------------------------------------------------------------- #
# Grafo
# --------------------------------------------------------------------------- #
class State(MessagesState):
    """State carried through the OCI operations workflow."""

    route: str
    approved: bool


def build_graph(llm: BaseChatModel, checkpointer=None):
    """Build the OCI operations graph with human approval.

    Args:
        llm: Chat model used by graph nodes and the managed sub-agent.
        checkpointer: Optional LangGraph checkpointer for interrupt resumption.

    Returns:
        A compiled LangGraph workflow.
    """
    # Sotto-agente LangChain: middleware Relay -> ogni chiamata LLM e tool e' managed
    ops_agent_runnable = create_agent(
        model=llm,
        tools=[get_gpu_capacity, list_genai_models],
        middleware=[NemoRelayMiddleware()],
        system_prompt=(
            "Sei un assistente per le operations su OCI. Usa i tool per verificare "
            "modelli e capacita' GPU e proponi una raccomandazione concreta."
        ),
    )

    async def router(state: State) -> dict:
        decision = await relay_chat(
            llm,
            [
                SystemMessage(
                    "Classifica la richiesta. Rispondi solo con 'ops' se riguarda "
                    "modelli, GPU, capacita' o deployment su OCI, altrimenti 'general'."
                ),
                state["messages"][-1],
            ],
            name="router",
        )
        return {"route": "ops" if "ops" in decision.text.lower() else "general"}

    def pick_route(state: State) -> Literal["ops_agent", "general_answer"]:
        return "ops_agent" if state["route"] == "ops" else "general_answer"

    async def ops_agent(state: State, config: RunnableConfig) -> dict:
        # Passare config propaga callback e scope Relay al sotto-agente
        result = await ops_agent_runnable.ainvoke(
            {"messages": state["messages"]}, config=config
        )
        return {"messages": result["messages"][len(state["messages"]) :]}

    async def general_answer(state: State) -> dict:
        answer = await relay_chat(llm, state["messages"], name="general_answer")
        return {"messages": [answer]}

    def approval(state: State) -> dict:
        # Human-in-the-loop: il grafo si ferma e viene ripreso con Command(resume=...)
        decision = interrupt(
            {
                "question": "Approvi la raccomandazione?",
                "draft": state["messages"][-1].text,
            }
        )
        approved = str(decision).lower() in {"si", "sì", "yes", "ok"}
        note = "Raccomandazione approvata." if approved else "Raccomandazione respinta."
        return {"approved": approved, "messages": [AIMessage(content=note)]}

    builder = StateGraph(State)
    builder.add_node("router", router)
    builder.add_node("ops_agent", ops_agent)
    builder.add_node("general_answer", general_answer)
    builder.add_node("approval", approval)
    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", pick_route)
    builder.add_edge("ops_agent", "approval")
    builder.add_edge("approval", END)
    builder.add_edge("general_answer", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


# --------------------------------------------------------------------------- #
# Esecuzione
# --------------------------------------------------------------------------- #
async def run(llm: BaseChatModel, question: str, resume_answer: str = "si") -> dict:
    """Run the OCI operations graph through an approval cycle.

    Args:
        llm: Chat model used by the workflow.
        question: User request to process.
        resume_answer: Approval response used to resume the interrupted graph.

    Returns:
        The final graph state.
    """
    graph = build_graph(llm)
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    config: RunnableConfig = {**thread, "callbacks": [NemoRelayCallbackHandler()]}

    # Attiva i plugin Relay (exporter, PII, pricing...) definiti in plugins.toml
    async with plugin.activate(plugin.PluginConfig(), PLUGINS_TOML):
        with nemo_relay.scope.scope("oci-ops-request", nemo_relay.ScopeType.Agent):
            result = await graph.ainvoke(
                {"messages": [("user", question)]}, config=config
            )

            if "__interrupt__" in result:
                print("INTERRUPT:", result["__interrupt__"][0].value)
                result = await graph.ainvoke(
                    Command(resume=resume_answer), config=config
                )

        await nemo_relay.subscribers.flush_async()
    return result


if __name__ == "__main__":
    final = asyncio.run(
        run(build_oci_llm(), "Posso eseguire Nemotron su GPU H100 in eu-frankfurt-1?")
    )
    for m in final["messages"]:
        print(f"[{m.type}] {m.text[:300]}")
