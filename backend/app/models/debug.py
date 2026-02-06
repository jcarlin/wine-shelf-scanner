"""
Debug response models for pipeline introspection.

These models are only included when ?debug=true is passed to /scan.
"""

from typing import Optional

from pydantic import BaseModel, Field


class PipelineStats(BaseModel):
    """
    Pipeline breakdown showing where bottles are lost at each stage.

    This helps debug why some bottles aren't being matched.
    """
    bottles_detected: int = Field(..., description="Bottles found by Vision API object detection")
    bottles_with_text: int = Field(..., description="Bottles with OCR text assigned")
    bottles_empty: int = Field(..., description="Bottles with no OCR text")
    fuzzy_matched: int = Field(..., description="Direct high-confidence DB matches (skipped LLM)")
    llm_validated: int = Field(..., description="Matches validated/identified by LLM")
    unmatched_count: int = Field(..., description="Bottles sent to Claude Vision fallback")
    vision_attempted: int = Field(..., description="Claude Vision calls made")
    vision_identified: int = Field(..., description="Wines identified by Claude Vision")
    vision_error: Optional[str] = Field(None, description="Error if Claude Vision failed")
    llm_rescue_attempted: int = Field(0, description="Bottles/orphans sent to LLM batch rescue")
    llm_rescue_identified: int = Field(0, description="Wines identified by LLM batch rescue")
    final_results: int = Field(..., description="Total wines in response results array")


class FuzzyMatchScores(BaseModel):
    """Individual scores from fuzzy matching algorithms."""
    ratio: float = Field(..., description="Overall character similarity (0-1)")
    partial_ratio: float = Field(..., description="Best substring match (0-1)")
    token_sort_ratio: float = Field(..., description="Word-order-independent match (0-1)")
    phonetic_bonus: float = Field(..., description="Phonetic similarity bonus (0-0.1)")
    weighted_score: float = Field(..., description="Final weighted score (0-1)")


class FuzzyMatchDebug(BaseModel):
    """Debug info for fuzzy match step."""
    candidate: Optional[str] = Field(None, description="Matched wine name from DB")
    scores: Optional[FuzzyMatchScores] = Field(None, description="Individual algorithm scores")
    rating: Optional[float] = Field(None, description="Rating of matched wine")


class LLMValidationDebug(BaseModel):
    """Debug info for LLM validation step."""
    is_valid_match: bool = Field(..., description="Whether LLM confirmed the match")
    wine_name: Optional[str] = Field(None, description="Wine name from LLM")
    confidence: float = Field(..., description="LLM confidence (0-1)")
    reasoning: str = Field(..., description="LLM's explanation")


class DebugPipelineStep(BaseModel):
    """Debug info for a single OCR text through the pipeline."""
    raw_text: str = Field(..., description="Original OCR text")
    normalized_text: str = Field(..., description="Text after cleanup")
    bottle_index: int = Field(..., description="Which bottle this belongs to")
    fuzzy_match: Optional[FuzzyMatchDebug] = Field(None, description="Fuzzy match results")
    llm_validation: Optional[LLMValidationDebug] = Field(None, description="LLM validation results")
    final_result: Optional[dict] = Field(None, description="Final result {wine_name, confidence, source}")
    step_failed: Optional[str] = Field(None, description="Step where processing failed")
    included_in_results: bool = Field(..., description="Whether this made it to results")


class SimplifiedStepResult(BaseModel):
    """Simplified step result for easy display."""
    ocr_text: str = Field(..., description="OCR text (truncated)")
    status: str = Field(..., description="✓ matched, ✗ failed, or reason")
    result: Optional[str] = Field(None, description="Final wine name if matched")


class DebugData(BaseModel):
    """Complete debug information for a scan."""
    pipeline_steps: list[DebugPipelineStep] = Field(
        default_factory=list,
        description="Debug info for each OCR text processed"
    )
    total_ocr_texts: int = Field(..., description="Total OCR text blocks found")
    bottles_detected: int = Field(..., description="Number of bottles detected")
    texts_matched: int = Field(..., description="OCR texts that matched a wine")
    llm_calls_made: int = Field(..., description="Number of LLM API calls")
    pipeline_stats: Optional[PipelineStats] = Field(
        None,
        description="Breakdown of where bottles were lost at each pipeline stage"
    )

    def get_summary(self) -> list[SimplifiedStepResult]:
        """Get a simplified summary of each step for easy display."""
        summary = []
        for step in self.pipeline_steps:
            # Truncate OCR text for display
            ocr = step.normalized_text[:50] + "..." if len(step.normalized_text) > 50 else step.normalized_text

            # Determine status
            if step.included_in_results:
                status = "✓ matched"
                result = step.final_result.get("wine_name") if step.final_result else None
            elif step.step_failed:
                status = f"✗ {step.step_failed}"
                result = None
            else:
                status = "✗ no match"
                result = None

            summary.append(SimplifiedStepResult(
                ocr_text=ocr,
                status=status,
                result=result
            ))
        return summary

    def format_summary_table(self) -> str:
        """Format a simple text table showing each OCR text and its status."""
        lines = [
            f"Pipeline Summary: {self.texts_matched}/{self.total_ocr_texts} matched, {self.llm_calls_made} LLM calls",
            "-" * 80,
            f"{'OCR Text':<40} | {'Status':<15} | {'Result':<20}",
            "-" * 80,
        ]

        for step in self.pipeline_steps:
            # Truncate OCR text
            ocr = step.normalized_text[:38] + ".." if len(step.normalized_text) > 40 else step.normalized_text

            # Status
            if step.included_in_results:
                status = "✓ matched"
            elif step.step_failed:
                status = f"✗ {step.step_failed[:13]}"
            else:
                status = "✗ no match"

            # Result
            result = ""
            if step.final_result:
                result = step.final_result.get("wine_name", "")[:20]

            lines.append(f"{ocr:<40} | {status:<15} | {result:<20}")

        lines.append("-" * 80)
        return "\n".join(lines)
