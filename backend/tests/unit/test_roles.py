import pytest

from app.domain.roles import ROLES, Role, has_rank


def test_roles_ordered_by_rank():
    assert ROLES == ("viewer", "editor", "admin")


class TestHasRank:
    def test_exact_match(self):
        assert has_rank(Role.editor, Role.editor) is True

    def test_higher_passes(self):
        assert has_rank(Role.admin, Role.editor) is True

    def test_lower_denied(self):
        assert has_rank(Role.viewer, Role.editor) is False

    def test_viewer_is_lowest(self):
        assert has_rank(Role.viewer, Role.viewer) is True
        assert has_rank(Role.viewer, Role.admin) is False


def test_unknown_role_denies_rather_than_passes():
    # Ошибка настройки обязана закрывать доступ, а не открывать. В эталоне
    # это была ловушка с indexOf, возвращающим -1: условие «has < -1» ложно
    # для любой роли, и разграничение пускало бы каждого.
    with pytest.raises(ValueError):
        Role("superuser")
