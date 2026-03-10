from database.queries import get_total_income, get_unpaid_tours_count


def get_income_summary(user_id: int) -> dict:
    total_income = get_total_income(user_id)
    unpaid_tours = get_unpaid_tours_count(user_id)

    return {
        "total_income": total_income,
        "unpaid_tours": unpaid_tours,
    }