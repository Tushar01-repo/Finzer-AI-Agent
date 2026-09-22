import json
from dataclasses import dataclass
from typing import Any

from app.clients.llm_router import LLMRouter
from app.config.settings import settings


@dataclass
class ArticleAnalysis:
    is_valid_article: bool
    relevance_score: float
    is_relevant: bool
    relevance_reason: str
    summary: str | None
    key_facts: list[str]
    companies_mentioned: list[str]
    market_impact: str | None
    raw_response: dict[str, Any]


# class ArticleAnalyzer:
#     """
#     Analyzes extracted articles using the Finzer LLM service.

#     Responsibilities:
#     - Validate whether extracted content represents a real article
#     - Score relevance against the feed
#     - Generate a concise factual summary
#     - Extract key facts
#     - Extract explicitly named companies
#     - Determine market impact when supported by the article
#     - Retry transient LLM connection/time-out failures
#     """

#     def __init__(
#         self,
#         relevance_threshold: float | None = None,
#     ):
#         self.relevance_threshold = float(
#             relevance_threshold
#             if relevance_threshold is not None
#             else settings.ARTICLE_RELEVANCE_THRESHOLD
#         )
#         self.max_article_chars = settings.LLM_MAX_ARTICLE_CHARS
#         self.llm_client = LLMRouter()
#         self.model = self.llm_client.model

#     def analyze(
#         self,
#         *,
#         feed_id: str,
#         feed_target: str,
#         feed_description: str,
#         title: str,
#         content: str,
#         source: str | None = None,
#         published_at: str | None = None,
#     ) -> ArticleAnalysis:
#         """
#         Analyze one article using the configured LLM service.
#         """

#         if not content or not content.strip():
#             raise ValueError(
#                 "Article content cannot be empty."
#             )

#         system_prompt = self._build_system_prompt()

#         user_prompt = self._build_user_prompt(
#             feed_id=feed_id,
#             feed_target=feed_target,
#             feed_description=feed_description,
#             title=title,
#             source=source,
#             published_at=published_at,
#             content=content,
#         )

#         response_data = self.llm_client.chat_completion(
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": user_prompt},
#             ],
#             max_tokens=settings.BEDROCK_LLM_MAX_TOKENS,
#             temperature=settings.BEDROCK_LLM_TEMPERATURE,
#         )

#         try:
#             model_output = response_data["choices"][0]["message"]["content"]
#         except (KeyError, IndexError, TypeError) as exc:
#             raise RuntimeError(
#                 f"Unexpected LLM response format: {response_data}"
#             ) from exc

#         parsed = self._parse_json_response(
#             model_output
#         )

#         return self._build_analysis(
#             parsed
#         )

#     def _build_system_prompt(
#         self,
#     ) -> str:
#         return """
# You are Finzer's financial news classifier.

# Evaluate one news article against the supplied Feed Target.

# The Feed Target may be:
# - a company or stock
# - an ETF or mutual fund
# - an index
# - a commodity
# - a sector or industry
# - a country/economy
# - a macroeconomic topic
# - another finance-related target

# IMPORTANT:
# - Feed Target is the real subject being evaluated.
# - Feed Description gives useful financial context.
# - Feed ID is only an internal identifier.
# - Never infer meaning from Feed ID.

# ARTICLE VALIDITY

# Validity and relevance are separate.

# Set is_valid_article=true if the content is a coherent news, business,
# market, economic, regulatory, or financial article.

# Set is_valid_article=false only for broken extraction, login pages,
# navigation, ads, access-denied pages, cookie/privacy UI, or other
# non-article content.

# A valid article may still be irrelevant.

# FINANCIAL RELEVANCE

# Relevance may be DIRECT or INDIRECT.

# DIRECT means the article materially discusses the Feed Target itself.

# Common direct financial events:
# - earnings, revenue, profit, margins, guidance
# - investment, capex, debt, fundraising, refinancing
# - acquisition, merger, divestiture
# - partnership, joint venture, contract, order
# - product launch, product development, technology
# - production, capacity expansion, market share
# - management or board changes
# - restructuring or layoffs
# - regulation, taxation, legal action
# - cybersecurity or operational disruption
# - analyst rating or shareholding changes
# - target-specific share-price or market movement

# INDIRECT means the article mainly concerns an external development that has
# a clear and supported financial connection to the Feed Target.

