"""
This module provides a function to convert markdown content to HTML.
The convert api is provided by the frontend service.
"""

import os
from typing import Dict, List

import dotenv
import requests
from pydantic import BaseModel
from typing_extensions import deprecated


class FrontendMarkdownResponse(BaseModel):
    frontmatter: Dict[str, str | List[str] | bool | int]
    html: str


@deprecated("Next.js frontend is deprecated")
def markdown_to_html_frontend(content: str) -> FrontendMarkdownResponse:
    """
    Converts markdown content to HTML using the frontend service.

    Args:
        content (str): The markdown content to be converted.

    Returns:
        FrontendMarkdownResponse: A dictionary containing the frontmatter
        and rendered HTML.

    Raises:
        ValueError: If the `FRONTEND_URL` environment variable is not set.
        RuntimeError: If the request to the frontend service fails or
        the response cannot be parsed as JSON.
    """

    url = os.getenv("FRONTEND_URL")
    if url is None:
        err_msg = (
            "Environment variable `FRONTEND_URL` is not set. "
            "Please set it to the frontend URL."
        )
        raise ValueError(err_msg)

    if not url.endswith("/"):
        url += "/"
    url += "api/markdown/render"

    try:
        response = requests.post(
            url, json={"content": content, "options": {"allowUnsafe": True}}
        )
        response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
    except requests.RequestException as e:
        err_msg = f"Failed to render markdown: {e}"
        raise RuntimeError(err_msg) from e

    try:
        json_data = response.json()

        if not isinstance(json_data, dict):
            raise ValueError("Response is not a valid JSON object")
        if "error" in json_data:
            err_msg = f"Error from frontend service: {json_data['error']}"
            raise RuntimeError(err_msg)

        return FrontendMarkdownResponse.model_validate(json_data)
    except ValueError as e:
        err_msg = f"Failed to parse JSON response: {e}"
        raise RuntimeError(err_msg) from e


if __name__ == "__main__":
    test_md = """---
title: Test Markdown
description: This is a test markdown file.
tags: [test, markdown]
datatime: 2025-07-23 14:34:00
math: true
keywords: 
  - test
  - markdown
---

# heading

content

$$
E = mc^2
$$

<a herf="https://a.com">inline html</a>
"""

    dotenv.load_dotenv()
    res = markdown_to_html_frontend(test_md)
    print(res.frontmatter)
    print(res.html)
