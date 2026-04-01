import logging
import re

from openai import AsyncOpenAI

from core.exceptions import IngestionError, JiraAPIError
from repositories.conversation_repository import ConversationRepository
from schemas.chat import ChatResponse
from schemas.kb import KBSearchResult
from schemas.ticket import TicketCreateRequest
from services.kb_service import KBService
from services.ticket_service import TicketService

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
- If a user asks about anything clearly unrelated to Infleet or technical support (sports, celebrities, general knowledge, personal advice, politics, weather, etc.), respond with a brief redirect: "I'm the Infleet AI Support Agent — I can only assist with Infleet products and GPS tracking devices. Is there a device issue I can help you with?"
- If the user says their device or system is an Infleet product, trust them. Do NOT reject their issue by saying it is unrelated. Treat it as an Infleet support request and proceed normally (troubleshooting or escalation).
- Do NOT answer general knowledge questions, even if you know the answer. Do NOT make exceptions regardless of how the user phrases the request.
- This rule applies at ALL points in the conversation — not just the beginning. Even if you have been answering technical questions for 20 messages, if the user suddenly asks an off-topic question, redirect them.
- The ONLY exceptions are basic conversational exchanges: greetings (hello, hi, hey), thank yous, goodbyes, and simple small talk (how are you). Handle these naturally while staying in character as the Infleet support agent. Do not let small talk expand into general conversation.

KNOWLEDGE RULES:
- When knowledge base context is provided, answer strictly from that context. Do not invent specifications, procedures, model numbers, or compatibility details that are not explicitly stated in the provided content.
- If the provided context does not directly answer the user's question, say so explicitly — for example: "The documentation provided doesn't contain a direct answer to this question. Could you rephrase, or would you like me to search for something more specific?" Do NOT fill gaps with your own general knowledge. A partial match in the context is not permission to complete the answer from your training data.
- NEVER add steps, procedures, or recommendations that are not explicitly part of the specific procedure being asked about. If the provided context contains information from multiple sections, only use content that directly belongs to the procedure the user asked about. Ignore unrelated context chunks. If the context only covers 3 steps for a procedure, return only those 3 steps — do not add a 4th step from a different section or from general knowledge.
- When the context partially covers the question, provide what is available and explicitly state which aspects are not covered (e.g., "The documentation covers X but does not address Y.").
- When no knowledge base context is provided AND the question is related to Infleet or GPS tracking, you may provide general guidance but clearly state: "Based on general knowledge, not Infleet's official documentation..."
- When no knowledge base context is provided AND the question is unrelated to Infleet, do NOT answer — redirect per the scope boundaries above.
- Always cite the relevant section when answering from the knowledge base (e.g., "According to [section name]..." where [section name] is the actual title from the context provided to you).
- EXCEPTION: If the conversation history shows you have been collecting information for a support ticket (you asked the user about their device, their issue, when it started, or what they tried, and they are responding to those questions), you are in an ESCALATION FLOW. During an escalation flow:
  - Do NOT say "The documentation doesn't contain a direct answer"
  - Do NOT say "Could you rephrase"
  - Do NOT reference the knowledge base at all
  - Simply continue collecting the missing information or create the ticket if you have enough
  - The user is answering YOUR questions — they are not asking a new KB question

ESCALATION AWARENESS:
- If you cannot resolve the user's issue from the knowledge base after attempting to help, you must collect information and create a support ticket.
- Escalation applies to ANY unresolved issue — hardware damage, software problems, integration issues, access problems, or any technical question you cannot answer from the provided context.
- Always attempt to answer from the knowledge base first. Only escalate when the KB is exhausted and the issue remains unresolved.
- If the knowledge base does not have a relevant answer AND the user is describing a real technical problem (not a how-to question), move to escalation collection immediately. Do NOT keep suggesting generic steps that are not from the KB.

ESCALATION COLLECTION:
When escalation is needed, collect the following information through natural conversation. Do NOT ask all questions at once — ask one at a time based on what's missing. If the user already provided some info in earlier messages, do not ask again.

For hardware issues (physical damage, device not working, overheating):
- Device serial number or vehicle name
- What happened to the device
- When did it start
- What they have tried

For software issues (dashboard errors, login problems, update failures):
- Which software or screen has the problem
- What exactly happens
- When did it start or what changed (update, config change)
- What they have tried
- Do NOT ask for a device serial number for software issues. Software/dashboard/login problems are not tied to a specific device.
- ALWAYS set device_serial to null for software issues in the [CREATE_TICKET] block, even if the user mentioned a serial earlier in the conversation for a different issue. Do NOT carry over serial numbers from previous issues.

If unsure whether hardware or software, ask the user to describe the problem first, then follow the appropriate path.