# Common indirect factors:
# - interest rates
# - inflation
# - currency movement
# - commodity or raw-material prices
# - government policy
# - regulation or taxation
# - tariffs or sanctions
# - geopolitical events
# - supply-chain disruption
# - industry demand
# - major competitor actions
# - major customer or supplier developments
# - economic growth or consumer demand

# For INDIRECT relevance:
# - use only the article and Feed Description
# - do not invent business exposure
# - require an explainable financial connection

# TARGET MENTION RULE

# A simple target-name mention is not enough.

# But if the article is substantially about the Feed Target and contains a
# recognized financial/business event, it has DIRECT relevance even when the
# article does not contain earnings, valuation, or accounting data.

# DIRECT EVENT SCORING GUIDE

# If the article is substantially about the Feed Target, use these ranges:

# 0.85 - 1.00
# Major earnings/results, large acquisition, major financing, major regulatory
# action, major strategic investment, or another highly material development.

# 0.70 - 0.89
# Meaningful investment, contract, partnership, product launch, capacity
# expansion, management leadership change, legal/regulatory development,
# material analyst/shareholding event, or other strong direct development.

# 0.55 - 0.75
# Target-specific share-price movement, moderate operational development,
# smaller management change, product update, routine but useful market event,
# or other directly relevant financial information.

# Do NOT assign 0.00 to an article substantially about the Feed Target if it
# contains a recognized financial/business event.

# INDIRECT EVENT SCORING GUIDE

# 0.65 - 0.85
# External event with a strong, explicit, and material connection to the target.

# 0.40 - 0.64
# Plausible and meaningful indirect connection, but materiality is moderate.

# 0.15 - 0.39
# Weak or contextual connection.

# 0.00 - 0.14
# No meaningful financial connection.

# RELEVANCE TYPE

# Use exactly one:
# - "direct"
# - "indirect"
# - "none"

# FINANCIAL EVENT TYPES

# Use only these values:

# - earnings
# - investment
# - financing
# - debt
# - mna
# - partnership
# - contract
# - product
# - capacity
# - management_change
# - restructuring
# - regulation
# - legal
# - geopolitical
# - commodity
# - macro
# - supply_chain
# - competition
# - market_movement
# - shareholding
# - cybersecurity
# - other

# Use [] if none apply.

# IMPORTANT EXAMPLES

# Example 1:
# Target: HDFC Bank
# Article: HDFC Bank board approves MD/CEO nominees.
# Result:
# - direct relevance
# - financial_event_types includes management_change
# - relevance_score should normally be at least 0.65

# Example 2:
# Target: HDFC Bank
# Article: HDFC Bank share price rises 2%.
# Result:
# - direct relevance
# - financial_event_types includes market_movement
# - relevance_score should normally be around 0.55-0.75 depending on article depth

# Example 3:
# Target: HDFC Bank
# Article: Consumer loses money in fraud and one transaction used an HDFC account.
# Result:
# - usually weak or no relevance unless the article describes a bank-specific
#   security failure, regulatory issue, operational issue, or material pattern

# Example 4:
# Target: Reliance Industries
# Article: Crude-oil supply changes.
# Result:
# - only indirect relevance if Feed Description establishes material refining,
#   petrochemical, or energy exposure and the article supports that connection

# SUMMARY

# Provide a concise factual summary.
# Preserve important names, numbers, dates, financial events, and market facts.
# Do not speculate.

# KEY FACTS

# Return complete factual statements.
# Avoid duplicates.

# COMPANIES

# companies_mentioned must contain explicitly named companies or organizations.
# Avoid duplicates.

# MARKET IMPACT

# Describe potential impact only when supported.
# Do not invent exact price predictions.

# IMPACT DIRECTION

# Use exactly one:
# - "positive"
# - "negative"
# - "mixed"
# - "neutral"
# - "unclear"

# IMPACT HORIZON

# Use exactly one:
# - "immediate"
# - "short_term"
# - "medium_term"
# - "long_term"
# - "unclear"

# OUTPUT

# Return ONLY valid JSON with exactly this structure:

