from django.db.models import Q, Exists, OuterRef, When, IntegerField, FloatField, Count, ExpressionWrapper, Case, Value, F, Prefetch

from fame.models import Fame, FameLevels, FameUsers, ExpertiseAreas
from socialnetwork.models import Posts, SocialNetworkUsers
from collections import defaultdict
from fame.models import Fame

# general methods independent of html and REST views
# should be used by REST and html views


def _get_social_network_user(user) -> SocialNetworkUsers:
    """Given a FameUser, gets the social network user from the request. Assumes that the user is authenticated."""
    try:
        user = SocialNetworkUsers.objects.get(id=user.id)
    except SocialNetworkUsers.DoesNotExist:
        raise PermissionError("User does not exist")
    return user

from django.db.models import Q

def timeline(user: SocialNetworkUsers,
             start: int = 0,
             end: int | None = None,
             published: bool = True,
             community_mode: bool = False):

    if community_mode:
        # ------- prepare ----------------------------------------------------
        user_communities = set(user.communities.all().values_list("pk", flat=True))

        # candidate posts: published OR my own drafts
        candidates = (
            Posts.objects
                 .filter(Q(published=published) | Q(author=user))
                 .select_related("author")                                 # -> no extra query for author
                 .prefetch_related("expertise_area_and_truth_ratings",      # -> bring M2M rows in bulk
                                   "author__communities")
                 .order_by("-submitted")
        )

        # ------- python-side filter (keeps logic crystal-clear) ------------
        valid_post_ids = []
        for post in candidates:
            post_area_ids   = {ea.pk for ea in post.expertise_area_and_truth_ratings.all()}
            author_area_ids = {ea.pk for ea in post.author.communities.all()}

            # intersection of all three sets?
            if post_area_ids & user_communities & author_area_ids:
                valid_post_ids.append(post.pk)

        posts = Posts.objects.filter(pk__in=valid_post_ids).order_by("-submitted")

    else:
        # -------- standard mode (unchanged) --------------------------------
        _follows = user.follows.all()
        posts = (
            Posts.objects
                 .filter((Q(author__in=_follows) & Q(published=published)) | Q(author=user))
                 .order_by("-submitted")
        )

    # --------------- slicing ----------------------------------------------
    if end is None:
        return posts[start:]
    return posts[start:end + 1]


def search(keyword: str, start: int = 0, end: int = None, published=True):
    """Search for all posts in the system containing the keyword. Assumes that all posts are public"""
    posts = Posts.objects.filter(
        Q(content__icontains=keyword)
        | Q(author__email__icontains=keyword)
        | Q(author__first_name__icontains=keyword)
        | Q(author__last_name__icontains=keyword),
        published=published,
    ).order_by("-submitted")
    if end is None:
        return posts[start:]
    else:
        return posts[start:end+1]


def follows(user: SocialNetworkUsers, start: int = 0, end: int = None):
    """Get the users followed by this user. Assumes that the user is authenticated."""
    _follows = user.follows.all()
    if end is None:
        return _follows[start:]
    else:
        return _follows[start:end+1]


def followers(user: SocialNetworkUsers, start: int = 0, end: int = None):
    """Get the followers of this user. Assumes that the user is authenticated."""
    _followers = user.followed_by.all()
    if end is None:
        return _followers[start:]
    else:
        return _followers[start:end+1]


def follow(user: SocialNetworkUsers, user_to_follow: SocialNetworkUsers):
    """Follow a user. Assumes that the user is authenticated. If user already follows the user, signal that."""
    if user_to_follow in user.follows.all():
        return {"followed": False}
    user.follows.add(user_to_follow)
    user.save()
    return {"followed": True}


def unfollow(user: SocialNetworkUsers, user_to_unfollow: SocialNetworkUsers):
    """Unfollow a user. Assumes that the user is authenticated. If user does not follow the user anyway, signal that."""
    if user_to_unfollow not in user.follows.all():
        return {"unfollowed": False}
    user.follows.remove(user_to_unfollow)
    user.save()
    return {"unfollowed": True}


