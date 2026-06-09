import copy
import hashlib
import re
from functools import wraps
from typing import Any, Dict, List, Optional, TypedDict

import yaml
from django.utils.text import Truncator


class MetadataResult(TypedDict):
    keywords: str
    tags: List[str]
    description: str
    title: Optional[str]
    slug: Optional[str]
    category: Optional[str]
    cover_image: Optional[str]
    header_image: Optional[str]
    layout: Optional[str]


def remove_html_tags(text: str) -> str:
    """
    Remove HTML tags from a string.

    Args:
        text (str): The input string containing HTML tags.

    Returns:
        str: The input string with HTML tags removed.
    """
    # Remove script and style tags with their content
    text = re.sub(
        r"<script[^>]*>[\s\S]*?</\s*script[^>]*>", "", text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"<style[^>]*>[\s\S]*?</\s*style[^>]*>", "", text, flags=re.IGNORECASE
    )

    # Remove HTML comments
    text = re.sub(r"<!--[\s\S]*?-->", "", text)

    # Remove CDATA sections
    text = re.sub(r"<!\[CDATA\[[\s\S]*?]]>", "", text)

    # Remove DOCTYPE declarations
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, flags=re.IGNORECASE)

    # Remove all other HTML tags (including self-closing tags)
    text = re.sub(r"<[^>]+>", "", text)

    return text


def remove_markdown(text: str) -> str:
    """
    Remove Markdown syntax from a string.

    Args:
        text (str): The input string containing Markdown syntax.

    Returns:
        str: The input string with Markdown syntax removed.
    """
    # Remove front matter first (to avoid interfering with other patterns)
    text = re.sub(r"^---\s*\n(.*?)\n---\s*\n", "", text, flags=re.DOTALL)

    # Remove math blocks (do this before inline patterns)
    text = re.sub(r"\$\$[\s\S]*?\$\$", "", text)
    text = re.sub(r"\\\[[\s\S]*?\\\]", "", text)

    # Remove code blocks (fenced and indented)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)
    text = re.sub(r"(?m)^ {4,}.*$", "", text)

    # Remove inline math
    text = re.sub(r"\$[^$\n]+\$", "", text)
    text = re.sub(r"\\\([^)]+\\\)", "", text)

    # Remove images (complete removal, not just alt text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)

    # Remove links (keep link text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

    # Remove horizontal rules first (exactly 3 or more of the same character)
    # Do this before emphasis to avoid *** being interpreted as emphasis
    text = re.sub(r"^([-*_])\1\1+\s*$", "", text, flags=re.MULTILINE)

    # Remove emphasis (bold, italic, strikethrough)
    # Handle nested emphasis by removing markers from outside in
    text = re.sub(r"(\*\*\*|___)(.*?)\1", r"\2", text, flags=re.DOTALL)  # bold+italic
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text, flags=re.DOTALL)  # bold
    text = re.sub(r"([*_])(.*?)\1", r"\2", text, flags=re.DOTALL)  # italic
    text = re.sub(r"~~(.*?)~~", r"\1", text, flags=re.DOTALL)  # strikethrough

    # Remove inline code (keep content)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove blockquotes
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)

    # Remove list markers
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Clean up extra whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_code_blocks(text: str) -> str:
    """
    Remove code blocks from a string.

    Args:
        text (str): The input string containing code blocks.

    Returns:
        str: The input string with code blocks removed.
    """
    # Remove HTML pre blocks (they are block-level)
    text = re.sub(r"<pre[\s\S]*?</pre>", "", text, flags=re.IGNORECASE)

    # Remove fenced code blocks (backticks and tildes)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)

    # Remove indented code blocks (4 spaces or 1 tab at start of line)
    text = re.sub(r"(?m)^(?: {4,}|\t).*$", "", text)

    # Remove inline code (keep content) - both Markdown and HTML
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Handle HTML code tags with or without attributes
    text = re.sub(r"<code[^>]*>([^<]+)</code>", r"\1", text, flags=re.IGNORECASE)

    # Clean up extra whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_front_matter(text: str) -> Dict[str, Any]:
    """
    Extract front matter from a string.

    Args:
        text (str): The input string containing front matter.

    Returns:
        Dict[str, Any]: The extracted front matter as a dictionary,
                        or empty dict if no valid front matter found.
    """

    front_matter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    matched = front_matter_pattern.match(text)

    if matched:
        yaml_content = matched.group(1)
        try:
            front_matter = yaml.safe_load(yaml_content)
            if front_matter is None:
                return {}
            # Ensure we return a dictionary, not a string or other type
            if isinstance(front_matter, dict):
                return front_matter
            else:
                return {}
        except yaml.YAMLError:
            return {}

    # If not have front matter
    return {}