# {
#   "is_valid_article": true,
#   "relevance_score": 0.0,
#   "is_relevant": false,
#   "relevance_type": "none",
#   "financial_event_types": [],
#   "relevance_reason": "",
#   "summary": "",
#   "key_facts": [],
#   "companies_mentioned": [],
#   "market_impact": "",
#   "impact_direction": "unclear",
#   "impact_horizon": "unclear"
# }

# Do not return markdown or code fences.

# is_relevant should normally be true when relevance_score >= 0.55.
# The application applies the final threshold independently, so provide an
# honest score.
# """.strip()

#     def _build_user_prompt(
#         self,
#         *,
#         feed_id: str,
#         feed_target: str,
#         feed_description: str,
#         title: str,
#         content: str,
#         source: str | None,
#         published_at: str | None,
#     ) -> str:
#         content = self._truncate_content(content)

#         return f"""
# FEED TARGET:
# {feed_target}

# FEED DESCRIPTION:
# {feed_description}

# FEED ID:
# {feed_id}

# ARTICLE TITLE:
# {title}

# SOURCE:
# {source or "Unknown"}

# PUBLISHED AT:
# {published_at or "Unknown"}

# ARTICLE:
# {content}

# Return the required JSON only.
# """.strip()

#     def _truncate_content(
#         self,
#         content: str,
#     ) -> str:
#         """
#         Limit article size to keep Qwen 3B inference fast and predictable.

#         Character-based truncation is used intentionally here because the
#         current service does not expose a tokenizer to this client.
#         """
#         if len(content) <= self.max_article_chars:
#             return content

#         return (
#             content[: self.max_article_chars]
#             + "\n\n[ARTICLE TRUNCATED]"
#         )

#     def _parse_json_response(
#         self,
#         model_output: str,
#     ) -> dict[str, Any]:
#         cleaned = model_output.strip()

#         # Defensive handling in case the model accidentally returns
#         # a markdown JSON code block despite instructions.
#         if cleaned.startswith("```"):
#             cleaned = cleaned.strip("`")

#             if cleaned.lower().startswith(
#                 "json"
#             ):
#                 cleaned = cleaned[
#                     4:
#                 ].strip()

#         try:
#             parsed = json.loads(
#                 cleaned
#             )

#         except json.JSONDecodeError as exc:
#             raise RuntimeError(
#                 "LLM returned invalid JSON.\n"
#                 f"Raw output:\n{model_output}"
#             ) from exc

#         if not isinstance(
#             parsed,
#             dict,
#         ):
#             raise RuntimeError(
#                 "LLM JSON response must be "
#                 "a JSON object."
#             )

#         return parsed

#     def _build_analysis(
#         self,
#         parsed: dict[str, Any],
#     ) -> ArticleAnalysis:
#         score = self._normalize_score(
#             parsed.get(
#                 "relevance_score",
#                 0.0,
#             )
#         )

#         is_valid = self._normalize_bool(
#             parsed.get(
#                 "is_valid_article",
#                 False,
#             )
#         )

#         relevance_type = self._normalize_choice(
#             parsed.get(
#                 "relevance_type",
#                 "none",
#             ),
#             allowed={
#                 "direct",
#                 "indirect",
#                 "none",
#             },
#             default="none",
#         )

#         event_types = self._normalize_allowed_string_list(
#             parsed.get(
#                 "financial_event_types",
#                 [],
#             ),
#             allowed={
#                 "earnings",
#                 "investment",
#                 "financing",
#                 "debt",
#                 "mna",
#                 "partnership",
#                 "contract",
#                 "product",
#                 "capacity",
#                 "management_change",
#                 "restructuring",
#                 "regulation",
#                 "legal",
#                 "geopolitical",
#                 "commodity",
#                 "macro",
#                 "supply_chain",
#                 "competition",
#                 "market_movement",
#                 "shareholding",
#                 "cybersecurity",
#                 "other",
#             },
#         )

#         impact_direction = self._normalize_choice(
#             parsed.get(
#                 "impact_direction",
#                 "unclear",
#             ),
#             allowed={
#                 "positive",
#                 "negative",
#                 "mixed",
#                 "neutral",
#                 "unclear",
#             },
#             default="unclear",
#         )

#         impact_horizon = self._normalize_choice(
#             parsed.get(
#                 "impact_horizon",
#                 "unclear",
#             ),
#             allowed={
#                 "immediate",
#                 "short_term",
#                 "medium_term",
#                 "long_term",
#                 "unclear",
#             },
#             default="unclear",
#         )

