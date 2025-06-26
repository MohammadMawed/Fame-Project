from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from fame.models import Expertise
from socialnetwork import api
from socialnetwork.api import _get_social_network_user
from socialnetwork.models import SocialNetworkUsers
from socialnetwork.serializers import PostsSerializer


@require_http_methods(["GET"])
@login_required
def timeline(request):
    user = _get_social_network_user(request.user)

    # initialize community mode to False the first time in the session
    if 'community_mode' not in request.session:
        request.session['community_mode'] = False

    community_mode = request.session.get('community_mode', False)

    # get extra URL parameters:
    keyword = request.GET.get("search", "")
    published = request.GET.get("published", True)
    error = request.GET.get("error", None)

    # if keyword is not empty, use search method of API:
    if keyword and keyword != "":
        posts_data = PostsSerializer(
            api.search(keyword, published=published), many=True
        ).data
    else:  # otherwise, use timeline method of API:
        posts_data = PostsSerializer(
            api.timeline(
                user,
                published=published,
                community_mode=community_mode
            ),
            many=True,
        ).data

    context = {
        "posts": posts_data,
        "searchkeyword": keyword,
        "error": error,
        "followers": list(api.follows(user).values_list('id', flat=True)),
        "is_community_mode": community_mode,
        "member_of_communities": user.communities.all(),
        "eligible_communities": api.eligible_communities(user)
    }

    return render(request, "timeline.html", context=context)


@require_http_methods(["POST"])
@login_required
def follow(request):
    user = _get_social_network_user(request.user)
    user_to_follow = SocialNetworkUsers.objects.get(id=request.POST.get("user_id"))
    api.follow(user, user_to_follow)
    return redirect(reverse("sn:timeline"))


@require_http_methods(["POST"])
@login_required
def unfollow(request):
    user = _get_social_network_user(request.user)
    user_to_unfollow = SocialNetworkUsers.objects.get(id=request.POST.get("user_id"))
    api.unfollow(user, user_to_unfollow)
    return redirect(reverse("sn:timeline"))


@require_http_methods(["GET"])
@login_required
def bullshitters(request):
    bullshitters_data = api.bullshitters()
    context = {
        'bullshitters_data': bullshitters_data
    }
    return render(request, "bullshitters.html", context=context)

@require_http_methods(["POST"])
@login_required
def toggle_community_mode(request):
    request.session['community_mode'] = not request.session.get('community_mode', False)
    return redirect(reverse("sn:timeline"))

@require_http_methods(["POST"])
@login_required
def join_community(request):
    user = _get_social_network_user(request.user)
    expertise_id = request.POST.get("expertise_id")
    if expertise_id:
        expertise = Expertise.objects.get(id=expertise_id)
        api.join_community(user, expertise)
    return redirect(reverse("sn:timeline"))

@require_http_methods(["POST"])
@login_required
def leave_community(request):
    user = _get_social_network_user(request.user)
    expertise_id = request.POST.get("expertise_id")
    if expertise_id:
        expertise = Expertise.objects.get(id=expertise_id)
        api.leave_community(user, expertise)
    return redirect(reverse("sn:timeline"))

@require_http_methods(["GET"])
@login_required
def similar_users(request):
    user = _get_social_network_user(request.user)
    similar_users_list = api.similar_users(user)
    context = {
        'similar_users_list': similar_users_list
    }
    return render(request, "similar_users.html", context=context)
