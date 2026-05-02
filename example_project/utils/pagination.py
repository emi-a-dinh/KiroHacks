"""
Pagination utilities.

NOTE: This module exists but is NOT used anywhere in the routes.
It was written but never wired up — part of Issue 4.
"""

from flask import request


def paginate_query(query, default_page_size=20, max_page_size=100):
    """
    Apply pagination to a SQLAlchemy query using request args.

    Usage:
        result = paginate_query(Task.query.filter_by(user_id=user_id))
        return jsonify(result)

    Query params:
        page      - page number, 1-indexed (default: 1)
        page_size - items per page (default: 20, max: 100)
    """
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        page_size = min(max_page_size, max(1, int(request.args.get("page_size", default_page_size))))
    except (ValueError, TypeError):
        page_size = default_page_size

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [item.to_dict() for item in items],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1,
        },
    }