#         # Repair only obvious structural contradictions from a small model.
#         # We do NOT boost scores just because a company name appears.
#         if relevance_type == "direct" and event_types:
#             score = max(
#                 score,
#                 self._direct_event_floor(
#                     event_types
#                 ),
#             )

#         if relevance_type == "none":
#             # Keep "none" conservative. Do not let a malformed high score
#             # accidentally promote a clearly non-relevant classification.
#             score = min(
#                 score,
#                 0.49,
#             )

#         parsed["relevance_score"] = score
#         parsed["relevance_type"] = relevance_type
#         parsed["financial_event_types"] = event_types
#         parsed["impact_direction"] = impact_direction
#         parsed["impact_horizon"] = impact_horizon

#         is_relevant = (
#             is_valid
#             and score
#             >= self.relevance_threshold
#         )

#         # Keep raw response consistent with application decision.
#         parsed["is_relevant"] = is_relevant

#         summary = self._normalize_optional_string(
#             parsed.get(
#                 "summary"
#             )
#         )

#         market_impact = self._normalize_optional_string(
#             parsed.get(
#                 "market_impact"
#             )
#         )

#         relevance_reason = str(
#             parsed.get(
#                 "relevance_reason",
#                 "",
#             )
#         ).strip()

#         key_facts = self._normalize_string_list(
#             parsed.get(
#                 "key_facts",
#                 [],
#             )
#         )

#         companies = self._normalize_string_list(
#             parsed.get(
#                 "companies_mentioned",
#                 [],
#             )
#         )

#         if not is_relevant:
#             summary = None
#             key_facts = []
#             market_impact = None

#         return ArticleAnalysis(
#             is_valid_article=is_valid,
#             relevance_score=score,
#             is_relevant=is_relevant,
#             relevance_reason=relevance_reason,
#             summary=summary,
#             key_facts=key_facts,
#             companies_mentioned=companies,
#             market_impact=market_impact,
#             raw_response=parsed,
#         )

#     @staticmethod
#     def _direct_event_floor(
#         event_types: list[str],
#     ) -> float:
#         """
#         Conservative deterministic floors for direct events.

#         These floors repair obvious small-model contradictions without
#         treating a simple company-name mention as proof of relevance.
#         """
#         strong_events = {
#             "earnings",
#             "investment",
#             "financing",
#             "debt",
#             "mna",
#             "regulation",
#         }

#         medium_events = {
#             "partnership",
#             "contract",
#             "product",
#             "capacity",
#             "management_change",
#             "legal",
#             "restructuring",
#             "shareholding",
#             "cybersecurity",
#         }

#         lighter_events = {
#             "market_movement",
#             "other",
#         }

#         events = set(event_types)

#         if events & strong_events:
#             return 0.70

#         if events & medium_events:
#             return 0.60

#         if events & lighter_events:
#             return 0.55

#         return 0.50

#     @staticmethod
#     def _normalize_choice(
#         value: Any,
#         *,
#         allowed: set[str],
#         default: str,
#     ) -> str:
#         normalized = str(
#             value or ""
#         ).strip().lower()

#         if normalized in allowed:
#             return normalized

#         return default

#     @staticmethod
#     def _normalize_allowed_string_list(
#         value: Any,
#         *,
#         allowed: set[str],
#     ) -> list[str]:
#         if not isinstance(
#             value,
#             list,
#         ):
#             return []

#         normalized: list[str] = []
#         seen: set[str] = set()

#         for item in value:
#             if not isinstance(
#                 item,
#                 str,
#             ):
#                 continue

#             item = item.strip().lower()

#             if (
#                 not item
#                 or item not in allowed
#                 or item in seen
#             ):
#                 continue

#             seen.add(item)
#             normalized.append(item)

#         return normalized

#     @staticmethod
#     def _normalize_score(
#         value: Any,
#     ) -> float:
#         try:
#             score = float(
#                 value
#             )

#         except (
#             TypeError,
#             ValueError,
#         ):
#             score = 0.0

#         return max(
#             0.0,
#             min(
#                 score,
#                 1.0,
#             ),
#         )

#     @staticmethod
#     def _normalize_bool(
#         value: Any,
#     ) -> bool:
#         if isinstance(value, bool):
#             return value