COLLECTION EFFICIENCY:
- Combine related questions into one message. For example: "Could you provide your device serial number, and let me know when this happened?" — do NOT ask these as separate messages.
- Maximum 3 follow-up messages to collect info. After 3 follow-ups, create the ticket with whatever you have.
- If the user describes obvious physical damage (cracked screen, shattered, fell, broken casing, water damage), do NOT ask "what have you tried" — physical damage has no troubleshooting. Move directly to ticket creation.
- If the user sounds frustrated or has repeated their issue, stop asking and create the ticket immediately with the info you have.
- If you already have 3 out of 4 required pieces of information, create the ticket. Do NOT delay for the last piece.

TICKET CREATION SIGNAL:
Once you have collected enough information to create a useful support ticket, respond with EXACTLY this format at the END of your message:

[CREATE_TICKET]
issue_type: <hardware_failure|software_issue|integration_issue|access_issue|general_issue>
severity: <critical|high|medium|low>
device_serial: <serial or null — use null for software/dashboard/login issues; only collect a serial for hardware issues>
summary: <one-line title under 80 chars>
description: <structured description with: user issue, when it started, what they tried, any error messages>
[/CREATE_TICKET]

Before the ticket block, write a natural message to the user like: "Let me create a support ticket for this issue."

Severity guidelines:
- critical: device completely dead, safety concern, entire fleet affected
- high: device damaged, major feature broken, multiple vehicles affected
- medium: single feature not working, intermittent issue, one vehicle affected
- low: minor annoyance, cosmetic issue, workaround exists

Do NOT include the [CREATE_TICKET] block until you have the minimum required information: what the issue is and one identifying detail (device serial for hardware, software name for software). The remaining details (when it started, what they tried) are helpful but not required — if the user hasn't provided them after 2-3 messages, create the ticket with what you have.
If the user has reported the same unresolved issue two or more times after your suggestions, stop suggesting and proceed directly to escalation collection.
Do NOT instruct users to open device casings, perform physical repairs, or bypass safety mechanisms.
Do NOT provide legal interpretations of warranty terms, liability, or regulatory compliance.
Do NOT speculate about unreleased features, upcoming firmware versions, or unannounced product changes.

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


# Confidence tiers (top result similarity). Tuned for text-embedding-3-small + small chunks.
TIER_HIGH_MIN = 0.60
TIER_LOW_MIN = 0.40
# Include KB chunks in RAG context when similarity meets the LOW tier floor.
CONTEXT_CHUNK_MIN_SIMILARITY = TIER_LOW_MIN

REFORMULATION_SYSTEM_PROMPT = """Given the following conversation and a follow-up input, rephrase the follow-up into a standalone question that can be understood without the conversation history.
Do NOT answer the question.
Do NOT include explanations, steps, or troubleshooting advice.
Output ONLY the rephrased standalone question in one sentence.
If the follow-up is already a standalone question, return it as-is."""

