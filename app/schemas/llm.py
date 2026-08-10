from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    """Count provider-reported tokens consumed by one research run."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    request_count: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        """Return the combined provider-reported token count."""

        return self.input_tokens + self.output_tokens
