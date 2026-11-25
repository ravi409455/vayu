"""F-247: the heartbeat keeps which app version each phone runs (for metrics)."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Device

from .test_devices import heartbeat

pytestmark = pytest.mark.django_db


def test_the_heartbeat_stores_the_app_version_and_keeps_it_when_left_out(make_user, login):
    make_user(username="asha")
    tokens = login(APIClient(), "asha", device_name="iQOO Z7s").json()
    assert heartbeat(tokens, drafts=0, files=1, app_version=" 1.4.2 ").status_code == 200
    device = Device.objects.get(pk=tokens["device_id"])
    assert device.app_version == "1.4.2"
    heartbeat(tokens, drafts=0, files=0)                      # an older app sends none
    device.refresh_from_db()
    assert device.app_version == "1.4.2"
