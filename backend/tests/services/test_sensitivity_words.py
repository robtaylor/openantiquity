"""The words `/meta` gives for each location level are true of `services.sensitivity` (Decision 0005).

Each level states who sees the exact place (`exact_for`), and two sentences
say it in words. The audience is held to `sensitivity.sees_exact` for every
kind of viewer, and each sentence to the audience, so neither can drift from
the code's own rule. Where downloads are stricter (`sensitivity.downloads_exact`),
a third sentence says so.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from fieldclub.models import User
from fieldclub.services import sensitivity
from fieldclub.vocab import OFFERED_SENSITIVITIES, SENSITIVITY_LEVELS, Role, Sensitivity, SensitivityViewer
from tests.helpers import MakeFinding, MakeUser

FEW = frozenset(
    {
        SensitivityViewer.FINDER,
        SensitivityViewer.TRUSTED,
        SensitivityViewer.EXPERT,
        SensitivityViewer.MODERATOR,
    }
)
FEW_WORDS = "Only its finder, trusted members, archaeologists and moderators see"


def _viewers(make_user: MakeUser, finder: User) -> dict[SensitivityViewer, list[User | None]]:
    """Each kind of viewer the table tells apart. Admins count as moderators."""
    return {
        SensitivityViewer.SIGNED_OUT: [None, make_user(banned_at=finder.created_at)],
        SensitivityViewer.MEMBER: [make_user(Role.MEMBER)],
        SensitivityViewer.FINDER: [finder],
        SensitivityViewer.TRUSTED: [make_user(Role.TRUSTED)],
        SensitivityViewer.EXPERT: [make_user(Role.EXPERT)],
        SensitivityViewer.MODERATOR: [make_user(Role.MODERATOR), make_user(Role.ADMIN)],
    }


def test_each_level_s_stated_audience_is_the_code_s_rule(
    make_user: MakeUser, make_finding: MakeFinding
) -> None:
    finder = make_user(Role.MEMBER, handle="Finder")
    viewers = _viewers(make_user, finder)
    assert set(viewers) == set(SensitivityViewer), "every kind of viewer is tried"
    assert [item.id for item in SENSITIVITY_LEVELS] == list(Sensitivity)
    for level in SENSITIVITY_LEVELS:
        finding = make_finding(finder, sensitivity=level.id.value)
        for kind, people in viewers.items():
            for viewer in people:
                exact = sensitivity.sees_exact(finding, viewer)
                assert exact == (kind in level.exact_for), (level.id, kind, viewer)
                assert sensitivity.visible_location(finding, viewer).obscured is not exact


def test_each_level_s_sentences_say_what_its_audience_is() -> None:
    for level in SENSITIVITY_LEVELS:
        everyone = level.exact_for == frozenset(SensitivityViewer)
        signed_in = level.exact_for == frozenset(SensitivityViewer) - {SensitivityViewer.SIGNED_OUT}
        few = level.exact_for == FEW
        assert everyone + signed_in + few == 1, f"{level.id} has an audience no sentence describes"
        if everyone:
            assert level.who_sees == "Everyone sees its exact place."
            # Nobody is shown the square, so nobody is told why.
            assert level.square_sentence is None
            continue
        assert "Everyone else sees its one-kilometre square." in level.who_sees
        assert level.square_sentence is not None
        if signed_in:
            assert level.who_sees.startswith("Only people who have signed in see its exact place.")
            # Only the signed out see the square here, and signing in shows them the place.
            assert level.square_sentence.endswith("Sign in to see it.")
        else:
            assert level.who_sees.startswith(f"{FEW_WORDS} its exact place.")
            # A member sees the square too, so signing in is no help.
            assert level.square_sentence.endswith(f"{FEW_WORDS} it.")
            assert "Sign in" not in level.square_sentence


def test_a_level_whose_downloads_are_stricter_than_its_page_says_so(
    make_user: MakeUser, make_finding: MakeFinding
) -> None:
    """A member sees a protected finding's place on its page, but a download gives them its square."""
    finder = make_user(Role.MEMBER, handle="Finder")
    viewers = _viewers(make_user, finder)
    download_words = (
        "Downloads give its exact place only to its finder, trusted members, archaeologists and moderators."
    )
    for level in SENSITIVITY_LEVELS:
        finding = make_finding(finder, sensitivity=level.id.value)
        downloads_for = {
            kind
            for kind, people in viewers.items()
            if all(sensitivity.downloads_exact(finding, viewer) for viewer in people)
        }
        assert downloads_for <= level.exact_for, level.id
        if downloads_for == level.exact_for:
            assert "Downloads" not in level.who_sees, level.id
        else:
            assert downloads_for == FEW, level.id
            assert level.who_sees.endswith(download_words), level.id


def test_meta_serves_the_words(client: TestClient) -> None:
    served = client.get("/api/v1/meta").json()["vocab"]["sensitivity_levels"]
    assert served == [
        {
            "id": level.id.value,
            "label": level.label,
            "who_sees": level.who_sees,
            "square_sentence": level.square_sentence,
            "exact_for": [kind.value for kind in SensitivityViewer if kind in level.exact_for],
        }
        for level in SENSITIVITY_LEVELS
        if level.id in OFFERED_SENSITIVITIES
    ]
    # Restricted is dropped (Decision 0032). Its words stay for a stored finding until the sweep.
    assert [item["label"] for item in served] == ["Open", "Protected"]
    for item in served:
        assert "restricted" not in f"{item['who_sees']} {item['square_sentence']}".lower(), item["id"]