#         if isinstance(value, (int, float)):
#             return value != 0

#         if isinstance(value, str):
#             normalized = value.strip().lower()

#             if normalized in {"true", "1", "yes", "y"}:
#                 return True

#             if normalized in {"false", "0", "no", "n", ""}:
#                 return False

#         return False

#     @staticmethod
#     def _normalize_string_list(
#         value: Any,
#     ) -> list[str]:
#         if not isinstance(
#             value,
#             list,
#         ):
#             return []

#         normalized: list[str] = []

#         for item in value:
#             if isinstance(
#                 item,
#                 str,
#             ):
#                 item = item.strip()

#                 if item:
#                     normalized.append(
#                         item
#                     )

#         return normalized

#     @staticmethod
#     def _normalize_optional_string(
#         value: Any,
#     ) -> str | None:
#         if value is None:
#             return None

#         value = str(
#             value
#         ).strip()

#         return value or None


class ArticleAnalyzer:
    """
    Analyze extracted financial/news articles using Finzer's
    configured LLM router.

    Responsibilities:
    - Validate article content
    - Determine financial relevance
    - Generate concise summaries
    - Extract key facts
    - Extract materially relevant companies
    - Determine supported market impact
    - Detect truncated LLM responses
    - Parse structured JSON output
    """

    def __init__(
        self,
        relevance_threshold: float | None = None,
    ):
        self.relevance_threshold = float(
            relevance_threshold
            if relevance_threshold is not None
            else settings.ARTICLE_RELEVANCE_THRESHOLD
        )

        self.max_article_chars = (
            settings.LLM_MAX_ARTICLE_CHARS
        )

        self.llm_client = LLMRouter()
        self.model = self.llm_client.model

    def analyze(
        self,
        *,
        feed_id: str,
        feed_target: str,
        feed_description: str,
        title: str,
        content: str,
        source: str | None = None,
        published_at: str | None = None,
    ) -> ArticleAnalysis:
        """
        Analyze one article using the configured LLM service.
        """

        if not content or not content.strip():
            raise ValueError(
                "Article content cannot be empty."
            )

        system_prompt = self._build_system_prompt()

        user_prompt = self._build_user_prompt(
            feed_id=feed_id,
            feed_target=feed_target,
            feed_description=feed_description,
            title=title,
            source=source,
            published_at=published_at,
            content=content,
        )

        response_data = self.llm_client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            max_tokens=settings.BEDROCK_LLM_MAX_TOKENS,
            temperature=settings.BEDROCK_LLM_TEMPERATURE,
        )

        try:
            choice = response_data["choices"][0]

            model_output = (
                choice["message"]["content"]
            )

            finish_reason = choice.get(
                "finish_reason"
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise RuntimeError(
                "Unexpected LLM response format: "
                f"{response_data}"
            ) from exc

        # ------------------------------------------------------
        # Detect token-limit truncation BEFORE JSON parsing.
        # ------------------------------------------------------

        if finish_reason == "length":
            raise RuntimeError(
                "LLM response was truncated because the "
                "output token limit was reached.\n"
                f"Raw output:\n{model_output}"
            )

        parsed = self._parse_json_response(
            model_output
        )

        return self._build_analysis(
            parsed
        )

    def _build_system_prompt(
        self,
    ) -> str:
        return """
You are Finzer's financial news classifier.

Evaluate one news article against the supplied Feed Target.

The Feed Target may be:
- a company or stock
- an ETF or mutual fund
- an index
- a commodity
- a sector or industry
- a country/economy
- a macroeconomic topic
- another finance-related target

IMPORTANT:
- Feed Target is the real subject being evaluated.
- Feed Description gives useful financial context.
- Feed ID is only an internal identifier.
- Never infer meaning from Feed ID.

ARTICLE VALIDITY

Validity and relevance are separate.

Set is_valid_article=true if the content is a coherent news,
business, market, economic, regulatory, or financial article.

Set is_valid_article=false only for broken extraction,
login pages, navigation, ads, access-denied pages,
cookie/privacy UI, or other non-article content.

A valid article may still be irrelevant.

FINANCIAL RELEVANCE

Relevance may be DIRECT or INDIRECT.

DIRECT means the article materially discusses the Feed Target
itself.

Common direct financial events:
- earnings, revenue, profit, margins, guidance
- investment, capex, debt, fundraising, refinancing
- acquisition, merger, divestiture
- partnership, joint venture, contract, order
- product launch, product development, technology
- production, capacity expansion, market share
- management or board changes
- restructuring or layoffs
- regulation, taxation, legal action
- cybersecurity or operational disruption
- analyst rating or shareholding changes
- target-specific share-price or market movement

INDIRECT means the article mainly concerns an external
development that has a clear and supported financial
connection to the Feed Target.

Common indirect factors:
- interest rates
- inflation
- currency movement
- commodity or raw-material prices
- government policy
- regulation or taxation
- tariffs or sanctions
- geopolitical events
- supply-chain disruption
- industry demand
- major competitor actions
- major customer or supplier developments
- economic growth or consumer demand

For INDIRECT relevance:
- use only the article and Feed Description
- do not invent business exposure
- require an explainable financial connection

TARGET MENTION RULE

A simple target-name mention is not enough.

But if the article is substantially about the Feed Target
and contains a recognized financial/business event,
it has DIRECT relevance even when the article does not
contain earnings, valuation, or accounting data.

DIRECT EVENT SCORING GUIDE

If the article is substantially about the Feed Target,
use these ranges:

0.85 - 1.00
Major earnings/results, large acquisition, major financing,
major regulatory action, major strategic investment,
or another highly material development.

0.70 - 0.89
Meaningful investment, contract, partnership, product launch,
capacity expansion, management leadership change,
legal/regulatory development, material analyst/shareholding
event, or other strong direct development.

0.55 - 0.75
Target-specific share-price movement, moderate operational
development, smaller management change, product update,
routine but useful market event, or other directly relevant
financial information.

Do NOT assign 0.00 to an article substantially about the
Feed Target if it contains a recognized financial/business
event.

INDIRECT EVENT SCORING GUIDE

0.65 - 0.85
External event with a strong, explicit, and material
connection to the target.

0.40 - 0.64
Plausible and meaningful indirect connection,
but materiality is moderate.

0.15 - 0.39
Weak or contextual connection.

0.00 - 0.14
No meaningful financial connection.

RELEVANCE TYPE

Use exactly one:
- "direct"
- "indirect"
- "none"

FINANCIAL EVENT TYPES

Use only these values:

- earnings
- investment
- financing
- debt
- mna
- partnership
- contract
- product
- capacity
- management_change
- restructuring
- regulation
- legal
- geopolitical
- commodity
- macro
- supply_chain
- competition
- market_movement
- shareholding
- cybersecurity
- other

Use [] if none apply.

IMPORTANT EXAMPLES

Example 1:

Target: HDFC Bank
Article: HDFC Bank board approves MD/CEO nominees.

Result:
- direct relevance
- financial_event_types includes management_change
- relevance_score should normally be at least 0.65

Example 2:

Target: HDFC Bank
Article: HDFC Bank share price rises 2%.

Result:
- direct relevance
- financial_event_types includes market_movement
- relevance_score should normally be around 0.55-0.75
  depending on article depth

Example 3:

Target: HDFC Bank
Article: Consumer loses money in fraud and one transaction
used an HDFC account.

Result:
- usually weak or no relevance unless the article describes
  a bank-specific security failure, regulatory issue,
  operational issue, or material pattern

Example 4:

Target: Reliance Industries
Article: Crude-oil supply changes.

Result:
- only indirect relevance if Feed Description establishes
  material refining, petrochemical, or energy exposure and
  the article supports that connection

SUMMARY

Provide a concise factual summary in at most 3 sentences.

Preserve important:
- names
- numbers
- dates
- financial events
- market facts

Do not speculate.

KEY FACTS

Return at most 6 key facts.

Each fact must be one concise complete factual sentence.

Include only facts materially useful for understanding
the article.

Avoid duplicates.

COMPANIES

companies_mentioned must contain at most 12 explicitly
named companies or organizations.

Prioritize:
1. the Feed Target
2. entities materially relevant to the financial event
3. other important entities required to understand the article

Do not list every company appearing in a broad market roundup.

Avoid duplicates.

MARKET IMPACT

Describe potential impact only when supported by the article.

Keep market_impact concise.

Do not invent exact price predictions.

IMPACT DIRECTION

Use exactly one:
- "positive"
- "negative"
- "mixed"
- "neutral"
- "unclear"

IMPACT HORIZON

Use exactly one:
- "immediate"
- "short_term"
- "medium_term"
- "long_term"
- "unclear"

OUTPUT

Return ONLY valid JSON with exactly this structure:

{
  "is_valid_article": true,
  "relevance_score": 0.0,
  "is_relevant": false,
  "relevance_type": "none",
  "financial_event_types": [],
  "relevance_reason": "",
  "summary": "",
  "key_facts": [],
  "companies_mentioned": [],
  "market_impact": "",
  "impact_direction": "unclear",
  "impact_horizon": "unclear"
}

IMPORTANT OUTPUT RULES:

- Return one JSON object only.
- Do not return markdown.
- Do not return code fences.
- Do not include text before the JSON.
- Do not include text after the JSON.
- Keep the entire response concise.
- key_facts must contain at most 6 items.
- companies_mentioned must contain at most 12 items.
- summary must contain at most 3 sentences.

is_relevant should normally be true when
relevance_score >= 0.55.

The application applies the final threshold independently,
so provide an honest relevance score.
""".strip()

    def _build_user_prompt(
        self,
        *,
        feed_id: str,
        feed_target: str,
        feed_description: str,
        title: str,
        content: str,
        source: str | None,
        published_at: str | None,
    ) -> str:
        content = self._truncate_content(
            content
        )

        return f"""
FEED TARGET:
{feed_target}

FEED DESCRIPTION:
{feed_description}

FEED ID:
{feed_id}

ARTICLE TITLE:
{title}

SOURCE:
{source or "Unknown"}

PUBLISHED AT:
{published_at or "Unknown"}

ARTICLE:
{content}

Return the required JSON only.
""".strip()

    def _truncate_content(
        self,
        content: str,
    ) -> str:
        """
        Limit article size to keep inference predictable.

        Character-based truncation is intentionally used
        because this layer does not depend on a provider
        tokenizer.
        """

        if len(content) <= self.max_article_chars:
            return content

        return (
            content[:self.max_article_chars]
            + "\n\n[ARTICLE TRUNCATED]"
        )

    def _parse_json_response(
        self,
        model_output: str,
    ) -> dict[str, Any]:
        """
        Parse the model's structured JSON response.

        Truncation caused by finish_reason='length' is handled
        earlier in analyze(). This function handles genuinely
        malformed model output.
        """

        cleaned = model_output.strip()

        # Defensive handling in case a model ignores the
        # instruction and returns a fenced JSON block.
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")

            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        try:
            parsed = json.loads(
                cleaned
            )

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "LLM returned invalid JSON.\n"
                f"Raw output:\n{model_output}"
            ) from exc

        if not isinstance(
            parsed,
            dict,
        ):
            raise RuntimeError(
                "LLM JSON response must be a JSON object."
            )

        return parsed


    def _build_analysis(
        self,
        parsed: dict[str, Any],
    ) -> ArticleAnalysis:
        score = self._normalize_score(
            parsed.get(
                "relevance_score",
                0.0,
            )
        )

        is_valid = self._normalize_bool(
            parsed.get(
                "is_valid_article",
                False,
            )
        )

        relevance_type = self._normalize_choice(
            parsed.get(
                "relevance_type",
                "none",
            ),
            allowed={
                "direct",
                "indirect",
                "none",
            },
            default="none",
        )

        event_types = self._normalize_allowed_string_list(
            parsed.get(
                "financial_event_types",
                [],
            ),
            allowed={
                "earnings",
                "investment",
                "financing",
                "debt",
                "mna",
                "partnership",
                "contract",
                "product",
                "capacity",
                "management_change",
                "restructuring",
                "regulation",
                "legal",
                "geopolitical",
                "commodity",
                "macro",
                "supply_chain",
                "competition",
                "market_movement",
                "shareholding",
                "cybersecurity",
                "other",
            },
        )

        impact_direction = self._normalize_choice(
            parsed.get(
                "impact_direction",
                "unclear",
            ),
            allowed={
                "positive",
                "negative",
                "mixed",
                "neutral",
                "unclear",
            },
            default="unclear",
        )

        impact_horizon = self._normalize_choice(
            parsed.get(
                "impact_horizon",
                "unclear",
            ),
            allowed={
                "immediate",
                "short_term",
                "medium_term",
                "long_term",
                "unclear",
            },
            default="unclear",
        )

        # Repair only obvious structural contradictions.
        # Do NOT boost scores merely because the company name appears.
        if relevance_type == "direct" and event_types:
            score = max(
                score,
                self._direct_event_floor(
                    event_types
                ),
            )

        if relevance_type == "none":
            # Prevent malformed high scores from promoting
            # an explicitly non-relevant classification.
            score = min(
                score,
                0.49,
            )

        parsed["relevance_score"] = score
        parsed["relevance_type"] = relevance_type
        parsed["financial_event_types"] = event_types
        parsed["impact_direction"] = impact_direction
        parsed["impact_horizon"] = impact_horizon

        # Finzer's configured threshold is authoritative.
        is_relevant = (
            is_valid
            and score >= self.relevance_threshold
        )

        parsed["is_relevant"] = is_relevant

        summary = self._normalize_optional_string(
            parsed.get(
                "summary"
            )
        )

        market_impact = self._normalize_optional_string(
            parsed.get(
                "market_impact"
            )
        )

        relevance_reason = str(
            parsed.get(
                "relevance_reason",
                "",
            )
        ).strip()

        key_facts = self._normalize_string_list(
            parsed.get(
                "key_facts",
                [],
            )
        )

        companies = self._normalize_string_list(
            parsed.get(
                "companies_mentioned",
                [],
            )
        )

        if not is_relevant:
            summary = None
            key_facts = []
            market_impact = None

        return ArticleAnalysis(
            is_valid_article=is_valid,
            relevance_score=score,
            is_relevant=is_relevant,
            relevance_reason=relevance_reason,
            summary=summary,
            key_facts=key_facts,
            companies_mentioned=companies,
            market_impact=market_impact,
            raw_response=parsed,
        )

    @staticmethod
    def _direct_event_floor(
        event_types: list[str],
    ) -> float:
        """
        Conservative deterministic floors for direct events.
        """

        strong_events = {
            "earnings",
            "investment",
            "financing",
            "debt",
            "mna",
            "regulation",
        }

        medium_events = {
            "partnership",
            "contract",
            "product",
            "capacity",
            "management_change",
            "legal",
            "restructuring",
            "shareholding",
            "cybersecurity",
        }

        lighter_events = {
            "market_movement",
            "other",
        }

        events = set(event_types)

        if events & strong_events:
            return 0.70

        if events & medium_events:
            return 0.60

        if events & lighter_events:
            return 0.55

        return 0.50

    @staticmethod
    def _normalize_choice(
        value: Any,
        *,
        allowed: set[str],
        default: str,
    ) -> str:
        normalized = str(
            value or ""
        ).strip().lower()

        if normalized in allowed:
            return normalized

        return default

    @staticmethod
    def _normalize_allowed_string_list(
        value: Any,
        *,
        allowed: set[str],
    ) -> list[str]:
        if not isinstance(
            value,
            list,
        ):
            return []

        normalized: list[str] = []
        seen: set[str] = set()

        for item in value:
            if not isinstance(
                item,
                str,
            ):
                continue

            item = item.strip().lower()

            if (
                not item
                or item not in allowed
                or item in seen
            ):
                continue

            seen.add(item)
            normalized.append(item)

        return normalized

    @staticmethod
    def _normalize_score(
        value: Any,
    ) -> float:
        try:
            score = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            score = 0.0

        return max(
            0.0,
            min(
                score,
                1.0,
            ),
        )

    @staticmethod
    def _normalize_bool(
        value: Any,
    ) -> bool:
        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            (int, float),
        ):
            return value != 0

        if isinstance(
            value,
            str,
        ):
            normalized = value.strip().lower()

            if normalized in {
                "true",
                "1",
                "yes",
                "y",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "n",
                "",
            }:
                return False

        return False

    @staticmethod
    def _normalize_string_list(
        value: Any,
    ) -> list[str]:
        if not isinstance(
            value,
            list,
        ):
            return []

        normalized: list[str] = []

        for item in value:
            if isinstance(
                item,
                str,
            ):
                item = item.strip()

                if item:
                    normalized.append(
                        item
                    )

        return normalized

    @staticmethod
    def _normalize_optional_string(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        value = str(
            value
        ).strip()

        return value or None