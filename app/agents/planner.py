import logging

from app.schemas.planner import ResearchPlan
from app.services.llm.base import LLMClient

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Create structured research plans for deep-research requests."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def create_plan(self, query: str) -> ResearchPlan:
        """Generate a validated research plan for a user query."""

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("Query must not be empty.")

        prompt = (
            "Create a focused research plan for the following software "
            "engineering request.\n\n"
            "Requirements:\n"
            "- Define one clear research goal.\n"
            "- Produce between 2 and 6 distinct sub-questions.\n"
            "- Produce between 2 and 6 independent research tasks.\n"
            "- Each task must have a concise title, a search-ready query, "
            "and a short rationale.\n"
            "- Ensure every sub-question is covered by at least one task.\n"
            "- Avoid overlapping tasks and duplicate search queries.\n"
            "- Create an ordered report outline with 3 to 8 sections.\n"
            "- Use engineering-focused sections such as technical background, "
            "architecture, trade-offs, reliability, performance, security, "
            "and recommendations when relevant.\n"
            "- Focus on standards and current adoption only when relevant.\n"
            "- Do not answer the user's question yet.\n\n"
            f"User request: {normalized_query}"
        )

        logger.info("Creating research plan")

        plan = await self._llm_client.generate_structured(
            prompt,
            ResearchPlan,
            max_tokens=1200,
        )

        logger.info(
            "Research plan created | sub_question_count=%s | task_count=%s | section_count=%s",
            len(plan.sub_questions),
            len(plan.tasks),
            len(plan.report_outline),
        )

        return plan
