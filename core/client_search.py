from django.db.models import Q


def build_client_name_search_q(query: str) -> Q:
    """Match clients by individual name parts or combined full-name queries."""
    q = (query or "").strip()
    if not q:
        return Q()

    name_q = (
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(middle_name__icontains=q)
        | Q(business_name__icontains=q)
    )

    if "," in q:
        pieces = [p.strip() for p in q.split(",", 1)]
        if len(pieces) == 2 and pieces[0] and pieces[1]:
            name_q |= Q(last_name__icontains=pieces[0], first_name__icontains=pieces[1])

    tokens = [t for t in q.replace(",", " ").split() if t]
    if len(tokens) >= 2:
        first_token = tokens[0]
        remaining = " ".join(tokens[1:])
        name_q |= Q(first_name__icontains=first_token, last_name__icontains=remaining)
        name_q |= Q(last_name__icontains=first_token, first_name__icontains=remaining)

        if len(tokens) >= 3:
            name_q |= Q(
                first_name__icontains=tokens[0],
                middle_name__icontains=tokens[1],
                last_name__icontains=" ".join(tokens[2:]),
            )

    return name_q
