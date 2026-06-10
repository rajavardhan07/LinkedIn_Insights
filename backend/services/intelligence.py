import os
import json
import asyncio
from typing import Any
from pydantic import BaseModel, Field

from langchain_mistralai import ChatMistralAI
from utils.logger import get_logger

logger = get_logger(__name__)

# Max attempts before giving up and storing fallback
_MAX_RETRIES = 3
_RETRY_DELAY = 5  # seconds (doubles each retry)

class AnalysisSchema(BaseModel):
    """Structured output expected from Mistral AI."""
    executive_snapshot: str = Field(description="A 1-sentence executive summary of the post.")
    content_classification: str = Field(description="The primary classification or topic (e.g. CSR, Product Launch, Thought Leadership).")
    strategic_intent: str = Field(description="What the company is trying to achieve with this post.")
    engagement_analysis: str = Field(description="Why this post did or did not perform well based on the engagement metrics.")
    creative_breakdown: str = Field(description="Analysis of the media, text, tone, and formatting.")
    competitive_insight: str = Field(description="What competitors can learn from this post.")
    recommended_action: str = Field(description="Actionable takeaway for marketing teams.")
    alert_tag: str = Field(description="Must be exactly one of: HIGH PRIORITY, MEDIUM, LOW")
    trend_signal: str = Field(description="Any emerging market trends signaled by this post.")

