from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth import views as django_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils.translation import pgettext, ugettext_lazy as _
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden

from ..account import events as account_events
from ..checkout.utils import find_and_assign_anonymous_checkout
from ..core.utils import get_paginator_items
from .emails import send_account_delete_confirmation_email
from ..product.models import Product
from .forms import (
    ChangePasswordForm,
    LoginForm,
    NameForm,
    PasswordResetForm,
    SignupForm,
    get_address_form,
    logout_on_password_change,
)
from .models import User


@find_and_assign_anonymous_checkout()
def login(request):
    kwargs = {"template_name": "account/login.html", "authentication_form": LoginForm}
    return django_views.LoginView.as_view(**kwargs)(request, **kwargs)


@login_required
def logout(request):
    auth.logout(request)
    messages.success(request, _("You have been successfully logged out."))
    return redirect(settings.LOGIN_REDIRECT_URL)


def signup(request):
    form = SignupForm(request.POST or None)
    if form.is_valid():
        form.save()
        password = form.cleaned_data.get("password")
        email = form.cleaned_data.get("email")
        user = auth.authenticate(request=request, email=email, password=password)
        if user:
            auth.login(request, user)
        messages.success(request, _("User has been created"))
        redirect_url = request.POST.get("next", settings.LOGIN_REDIRECT_URL)
        return redirect(redirect_url)
    ctx = {"form": form}
    return TemplateResponse(request, "account/signup.html", ctx)


def password_reset(request):
    kwargs = {
        "template_name": "account/password_reset.html",
        "success_url": reverse_lazy("account:reset-password-done"),
        "form_class": PasswordResetForm,
    }
    return django_views.PasswordResetView.as_view(**kwargs)(request, **kwargs)


class PasswordResetConfirm(django_views.PasswordResetConfirmView):
    template_name = "account/password_reset_from_key.html"
    success_url = reverse_lazy("account:reset-password-complete")
    token = None
    uidb64 = None

    def form_valid(self, form):
        response = super(PasswordResetConfirm, self).form_valid(form)
        account_events.customer_password_reset_event(user=self.user)
        return response


def password_reset_confirm(request, uidb64=None, token=None):
    kwargs = {
        "template_name": "account/password_reset_from_key.html",
        "success_url": reverse_lazy("account:reset-password-complete"),
        "token": token,
        "uidb64": uidb64,
    }
    return PasswordResetConfirm.as_view(**kwargs)(request, **kwargs)


@login_required
def videos_list(request, course_pk):
    resp = get_purchased_product_or_forbidden(request, course_pk)

    if resp is HttpResponseForbidden:
        return HttpResponseForbidden

    product = Product.objects.prefetch_related("videos").get(pk=course_pk)
    videos = product.videos.all()

    ctx = {
        "course": product,
        "videos": videos
    }

    return TemplateResponse(request, "account/videos.html", ctx)


def get_purchased_product_or_forbidden(request, pk):
    orders = request.user.orders.confirmed().prefetch_related("lines")
    paid_orders = [order for order in orders if order.is_fully_paid()]
    lines = []

    for order in paid_orders:
        lines += order.lines.all()

    found = [line for line in lines if int(line.variant.pk) == int(pk)]
    if not found:
        return HttpResponseForbidden

    return Product.objects.prefetch_related("videos").get(pk=pk)


@login_required
def video(request, course_pk, video_pk):
    resp = get_purchased_product_or_forbidden(request, course_pk)

    if resp is HttpResponseForbidden:
        return HttpResponseForbidden

    product = Product.objects.prefetch_related("videos").get(pk=course_pk)
    video = product.videos.get(pk=video_pk)

    ctx = {
        "course": product,
        "video": video
    }

    return TemplateResponse(request, "account/video.html", ctx)


@login_required
def details(request):
    password_form = get_or_process_password_form(request)
    name_form = get_or_process_name_form(request)
    orders = request.user.orders.confirmed().prefetch_related("lines")

    paid_orders = [order for order in orders if order.is_fully_paid()]
    lines = [order.lines.prefetch_related(
                "variant__product",
                "variant__videos",
                "variant__images")
                    .first() for order in paid_orders]

    variants = list(map(lambda x: x.variant, lines))
    courses = []
    for variant in variants:
        course = {}
        course["pk"] = variant.product.pk
        course["details"] = variant.product
        course["images"] = variant.product.images.all()
        course["videos"] = variant.product.videos.all()
        courses.append(course)

    orders_paginated = get_paginator_items(
        orders, settings.PAGINATE_BY, request.GET.get("page")
    )
    ctx = {
        "addresses": request.user.addresses.all(),
        "orders": orders_paginated,
        "change_password_form": password_form,
        "user_name_form": name_form,
        "courses": courses,
    }

    return TemplateResponse(request, "account/details.html", ctx)


def get_or_process_password_form(request):
    form = ChangePasswordForm(data=request.POST or None, user=request.user)
    if form.is_valid():
        form.save()
        logout_on_password_change(request, form.user)
        messages.success(
            request, pgettext("Storefront message", "Password successfully changed.")
        )
    return form


def get_or_process_name_form(request):
    form = NameForm(data=request.POST or None, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(
            request, pgettext("Storefront message", "Account successfully updated.")
        )
    return form


@login_required
def address_edit(request, pk):
    address = get_object_or_404(request.user.addresses, pk=pk)
    address_form, preview = get_address_form(
        request.POST or None, instance=address, country_code=address.country.code
    )
    if address_form.is_valid() and not preview:
        address = address_form.save()
        request.extensions.change_user_address(
            address, address_type=None, user=request.user
        )
        message = pgettext("Storefront message", "Address successfully updated.")
        messages.success(request, message)
        return HttpResponseRedirect(reverse("account:details") + "#addresses")
    return TemplateResponse(
        request, "account/address_edit.html", {"address_form": address_form}
    )


@login_required
def address_delete(request, pk):
    address = get_object_or_404(request.user.addresses, pk=pk)
    if request.method == "POST":
        address.delete()
        messages.success(
            request, pgettext("Storefront message", "Address successfully removed")
        )
        return HttpResponseRedirect(reverse("account:details") + "#addresses")
    return TemplateResponse(
        request, "account/address_delete.html", {"address": address}
    )


@login_required
@require_POST
def account_delete(request):
    user = User.objects.get(pk=request.user.pk)
    send_account_delete_confirmation_email(user)
    messages.success(
        request,
        pgettext(
            "Storefront message, when user requested his account removed",
            "Please check your inbox for a confirmation e-mail.",
        ),
    )
    return HttpResponseRedirect(reverse("account:details") + "#settings")


@login_required
def account_delete_confirm(request, token):
    user = User.objects.get(pk=request.user.pk)

    if not default_token_generator.check_token(user, token):
        raise Http404("No such page!")

    if request.method == "POST":
        user.delete()
        msg = pgettext(
            "Account deleted",
            "Your account was deleted successfully. "
            "In case of any trouble or questions feel free to contact us.",
        )
        messages.success(request, msg)
        return redirect("home")

    return TemplateResponse(request, "account/account_delete_prompt.html")
