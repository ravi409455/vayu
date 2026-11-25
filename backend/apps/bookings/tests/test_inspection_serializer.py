"""The inspection serializer works out which forms are hidden from the reader once per request,
not once per row (F-090), and the second row reuses it."""
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.bookings.serializers import InspectionSerializer

from .test_scoring import run, senv  # noqa: F401

pytestmark = pytest.mark.django_db


def test_hidden_forms_are_looked_up_once_for_a_list(senv):  # noqa: F811
    _, first = run(senv, {"door": "ok"})
    _, second = run(senv, {"door": "dent"})
    from apps.accounts.models import User

    ops = SimpleNamespace(user=User.objects.filter(role="ops").first())
    with mock.patch("apps.bookings.serializers.hidden_inspection_forms",
                    return_value=set()) as hidden:
        rows = InspectionSerializer([first, second], many=True, context={"request": ops}).data
    assert hidden.call_count == 1
    assert [r["id"] for r in rows] == [str(first.id), str(second.id)]
