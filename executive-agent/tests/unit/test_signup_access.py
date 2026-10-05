"""Who may talk to the bot before an account is active."""

from app.bot.middleware import access_allowed


def test_strangers_only_get_the_signup_flow() -> None:
    assert access_allowed(has_account=False, status="", command="start", callback="", is_text=False)
    assert access_allowed(
        has_account=False, status="", command="privacy", callback="", is_text=False
    )
    assert access_allowed(has_account=False, status="", command="", callback="agr", is_text=False)
    assert not access_allowed(
        has_account=False, status="", command="brief", callback="", is_text=False
    )
    assert not access_allowed(
        has_account=False, status="", command="", callback="drf", is_text=False
    )


def test_pending_users_stay_inside_signup_and_banned_users_get_nothing() -> None:
    assert access_allowed(has_account=True, status="pending", command="", callback="", is_text=True)
    assert not access_allowed(
        has_account=True, status="pending", command="tasks", callback="", is_text=False
    )
    assert not access_allowed(
        has_account=True, status="banned", command="start", callback="", is_text=False
    )
