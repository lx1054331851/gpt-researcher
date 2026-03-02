from .arxiv.arxiv import ArxivSearch
from .bing.bing import BingSearch
from .custom.custom import CustomRetriever
from .duckduckgo.duckduckgo import Duckduckgo
from .google.google import GoogleSearch
from .pubmed_central.pubmed_central import PubMedCentralSearch
from .searx.searx import SearxSearch
from .semantic_scholar.semantic_scholar import SemanticScholarSearch
from .searchapi.searchapi import SearchApiSearch
from .serpapi.serpapi import SerpApiSearch
from .serper.serper import SerperSearch
from .tavily.tavily_search import TavilySearch
from .exa.exa import ExaSearch
from .bocha.bocha import BoChaSearch

__all__ = [
    "TavilySearch",
    "CustomRetriever",
    "Duckduckgo",
    "SearchApiSearch",
    "SerperSearch",
    "SerpApiSearch",
    "GoogleSearch",
    "SearxSearch",
    "BingSearch",
    "ArxivSearch",
    "SemanticScholarSearch",
    "PubMedCentralSearch",
    "ExaSearch",
    "MCPRetriever",
    "BoChaSearch"
]


def __getattr__(name: str):
    if name == "MCPRetriever":
        from .mcp import MCPRetriever

        if MCPRetriever is None:
            raise ImportError(
                "MCPRetriever requires optional dependency 'langchain-mcp-adapters'. "
                "Install it to use RETRIEVER=mcp."
            )
        return MCPRetriever
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
