from .base import BaseConfig

DEFAULT_CONFIG: BaseConfig = {
    "RETRIEVER": "tavily",
    "EMBEDDING": "openai:text-embedding-3-small",
    "SIMILARITY_THRESHOLD": 0.42,
    "FAST_LLM": "openai:gpt-4o-mini",
    "SMART_LLM": "openai:gpt-4.1",  # Has support for long responses (2k+ words).
    "STRATEGIC_LLM": "openai:o4-mini",  # Can be used with o1 or o3, please note it will make tasks slower.
    "FAST_TOKEN_LIMIT": 3000,
    "SMART_TOKEN_LIMIT": 6000,
    "STRATEGIC_TOKEN_LIMIT": 4000,
    "BROWSE_CHUNK_MAX_LENGTH": 8192,
    "CURATE_SOURCES": False,
    "SUMMARY_TOKEN_LIMIT": 700,
    "TEMPERATURE": 0.4,
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "MAX_SEARCH_RESULTS_PER_QUERY": 5,
    "MEMORY_BACKEND": "local",
    "TOTAL_WORDS": 1200,
    "REPORT_FORMAT": "APA",
    "REPORT_STYLE": "strategic_report",
    "SOURCE_POLICY": "medium_tier",
    "MAX_ITERATIONS": 3,
    "AGENT_ROLE": None,
    "SCRAPER": "bs",
    "MAX_SCRAPER_WORKERS": 15,
    "SCRAPER_RATE_LIMIT_DELAY": 0.0,  # Minimum seconds between scraper requests (0 = no limit, useful for API rate limiting)
    "MAX_SUBTOPICS": 3,
    "LANGUAGE": "english",
    "REPORT_SOURCE": "web",
    "DOC_PATH": "./my-docs",
    "PROMPT_FAMILY": "default",
    "LLM_KWARGS": {},
    "EMBEDDING_KWARGS": {},
    "VERBOSE": False,
    # Deep research specific settings
    "DEEP_RESEARCH_BREADTH": 3,
    "DEEP_RESEARCH_DEPTH": 2,
    "DEEP_RESEARCH_CONCURRENCY": 4,
    "DEEP_RESEARCH_MODE": "fixed",  # fixed|adaptive
    "ADAPTIVE_MIN_DEPTH": 1,
    "ADAPTIVE_MAX_DEPTH": 5,
    "ADAPTIVE_RUN_TIMEOUT_SECONDS": 1800,
    "ADAPTIVE_QUALITY_THRESHOLD": 7.5,
    "ADAPTIVE_SEARCH_TIMEOUT_SECONDS": 30,
    "ADAPTIVE_QUERY_MATRIX_TIMEOUT_SECONDS": 25,
    "ADAPTIVE_CLAIM_EXTRACTION_TIMEOUT_SECONDS": 35,
    "ADAPTIVE_MAX_CONSECUTIVE_EMPTY_ROUNDS": 2,
    "ADAPTIVE_MAX_CONFLICTS_PER_NODE": 2,
    "ADAPTIVE_MAX_DIMENSIONS": 10,
    "ADAPTIVE_SOURCE_QUALITY_FILTER_ENABLED": True,
    "ADAPTIVE_MAX_SOURCES_PER_QUERY": 5,
    "ADAPTIVE_MAX_SOURCES_PER_DOMAIN": 2,
    "ADAPTIVE_MIN_SOURCE_QUALITY_SCORE": 0.0,
    "ADAPTIVE_REQUIRE_HIGH_QUALITY_SOURCE_QUOTA": True,
    "ADAPTIVE_HIGH_QUALITY_SOURCE_QUOTA": 0.5,
    "ADAPTIVE_HIGH_QUALITY_DOMAINS": [
        "www.vfc.com",
        "www.sec.gov",
        "www.wsj.com",
        "www.reuters.com",
        "www.bloomberg.com",
        "www.ft.com",
    ],
    "ADAPTIVE_LOW_QUALITY_DOMAINS": [
        "www.accio.com",
        "www.msn.com",
        "www.stocktitan.net",
        "live.worldtourismforum.net",
    ],
    "ADAPTIVE_CACHE_ENABLED": True,
    "ADAPTIVE_MAX_ROUNDS_PER_NODE": 2,
    "ADAPTIVE_MAX_QUERIES_PER_ROUND": 3,
    "ADAPTIVE_MAX_QUERY_FAILURES_PER_NODE": 3,
    "ADAPTIVE_FAILURE_RATE_REDUCE_THRESHOLD": 0.8,
    "ADAPTIVE_QUERY_MATRIX_LLM_DISABLE_AFTER_FAILURES": 3,
    "ADAPTIVE_CLAIM_LLM_DISABLE_AFTER_FAILURES": 4,
    "ADAPTIVE_FAILED_DOMAIN_THRESHOLD": 2,
    "ADAPTIVE_MIN_COMPLETED_NODES_FOR_EARLY_STOP": 4,
    "ADAPTIVE_COVERAGE_ENHANCER_ENABLED": True,
    "ADAPTIVE_COVERAGE_MIN_RATIO": 0.75,
    "ADAPTIVE_COVERAGE_REVISE_MAX_ROUNDS": 1,
    "ADAPTIVE_COVERAGE_PROFILE": "high_coverage",  # balanced|high_coverage
    "ADAPTIVE_CHAIN_ENFORCER_ENABLED": True,
    "ADAPTIVE_CHAIN_MIN_RATIO": 0.90,
    "ADAPTIVE_CHAIN_REQUIRE_EXPLICIT_SECTIONS": True,
    "ADAPTIVE_CHAIN_PROFILE_MODE": "dual",  # generic|dual
    "ADAPTIVE_CHAIN_INDUSTRY_PROFILE": "auto",  # auto|apparel_supply_chain|generic
    "ADAPTIVE_CHAIN_PATCH_MAX_ROUNDS": 1,
    "ADAPTIVE_REFERENCE_URL_MIN_RATIO": 0.80,
    "ADAPTIVE_EXPLORATION_PROFILE": "high_recall",  # balanced|high_recall
    "ADAPTIVE_MIN_UNIQUE_DOMAINS": 25,
    "ADAPTIVE_MIN_UNIQUE_URLS": 45,
    "ADAPTIVE_FRONTIER_QUERY_RATIO": 0.35,
    "ADAPTIVE_DOMAIN_HARD_BLOCKLIST": [
        "plecoforums.com",
    ],
    "ADAPTIVE_LOW_SIGNAL_URL_PATTERNS": [
        r"wordfreq",
        r"dictionary",
        r"glossary",
        r"wordlist",
        r"corpus.*txt",
        r"dict_.*\\.txt",
        r"technology_wordfreq",
    ],
    "ADAPTIVE_LOW_SIGNAL_TITLE_PATTERNS": [
        r"词频",
        r"词表",
        r"字典",
        r"lexicon",
        r"frequency list",
    ],
    "ENTROPY_MIN_GAIN": 0.08,
    "SALIENCY_THRESHOLD": 0.72,
    "RABBIT_HOLE_MAX_BRANCHES": 2,
    "RABBIT_HOLE_MAX_QUERIES_PER_BRANCH": 3,
    "TAVILY_SEARCH_DEPTH_DEFAULT": "basic",
    "TAVILY_ADVANCED_ENABLED": False,
    "REPORT_COMPLETION_GUARD_ENABLED": True,
    "REPORT_COMPLETION_MAX_ATTEMPTS": 2,
    "REPORT_COMPLETION_REQUIRE_MARKER": True,
    "REPORT_SECTIONAL_FALLBACK_ENABLED": True,
    "REPORT_SECTIONAL_MAX_SECTIONS": 6,
    "REPORT_SECTIONAL_CONTEXT_CHARS": 24000,
    "REPORT_SECTIONAL_PREFLIGHT_ENABLED": True,
    "REPORT_SECTIONAL_PREFLIGHT_MIN_CONTEXT_CHARS": 14000,
    "REPORT_SECTIONAL_TIMEOUT_SECONDS": 180,
    "REPORT_SECTIONAL_FALLBACK_REDUCED_MAX_SECTIONS": 4,
    "REPORT_SECTIONAL_FALLBACK_REDUCED_CONTEXT_CHARS": 12000,
    
    # MCP retriever specific settings
    "MCP_SERVERS": [],  # List of predefined MCP server configurations
    "MCP_AUTO_TOOL_SELECTION": True,  # Whether to automatically select the best tool for a query
    "MCP_ALLOWED_ROOT_PATHS": [],  # List of allowed root paths for local file access
    "MCP_STRATEGY": "fast",  # MCP execution strategy: "fast", "deep", "disabled"
    "REASONING_EFFORT": "medium",
    
    # Image generation settings (optional - requires GOOGLE_API_KEY)
    # Free tier models: gemini-2.5-flash-image, gemini-2.0-flash-exp-image-generation
    # Paid tier models: imagen-4.0-generate-001, imagen-4.0-fast-generate-001
    "IMAGE_GENERATION_MODEL": "models/gemini-2.5-flash-image",
    "IMAGE_GENERATION_MAX_IMAGES": 3,  # Maximum number of images to generate per report
    "IMAGE_GENERATION_ENABLED": False,  # Master switch for inline image generation
    "IMAGE_GENERATION_STYLE": "dark",  # Image style: "dark" (matches app theme), "light", or "auto"
}
