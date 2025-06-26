from django.urls import path

from socialnetwork.views.html import (
    timeline,
    follow,
    unfollow,
    bullshitters,
    toggle_community_mode,
    join_community,
    leave_community,
    similar_users
)
from socialnetwork.views.rest import PostsListApiView

app_name = "socialnetwork"

urlpatterns = [
    path("api/posts", PostsListApiView.as_view(), name="posts_fulllist"),
    path("html/timeline", timeline, name="timeline"),
    path("api/follow", follow, name="follow"),
    path("api/unfollow", unfollow, name="unfollow"),
    path("html/bullshitters", bullshitters, name="bullshitters"),
    path("api/toggle_community_mode", toggle_community_mode, name="toggle_community_mode"),
    path("api/join_community", join_community, name="join_community"),
    path("api/leave_community", leave_community, name="leave_community"),
    path("html/similar_users", similar_users, name="similar_users"),
]