async def analyze_post(post_data: dict[str, Any]) -> dict[str, Any]:
    """Uses Mistral AI to analyze a LinkedIn post and generate a 9-section intelligence report."""
    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    mistral_model = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
    
    if not mistral_api_key:
        logger.error("MISTRAL_API_KEY is not set. Returning empty analysis.")
        return get_fallback_analysis()

    # Initialize Mistral AI Model
    llm = ChatMistralAI(
        model=mistral_model, 
        mistral_api_key=mistral_api_key,
        temperature=0.2
    )
    
    # Enforce strict output format
    structured_llm = llm.with_structured_output(AnalysisSchema)
    
    company_name = post_data.get('company', 'Unknown')
    is_hartford = "Hartford" in company_name
    
    target_role = "our OWN company's" if is_hartford else f"our competitor {company_name}'s"
    
    insight_instructions = (
        "**What we did well**:\n       - Point 1...\n       \n       **Areas for Improvement**:\n       - Point 1..."
        if is_hartford else
        "**What they're doing better**:\n       - Point 1...\n       \n       **Gap for The Hartford India**:\n       - Point 1..."
    )

    # Build the post content block — use media_description as fallback when text is empty
    post_text = (post_data.get('text') or '').strip()
    media_desc = (post_data.get('media_description') or '').strip()
    post_type  = post_data.get('post_type', 'text')

    if not post_text and media_desc:
        content_block = f"[No caption text — this is a {post_type} post]\nMedia description: {media_desc}"
    elif not post_text:
        content_block = f"[No caption text — this is a {post_type} post with no media description available]"
    else:
        content_block = post_text

    prompt = f"""
    You are the Lead Competitive Intelligence Analyst for "The Hartford India", an enterprise GCC.
    Analyze the following LinkedIn post from {target_role} recent LinkedIn activity.
    
    CRITICAL FORMATTING RULES:
    1. executive_snapshot: Write aggressively. Use *italics* and **bold** for emphasis. End with exactly: "This matters to us because..."
    2. engagement_analysis: Highlight why the post worked. Use bolding (e.g. "**High comment quality**:").
    3. creative_breakdown: Use bullet points wrapped in bold: "- **Hook**: ... \\n- **Tone**: ... \\n- **Format**: ..."
    4. competitive_insight: You MUST split this into exactly two sections:
       {insight_instructions}
    5. recommended_action: Provide exactly 3 numbered actions formatted like this (the UI regex relies on this exact spacing!):
       "1. **Action Title**:
          - **Post idea**: ...
          - **Format**: ..."
    6. trend_signal: Start exactly with "**Emerging pattern**:" and explain the broader GCC trend.
    
    POST DETAILS:
    Author: {post_data.get('author_name', 'Unknown')}
    Text: {content_block}
    Engagement: Likes: {post_data.get('likes', 0)}, Comments: {post_data.get('comments', 0)}, Shares: {post_data.get('shares', 0)}
    Metrics: Rate: {post_data.get('engagement_rate', 0.0)}%, Score: {post_data.get('engagement_score', 0)}
    Post Type: {post_type}
    Media: {media_desc or 'None'}
    """

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            logger.info(f"🤖 Mistral analysis attempt {attempt}/{_MAX_RETRIES}...")
            result = await structured_llm.ainvoke(prompt)

            if result is None:
                logger.warning(f"Mistral returned None on attempt {attempt}.")
                raise ValueError("Mistral returned None")

            # Convert schema to dict
            analysis_dict = result.dict() if hasattr(result, "dict") else result.model_dump()
            analysis_dict["raw_analysis_json"] = json.dumps(analysis_dict)
            return analysis_dict

        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                wait = _RETRY_DELAY * (2 ** (attempt - 1))  # 5s, 10s, 20s
                logger.warning(f"Attempt {attempt} failed ({e}). Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"All {_MAX_RETRIES} attempts failed. Last error: {last_error}")

    return get_fallback_analysis()

def get_fallback_analysis() -> dict[str, Any]:
    """Returns an empty/failed structure when the AI fails to generate one."""
    return {
        "executive_snapshot": "Analysis failed or API key missing.",
        "content_classification": "UNKNOWN",
        "strategic_intent": "N/A",
        "engagement_analysis": "N/A",
        "creative_breakdown": "N/A",
        "competitive_insight": "N/A",
        "recommended_action": "N/A",
        "alert_tag": "LOW",
        "trend_signal": "N/A",
        "raw_analysis_json": "{}"
    }

async def draft_counter_post(competitor_post: dict[str, Any], analysis: Any) -> str:
    """Generates a LinkedIn counter-post for The Hartford India based on competitor insight."""
    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    mistral_model = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
    
    if not mistral_api_key:
        return "⚠️ MISTRAL_API_KEY is not set. Cannot format counter-post."

    llm = ChatMistralAI(
        model=mistral_model, 
        mistral_api_key=mistral_api_key,
        temperature=0.7
    )
    
    comp_company = competitor_post.get("company", "A competitor")
    comp_text = competitor_post.get("text", "")
    action = getattr(analysis, "recommended_action", "") if analysis else "Capitalize on the competitor's post engagement."
    insight = getattr(analysis, "competitive_insight", "") if analysis else "The competitor is gaining traction with this topic."

    prompt = f"""
    Act as the Lead Brand Manager for "The Hartford India", an enterprise Global Capability Center (GCC).
    A competitor ({comp_company}) recently made a successful LinkedIn post:
    
    COMPETITOR POST:
    "{comp_text}"
    
    COMPETITIVE INSIGHT:
    "{insight}"
    
    RECOMMENDED ACTION:
    "{action}"
    
    Your task: Draft a powerful, original LinkedIn post for "The Hartford India" that capitalizes on this same trending topic or tackles the recommended action.
    Make it highly engaging, professional but modern, and match The Hartford's voice (innovation, inclusion, and excellence).
    Include 2-3 paragraphs, a strong hook, and appropriate emojis and hashtags. Do not copy the competitor directly—create a counter-narrative or a superior viewpoint.
    Return ONLY the drafted LinkedIn post copy.
    """

    try:
        logger.info("🤖 Drafting counter-post via Mistral AI...")
        response = await llm.ainvoke(prompt)
        return response.content
    except Exception as e:
        logger.error(f"Failed to draft counter-post: {e}")
        return f"⚠️ Failed to draft counter-post: {e}"
