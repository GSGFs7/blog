from django.urls import path

from . import feed, views

urlpatterns = [
    path("", views.index, name="index"),
    path("test", views.test, name="test"),
    path("blog", views.blog, name="blog"),
    path("blog/random", views.blog_random_post, name="blog_random_post"),
    path("blog/feed.atom", feed.BlogPostFeed(), name="blog_feed"),
    path("blog/<int:post_id>", views.blog_post_id, name="blog_post_id"),
    path("blog/<str:post_slug>", views.blog_post_slug, name="blog_post_slug"),
    path("about", views.about, name="about"),
]
