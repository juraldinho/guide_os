from database.queries import (
    get_total_income,
    get_unpaid_tours_count,
    get_total_tours_count,
)


def get_stats_summary(user_id: int) -> dict:
    total_tours = get_total_tours_count(user_id)
    total_income = get_total_income(user_id)
    unpaid_tours = get_unpaid_tours_count(user_id)

    return {
        "total_tours": total_tours,
        "total_income": total_income,
        "unpaid_tours": unpaid_tours,
    }
