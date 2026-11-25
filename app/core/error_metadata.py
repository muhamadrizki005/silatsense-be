"""Allowlisted diagnostics: never serialize exceptions, statements or parameters."""

import re

from sqlalchemy.exc import ArgumentError, DBAPIError, SQLAlchemyError, TimeoutError


def safe_error_metadata(error):
    if isinstance(error, TimeoutError):
        return {"errorCategory": "database_pool_timeout"}
    if isinstance(error, ArgumentError):
        return {"errorCategory": "database_configuration"}
    if isinstance(error, DBAPIError):
        original = error.orig
    else:
        original = error
    # Accept only actual DBAPI exceptions, not arbitrary exception attributes.
    dbapi = isinstance(error, DBAPIError) or type(original).__module__.startswith(
        "pymysql."
    )
    if dbapi:
        args = getattr(original, "args", ())
        code = (
            args[0] if args and type(args[0]) is int and 0 <= args[0] <= 65535 else None
        )
        category = (
            "database_capacity"
            if code in {1040, 1226}
            else "database_authentication"
            if code in {1044, 1045}
            else "database_connection"
            if code in {2002, 2003, 2006, 2013, 2055}
            else "database_error"
        )
        result = {"errorCategory": category}
        if code is not None:
            result["dbErrorCode"] = code
        if code == 1226 and len(args) > 1 and type(args[1]) is str:
            # Only extract fixed resource names and numeric limits, never the user/message.
            for resource in (
                "max_user_connections",
                "max_connections",
                "max_questions",
                "max_updates",
            ):
                if re.search(r"['\"]" + resource + r"['\"]", args[1]):
                    result["resource"] = resource
                    match = re.search(r"current value:\s*(\d{1,10})\)", args[1])
                    if match:
                        result["resourceLimit"] = int(match[1])
                    break
        return result
    if isinstance(error, SQLAlchemyError):
        return {"errorCategory": "database_error"}
    return {
        "errorCategory": "filesystem_error"
        if isinstance(error, OSError)
        else "unexpected_error"
    }
