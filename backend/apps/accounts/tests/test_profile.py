"""A person's own profile (picture, theme, password), and what only an Admin may change about people."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts import avatars
from apps.accounts.models import AuditLog, Role, RolePermission, User

pytestmark = pytest.mark.django_db


def picture(size=(300, 200), fmt="JPEG", color=(200, 30, 30), exif=False) -> bytes:
    img = Image.new("RGB", size, color)
    img.paste((20, 20, 220), (0, 0, size[0] // 2, size[1]))                  # left half blue
    buf = io.BytesIO()
    if exif and fmt == "JPEG":
        ex = Image.Exif()
        ex[0x010F] = "SecretCameraMaker"                                      # Make
        gps = ex.get_ifd(0x8825)
        gps[2] = (12.0, 34.0, 56.0)
        gps[1] = "N"
        img.save(buf, fmt, exif=ex)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def upload(client, data: bytes, name="me.jpg", ctype="image/jpeg"):
    return client.put("/api/v1/auth/me/picture", {"file": SimpleUploadedFile(name, data, ctype)},
                      format="multipart")


def raw(user) -> bytes:
    """The stored picture bytes."""
    data = User.objects.defer(None).get(pk=user.pk).avatar
    assert data is not None
    return bytes(data)


def stored(user) -> Image.Image:
    return Image.open(io.BytesIO(raw(user)))


def px(img: Image.Image, xy) -> tuple[int, ...]:
    value = img.getpixel(xy)
    assert isinstance(value, tuple)
    return value


# ---------------------------------------------------------------- the model and /auth/me

def test_a_new_user_has_a_light_theme_no_phone_and_no_picture(make_user):
    u = make_user()
    assert (u.theme, u.phone, u.avatar, u.avatar_version) == ("light", "", None, 0)


def test_me_returns_phone_theme_and_a_picture_url_once_there_is_one(api_as):
    client, user = api_as(Role.EXPERT)
    me = client.get("/api/v1/auth/me").json()
    assert me["theme"] == "light" and me["phone"] == "" and me["avatar_url"] is None
    upload(client, picture())
    me = client.get("/api/v1/auth/me").json()
    assert me["avatar_url"] == f"/api/v1/users/{user.pk}/picture?v=1"


def test_the_picture_bytes_are_never_loaded_by_ordinary_queries(make_user):
    u = make_user()
    User.objects.filter(pk=u.pk).update(avatar=b"x" * 100, has_avatar=True, avatar_version=1)
    loaded = User.objects.get(pk=u.pk)
    assert "avatar" in loaded.get_deferred_fields()


# ---------------------------------------------------------------- self service limits

def test_a_person_may_choose_their_theme_and_it_is_saved_and_audited(api_as):
    client, user = api_as(Role.OPS)
    r = client.patch("/api/v1/auth/me/profile", {"theme": "dark"}, format="json")
    assert r.status_code == 200 and r.json()["theme"] == "dark"
    assert User.objects.get(pk=user.pk).theme == "dark"
    row = AuditLog.objects.get(action="user.theme_change")
    assert row.summary == "Theme set to dark"
    client.patch("/api/v1/auth/me/profile", {"theme": "dark"}, format="json")
    assert AuditLog.objects.filter(action="user.theme_change").count() == 1     # no change: no row
    assert client.patch("/api/v1/auth/me/profile", {"theme": "system"},
                        format="json").json()["theme"] == "system"


@pytest.mark.parametrize("body", [{"theme": "neon"}, {}, {"theme": 5}])
def test_a_bad_or_missing_theme_is_refused(api_as, body):
    client, _ = api_as(Role.EXPERT)
    assert client.patch("/api/v1/auth/me/profile", body, format="json").status_code == 400


@pytest.mark.parametrize("key", ["name", "email", "username", "role", "phone", "is_active",
                                 "must_change_password"])
def test_nothing_but_the_theme_can_be_changed_by_the_person_themselves(api_as, key):
    client, user = api_as(Role.OPS)
    r = client.patch("/api/v1/auth/me/profile", {"theme": "dark", key: "x"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "FIELD_NOT_EDITABLE"
    assert r.json()["keys"] == [key]
    assert User.objects.get(pk=user.pk).theme == "light"                          # nothing applied


def test_profile_needs_a_signed_in_person_who_is_past_the_forced_password_change(make_user):
    assert APIClient().patch("/api/v1/auth/me/profile", {"theme": "dark"},
                             format="json").status_code == 401
    c = APIClient()
    c.force_authenticate(user=make_user(must_change_password=True))
    assert c.patch("/api/v1/auth/me/profile", {"theme": "dark"}, format="json").status_code == 403


# ---------------------------------------------------------------- picture upload

@pytest.mark.parametrize("fmt,name,ctype", [("JPEG", "a.jpg", "image/jpeg"),
                                            ("PNG", "a.png", "image/png"),
                                            ("WEBP", "a.webp", "image/webp"),
                                            ("PNG", "really-a-png.jpg", "image/jpeg")])
def test_jpeg_png_and_webp_become_a_256_square_jpeg_whatever_the_file_is_called(
        api_as, fmt, name, ctype):
    client, user = api_as(Role.EXPERT)
    r = upload(client, picture(fmt=fmt), name, ctype)
    assert r.status_code == 200 and r.json()["avatar_url"].endswith("v=1")
    img = stored(user)
    assert img.format == "JPEG" and img.size == (256, 256)


def test_a_wide_photo_is_cropped_to_a_square_from_the_centre(api_as):
    client, user = api_as(Role.EXPERT)
    upload(client, picture(size=(600, 200)))                  # blue left half, red right half
    img = stored(user)
    left, right = px(img, (10, 128)), px(img, (245, 128))
    assert left[2] > 150 and right[0] > 150                   # both halves survive the centre crop
    tall = picture(size=(200, 600))
    upload(client, tall)
    assert stored(user).size == (256, 256)


def test_location_and_camera_details_are_not_kept(api_as):
    client, user = api_as(Role.EXPERT)
    data = picture(exif=True)
    assert b"SecretCameraMaker" in data
    upload(client, data)
    kept = raw(user)
    assert b"SecretCameraMaker" not in kept and b"Exif" not in kept
    assert not stored(user).getexif()


def test_a_photo_taken_sideways_is_turned_the_right_way_up(api_as):
    client, user = api_as(Role.EXPERT)
    img = Image.new("RGB", (400, 200), (255, 0, 0))
    img.paste((0, 0, 255), (0, 0, 200, 200))                  # blue left, red right
    ex = Image.Exif()
    ex[0x0112] = 6                                            # rotate 90 degrees clockwise to view
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=ex)
    upload(client, buf.getvalue())
    out = stored(user)
    top, bottom = px(out, (128, 10)), px(out, (128, 245))
    assert top[2] > 150 and bottom[0] > 150                   # blue is now on top


def test_replacing_the_picture_overwrites_it_and_changes_the_version(api_as):
    client, user = api_as(Role.EXPERT)
    upload(client, picture(color=(10, 10, 10)))
    first = raw(user)
    r = upload(client, picture(color=(250, 250, 250), size=(400, 400)))
    assert r.json()["avatar_url"].endswith("v=2")
    assert raw(user) != first
    assert AuditLog.objects.filter(action="user.picture_set", actor=user).count() == 2


def gif() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, "GIF")
    return buf.getvalue()


@pytest.mark.parametrize("data,ctype,code,status", [
    (b"", "image/jpeg", "INVALID_IMAGE", 400),
    (b"hello, not a picture", "image/jpeg", "INVALID_IMAGE", 400),
    (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml", "INVALID_IMAGE", 400),
    (gif(), "image/gif", "INVALID_IMAGE", 400),
    (picture()[:200], "image/jpeg", "INVALID_IMAGE", 400),                      # truncated
    (b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024 + 1), "image/jpeg", "IMAGE_TOO_LARGE", 413),
])
def test_files_that_are_not_usable_pictures_are_refused_with_a_clear_code(
        api_as, data, ctype, code, status):
    client, user = api_as(Role.EXPERT)
    r = upload(client, data, "x.jpg", ctype)
    assert r.status_code == status and r.json()["code"] == code
    assert User.objects.defer(None).get(pk=user.pk).avatar is None


def test_a_picture_with_too_many_pixels_is_refused_whether_just_over_or_far_over(api_as,
                                                                                   monkeypatch):
    client, _ = api_as(Role.EXPERT)
    monkeypatch.setattr(avatars, "MAX_PIXELS", 8000)                 # 100 x 100 = 10000: just over
    r = upload(client, picture(size=(100, 100)))
    assert r.status_code == 413 and r.json()["code"] == "IMAGE_TOO_LARGE"
    monkeypatch.setattr(avatars, "MAX_PIXELS", 1000)                 # now over twice the limit
    r = upload(client, picture(size=(100, 100)))
    assert r.status_code == 413 and r.json()["code"] == "IMAGE_TOO_LARGE"


def test_the_picture_module_refuses_an_oversized_body_itself_too():
    with pytest.raises(Exception) as e:
        avatars.process(b"0" * (avatars.MAX_BYTES + 1))
    assert getattr(e.value, "detail", {}).get("code") == "IMAGE_TOO_LARGE"


def test_the_missing_file_and_the_large_declared_size_are_refused(api_as):
    client, _ = api_as(Role.EXPERT)
    r = client.put("/api/v1/auth/me/picture", {}, format="multipart")
    assert r.status_code == 400 and r.json()["code"] == "INVALID_IMAGE"
    big = SimpleUploadedFile("big.jpg", b"0" * (5 * 1024 * 1024 + 10), "image/jpeg")
    r = client.put("/api/v1/auth/me/picture", {"file": big}, format="multipart")
    assert r.status_code == 413 and r.json()["code"] == "IMAGE_TOO_LARGE"


def test_uploads_are_rate_limited(api_as, monkeypatch):
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "avatar", "2/min")
    client, _ = api_as(Role.EXPERT)
    codes = [upload(client, picture()).status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]


def test_a_person_can_remove_their_own_picture_and_it_is_audited(api_as):
    client, user = api_as(Role.EXPERT)
    upload(client, picture())
    r = client.delete("/api/v1/auth/me/picture")
    assert r.status_code == 200 and r.json()["avatar_url"] is None
    assert User.objects.defer(None).get(pk=user.pk).avatar is None
    assert AuditLog.objects.filter(action="user.picture_removed", actor=user).count() == 1
    client.delete("/api/v1/auth/me/picture")                              # nothing left: no new row
    assert AuditLog.objects.filter(action="user.picture_removed").count() == 1


# ---------------------------------------------------------------- who can see a picture

def test_the_owner_ops_and_admin_can_see_a_picture_but_another_expert_cannot(api_as, make_user):
    owner, user = api_as(Role.EXPERT)
    upload(owner, picture())
    url = f"/api/v1/users/{user.pk}/picture"
    for who in (owner, api_as(Role.OPS)[0], api_as(Role.ADMIN)[0]):
        r = who.get(url)
        assert r.status_code == 200 and r["Content-Type"] == "image/jpeg"
        assert Image.open(io.BytesIO(r.content)).size == (256, 256)
    other, _ = api_as(Role.EXPERT)
    r = other.get(url)
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"
    assert APIClient().get(url).status_code == 401


def test_a_deactivated_users_picture_is_still_readable_by_staff(api_as):
    owner, user = api_as(Role.EXPERT)
    upload(owner, picture())
    User.objects.filter(pk=user.pk).update(is_active=False)
    assert api_as(Role.OPS)[0].get(f"/api/v1/users/{user.pk}/picture").status_code == 200


def test_the_picture_is_cached_privately_and_revalidated_with_its_version(api_as):
    owner, user = api_as(Role.EXPERT)
    upload(owner, picture())
    url = f"/api/v1/users/{user.pk}/picture"
    r = owner.get(url)
    assert r["Cache-Control"] == "private, max-age=86400" and r["ETag"] == f'W/"{user.pk}-1"'
    again = owner.get(url, HTTP_IF_NONE_MATCH=r["ETag"])
    assert again.status_code == 304 and not again.content and again["ETag"] == r["ETag"]
    upload(owner, picture(color=(1, 2, 3)))
    assert owner.get(url, HTTP_IF_NONE_MATCH=r["ETag"]).status_code == 200      # new version


def test_users_themselves_can_never_be_deleted(api_as, make_user):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(Role.EXPERT)
    assert admin.delete(f"/api/v1/users/{target.pk}").status_code == 405
    assert User.objects.filter(pk=target.pk).exists()


def test_no_picture_means_404(api_as):
    owner, user = api_as(Role.EXPERT)
    assert owner.get(f"/api/v1/users/{user.pk}/picture").status_code == 404
    assert api_as(Role.ADMIN)[0].get("/api/v1/users/99999/picture").status_code == 404


# ---------------------------------------------------------------- what only an Admin may do

def test_an_admin_sets_and_clears_a_phone_and_it_is_normalised(api_as, make_user):
    admin, _ = api_as(Role.ADMIN)
    target = make_user(Role.EXPERT)
    for given in ("98765 43210", "+91-98765-43210", "09876543210", "919876543210"):
        r = admin.patch(f"/api/v1/users/{target.pk}", {"phone": given}, format="json")
        assert r.status_code == 200 and r.json()["phone"] == "+919876543210"
    cleared = admin.patch(f"/api/v1/users/{target.pk}", {"phone": "  "}, format="json")
    assert cleared.status_code == 200 and cleared.json()["phone"] == ""
    bad = admin.patch(f"/api/v1/users/{target.pk}", {"phone": "12345"}, format="json")
    assert bad.status_code == 400 and "10-digit" in str(bad.json())


def test_ops_and_experts_cannot_change_people_or_remove_pictures(api_as, make_user):
    target = make_user(Role.EXPERT)
    User.objects.filter(pk=target.pk).update(avatar=b"x", has_avatar=True, avatar_version=1)
    for who in (api_as(Role.OPS)[0], api_as(Role.EXPERT)[0]):
        assert who.patch(f"/api/v1/users/{target.pk}", {"phone": "9876543210"},
                         format="json").status_code == 403
        assert who.delete(f"/api/v1/users/{target.pk}/picture").status_code == 403
        assert who.post(f"/api/v1/users/{target.pk}/reset-password", {"password": "Another-pass-9"},
                        format="json").status_code == 403
        assert who.post("/api/v1/users", {"username": "x1", "name": "X", "role": "expert",
                                          "password": "Another-pass-9"},
                        format="json").status_code == 403


def test_ops_see_a_phone_and_a_picture_link_in_the_user_list_but_experts_see_no_list(api_as,
                                                                                   make_user):
    target = make_user(Role.EXPERT)
    User.objects.filter(pk=target.pk).update(phone="+919876543210", avatar=b"x", has_avatar=True,
                                             avatar_version=2)
    rows = api_as(Role.OPS)[0].get("/api/v1/users?role=expert").json()["results"]
    row = next(r for r in rows if r["id"] == target.pk)
    assert row["phone"] == "+919876543210" and row["avatar_url"].endswith("v=2")
    assert api_as(Role.EXPERT)[0].get("/api/v1/users").status_code == 403


def test_an_admin_removes_a_picture_and_it_is_audited_without_the_image(api_as, make_user):
    admin, admin_user = api_as(Role.ADMIN)
    owner, user = api_as(Role.EXPERT)
    upload(owner, picture())
    assert admin.delete(f"/api/v1/users/{user.pk}/picture").status_code == 204
    after = User.objects.defer(None).get(pk=user.pk)
    assert after.avatar is None and after.avatar_version == 2
    fresh = APIClient()                                                   # a new request reloads the user
    fresh.force_authenticate(user=User.objects.get(pk=user.pk))
    assert fresh.get("/api/v1/auth/me").json()["avatar_url"] is None
    row = AuditLog.objects.get(action="user.picture_removed_by_admin")
    assert row.actor == admin_user and user.username in row.summary
    admin.delete(f"/api/v1/users/{user.pk}/picture")                      # nothing left: no new row
    assert AuditLog.objects.filter(action="user.picture_removed_by_admin").count() == 1


# ---------------------------------------------------------------- users.manage is the Admin's alone

def test_users_manage_cannot_be_given_to_another_role(api_as):
    admin, _ = api_as(Role.ADMIN)
    r = admin.put("/api/v1/roles/ops/permissions", {"permissions": {"users.manage": "all"}},
                  format="json")
    assert r.status_code == 400 and r.json()["code"] == "NOT_GRANTABLE"
    catalog = {p["key"]: p for p in admin.get("/api/v1/permissions").json()}
    assert catalog["users.manage"]["grantable"] is False


def test_the_migration_takes_away_an_old_users_manage_grant():
    import importlib

    from django.apps import apps as real_apps

    RolePermission.objects.create(role="ops", permission="users.manage", scope="all")
    migration = importlib.import_module("apps.accounts.migrations.0007_users_manage_admin_only")
    migration.remove_grants(real_apps, None)
    assert not RolePermission.objects.filter(permission="users.manage").exists()


# ---------------------------------------------------------------- audit of the password change

def test_changing_a_password_is_audited_without_any_password(make_user, login):
    user = make_user(Role.OPS)
    client = APIClient()
    token = login(client, user.username).json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    r = client.post("/api/v1/auth/change-password",
                    {"old_password": "Str0ng-pass-1", "new_password": "Brand-new-pass-7"},
                    format="json")
    assert r.status_code == 200
    row = AuditLog.objects.get(action="user.change_password")
    assert row.actor == user and "Brand-new" not in row.summary and "Str0ng" not in row.summary


def test_no_audit_row_ever_holds_a_picture_or_secret(api_as):
    client, _ = api_as(Role.EXPERT)
    upload(client, picture())
    client.patch("/api/v1/auth/me/profile", {"theme": "dark"}, format="json")
    for row in AuditLog.objects.all():
        assert len(row.summary) < 200 and "\xff\xd8" not in row.summary
