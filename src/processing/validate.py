def validate_record(record):
    """Validate required fields in a normalized record."""

    required_fields = ["source_api", "source_id", "title"]

    missing_fields = [
        field
        for field in required_fields
        if not record.get(field)
    ]

    return {
        "is_valid": len(missing_fields) == 0,
        "missing_fields": missing_fields,
    }


from datetime import datetime


def validate_date(date_string):
    """Check whether a date follows YYYY-MM-DD format."""

    if not isinstance(date_string, str):
        return False

    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_record(record):
    """Validate required fields and date format."""

    required_fields = ["source_api", "source_id", "title"]

    missing_fields = [
        field
        for field in required_fields
        if not record.get(field)
    ]

    date_is_valid = validate_date(record.get("date"))

    return {
        "is_valid": len(missing_fields) == 0 and date_is_valid,
        "missing_fields": missing_fields,
        "date_is_valid": date_is_valid,
    }


def find_duplicate_records(records):
    """Find duplicate records using source_api and source_id."""

    seen = set()
    duplicates = []

    for record in records:
        key = (record.get("source_api"), record.get("source_id"))

        if key in seen:
            duplicates.append(record)
        else:
            seen.add(key)

    return duplicates

