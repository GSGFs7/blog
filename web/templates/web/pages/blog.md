{% load markdown_text %}# Article Contents

Page {{ page_number }} of {{ total_pages }}, with a total of {{ total_posts }} articles.
The links below point to the Markdown content of the articles.

## Articles on this page

{% autoescape off %}{% for post in post_list %}
- [{{ post.title|markdown_inline }}]({{ SITE_CANONICAL }}{% url 'blog_post_markdown' post.slug %}){% if post.meta_description %}: {{ post.meta_description|markdown_inline }}{% endif %}
{% empty %}
No published articles yet.
{% endfor %}{% endautoescape %}

## Navigate

{% if has_previous %}- [Previous page]({{ SITE_CANONICAL }}{% url 'blog_markdown' %}?page={{ previous_page_number }}){% endif %}
{% if has_next %}- [Next page]({{ SITE_CANONICAL }}{% url 'blog_markdown' %}?page={{ next_page_number }}){% endif %}
- [HTML for this page]({{ SITE_CANONICAL }}{% url 'blog' %}?page={{ page_number }})
- [Site Information]({{ SITE_CANONICAL }}{% url 'llms' %})