def extract_first_image(text: str) -> Optional[str]:
    """
    Extracts the URL of the first image found in the given text.

    The function searches for images in Markdown format (`![alt](url)`) first,
    and if none are found, it searches for images in HTML format (`<img src="url">`).
    Returns the URL of the first image found, or None if no image is present.

    Args:
        text (str): The input text to search for image URLs.

    Returns:
        Optional[str]: The URL of the first image found, or None if no image is present.
    """

    markdown_img_pattern = r"!\[([^\]]*)\]\(([^)]+)\)"
    match_result = re.search(markdown_img_pattern, text)
    if match_result is not None:
        return match_result.group(2)

    html_img_pattern = r'<img[^>]*src=["\']([^"\']+)["\']'
    match_result = re.search(html_img_pattern, text)
    if match_result is not None:
        return match_result.group(1)

    return None


def extract_metadata(text: str, num_keywords=5) -> MetadataResult:
    from jieba import analyse as jieba_analyse

    """
    Extracts metadata from a given text,
    including keywords, tags, category, title, slug, cover image, and header image.
    The function processes the input text by:
    - Extracting front matter metadata if present.
    - Identifying the first image in the text.
    - Removing code blocks, Markdown syntax, and HTML tags from the text.
    - Collecting keywords and tags from front matter and by analyzing the text content.
    - Determining the category from front matter fields.
    - Extracting cover and header images from front matter using common field names.
    Args:
        text (str): The input text from which metadata is to be extracted.
        num_keywords (int, optional): The maximum number of keywords to extract.
        Defaults to 5.
    Returns:
        MetadataResult: A dictionary containing extracted metadata fields:
            - keywords (str): Comma-separated keywords.
            - tags (List[str]): List of tags.
            - title (Optional[str]): Title from front matter.
            - slug (Optional[str]): Slug from front matter.
            - category (Optional[str]): Category from front matter.
            - cover_image (Optional[str]): Cover image URL or path.
            - header_image (Optional[str]): Header image URL or path.
    """

    # Get front matter if exists
    front_matter = extract_front_matter(text)

    first_image = extract_first_image(text)

    # Remove HTML tags and Markdown syntax
    text = remove_code_blocks(text)
    text = remove_markdown(text)
    text = remove_html_tags(text)

    # === tags ===
    tags_list: List[str] = []
    if "tags" in front_matter:
        field_value = front_matter["tags"]
        if isinstance(field_value, list):
            tags_list.extend(field_value)
        if isinstance(field_value, str):
            tags_list.append(field_value)
    if "tag" in front_matter:
        field_value = front_matter["tag"]
        if isinstance(field_value, list):
            tags_list.extend(field_value)
        if isinstance(field_value, str):
            tags_list.append(field_value)

    # === keywords ===
    keywords_list: List[str] = []
    if "keywords" in front_matter:
        keywords_list.extend(front_matter["keywords"])
    if "tags" in front_matter:
        keywords_list.extend(tags_list)
    most_common = jieba_analyse.extract_tags(text, topK=num_keywords)
    # Ensure most_common is a list of strings (extract the first element if tuples)
    if most_common and isinstance(most_common[0], tuple):
        most_common = [item[0] for item in most_common if item[0] not in keywords_list]
    else:
        most_common = [
            str(item) for item in most_common if str(item) not in keywords_list
        ]
    keywords_list.extend(most_common)

    # === category ===
    category: str | None = None
    if "category" in front_matter:
        field_value = front_matter["category"]
        if isinstance(field_value, list) and field_value:
            category = field_value[0]
        if isinstance(field_value, str):
            category = field_value
    if "categories" in front_matter and category is None:
        field_value = front_matter["categories"]
        if isinstance(field_value, list) and field_value:
            category = field_value[0]
        if isinstance(field_value, str):
            category = field_value

    # === cover image ===
    cover_image: str | None = None
    cover_image_names: List[str] = [
        "cover_image",
        "cover-image",
        "cover_img",
        "cover-img",
        "cover",
    ]
    for name in cover_image_names:
        cover_image = front_matter.get(name)
        if cover_image is not None:  # if found
            break

    # === header_image ===
    # now used as og image
    header_image: str | None = None
    header_image_names: List[str] = [
        "header_image",
        "header-image",
        "og_image",
        "og-image",
    ]
    for name in header_image_names:
        header_image = front_matter.get(name)
        if header_image is not None:  # if found
            break
    if header_image is None and first_image:
        header_image = first_image

    # === description ===
    description = Truncator(text).chars(150)

    # === layout ===
    layout = front_matter.get("layout")

    # Return the most common words as a comma-separated string
    return {
        "keywords": ",".join(keywords_list[:num_keywords]),
        "tags": tags_list,
        "title": front_matter.get("title"),
        "slug": front_matter.get("slug"),
        "category": category,
        "cover_image": cover_image,
        "header_image": header_image,
        "description": description,
        "layout": layout,
    }


