import logging

from app.services.llm.base import LLMClient

logger = logging.getLogger(__name__)


class DirectAnswerAgent:
    """Answer stable engineering questions without running deep research."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def answer(self, query: str) -> str:
        """Generate a concise answer for a direct-route query."""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Query must not be empty.")

        prompt = (
            "Answer the following software engineering question using stable "
            "technical knowledge.\n\n"
            "Requirements:\n"
            "- Be concise and technically accurate.\n"
            "- Explain the core concept before adding details.\n"
            "- Use a small example when it improves understanding.\n"
            "- Do not invent citations or claim that sources were searched.\n"
            "- If the question requires current information or extensive "
            "comparison, state that deep research is required.\n\n"
            f"User question: {normalized_query}"
        )

        logger.info("Generating direct answer")

        response = await self._llm_client.generate_text(
            prompt,
            max_tokens=500,
        )

        answer = response.strip()

        if not answer:
            raise RuntimeError("LLM provider returned an empty direct answer.")

        logger.info("Direct answer generated")

        return answer