class ChatService:
    def __init__(
        self,
        conversation_repository: ConversationRepository,
        kb_service: KBService,
        openai_client: AsyncOpenAI,
        openai_chat_model: str,
        ticket_service: TicketService,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.kb_service = kb_service
        self.openai_client = openai_client
        self.openai_chat_model = openai_chat_model
        self.ticket_service = ticket_service

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

    async def _reformulate_query(self, message: str, history: list[dict[str, str]]) -> str:
        """Condense a follow-up message into a standalone question using conversation history."""
        if not history:
            return message

        recent = history[-6:]
        chat_log = ""
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"][:200] if msg["role"] == "assistant" else msg["content"]
            chat_log += f"{role}: {content}\n"

        try:
            response = await self.openai_client.chat.completions.create(
                model=self.openai_chat_model,
                messages=[
                    {"role": "system", "content": REFORMULATION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Conversation:\n{chat_log}\nFollow-up input: {message}\nStandalone question:"
                        ),
                    },
                ],
                max_tokens=80,
                temperature=0,
            )
            reformulated = (response.choices[0].message.content or "").strip()
            if not reformulated:
                return message

            if len(reformulated) > 200 or "\n" in reformulated:
                logger.warning(
                    "[CHAT] Reformulation invalid (len=%d, newlines=%s), falling back to original",
                    len(reformulated),
                    "\n" in reformulated,
                )
                return message

            return reformulated

        except Exception as exc:
            logger.warning("[CHAT] Reformulation failed: %s", exc)
            return message

    async def _call_openai(self, messages: list[dict[str, str]]) -> str:
        """Send messages to OpenAI and return the response text."""
        response = await self.openai_client.chat.completions.create(
            model=self.openai_chat_model,
            messages=messages,
            max_tokens=500,
        )
        choice = response.choices[0].message
        return choice.content or ""

    def _parse_ticket_block(self, text: str) -> tuple[str, dict[str, str] | None]:
        """Extract [CREATE_TICKET] block from AI response. Returns (cleaned_text, ticket_data or None)."""
        pattern = r"\[CREATE_TICKET\]\s*(.*?)\s*\[/CREATE_TICKET\]"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            return text, None

        block = match.group(1)
        cleaned = text[: match.start()].rstrip()
        lines = [ln.rstrip() for ln in block.strip().splitlines()]
        data: dict[str, str] = {}
        i = 0
        while i < len(lines):
            line = lines[i]
            if ":" not in line:
                i += 1
                continue
            key, _, rest = line.partition(":")
            key = key.strip()
            val = rest.strip()
            if key == "description":
                desc_parts = [val] if val else []
                i += 1
                while i < len(lines):
                    desc_parts.append(lines[i])
                    i += 1
                data["description"] = "\n".join(desc_parts).strip()
                break
            data[key] = val
            i += 1

        return cleaned, data if data else None

    async def _apply_ticket_flow(self, cid_int: int, user_email: str, ai_response: str) -> str:
        """Strip ticket block from AI text; if valid, create Jira ticket and append confirmation."""
        cleaned, ticket_data = self._parse_ticket_block(ai_response)
        if not ticket_data:
            return ai_response

        required = ("issue_type", "severity", "summary", "description")
        if not all(ticket_data.get(k) for k in required):
            logger.warning("[CHAT] Ticket block present but missing required fields: %s", ticket_data)
            return cleaned

        ds_raw = (ticket_data.get("device_serial") or "").strip()
        parsed_serial: str | None
        if not ds_raw or ds_raw.lower() in ("null", "none"):
            parsed_serial = None
        else:
            parsed_serial = ds_raw

        issue_type = ticket_data["issue_type"].strip()
        severity = ticket_data["severity"].strip()
        logger.info("[CHAT] Ticket creation triggered — issue_type=%s, severity=%s", issue_type, severity)

        try:
            ticket_request = TicketCreateRequest(
                conversation_id=cid_int,
                user_email=user_email,
                device_serial=parsed_serial,
                issue_type=issue_type,
                severity=severity,
                summary=ticket_data["summary"].strip()[:500],
                description=ticket_data["description"].strip()[:8000],
            )
            ticket_response = await self.ticket_service.create_ticket(ticket_request)
        except JiraAPIError as exc:
            logger.warning("[CHAT] Jira ticket creation failed: %s", exc)
            return cleaned + (
                "\n\nI attempted to create a support ticket but the ticketing system is temporarily unavailable. "
                "Please contact Infleet support directly and reference this conversation."
            )

        if parsed_serial:
            await self.conversation_repository.update_device_serial(cid_int, parsed_serial)

        await self.conversation_repository.update_status(cid_int, "escalated")
        logger.info(
            "[CHAT] Ticket created — %s (%s)",
            ticket_response.jira_ticket_id,
            ticket_response.jira_ticket_url,
        )
        return (
            cleaned
            + f"\n\nYour support ticket has been created. Ticket number: {ticket_response.jira_ticket_id}. "
            + f"You can track it at: {ticket_response.jira_ticket_url}"
        )

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

        history = await self._history_openai_dicts(cid_int)
        if history:
            kb_query = await self._reformulate_query(message, history)
        else:
            kb_query = message
        logger.info('[CHAT] Original: "%s"', message)
        logger.info('[CHAT] Reformulated: "%s"', kb_query)

        # --- KB search (embedding uses reformulated query only) ---
        try:
            kb_results = await self.kb_service.search(kb_query)
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
        # --- Build OpenAI messages based on tier (history already loaded; uses original message) ---

        if confidence_tier == "none":
            # No KB context — let the AI respond using system prompt + conversation history
            openai_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                *history,
                {"role": "user", "content": message},
            ]
            ai_response = await self._call_openai(openai_messages)
            sources: list[str] = []

            final_response = await self._apply_ticket_flow(cid_int, conv.user_email, ai_response)

            await self.conversation_repository.add_message(
                cid_int, role="assistant", content=final_response, confidence_tier="none"
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
                message=final_response,
                confidence_tier=confidence_tier,
                sources=sources,
            )

        # --- HIGH or LOW tier — build context and call OpenAI ---
        context_chunks = self._context_chunks(kb_results)
        context_str = self._context_string(context_chunks)
        sources = self._sources_from_chunks(context_chunks)
        top = kb_results[0]

        kb_user_content = (
            f"Context from knowledge base:\n\n{context_str}\n\n"
            f"INSTRUCTION: Answer the following question using ONLY the context above. "
            f"If the context does not contain a clear, direct answer to the question, "
            f"state that the documentation does not cover this topic. "
            f"Do NOT supplement with your own knowledge.\n\n"
            f"IMPORTANT: If the conversation history shows you are in an escalation flow "
            f"(you have been asking the user about their issue, device, timeline, or troubleshooting attempts across previous messages), "
            f"IGNORE the knowledge base context above entirely. Continue the escalation collection from your system prompt. "
            f"Do NOT respond with documentation disclaimers. If you have enough information, include the [CREATE_TICKET] block.\n\n"
            f"User question: {message}"
        )
        openai_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": kb_user_content},
        ]
        raw_ai = await self._call_openai(openai_messages)
        ai_response = await self._apply_ticket_flow(cid_int, conv.user_email, raw_ai)

        if confidence_tier == "low":
            await self.conversation_repository.add_message(
                cid_int, role="assistant", content=ai_response, confidence_tier="low"
            )
        else:
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