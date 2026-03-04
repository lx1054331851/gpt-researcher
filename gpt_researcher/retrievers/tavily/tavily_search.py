"""Tavily API search retriever for GPT Researcher.

This module provides the TavilySearch class for performing web searches
using the Tavily API.
"""

import json
import os
from typing import Literal, Optional, Sequence

import requests


class TavilySearch:
    """
    Tavily API Retriever
    """

    def __init__(self, query, headers=None, topic="general", query_domains=None):
        """
        Initializes the TavilySearch object.

        Args:
            query (str): The search query string.
            headers (dict, optional): Additional headers to include in the request. Defaults to None.
            topic (str, optional): The topic for the search. Defaults to "general".
            query_domains (list, optional): List of domains to include in the search. Defaults to None.
        """
        self.query = " ".join(str(query).split())[:700]
        self.headers = headers or {}
        self.topic = topic
        self.base_url = "https://api.tavily.com/search"
        self.api_key = self.get_api_key()
        self.request_headers = {
            "Content-Type": "application/json",
        }
        self.query_domains = query_domains or None

    @staticmethod
    def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def get_api_key(self):
        """
        Gets the Tavily API key
        Returns:

        """
        api_key = self.headers.get("tavily_api_key")
        if not api_key:
            try:
                api_key = os.environ["TAVILY_API_KEY"]
            except KeyError:
                print(
                    "Tavily API key not found, set to blank. If you need a retriver, please set the TAVILY_API_KEY environment variable."
                )
                return ""
        return api_key


    def _search(
        self,
        query: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        topic: str = "general",
        days: int = 2,
        max_results: int = 10,
        include_domains: Sequence[str] = None,
        exclude_domains: Sequence[str] = None,
        include_answer: bool = False,
        include_raw_content: bool = False,
        include_images: bool = False,
        use_cache: bool = True,
    ) -> dict:
        """
        Internal search method to send the request to the API.
        """

        data = {
            "query": query,
            "search_depth": search_depth,
            "topic": topic,
            "days": days,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "max_results": max_results,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
            "include_images": include_images,
            "api_key": self.api_key,
            "use_cache": use_cache,
        }

        response = requests.post(
            self.base_url,
            data=json.dumps(data),
            headers=self.request_headers,
            timeout=float(os.getenv("TAVILY_TIMEOUT_SECONDS", "30")),
        )

        if response.status_code == 200:
            return response.json()
        else:
            # Raises a HTTPError if the HTTP request returned an unsuccessful status code
            response.raise_for_status()

    def search(self, max_results=10):
        """
        Searches the query
        Returns:

        """
        try:
            search_depth = (
                self.headers.get("tavily_search_depth")
                or os.getenv("TAVILY_SEARCH_DEPTH")
                or os.getenv("TAVILY_SEARCH_DEPTH_DEFAULT")
                or "basic"
            )
            if search_depth not in {"basic", "advanced"}:
                search_depth = "basic"

            include_raw_content = self._parse_bool(
                self.headers.get("tavily_include_raw_content"),
                default=self._parse_bool(os.getenv("TAVILY_INCLUDE_RAW_CONTENT"), default=False),
            )
            include_images = self._parse_bool(
                self.headers.get("tavily_include_images"),
                default=self._parse_bool(os.getenv("TAVILY_INCLUDE_IMAGES"), default=False),
            )

            # Search the query. Retry once with a minimal payload on transient/400 failures.
            try:
                results = self._search(
                    self.query,
                    search_depth=search_depth,
                    max_results=max_results,
                    topic=self.topic,
                    include_domains=self.query_domains,
                    include_raw_content=include_raw_content,
                    include_images=include_images,
                )
            except Exception:
                results = self._search(
                    self.query,
                    search_depth="basic",
                    max_results=max_results,
                    topic=self.topic,
                    include_domains=None,
                    include_raw_content=False,
                    include_images=False,
                    use_cache=True,
                )
            sources = results.get("results", [])
            if not sources:
                raise Exception("No results found with Tavily API search.")
            # Return the results
            search_response = [
                {
                    "href": obj.get("url"),
                    "body": obj.get("content", ""),
                    "raw_content": obj.get("raw_content", ""),
                    "title": obj.get("title", ""),
                }
                for obj in sources
            ]
        except Exception as e:
            print(f"Error: {e}. Failed fetching sources. Resulting in empty response.")
            search_response = []
        return search_response