def chinese_slugify(title: str, max_length: int = 50) -> str:
    from pypinyin import Style, lazy_pinyin

    """
    Generates a URL-friendly slug from a given title,
    supporting Chinese and English text.

    This function converts Chinese characters to their pinyin representation and
    lowercases English words. Non-alphanumeric characters are removed,
    and words are joined by hyphens. If the resulting slug exceeds the specified
    maximum length, it is truncated and appended with a hash suffix for uniqueness.

    Args:
        title (str): The input string to be slugified.
        max_length (int, optional): The maximum length of the resulting slug.
        Defaults to 50.

    Returns:
        str: The slugified string suitable for URLs.
    """

    if not title:
        return "untitled"

    # have some problem when Chinese and English are mixed
    # slug = django_slugify(title)

    cleaned = re.sub(r"[^\w\s\u4e00-\u9fff\-]", " ", title)

    parts = []
    for word in cleaned.split():
        if re.search(r"[\u4e00-\u9fff]", word):
            pinyin_parts = lazy_pinyin(word, style=Style.NORMAL)
            parts.extend([p.lower() for p in pinyin_parts])
        else:
            clean_word = re.sub(r"[^\w\-]", "", word.lower())
            if clean_word:
                parts.append(clean_word)

    slug = "-".join(parts)
    slug = re.sub(r"-+", "-", slug).strip("-")

    if len(slug) > max_length:
        hash_suffix = hashlib.md5(title.encode()).hexdigest()[:6]
        available_length = max_length - 7
        slug = slug[:available_length] + "-" + hash_suffix

    return slug or "untitled"


def _openapi_convert(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    convert django-ninja openapi 3.1 -> openapi 3.0
    :param spec: the Dict of django-ninja openapi.json
    :return: openapi 3.0 Dict
    """

    def _convert_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(schema, dict):
            return schema

        schema = copy.deepcopy(schema)

        # null in anyOf
        if "anyOf" in schema:
            has_null = False
            non_null_schemas = []

            for sub_schema in schema["anyOf"]:
                if isinstance(sub_schema, dict) and sub_schema.get("type") == "null":
                    has_null = True
                else:
                    non_null_schemas.append(sub_schema)

                if has_null:
                    schema["nullable"] = True
                    if len(non_null_schemas) == 1:
                        single_schema = non_null_schemas[0]
                        del schema["anyOf"]
                        schema.update(single_schema)
                    elif len(non_null_schemas) > 1:
                        schema["anyOf"] = non_null_schemas
                    else:
                        del schema["anyOf"]

        # type list
        if "type" in schema and isinstance(schema["type"], list):
            if "null" in schema["type"]:
                schema["nullable"] = True
                types = [t for t in schema["type"] if t != "null"]
                schema["type"] = types[0] if len(types) == 1 else types

        # examples -> example
        if "examples" in schema and isinstance(schema["examples"], list):
            schema["example"] = schema["examples"][0] if schema["examples"] else None
            del schema["examples"]

        # convert exclusiveMinimum/Maximum
        if "exclusiveMinimum" in schema and isinstance(
            schema["exclusiveMinimum"], (int, float)
        ):
            schema["maximum"] = schema["exclusiveMinimum"]
            schema["exclusiveMinimum"] = True
        if "exclusiveMaximum" in schema and isinstance(
            schema["exclusiveMaximum"], (int, float)
        ):
            schema["maximum"] = schema["exclusiveMaximum"]
            schema["exclusiveMaximum"] = True

        # recursive process schema
        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                schema["properties"][prop_name] = _convert_schema(prop_schema)

        if "additionalProperties" in schema and isinstance(
            schema["additionalProperties"], dict
        ):
            schema["additionalProperties"] = _convert_schema(
                schema["additionalProperties"]
            )

        for keyword in ["allOf", "anyOf", "oneOf"]:
            if keyword in schema:
                schema[keyword] = [_convert_schema(s) for s in schema[keyword]]

        return schema

    def _convert_operation(operation: Dict[str, Any]) -> None:
        if "requestBody" in operation:
            content = operation["requestBody"].get("content", {})
            for media_type, media_obj in content.items():
                if "schema" in media_obj:
                    media_obj["schema"] = _convert_schema(media_obj["schema"])
                if "examples" in media_obj and isinstance(media_obj["examples"], dict):
                    pass

        if "responses" in operation:
            for status, response in operation["responses"].items():
                if "content" in response:
                    for media_type, media_obj in response["content"].items():
                        if "schema" in media_obj:
                            media_obj["schema"] = _convert_schema(media_obj["schema"])

        if "parameters" in operation:
            for param in operation["parameters"]:
                if "schema" in param:
                    param["schema"] = _convert_schema(param["schema"])

    result = copy.deepcopy(spec)

    # change the version
    if "openapi" in result:
        result["openapi"] = "3.0.3"

    # convert schema
    if "components" in result and "schemas" in result["components"]:
        for schema_name, schema in result["components"]["schemas"].items():
            result["components"]["schemas"][schema_name] = _convert_schema(schema)

    if "paths" in result:
        for path, methods in result["paths"].items():
            for method, operation in methods.items():
                if isinstance(operation, dict):
                    _convert_operation(operation)

    return result


def convert_openapi(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        spec = func(*args, **kwargs)
        return _openapi_convert(spec)

    return wrapper


if __name__ == "__main__":
    import json

    import requests

    result = requests.get("http://localhost:8000/api/openapi.json")
    json_result = result.json()
    converted_result = _openapi_convert(json_result)
    with open("./openapi.json", "w") as f:
        f.write(json.dumps(converted_result))
