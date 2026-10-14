from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import PermissionDenied


class ClosedAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


class KakaoAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return sociallogin.account.provider == "kakao"

    def pre_social_login(self, request, sociallogin):
        if sociallogin.account.provider != "kakao":
            raise PermissionDenied

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        from .models import Profile

        Profile.objects.get_or_create(user=user, defaults={"role": "organizer"})
        return user