def submit_post(
    user: SocialNetworkUsers,
    content: str,
    cites: Posts = None,
    replies_to: Posts = None,
):
    """Submit a post for publication. Assumes that the user is authenticated.
    returns a tuple of three elements:
    1. a dictionary with the keys "published" and "id" (the id of the post)
    2. a list of dictionaries containing the expertise areas and their truth ratings
    3. a boolean indicating whether the user was banned and logged out and should be redirected to the login page
    """

    # create post  instance:
    post = Posts.objects.create(
        content=content,
        author=user,
        cites=cites,
        replies_to=replies_to,
    )

    # classify the content into expertise areas:
    # only publish the post if none of the expertise areas contains bullshit:
    _at_least_one_expertise_area_contains_bullshit, _expertise_areas = (
        post.determine_expertise_areas_and_truth_ratings()
    )
    post.published = not _at_least_one_expertise_area_contains_bullshit

    redirect_to_logout = False


    #########################
    # add your code here
    
        
    ##preventing posting with negative fame in expertise areas
    for expertise_area in _expertise_areas:
        user_fame_entries = Fame.objects.filter(
        user=user,
        expertise_area=expertise_area['expertise_area'],
        fame_level__numeric_value__lt=0)
        
        if user_fame_entries.exists():
            post.published = False
            break
        
    ##adjust fame for negative truth ratings
    for expertise_area in _expertise_areas:
        truth_rating = expertise_area['truth_rating']
        if truth_rating and truth_rating.numeric_value < 0:  
            area = expertise_area['expertise_area']
            existing_fame = Fame.objects.filter(user=user, expertise_area=area).first()
            
            if existing_fame:
                #lower existing fame level
                try:
                    existing_fame.fame_level = existing_fame.fame_level.get_next_lower_fame_level()
                    existing_fame.save()
                    # ─── AUTO–KICK WHEN FAME DROPS BELOW SUPER PRO ───
                    communities_rel = getattr(user, "communities", None)
                    if communities_rel and hasattr(communities_rel, "remove"):
                        communities_rel.remove(area)

                except ValueError:
                    # ban user if can't lower further
                    user.is_active = False
                    user.save()
                    user_posts = Posts.objects.filter(author=user)
                    post.published = False
                    user_posts.update(published=False)  
                    redirect_to_logout = True                 
            else:
                # add confuser level for new area
                confuser_level = FameLevels.objects.get(name="Confuser")
                Fame.objects.create(user=user, expertise_area=area, fame_level=confuser_level)
  
    #########################

    post.save()

    return (
        {"published": post.published, "id": post.id},
        _expertise_areas,
        redirect_to_logout,
    )


def rate_post(
    user: SocialNetworkUsers, post: Posts, rating_type: str, rating_score: int
):
    """Rate a post. Assumes that the user is authenticated. If user already rated the post with the given rating_type,
    update that rating score."""
    user_rating = None
    try:
        user_rating = user.userratings_set.get(post=post, rating_type=rating_type)
    except user.userratings_set.model.DoesNotExist:
        pass

    if user == post.author:
        raise PermissionError(
            "User is the author of the post. You cannot rate your own post."
        )

    if user_rating is not None:
        # update the existing rating:
        user_rating.rating_score = rating_score
        user_rating.save()
        return {"rated": True, "type": "update"}
    else:
        # create a new rating:
        user.userratings_set.add(
            post,
            through_defaults={"rating_type": rating_type, "rating_score": rating_score},
        )
        user.save()
        return {"rated": True, "type": "new"}


def fame(user: SocialNetworkUsers):
    """Get the fame of a user. Assumes that the user is authenticated."""
    try:
        user = SocialNetworkUsers.objects.get(id=user.id)
    except SocialNetworkUsers.DoesNotExist:
        raise ValueError("User does not exist")

    return user, Fame.objects.filter(user=user)


def bullshitters():
    #negative Fame Einträge
    entries = Fame.objects.filter(fame_level__numeric_value__lt=0)

    #pro Fachgebiet sammeln
    result = defaultdict(list)
    for entry in entries:
        ea = entry.expertise_area  # <— Objekt, kein String
        result[ea].append({
            "user": entry.user,
            "fame_level_numeric": entry.fame_level.numeric_value,
            "date_joined": entry.user.date_joined,
        })

    #schlechtester Fame zuerst, bei Gleichstand jüngstes Konto
    for area, user_list in result.items():
        user_list.sort(key=lambda x: (x["fame_level_numeric"], -x["date_joined"].timestamp()))
        for d in user_list:
            d.pop("date_joined", None)

    return dict(result)

def join_community(user: SocialNetworkUsers, community: ExpertiseAreas) -> None:
    """
    Add *user* to *community*.
    Idempotent: does nothing if the user is already a member.
    """
    if community is None:
        raise ValueError("community must not be None")
    user.communities.add(community)      # safe even if already there


def leave_community(user: SocialNetworkUsers, community: ExpertiseAreas) -> None:
    """
    Remove *user* from *community*.
    Idempotent: does nothing if the user is not a member.
    """
    if community is None:
        raise ValueError("community must not be None")
    user.communities.remove(community)






def similar_users(user: SocialNetworkUsers):
    """Compute the similarity of user with all other users. The method returns a QuerySet of FameUsers annotated
    with an additional field 'similarity'. Sort the result in descending order according to 'similarity', in case
    there is a tie, within that tie sort by date_joined (most recent first)"""
    pass
    #########################
    # add your code here
    #########################

