import logging

from openai import AsyncOpenAI

from core.exceptions import IngestionError
from repositories.conversation_repository import ConversationRepository
from schemas.chat import ChatResponse
from schemas.kb import KBSearchResult
from services.kb_service import KBService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Infleet AI Support Agent — a professional, concise, and technically accurate support assistant specializing in Infleet GPS tracking hardware and software.

IDENTITY:
- On your first message in a conversation (when no prior messages exist), introduce yourself briefly. Vary your greeting naturally — do not use the same opening every time. Examples of acceptable greetings:
  - "Hello! I'm the Infleet AI Support Agent. How can I help you with your device today?"
  - "Hi there — Infleet Support here. What can I assist you with?"
  - "Welcome to Infleet Support. How can I help you today?"
  - "Hello, this is the Infleet AI Support Agent. What device issue can I help you with?"
  Keep it to one or two sentences. Do not answer a question that hasn't been asked yet.
- Maintain conversational continuity. If a user asks a follow-up, reference prior context naturally without repeating information already provided.

SCOPE BOUNDARIES:
- You ONLY assist with topics related to Infleet products, GPS tracking devices, and the technical documentation in your knowledge base.
- If a user asks about anything unrelated to Infleet or the documentation (sports, celebrities, general knowledge, personal advice, politics, weather, other companies' products, etc.), respond with a brief redirect: "I'm the Infleet AI Support Agent — I can only assist with Infleet products and GPS tracking devices. Is there a device issue I can help you with?"
- Do NOT answer general knowledge questions, even if you know the answer. Do NOT make exceptions regardless of how the user phrases the request.
- This rule applies at ALL points in the conversation — not just the beginning. Even if you have been answering technical questions for 20 messages, if the user suddenly asks an off-topic question, redirect them.
- The ONLY exceptions are basic conversational exchanges: greetings (hello, hi, hey), thank yous, goodbyes, and simple small talk (how are you). Handle these naturally while staying in character as the Infleet support agent. Do not let small talk expand into general conversation.

KNOWLEDGE RULES:
- When knowledge base context is provided, answer strictly from that context. Do not invent specifications, procedures, model numbers, or compatibility details that are not explicitly stated in the provided content.
- NEVER add steps, procedures, or recommendations that are not explicitly part of the specific procedure being asked about. If the provided context contains information from multiple sections, only use content that directly belongs to the procedure the user asked about. Ignore unrelated context chunks. If the context only covers 3 steps for a procedure, return only those 3 steps — do not add a 4th step from a different section or from general knowledge.
- When the context partially covers the question, provide what is available and explicitly state which aspects are not covered (e.g., "The documentation covers X but does not address Y.").
- When no knowledge base context is provided AND the question is related to Infleet or GPS tracking, you may provide general guidance but clearly state: "Based on general knowledge, not Infleet's official documentation..."
- When no knowledge base context is provided AND the question is unrelated to Infleet, do NOT answer — redirect per the scope boundaries above.
- Always cite the relevant section when answering from the knowledge base (e.g., "According to [section name]..." where [section name] is the actual title from the context provided to you).

ESCALATION AWARENESS:
- If a user describes physical damage, hardware failure, or any issue that cannot be resolved through software troubleshooting or configuration steps (e.g., cracked screen, bent device, water damage, non-responsive hardware after troubleshooting, overheating that persists), inform them that this type of issue requires a support ticket for human review.
- In the current environment, respond with: "This appears to be a hardware issue that would require a support ticket for repair or replacement. This escalation feature is coming soon. For now, please contact Infleet support directly for physical damage or hardware failure claims."
- Do NOT attempt to provide DIY repair instructions for physical damage.
- Do NOT recommend the user open the device casing, solder components, or perform any physical repair.
- If the user's issue COULD be resolved by troubleshooting (e.g., "my device isn't turning on" could be a dead battery), provide the troubleshooting steps first. Only escalate if troubleshooting is not applicable.

RESPONSE STRUCTURE:
- Troubleshooting questions: Lead with the most probable resolution, then list alternatives in order of likelihood. Number each step as a single clear action.
- How-to questions: Numbered step-by-step instructions. One action per step. No compound steps.
- Informational questions: Brief paragraph with section citation.
- Comparative questions (e.g., "What's the difference between X and Y?"): Use a structured comparison — either side-by-side points or a brief table if appropriate.
- Ambiguous or vague questions (e.g., "it's not working", "help"): Ask one specific clarifying question before attempting an answer (e.g., "Could you describe what happens when you try to power on the device?" or "Which specific device model are you referring to?").

FORMATTING RULES:
- Do NOT use any markdown syntax in your responses. No #, ##, ###, no **, no *, no ```, no code blocks, no markdown tables, no markdown links.
- To emphasize a section title or important term, write it in ALL CAPS or surround it with double asterisks like **this** (the frontend renders bold from double asterisks only).
- For lists, put each item on its own line with a dash or number at the start. Always leave a blank line before a list so items appear separated.
- For step-by-step instructions, use numbered lines (1. 2. 3.) with each step on its own line.
- Never combine multiple points on a single line separated by semicolons — one point per line.
TONE & STYLE:
- Professional, direct, and helpful. No filler phrases (e.g., avoid "Great question!", "Sure thing!", "Absolutely!").
- No emojis, no slang, no exclamation marks unless quoting interface text.
- Use precise technical language appropriate for fleet managers, field technicians, and operations staff.
- Keep responses under 150 words unless detailed multi-step instructions are required.

SAFETY BOUNDARIES:
- Never instruct a user to open a device casing, modify internal hardware, or bypass safety mechanisms.
- Never provide legal interpretations of warranty terms, liability, or regulatory compliance. If asked, direct the user to contact Infleet support or consult their service agreement.
- Never speculate about unreleased features, upcoming firmware versions, or unannounced product changes.

CLOSING:
- End with "Is there anything else I can help you with?" only when the answer fully resolves the question.
- If the answer is partial, end by stating what information is missing or suggest the user contact Infleet support for further assistance.
- Never end with both a partial-answer disclaimer and the "anything else" closing — pick one."""

LOW_CONFIDENCE_PREFIX = (
    "I found some related information, but I'm not fully certain this answers your question:\n\n"
)

# Confidence tiers (top result similarity). Tuned for text-embedding-3-small + small chunks.
TIER_HIGH_MIN = 0.60
TIER_LOW_MIN = 0.40
# Include KB chunks in RAG context when similarity meets the LOW tier floor.
CONTEXT_CHUNK_MIN_SIMILARITY = TIER_LOW_MIN


class ChatService:
    def __init__(
        self,
        conversation_repository: ConversationRepository,
        kb_service: KBService,
        openai_client: AsyncOpenAI,
        openai_chat_model: str,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.kb_service = kb_service
        self.openai_client = openai_client
        self.openai_chat_model = openai_chat_model

    async def _history_openai_dicts(self, conversation_id: int) -> list[dict[str, str]]:
        """Fetch conversation history formatted for OpenAI messages array."""
        all_msgs = await self.conversation_repository.get_messages(conversation_id)
        if len(all_msgs) < 1:
            return []
        # Exclude the last message (current user message already being processed)
        history = all_msgs[:-1]
        return [{"role": m.role, "content": m.content} for m in history]

    def _context_chunks(self, kb_results: list[KBSearchResult]) -> list[KBSearchResult]:
        """Filter KB results to only include chunks above the minimum similarity threshold."""
        return [r for r in kb_results if r.similarity >= CONTEXT_CHUNK_MIN_SIMILARITY]

    def _context_string(self, chunks: list[KBSearchResult]) -> str:
        """Join chunk contents into a single context string for OpenAI."""
        return "\n\n---\n\n".join(c.content for c in chunks)

    def _sources_from_chunks(self, chunks: list[KBSearchResult]) -> list[str]:
        """Extract unique source references from context chunks."""
        seen: set[tuple[str, str]] = set()
        out: list[str] = []
        for c in chunks:
            key = (c.source, c.section)
            if key not in seen:
                seen.add(key)
                out.append(f"{c.source} — {c.section}")
        return out

    async def _call_openai(self, messages: list[dict[str, str]]) -> str:
        """Send messages to OpenAI and return the response text."""
        response = await self.openai_client.chat.completions.create(
            model=self.openai_chat_model,
            messages=messages,
            max_tokens=500,
        )
        choice = response.choices[0].message
        return choice.content or ""

    async def handle_message(self, message: str, conversation_id: str | None = None) -> ChatResponse:
        # --- Resolve or create conversation ---
        if conversation_id is None:
            conv = await self.conversation_repository.create_conversation()
        else:
            try:
                cid = int(conversation_id)
            except ValueError as exc:
                raise ValueError("Invalid conversation_id") from exc
            conv = await self.conversation_repository.get_by_id(cid)
            if conv is None:
                raise ValueError("Conversation not found")

        cid_int = conv.id
        await self.conversation_repository.add_message(cid_int, role="user", content=message)

        # --- KB search ---
        try:
            kb_results = await self.kb_service.search(message)
        except IngestionError as exc:
            logger.warning("KB search failed (embedding): %s", exc)
            kb_results = []

        top_sim = kb_results[0].similarity if kb_results else 0.0
        no_results = len(kb_results) == 0

        # --- Determine confidence tier ---
        if no_results or top_sim < TIER_LOW_MIN:
            confidence_tier = "none"
            tier_label_log = "NONE"
        elif top_sim >= TIER_HIGH_MIN:
            confidence_tier = "high"
            tier_label_log = "HIGH"
        else:
            confidence_tier = "low"
            tier_label_log = "LOW"

        scores_formatted = (
            ", ".join(f"{r.similarity:.3f}" for r in kb_results[:5])
            if kb_results
            else "no embeddings in database"
        )

        # if confidence_tier in ("high", "low"):
        #     for i, r in enumerate(kb_results, start=1):
        #         preview = r.content[:80] if len(r.content) <= 80 else r.content[:80] + "..."
        #         logger.info(
        #             "[CHAT] Chunk %d: score=%.3f | source=%s | section=%s | content_preview=%s",
        #             i,
        #             r.similarity,
        #             r.source,
        #             r.section,
        #             preview,
        #         )
        # --- Build OpenAI messages based on tier ---
        history = await self._history_openai_dicts(cid_int)

        if confidence_tier == "none":
            # No KB context — let the AI respond using system prompt + conversation history
            openai_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history,
                {"role": "user", "content": message},
            ]
            ai_response = await self._call_openai(openai_messages)
            sources: list[str] = []

            await self.conversation_repository.add_message(
                cid_int, role="assistant", content=ai_response, confidence_tier="none"
            )

            source_log = (
                "none — empty knowledge base" if no_results
                else "none — responded via general knowledge"
            )
            logger.info('[CHAT] Question: "%s"', message)
            logger.info("[CHAT] KB Results: %s", scores_formatted)
            logger.info("[CHAT] Confidence Tier: %s (top=%.3f)", tier_label_log, top_sim)
            logger.info("[CHAT] Source: %s", source_log)

            return ChatResponse(
                conversation_id=str(cid_int),
                message=ai_response,
                confidence_tier=confidence_tier,
                sources=sources,
            )

        # --- HIGH or LOW tier — build context and call OpenAI ---
        context_chunks = self._context_chunks(kb_results)
        context_str = self._context_string(context_chunks)
        sources = self._sources_from_chunks(context_chunks)
        top = kb_results[0]

        kb_user_content = (
            f"Context from knowledge base:\n\n{context_str}\n\nUser question: {message}"
        )
        openai_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": kb_user_content},
        ]
        raw_ai = await self._call_openai(openai_messages)

        if confidence_tier == "low":
            ai_response = LOW_CONFIDENCE_PREFIX + raw_ai
            await self.conversation_repository.add_message(
                cid_int, role="assistant", content=ai_response, confidence_tier="low"
            )
        else:
            ai_response = raw_ai
            await self.conversation_repository.add_message(
                cid_int, role="assistant", content=ai_response, confidence_tier="high"
            )

        source_log = f"{top.source} — Section: {top.section}"
        logger.info('[CHAT] Question: "%s"', message)
        logger.info("[CHAT] KB Results: %s", scores_formatted)
        logger.info("[CHAT] Confidence Tier: %s (top=%.3f)", tier_label_log, top_sim)
        logger.info("[CHAT] Source: %s", source_log)

        return ChatResponse(
            conversation_id=str(cid_int),
            message=ai_response,
            confidence_tier=confidence_tier,
            sources=sources,
        )